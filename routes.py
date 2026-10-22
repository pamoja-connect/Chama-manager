import os
import json
import hashlib
import hmac
import secrets
import subprocess
import threading
from datetime import datetime, timedelta
from html import escape as html_escape
from flask import render_template, request, redirect, url_for, flash, jsonify, send_file, make_response, session
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import func
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from app import app, db
from models import User, Contribution, Loan, LoanRepayment, Fine, Announcement, MeetingRecord, Document, Project, Notification, MembershipApplication, OfflineData, MemberPoints, UserBadge, Badge, Vote, VotingProposal, Payment, DigitalReceipt, WelfareContribution, WelfareExpense, Group, InAppMessage, LoanSettlement, FineSettlement, ActivityLog, PasswordResetToken
from forms import *
from utils import *
from utils import format_date, format_datetime

_PASSWORD_RESET_REQUESTS = {}
_PASSWORD_RESET_LOCK = threading.Lock()


def _password_reset_ip_allowed():
    """Allow up to five valid reset requests per source IP in a rolling hour."""
    remote_addr = request.remote_addr or 'unknown'
    key = hmac.new(
        str(app.secret_key).encode('utf-8'),
        remote_addr.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()
    now = datetime.utcnow()
    cutoff = now - timedelta(hours=1)

    with _PASSWORD_RESET_LOCK:
        if len(_PASSWORD_RESET_REQUESTS) > 2048:
            for old_key, timestamps in list(_PASSWORD_RESET_REQUESTS.items()):
                if not timestamps or timestamps[-1] < cutoff:
                    _PASSWORD_RESET_REQUESTS.pop(old_key, None)

        timestamps = _PASSWORD_RESET_REQUESTS.setdefault(key, [])
        timestamps[:] = [timestamp for timestamp in timestamps if timestamp >= cutoff]
        if len(timestamps) >= 5:
            return False
        timestamps.append(now)
        return True


def _password_reset_user_is_eligible(user):
    if not user or not user.is_active:
        return False
    if user.is_super_admin:
        return True
    return bool(
        user.group_id
        and Group.query.filter_by(id=user.group_id, is_active=True).first()
    )


def _send_password_reset_email(user, reset_url, group_name):
    """Send a reset link through the connected Resend integration."""
    sender = os.environ.get('RESEND_FROM_EMAIL', '').strip()
    if not sender:
        return False

    account_label = group_name or 'CONNECT platform'
    safe_label = html_escape(account_label)
    safe_url = html_escape(reset_url, quote=True)
    subject = 'Reset your account password'
    text = (
        f'We received a request to reset the password for your {account_label} account.\n\n'
        f'Reset your password using this link (expires in 30 minutes):\n{reset_url}\n\n'
        'If you did not request this, you can ignore this email.'
    )
    html = (
        '<div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;color:#243047">'
        f'<h2>Password reset for {safe_label}</h2>'
        '<p>We received a request to reset the password for your account.</p>'
        f'<p><a href="{safe_url}" style="display:inline-block;padding:12px 18px;'
        'background:#764ba2;color:#fff;text-decoration:none;border-radius:6px">'
        'Reset password</a></p>'
        '<p>This link expires in 30 minutes and can be used only once.</p>'
        '<p>If you did not request this, you can ignore this email.</p>'
        '</div>'
    )
    payload = {
        'from': sender,
        'to': [user.email],
        'subject': subject,
        'text': text,
        'html': html,
    }
    script_path = os.path.join(app.root_path, 'scripts', 'send_password_reset_email.cjs')

    try:
        result = subprocess.run(
            ['node', script_path],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        app.logger.warning('Password-reset email dispatch failed (%s).', type(exc).__name__)
        return False

    if result.returncode != 0:
        # Do not log subprocess output: it can contain request data.
        app.logger.warning('Password-reset email dispatch failed in the Resend connector.')
        return False
    return True


# Notification helper functions
def create_loan_notification(loan):
    """Create notification for loan application."""
    notification_users = User.query.filter(User.role.in_(['Admin', 'Treasurer', 'Secretary', 'Chairman']), User.is_active == True).all()

    borrower_name = loan.borrower_name if loan.loan_type == 'External' else loan.member.full_name

    for user in notification_users:
        notification = Notification(
            user_id=user.id,
            title='New Loan Application',
            message=f'{borrower_name} has applied for a {loan.loan_type.lower()} loan of {format_currency(loan.amount)}',
            notification_type='loan_application'
        )
        db.session.add(notification)
    db.session.commit()

def create_payment_notification(payment_type, member_name, amount, payment_method=None, transaction_reference=None, group_id=None, member_id=None):
    """Create notification for payments - for admins and the member themselves."""
    query = User.query.filter(User.role.in_(['Admin', 'Treasurer', 'Secretary', 'Chairman']), User.is_active == True)
    if group_id:
        query = query.filter(User.group_id == group_id)
    notification_users = query.all()

    method_str = ''
    ref_str = ''
    if payment_method:
        method_str = f' via {payment_method.upper()}'
    if transaction_reference:
        ref_str = f' (Ref: {transaction_reference})'

    for user in notification_users:
        notification = Notification(
            user_id=user.id,
            title=f'New {payment_type} Recorded',
            message=f'{member_name} has made a {payment_type.lower()} of {format_currency(amount)}{method_str}{ref_str}',
            notification_type='payment_recorded',
            payment_method=payment_method,
            transaction_reference=transaction_reference,
            link_url='/contributions'
        )
        db.session.add(notification)

    # Also notify the member themselves
    if member_id:
        member_notification = Notification(
            user_id=member_id,
            title=f'{payment_type} Recorded',
            message=f'Your {payment_type.lower()} of {format_currency(amount)}{method_str}{ref_str} has been recorded successfully.',
            notification_type='payment_confirmed',
            payment_method=payment_method,
            transaction_reference=transaction_reference,
            link_url='/contributions'
        )
        db.session.add(member_notification)

    db.session.commit()


def create_loan_decision_notification(loan, status_text):
    """Notify member of loan approval or rejection with full details."""
    if not loan.member_id:
        return
    member = User.query.get(loan.member_id)
    if not member:
        return

    if status_text == 'approved':
        monthly = loan.calculate_monthly_payment() if loan.duration_months else loan.calculate_total_repayment()
        msg = (
            f'Your loan application of {format_currency(loan.amount)} has been APPROVED.\n'
            f'Interest Rate: {loan.interest_rate}%\n'
            f'Total Repayment: {format_currency(loan.total_repayment or loan.calculate_total_repayment())}\n'
            f'Duration: {loan.duration_months} months\n'
            f'Monthly Payment: {format_currency(monthly)}\n'
            f'Repayment Mode: {loan.repayment_mode.replace("_", " ").title()}\n'
            f'Due Date: {loan.due_date.strftime("%d/%m/%Y") if loan.due_date else "TBD"}\n'
        )
        if loan.approval_notes:
            msg += f'Notes: {loan.approval_notes}'
    else:
        msg = (
            f'Your loan application of {format_currency(loan.amount)} has been REJECTED.\n'
        )
        if loan.rejection_reason:
            msg += f'Reason: {loan.rejection_reason}'
        elif loan.approval_notes:
            msg += f'Reason: {loan.approval_notes}'

    notification = Notification(
        user_id=member.id,
        title=f'Loan Application {status_text.title()}',
        message=msg,
        notification_type=f'loan_{status_text}',
        link_url='/loans'
    )
    db.session.add(notification)
    db.session.commit()


def get_group_users_ids(group_id):
    """Get list of user IDs for a group."""
    if not group_id:
        return []
    return [u.id for u in User.query.filter_by(group_id=group_id, is_active=True).all()]

def initialize_default_badges():
    """Initialize default badges in the database."""
    from models import Badge
    
    default_badges = [
        {
            'name': 'On-Time Payment',
            'description': 'Awarded for consistent on-time loan payments',
            'icon': 'fas fa-clock',
            'category': 'payments',
            'criteria': 'Make 5 consecutive on-time payments',
            'points_value': 25
        },
        {
            'name': 'Attendance Star',
            'description': 'Awarded for regular meeting attendance',
            'icon': 'fas fa-star',
            'category': 'attendance',
            'criteria': 'Attend 10 consecutive meetings',
            'points_value': 20
        },
        {
            'name': 'Consistent Saver',
            'description': 'Awarded for consistent monthly savings',
            'icon': 'fas fa-piggy-bank',
            'category': 'savings',
            'criteria': 'Make contributions for 6 consecutive months',
            'points_value': 30
        }
    ]
    
    for badge_data in default_badges:
        existing_badge = Badge.query.filter_by(name=badge_data['name']).first()
        if not existing_badge:
            badge = Badge(
                name=badge_data['name'],
                description=badge_data['description'],
                icon=badge_data['icon'],
                category=badge_data['category'],
                criteria=badge_data['criteria'],
                points_value=badge_data['points_value']
            )
            db.session.add(badge)
    
    db.session.commit()

# Gamification helper functions
def check_and_award_badges(member_id, activity_type):
    """Check and award badges based on member activity."""
    badges_awarded = []
    member = User.query.get(member_id)
    if not member:
        return badges_awarded

    from models import Badge
    
    # On-Time Payment Badge
    if activity_type == 'loan_repayment':
        badge = Badge.query.filter_by(name="On-Time Payment").first()
        if badge and not UserBadge.query.filter_by(member_id=member_id, badge_id=badge.id).first():
            new_badge = UserBadge(member_id=member_id, badge_id=badge.id, points_earned=badge.points_value)
            db.session.add(new_badge)
            badges_awarded.append("On-Time Payment")

    # Attendance Star Badge
    if activity_type == 'meeting_attendance':
        badge = Badge.query.filter_by(name="Attendance Star").first()
        if badge and not UserBadge.query.filter_by(member_id=member_id, badge_id=badge.id).first():
            new_badge = UserBadge(member_id=member_id, badge_id=badge.id, points_earned=badge.points_value)
            db.session.add(new_badge)
            badges_awarded.append("Attendance Star")

    # Consistent Saver Badge
    if activity_type == 'contribution':
        badge = Badge.query.filter_by(name="Consistent Saver").first()
        if badge and not UserBadge.query.filter_by(member_id=member_id, badge_id=badge.id).first():
            new_badge = UserBadge(member_id=member_id, badge_id=badge.id, points_earned=badge.points_value)
            db.session.add(new_badge)
            badges_awarded.append("Consistent Saver")

    db.session.commit()
    return badges_awarded

# Payment reminder functionality (placeholder)
def send_payment_reminder(member_id, loan_id):
    """Sends a payment reminder to a member."""
    # In a real app, this would send an email or in-app notification
    member = User.query.get(member_id)
    loan = Loan.query.get(loan_id)
    if member and loan:
        print(f"Sending payment reminder to {member.full_name} for loan {loan.id}. Due: {loan.due_date}")
        # Example: Create a notification
        notification = Notification(
            user_id=member_id,
            title="Loan Payment Reminder",
            message=f"Your loan payment of {format_currency(loan.remaining_amount)} is due on {format_date(loan.due_date)}.",
            notification_type="payment_reminder"
        )
        db.session.add(notification)
        db.session.commit()

# Placeholder for delete functionality with reason
def delete_record_with_reason(record, record_type, reason, deleted_by_user_id):
    """Marks a record as deleted with a reason."""
    if not hasattr(record, 'is_deleted'):
        raise AttributeError(f"{record_type} record does not have 'is_deleted' attribute.")

    record.is_deleted = True
    record.deletion_reason = reason
    record.deleted_by = deleted_by_user_id
    record.deleted_at = datetime.utcnow()
    db.session.commit()
    # Log activity if logger is available
    try:
        from activity_logger import log_activity
        log_activity('deleted', record_type, record.id, f'Deleted {record_type} - Reason: {reason}')
    except ImportError:
        pass # activity_logger not available


def _group_member_ids(group_id=None, active_only=False):
    """Return member IDs in the current tenant; None means platform-wide access."""
    if group_id is None:
        group_id = get_active_group_id()
    if current_user.is_super_admin and group_id is None:
        return None
    if group_id is None:
        return []
    query = db.session.query(User.id).filter(
        User.group_id == group_id,
        User.is_super_admin.is_(False),
    )
    if active_only:
        query = query.filter(User.is_active.is_(True))
    return [member_id for (member_id,) in query.all()]


def _can_access_member(member_id):
    """A group user may only access users assigned to their own group."""
    if current_user.is_super_admin:
        return True
    if not current_user.group_id:
        return False
    return User.query.filter_by(
        id=member_id, group_id=current_user.group_id
    ).first() is not None


def _can_access_record(record):
    """Check tenant ownership for records, including records linked through a member."""
    if current_user.is_super_admin:
        return True

    record_group_id = getattr(record, 'group_id', None)
    if record_group_id is not None:
        return bool(current_user.group_id and record_group_id == current_user.group_id)

    member_id = getattr(record, 'member_id', None)
    if member_id is not None:
        return _can_access_member(member_id)

    guarantor_id = getattr(record, 'guarantor_id', None)
    if guarantor_id is not None:
        return _can_access_member(guarantor_id)

    beneficiary_id = getattr(record, 'beneficiary_id', None)
    if beneficiary_id is not None:
        return _can_access_member(beneficiary_id)

    loan_id = getattr(record, 'loan_id', None)
    if loan_id is not None:
        loan = Loan.query.get(loan_id)
        return bool(loan and loan.member_id and _can_access_member(loan.member_id))

    payment_id = getattr(record, 'payment_id', None)
    if payment_id is not None:
        payment = Payment.query.get(payment_id)
        return bool(payment and _can_access_member(payment.member_id))

    contribution_id = getattr(record, 'contribution_id', None)
    if contribution_id is not None:
        contribution = Contribution.query.get(contribution_id)
        return bool(contribution and _can_access_member(contribution.member_id))

    welfare_id = getattr(record, 'welfare_contribution_id', None)
    if welfare_id is not None:
        welfare = WelfareContribution.query.get(welfare_id)
        return bool(welfare and _can_access_member(welfare.member_id))

    repayment_id = getattr(record, 'loan_repayment_id', None)
    if repayment_id is not None:
        repayment = LoanRepayment.query.get(repayment_id)
        loan = Loan.query.get(repayment.loan_id) if repayment else None
        return bool(loan and loan.member_id and _can_access_member(loan.member_id))

    return False


def _welfare_queries():
    """Return welfare contribution/expense queries limited to the active group."""
    member_ids = _group_member_ids()
    contributions = WelfareContribution.query.filter_by(is_deleted=False)
    expenses = WelfareExpense.query
    if member_ids is not None:
        contributions = contributions.filter(WelfareContribution.member_id.in_(member_ids))
        expenses = expenses.filter(WelfareExpense.beneficiary_id.in_(member_ids))
    return contributions, expenses


@app.before_request
def enforce_group_account_status():
    """Immediately revoke access for group accounts whose group is unavailable."""
    if not current_user.is_authenticated or current_user.is_super_admin:
        return None

    group = Group.query.filter_by(id=current_user.group_id).first() if current_user.group_id else None
    if group and group.is_active:
        return None

    logout_user()
    session.clear()
    flash('This group account is unavailable. Contact the platform administrator.', 'error')
    if request.endpoint in {'login', 'forgot_password', 'reset_password', 'static'}:
        return None
    return redirect(url_for('login'))


# Make utility functions available in templates
@app.context_processor
def utility_processor():
    return dict(has_permission=has_permission, format_currency=format_currency, format_date=format_date, format_datetime=format_datetime, datetime=datetime)

@app.route('/')
def index():
    """CONNECT platform landing page — lists all registered groups."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    # Gather all active groups with quick stats
    all_groups = Group.query.filter_by(is_active=True).order_by(Group.created_at.asc()).all()
    group_cards = []
    for g in all_groups:
        members = User.query.filter_by(group_id=g.id, is_active=True).count()
        group_cards.append({'group': g, 'members': members})

    platform_stats = {
        'total_groups': len(all_groups),
        'total_members': User.query.filter_by(is_active=True).filter(User.is_super_admin == False).count(),
    }
    return render_template('index.html', group_cards=group_cards, platform_stats=platform_stats)

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page — group-specific (via ?group=<id>) or CONNECT admin (no param)."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    form = LoginForm()

    # Determine group context from query param
    group_id = request.args.get('group', type=int)
    selected_group = None

    if group_id:
        selected_group = Group.query.filter_by(id=group_id, is_active=True).first_or_404()
        # Show only active members of that group
        active_users = User.query.filter_by(is_active=True, group_id=group_id)\
                                 .filter(User.is_super_admin == False)\
                                 .order_by(User.full_name).all()
    else:
        # No group selected → CONNECT admin login only
        active_users = User.query.filter_by(is_super_admin=True, is_active=True).all()

    form.username.choices = [(u.username, u.full_name or u.username) for u in active_users]

    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data, is_active=True).first()

        if user and check_password_hash(user.password_hash, form.password.data):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'error')

    return render_template('login.html', form=form, selected_group=selected_group)


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Request a password-reset link for a group account or the CONNECT admin."""
    group_id = request.args.get('group', type=int)
    selected_group = None
    if group_id:
        selected_group = Group.query.filter_by(id=group_id, is_active=True).first_or_404()

    form = PasswordResetRequestForm()
    if form.validate_on_submit():
        if not _password_reset_ip_allowed():
            flash('If an account matches that email, reset instructions will be sent shortly.', 'info')
        elif not os.environ.get('RESEND_FROM_EMAIL', '').strip():
            flash('Password reset email is not available right now. Please contact an administrator.', 'warning')
        else:
            email = form.email.data.strip().lower()
            user_query = User.query.filter(
                func.lower(User.email) == email,
                User.is_active.is_(True),
            )
            if selected_group:
                user_query = user_query.filter(
                    User.group_id == selected_group.id,
                    User.is_super_admin.is_(False),
                )
            else:
                user_query = user_query.filter(User.is_super_admin.is_(True))
            user = user_query.first()

            if user:
                now = datetime.utcnow()
                recent_token = PasswordResetToken.query.filter(
                    PasswordResetToken.user_id == user.id,
                    PasswordResetToken.created_at >= now - timedelta(minutes=1),
                ).first()
                if not recent_token:
                    raw_token = secrets.token_urlsafe(32)
                    token_record = PasswordResetToken(
                        user_id=user.id,
                        token_hash=hashlib.sha256(raw_token.encode('utf-8')).hexdigest(),
                        expires_at=now + timedelta(minutes=30),
                    )
                    for previous_token in PasswordResetToken.query.filter_by(
                        user_id=user.id,
                        used_at=None,
                    ).all():
                        previous_token.used_at = now
                    db.session.add(token_record)
                    db.session.commit()

                    group_name = (
                        user.group.name
                        if not user.is_super_admin and user.group
                        else 'CONNECT platform'
                    )
                    reset_url = url_for('reset_password', token=raw_token, _external=True)
                    if not _send_password_reset_email(user, reset_url, group_name):
                        token_record.used_at = datetime.utcnow()
                        db.session.commit()

            flash('If an account matches that email, reset instructions will be sent shortly.', 'info')

    return render_template(
        'password_reset_request.html',
        form=form,
        selected_group=selected_group,
    )


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Set a new password using a single-use, expiring reset token."""
    invalid_message = 'This password-reset link is invalid or has expired. Please request a new one.'
    if not token or len(token) > 128:
        flash(invalid_message, 'error')
        return redirect(url_for('login'))

    token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
    reset_record = PasswordResetToken.query.filter_by(token_hash=token_hash).first()
    now = datetime.utcnow()
    if (
        not reset_record
        or reset_record.used_at is not None
        or reset_record.expires_at <= now
        or not _password_reset_user_is_eligible(reset_record.user)
    ):
        flash(invalid_message, 'error')
        return redirect(url_for('login'))

    user = reset_record.user
    form = PasswordResetForm()
    if form.validate_on_submit():
        # Lock the token row so two concurrent submissions cannot both succeed.
        reset_record = PasswordResetToken.query.filter_by(token_hash=token_hash).with_for_update().first()
        now = datetime.utcnow()
        if (
            not reset_record
            or reset_record.used_at is not None
            or reset_record.expires_at <= now
            or not _password_reset_user_is_eligible(reset_record.user)
        ):
            flash(invalid_message, 'error')
            return redirect(url_for('login'))

        user = reset_record.user
        user.password_hash = generate_password_hash(form.password.data)
        reset_record.used_at = now
        for other_token in PasswordResetToken.query.filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.id != reset_record.id,
            PasswordResetToken.used_at.is_(None),
        ).all():
            other_token.used_at = now
        db.session.commit()

        flash('Your password has been reset. Sign in with your new password.', 'success')
        login_args = {'group': user.group_id} if not user.is_super_admin and user.group_id else {}
        return redirect(url_for('login', **login_args))

    response = make_response(render_template('password_reset.html', form=form))
    response.headers['Cache-Control'] = 'no-store, max-age=0'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Robots-Tag'] = 'noindex, nofollow'
    return response


@app.route('/verify-2fa/<int:user_id>', methods=['GET', 'POST'])
def verify_2fa(user_id):
    """Verify Two-Factor Authentication - TEMPORARILY DISABLED."""
    flash('Two-factor authentication is temporarily disabled. Please contact support.', 'info')
    return redirect(url_for('login'))

# 2FA verification temporarily disabled for security
def verify_otp_code(user_id, otp_code):
    """OTP verification disabled - always returns False."""
    return False # 2FA disabled - no authentication bypass

@app.route('/logout')
@login_required
def logout():
    """Logout user."""
    session.pop('active_group_id', None)
    logout_user()
    flash('You have been logged out successfully', 'success')
    return redirect(url_for('index'))


@app.route('/switch-group', methods=['POST'])
@login_required
def switch_group():
    """Super admin only: switch the active group context."""
    if not current_user.is_super_admin:
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    group_id = request.form.get('group_id', type=int)
    if group_id:
        group = Group.query.filter_by(id=group_id, is_active=True).first()
        if group:
            session['active_group_id'] = group_id
            flash(f'Switched to group: {group.name}', 'success')
        else:
            flash('Group not found or inactive', 'error')
    else:
        session.pop('active_group_id', None)
        flash('Viewing all groups', 'info')
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard - role-based content."""
    if current_user.is_super_admin:
        return redirect(url_for('super_admin_dashboard'))
    gid = get_active_group_id()
    stats = get_group_statistics(group_id=gid)

    # Get user-specific data
    user_data = {}
    if current_user.role == 'Member':
        user_data['total_contributions'] = current_user.get_total_contributions()
        user_data['active_loans'] = current_user.get_active_loans()
        user_data['loan_balance'] = current_user.get_total_loan_balance()
        user_data['unpaid_fines'] = Fine.query.filter_by(member_id=current_user.id, is_paid=False).all()
        user_data['total_unpaid_fines'] = current_user.get_total_unpaid_fines()
        user_data['badges'] = UserBadge.query.filter_by(member_id=current_user.id).all()
    else:
        # Initialize for non-members to avoid template errors
        user_data['total_contributions'] = 0
        user_data['active_loans'] = []
        user_data['loan_balance'] = 0
        user_data['unpaid_fines'] = []
        user_data['badges'] = []

    # Recent announcements (group-filtered by active group context)
    if gid:
        recent_announcements = Announcement.query.filter(
            Announcement.is_deleted == False,
            db.or_(Announcement.group_id == gid, Announcement.group_id == None)
        ).order_by(Announcement.date_created.desc()).limit(5).all()
    else:
        recent_announcements = Announcement.query.filter_by(is_deleted=False).order_by(Announcement.date_created.desc()).limit(5).all()

    # Recent projects for the group
    if gid:
        recent_projects = Project.query.filter_by(group_id=gid).order_by(Project.created_date.desc()).limit(4).all()
    else:
        recent_projects = Project.query.order_by(Project.created_date.desc()).limit(4).all()

    # Pending loan applications (for Treasurer/Admin) - group-filtered
    pending_loans = []
    if has_permission(current_user, 'approve_loans'):
        if gid:
            group_member_ids = [u.id for u in User.query.filter_by(group_id=gid, is_active=True).all()]
            pending_loans = Loan.query.filter(
                Loan.status == 'Pending',
                Loan.member_id.in_(group_member_ids)
            ).order_by(Loan.application_date.desc()).all()
        else:
            pending_loans = Loan.query.filter_by(status='Pending').order_by(Loan.application_date.desc()).all()

    # Active proposals for voting (group-filtered)
    if gid:
        active_proposals = VotingProposal.query.filter(
            VotingProposal.status == 'Active',
            db.or_(VotingProposal.group_id == gid, VotingProposal.group_id == None)
        ).all()
    else:
        active_proposals = VotingProposal.query.filter_by(status='Active').all()

    # Active payment reminders (example)
    active_reminders = []
    if current_user.role == 'Member':
        # Fetch loans that are due soon or overdue
        active_reminders = Loan.query.filter(
            Loan.member_id == current_user.id,
            Loan.status == 'Active',
            Loan.due_date <= datetime.utcnow() + timedelta(days=7) # Due within a week
        ).order_by(Loan.due_date).all()


    return render_template('dashboard.html', 
                         stats=stats, 
                         user_data=user_data,
                         recent_announcements=recent_announcements,
                         recent_projects=recent_projects,
                         pending_loans=pending_loans,
                         active_proposals=active_proposals,
                         active_reminders=active_reminders)

@app.route('/members')
@login_required
def members():
    """Member management page."""
    if not has_permission(current_user, 'view_members'):
        flash('You do not have permission to view this page', 'error')
        return redirect(url_for('dashboard'))

    # Filter members by group
    active_gid = get_active_group_id()
    if active_gid:
        all_members = User.query.filter_by(is_active=True, group_id=active_gid).filter(User.is_super_admin == False).all()
    else:
        all_members = User.query.filter_by(is_active=True).filter(User.is_super_admin == False).all()
    return render_template('members.html', members=all_members)

@app.route('/members/add', methods=['GET', 'POST'])
@login_required
def add_member():
    """Add new member (Admin only)."""
    if current_user.role != 'Admin':
        flash('Only admins can add new members', 'error')
        return redirect(url_for('members'))

    form = MemberForm()
    active_gid = get_active_group_id()

    # A super admin must select a group before creating a member. Without
    # this guard, the old code created an unassigned user that was invisible
    # from every group's member list.
    if current_user.is_super_admin and not active_gid:
        flash('Select the group you want to add this member to, then try again.', 'warning')
        return redirect(url_for('members'))

    def render_add_form():
        if active_gid:
            visible_members = User.query.filter_by(
                is_active=True, group_id=active_gid
            ).filter(User.is_super_admin == False).all()
        else:
            visible_members = User.query.filter_by(
                is_active=True
            ).filter(User.is_super_admin == False).all()
        return render_template(
            'members.html',
            members=visible_members,
            form=form,
            action='Add'
        )

    if form.validate_on_submit():
        if not form.password.data:
            form.password.errors.append('A password is required when adding a member.')
            return render_add_form()

        # Check if username already exists
        existing_user = User.query.filter_by(username=form.username.data).first()
        if existing_user:
            flash('Username already exists', 'error')
            return render_add_form()

        # Check if email already exists
        existing_email = User.query.filter_by(email=form.email.data).first()
        if existing_email:
            flash('Email already exists', 'error')
            return render_add_form()

        new_member = User(
            username=form.username.data,
            full_name=form.full_name.data,
            email=form.email.data,
            phone=form.phone.data,
            role=form.role.data,
            password_hash=generate_password_hash(form.password.data),
            is_active=True,
            group_id=active_gid
        )

        db.session.add(new_member)
        db.session.commit()

        flash(f'Member {form.full_name.data} has been added successfully', 'success')
        return redirect(url_for('members'))

    return render_add_form()

@app.route('/members/<int:member_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_member(member_id):
    """Edit member details (Admin only)."""
    if current_user.role != 'Admin':
        flash('Only admins can edit member details', 'error')
        return redirect(url_for('members'))

    member = User.query.get_or_404(member_id)
    if member.is_super_admin or not _can_access_member(member.id):
        flash('You do not have permission to edit this account.', 'error')
        return redirect(url_for('members'))
    form = MemberForm(obj=member)

    if form.validate_on_submit():
        # Check for username conflicts (excluding current user)
        existing_user = User.query.filter(User.username == form.username.data, User.id != member_id).first()
        if existing_user:
            flash('Username already exists', 'error')
            return render_template('members.html', form=form, member=member, action='Edit')

        member.username = form.username.data
        member.full_name = form.full_name.data
        member.email = form.email.data
        member.phone = form.phone.data
        member.role = form.role.data

        if form.password.data:  # Only update password if provided
            member.password_hash = generate_password_hash(form.password.data)

        db.session.commit()
        flash(f'Member {member.full_name} has been updated successfully', 'success')
        return redirect(url_for('members'))

    return render_template('members.html', form=form, member=member, action='Edit')

@app.route('/members/<int:member_id>/deactivate', methods=['POST'])
@login_required
def deactivate_member(member_id):
    """Deactivate member (Admin only)."""
    if current_user.role != 'Admin':
        flash('Only admins can deactivate members', 'error')
        return redirect(url_for('members'))

    member = User.query.get_or_404(member_id)
    if member.is_super_admin or not _can_access_member(member.id):
        flash('You do not have permission to deactivate this account.', 'error')
        return redirect(url_for('members'))
    if member.id == current_user.id:
        flash('You cannot deactivate yourself', 'error')
        return redirect(url_for('members'))

    member.is_active = False
    db.session.commit()
    flash(f'Member {member.full_name} has been deactivated', 'success')
    return redirect(url_for('members'))

@app.route('/contributions')
@login_required
def contributions():
    """Contributions management page."""
    if not has_permission(current_user, 'record_contributions') and current_user.role != 'Member':
        flash('You do not have permission to view this page', 'error')
        return redirect(url_for('dashboard'))

    if current_user.role == 'Member':
        # Members see only their own contributions
        user_contributions = Contribution.query.filter_by(member_id=current_user.id).order_by(Contribution.date_recorded.desc()).all()
        return render_template('contributions.html', contributions=user_contributions, is_member_view=True)
    else:
        # Treasurer/Admin see group-filtered contributions
        active_gid = get_active_group_id()
        if active_gid:
            gids = [u.id for u in User.query.filter_by(group_id=active_gid, is_active=True).all()]
            all_contributions = Contribution.query.filter(
                Contribution.is_deleted == False,
                Contribution.member_id.in_(gids)
            ).order_by(Contribution.date_recorded.desc()).all()
        else:
            all_contributions = Contribution.query.filter_by(is_deleted=False).order_by(Contribution.date_recorded.desc()).all()
        return render_template('contributions.html', contributions=all_contributions, is_member_view=False)

@app.route('/contributions/add', methods=['GET', 'POST'])
@login_required
def add_contribution():
    """Add new contribution (Treasurer/Admin only)."""
    if not has_permission(current_user, 'record_contributions'):
        flash('You do not have permission to record contributions', 'error')
        return redirect(url_for('contributions'))

    form = ContributionForm()

    if current_user.is_super_admin and not get_active_group_id():
        flash('Select a group before recording a contribution.', 'warning')
        return redirect(url_for('groups'))

    # Populate member choices - group-filtered
    member_ids = _group_member_ids(active_only=True)
    member_query = User.query.filter_by(is_active=True).filter(User.is_super_admin.is_(False))
    if member_ids is not None:
        member_query = member_query.filter(User.id.in_(member_ids))
    active_members = member_query.all()
    form.member_id.choices = [(member.id, member.full_name) for member in active_members]

    if form.validate_on_submit():
        selected_member = User.query.filter_by(
            id=form.member_id.data, is_active=True, is_super_admin=False
        ).first()
        if not selected_member or not _can_access_member(selected_member.id):
            flash('Select an active member in the permitted group.', 'error')
            return render_template('contributions.html', form=form, action='Add')

        payment_method = form.payment_method.data if hasattr(form, 'payment_method') else 'cash'
        transaction_reference = form.transaction_reference.data if hasattr(form, 'transaction_reference') else None
        transaction_reference = transaction_reference.strip() if transaction_reference else None
        if transaction_reference and Contribution.query.filter_by(
            transaction_reference=transaction_reference
        ).first():
            flash('That transaction reference has already been recorded.', 'error')
            return render_template('contributions.html', form=form, action='Add')

        bank_name = form.bank_name.data.strip() if hasattr(form, 'bank_name') and form.bank_name.data else None

        contribution = Contribution(
            member_id=selected_member.id,
            amount=form.amount.data,
            contribution_type=form.contribution_type.data,
            payment_method=payment_method,
            transaction_reference=transaction_reference,
            bank_name=bank_name,
            notes=form.notes.data,
            recorded_by=current_user.id
        )

        db.session.add(contribution)
        db.session.commit()

        member = selected_member

        # Create notification for payment recording (with method and reference)
        try:
            group_id = current_user.group_id if not current_user.is_super_admin else None
            create_payment_notification(
                'Savings Contribution',
                member.full_name,
                form.amount.data,
                payment_method=payment_method,
                transaction_reference=transaction_reference,
                group_id=group_id,
                member_id=member.id
            )
        except Exception:
            pass

        # Generate digital receipt
        try:
            receipt_number = f"CONT{datetime.now().strftime('%Y%m%d')}{contribution.id:04d}"
            qr_data = {
                'receipt_number': receipt_number,
                'type': 'contribution',
                'amount': contribution.amount,
                'member': member.full_name,
                'date': contribution.date_recorded.isoformat(),
                'recorded_by': current_user.full_name
            }

            # Placeholder for actual QR code generation and storage
            digital_receipt = DigitalReceipt(
                payment_id=None, # This is a contribution, not a direct payment record in the Payment table
                contribution_id=contribution.id, # Link to contribution
                receipt_number=receipt_number,
                qr_code_data=json.dumps(qr_data),
                generated_at=datetime.utcnow(),
                group_id=member.group_id,
            )
            db.session.add(digital_receipt)
            db.session.commit()

            flash(f'Contribution of {format_currency(form.amount.data)} recorded for {member.full_name}. Receipt #{receipt_number} generated.', 'success')
        except Exception as e:
            flash(f'Contribution recorded but receipt generation failed: {str(e)}', 'warning')

        # Award badges for consistent saving
        try:
            badges_awarded = check_and_award_badges(member.id, 'contribution')
            if badges_awarded:
                flash(f'Congratulations! {member.full_name} earned badges: {", ".join(badges_awarded)}', 'info')
        except:
            pass

        return redirect(url_for('contributions'))

    return render_template('contributions.html', form=form, action='Add')

@app.route('/loans')
@login_required
def loans():
    """Loans management page."""
    if current_user.role == 'Member':
        # Members see only their own loans
        user_loans = Loan.query.filter_by(member_id=current_user.id, is_deleted=False).order_by(Loan.application_date.desc()).all()
        return render_template('loans.html', loans=user_loans, is_member_view=True, form=None, action=None)
    elif has_permission(current_user, 'approve_loans'):
        # Group-filter loan queries
        gids = _group_member_ids()

        def loan_q(status):
            q = Loan.query.filter_by(status=status, is_deleted=False)
            if gids is not None:
                q = q.filter(db.or_(
                    Loan.member_id.in_(gids),
                    Loan.guarantor_id.in_(gids),
                ))
            return q.order_by(Loan.application_date.desc()).all()

        applied_loans = loan_q('Pending')
        existing_query = Loan.query.filter_by(status='Active', is_deleted=False)
        if gids is not None:
            existing_query = existing_query.filter(db.or_(
                Loan.member_id.in_(gids),
                Loan.guarantor_id.in_(gids),
            ))
        existing_loans = existing_query.order_by(Loan.approval_date.desc()).all()
        expired_loans = loan_q('Expired')
        
        # For repayment mode, we'll need to infer it from the loan details or add a specific field
        # Repayment Mode could be a string like 'Weekly', 'Monthly', 'Lump Sum' stored in the Loan model
        # Assuming 'repayment_mode' field exists in Loan model:
        # loans_with_mode = Loan.query.filter_by(is_deleted=False).all()
        
        return render_template('loans.html', 
                               applied_loans=applied_loans,
                               existing_loans=existing_loans,
                               expired_loans=expired_loans,
                               is_member_view=False,
                               form=None, action=None)
    else:
        flash('You do not have permission to view this page', 'error')
        return redirect(url_for('dashboard'))

@app.route('/loans/apply', methods=['GET', 'POST'])
@login_required
def apply_loan():
    """Apply for a loan (Members)."""
    if not has_permission(current_user, 'apply_loan'):
        flash('You do not have permission to apply for loans', 'error')
        return redirect(url_for('loans'))

    form = LoanApplicationForm()

    # Populate guarantor choices for external loans
    member_ids = _group_member_ids(active_only=True)
    member_query = User.query.filter_by(is_active=True, is_super_admin=False)
    if member_ids is not None:
        member_query = member_query.filter(User.id.in_(member_ids))
    active_members = member_query.all()
    form.guarantor_id.choices = [(0, 'Select Guarantor')] + [(member.id, member.full_name) for member in active_members]

    # Calculate and display loan limit
    total_savings = current_user.get_total_contributions() # Assuming contributions are savings
    loan_limit = total_savings * 0.75
    form.amount.validators.append(validate_loan_amount(loan_limit)) # Add custom validator

    # Check for existing active loans
    active_internal_loans = Loan.query.filter_by(member_id=current_user.id, status='Active', is_deleted=False).count()
    if active_internal_loans > 0:
        flash('You already have an active loan. Please complete payment before applying for a new loan.', 'error')
        # Render the form but disable submission or show a message
        return render_template('loans.html', form=form, action='Apply', loans=[], is_member_view=True, loan_limit_exceeded=True, loan_limit=loan_limit)

    if form.validate_on_submit():
        try:
            # Check loan limit
            if form.amount.data > loan_limit:
                flash(f'Loan amount exceeds your limit of {format_currency(loan_limit)}.', 'error')
                return render_template('loans.html', form=form, action='Apply', loans=[], is_member_view=True, loan_limit_exceeded=True, loan_limit=loan_limit)

            # Set interest rate based on loan type
            interest_rate = 20.0 if form.loan_type.data == 'Internal' else 30.0
            duration = int(form.duration_months.data) if hasattr(form, 'duration_months') and form.duration_months.data else 3

            # Calculate total repayment (simple interest)
            interest = form.amount.data * (interest_rate / 100) * (duration / 12)
            total_repayment = form.amount.data + interest

            loan = Loan(
                member_id=current_user.id if form.loan_type.data == 'Internal' else None,
                amount=form.amount.data,
                remaining_amount=total_repayment,
                interest_rate=interest_rate,
                purpose=form.purpose.data,
                loan_type=form.loan_type.data,
                total_repayment=total_repayment,
                duration_months=duration,
                status='Pending',
                repayment_mode=form.repayment_mode.data # Assuming repayment_mode is a field in the form and model
            )

            # Add additional fields if available
            if hasattr(form, 'occupation') and form.occupation.data:
                loan.occupation = form.occupation.data
            if hasattr(form, 'monthly_income') and form.monthly_income.data:
                loan.monthly_income = form.monthly_income.data

            # Add external loan fields if applicable
            if form.loan_type.data == 'External':
                loan.guarantor_id = form.guarantor_id.data if form.guarantor_id.data != 0 else None
                if hasattr(form, 'kra_pin') and form.kra_pin.data:
                    loan.kra_pin = form.kra_pin.data
                if hasattr(form, 'id_number') and form.id_number.data:
                    loan.id_number = form.id_number.data
                if hasattr(form, 'borrower_phone') and form.borrower_phone.data:
                    loan.borrower_phone = form.borrower_phone.data
                if hasattr(form, 'borrower_name') and form.borrower_name.data:
                    loan.borrower_name = form.borrower_name.data
                if hasattr(form, 'borrower_address') and form.borrower_address.data:
                    loan.borrower_address = form.borrower_address.data

            db.session.add(loan)
            db.session.commit()

            # Create notification
            try:
                create_loan_notification(loan)
            except:
                pass  # Continue even if notification fails

            # Log activity
            try:
                from activity_logger import log_activity
                borrower_name = loan.borrower_name if loan.loan_type == 'External' else current_user.full_name
                log_activity('applied', 'loan', loan.id, f'{borrower_name} applied for {loan.loan_type.lower()} loan of {format_currency(loan.amount)}')
            except:
                pass  # Continue even if logging fails

            flash(f'Loan application for {format_currency(form.amount.data)} submitted successfully. Total to repay: {format_currency(total_repayment)} (including {interest_rate}% interest)', 'success')
            return redirect(url_for('loans'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error submitting loan application: {str(e)}', 'error')

    return render_template('loans.html', form=form, action='Apply', loan_limit=loan_limit)


# Custom validator for loan amount
def validate_loan_amount(loan_limit):
    def _validate(form, field):
        if field.data > loan_limit:
            raise ValidationError(f'Loan amount cannot exceed your limit of {format_currency(loan_limit)}.')
    return _validate


@app.route('/loans/<int:loan_id>/approve', methods=['GET', 'POST'])
@login_required
def approve_loan(loan_id):
    """Approve/Reject loan (Treasurer/Admin only)."""
    if not has_permission(current_user, 'approve_loans'):
        flash('You do not have permission to approve loans', 'error')
        return redirect(url_for('loans'))

    loan = Loan.query.get_or_404(loan_id)
    if not _can_access_record(loan):
        flash('You do not have permission to access this loan.', 'error')
        return redirect(url_for('loans'))
    form = LoanApprovalForm()

    if form.validate_on_submit():
        try:
            # Calculate interest and total repayment
            interest = form.amount.data * (form.interest_rate.data / 100) * (int(form.duration_months.data) / 12)
            total_repayment = form.amount.data + interest

            loan.amount = form.amount.data
            loan.remaining_amount = total_repayment
            loan.interest_rate = form.interest_rate.data
            loan.status = form.status.data
            loan.approved_by = current_user.id
            loan.approval_date = datetime.utcnow()
            loan.duration_months = int(form.duration_months.data)
            loan.total_repayment = total_repayment
            loan.approval_notes = form.approval_notes.data
            loan.repayment_mode = form.repayment_mode.data # Update repayment mode

            if form.status.data == 'Active':
                # Set due date based on duration and start date (e.g., approval date)
                loan.due_date = datetime.utcnow() + timedelta(days=int(form.duration_months.data) * 30) # Approximation

            # Store rejection reason
            if form.status.data == 'Rejected':
                loan.rejection_reason = form.rejection_reason.data if hasattr(form, 'rejection_reason') and form.rejection_reason.data else form.approval_notes.data

            db.session.commit()

            # Send notification to member with full loan terms
            try:
                status_text_for_notify = 'approved' if form.status.data == 'Active' else 'rejected'
                create_loan_decision_notification(loan, status_text_for_notify)
            except Exception:
                pass

            # Notify all admins/officials
            try:
                borrower_name = loan.borrower_name if loan.loan_type == 'External' else (loan.member.full_name if loan.member else 'Unknown')
                group_id = current_user.group_id if not current_user.is_super_admin else None
                query = User.query.filter(User.role.in_(['Admin', 'Treasurer', 'Secretary', 'Chairman']), User.is_active == True)
                if group_id:
                    query = query.filter(User.group_id == group_id)
                for u in query.all():
                    if u.id != current_user.id:
                        n = Notification(
                            user_id=u.id,
                            title=f'Loan {"Approved" if form.status.data == "Active" else "Rejected"}',
                            message=f'Loan for {borrower_name} ({format_currency(loan.amount)}) has been {"approved" if form.status.data == "Active" else "rejected"} by {current_user.full_name}.',
                            notification_type='loan_decision',
                            link_url='/loans'
                        )
                        db.session.add(n)
                db.session.commit()
            except Exception:
                pass

            # Log activity
            try:
                from activity_logger import log_activity
                status_text = 'approved' if form.status.data == 'Active' else 'rejected'
                borrower_name = loan.borrower_name if loan.loan_type == 'External' else (loan.member.full_name if loan.member else 'Unknown')
                log_activity(status_text, 'loan', loan.id, f'{status_text.title()} loan for {borrower_name} - Amount: {format_currency(loan.amount)}')
            except Exception:
                pass

            status_text = 'approved' if form.status.data == 'Active' else 'rejected'
            flash(f'Loan application has been {status_text}', 'success')
            return redirect(url_for('loans'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error processing loan: {str(e)}', 'error')

    # Pre-populate form with loan data
    if request.method == 'GET':
        form.amount.data = loan.amount
        form.interest_rate.data = loan.interest_rate
        form.duration_months.data = str(loan.duration_months)
        form.status.data = loan.status
        form.approval_notes.data = loan.approval_notes
        form.repayment_mode.data = loan.repayment_mode # Pre-populate repayment mode

    return render_template('loans.html', form=form, loan=loan, action='Approve', is_member_view=False)

@app.route('/loans/<int:loan_id>/delete', methods=['POST'])
@login_required
def delete_loan(loan_id):
    """Delete loan with reason (Admin/Treasurer only)."""
    if not has_permission(current_user, 'manage_finances'):
        flash('You do not have permission to delete loans', 'error')
        return redirect(url_for('loans'))

    loan = Loan.query.get_or_404(loan_id)
    if not _can_access_record(loan):
        flash('You do not have permission to access this loan.', 'error')
        return redirect(url_for('loans'))
    reason = request.form.get('reason', '').strip()

    if not reason:
        flash('Deletion reason is required', 'error')
        return redirect(url_for('loans'))

    # Use the helper function
    delete_record_with_reason(loan, 'loan', reason, current_user.id)

    flash('Loan has been deleted successfully', 'success')
    return redirect(url_for('loans'))

@app.route('/contributions/<int:contrib_id>/delete', methods=['POST'])
@login_required
def delete_contribution(contrib_id):
    """Delete contribution with reason (Admin/Treasurer only)."""
    if not has_permission(current_user, 'record_contributions'):
        flash('You do not have permission to delete contributions', 'error')
        return redirect(url_for('contributions'))

    contribution = Contribution.query.get_or_404(contrib_id)
    if not _can_access_record(contribution):
        flash('You do not have permission to access this contribution.', 'error')
        return redirect(url_for('contributions'))
    reason = request.form.get('reason', '').strip()

    if not reason:
        flash('Deletion reason is required', 'error')
        return redirect(url_for('contributions'))

    # Use the helper function
    delete_record_with_reason(contribution, 'contribution', reason, current_user.id)

    flash('Contribution has been deleted successfully', 'success')
    return redirect(url_for('contributions'))

@app.route('/loans/repayment', methods=['GET', 'POST'])
@login_required
def loan_repayment():
    """Record loan repayment (Treasurer/Admin only)."""
    if not has_permission(current_user, 'manage_finances'):
        flash('You do not have permission to record loan repayments', 'error')
        return redirect(url_for('loans'))

    form = LoanRepaymentForm()

    # Populate active loan choices — group-filtered
    gids = _group_member_ids()
    active_query = Loan.query.filter_by(status='Active', is_deleted=False)
    if gids is not None:
        active_query = active_query.filter(db.or_(
            Loan.member_id.in_(gids),
            Loan.guarantor_id.in_(gids),
        ))
    active_loans = active_query.all()
    form.loan_id.choices = [('', 'Select a loan to process repayment...')]

    for loan in active_loans:
        if loan.loan_type == 'Internal' and loan.member:
            borrower_name = loan.member.full_name
        elif loan.loan_type == 'External' and loan.borrower_name:
            borrower_name = loan.borrower_name
        else:
            borrower_name = 'Unknown Borrower'

        form.loan_id.choices.append((loan.id, f"{borrower_name} - {format_currency(loan.remaining_amount)}"))
    
    # If no active loans, update placeholder message
    if len(form.loan_id.choices) == 1:
        form.loan_id.choices = [('', 'No active loans available for repayment')]

    if form.validate_on_submit():
        try:
            loan = Loan.query.filter_by(id=form.loan_id.data).with_for_update().first()
            if not loan:
                flash('Loan not found', 'error')
                return render_template('loans.html', form=form, action='Repayment', loans=[], is_member_view=False)
            if loan.status != 'Active' or loan.is_deleted or not _can_access_record(loan):
                flash('This loan is unavailable or outside your group.', 'error')
                return redirect(url_for('loans'))

            repayment_amount = form.amount.data

            if repayment_amount > loan.remaining_amount:
                flash('Repayment amount cannot exceed remaining loan balance', 'error')
                return render_template('loans.html', form=form, action='Repayment', loans=[], is_member_view=False)

            # Record repayment (with payment method/reference)
            pay_method = form.payment_method.data if hasattr(form, 'payment_method') else 'cash'
            tx_ref = form.transaction_reference.data if hasattr(form, 'transaction_reference') else None
            tx_ref = tx_ref.strip() if tx_ref else None
            if tx_ref and LoanRepayment.query.filter_by(transaction_reference=tx_ref).first():
                flash('That transaction reference has already been recorded.', 'error')
                return redirect(url_for('loans'))
            bnk_name = form.bank_name.data.strip() if hasattr(form, 'bank_name') and form.bank_name.data else None
            repayment = LoanRepayment(
                loan_id=loan.id,
                amount=repayment_amount,
                recorded_by=current_user.id,
                payment_method=pay_method,
                transaction_reference=tx_ref,
                bank_name=bnk_name
            )

            # Update loan balance
            loan.remaining_amount = round(
                max(0.0, float(loan.remaining_amount) - float(repayment_amount)), 2
            )

            # Mark loan as completed if fully paid
            if loan.remaining_amount <= 0:
                loan.status = 'Completed'
                # Consider awarding "On-Time Payment" badge if applicable
                try:
                    check_and_award_badges(loan.member_id, 'loan_repayment')
                except:
                    pass # Ignore errors in badge awarding

            db.session.add(repayment)
            db.session.commit()

            # Determine borrower name for notification
            borrower_name = loan.member.full_name if loan.member else loan.borrower_name

            # Log activity
            try:
                from activity_logger import log_activity
                log_activity('recorded', 'loan_repayment', repayment.id, f'Recorded loan repayment of {format_currency(repayment_amount)} for {borrower_name}')
            except:
                pass  # Continue even if logging fails

            # Create payment notification
            try:
                create_payment_notification('Loan Repayment', borrower_name, repayment_amount)
            except:
                pass # Continue even if notification fails
                
            # Generate digital receipt for loan settlement
            if loan.remaining_amount <= 0 and loan.status == 'Completed':
                try:
                    receipt_number = f"LOANSETTLE{datetime.now().strftime('%Y%m%d')}{loan.id:04d}"
                    qr_data = {
                        'receipt_number': receipt_number,
                        'type': 'loan_settlement',
                        'amount': repayment_amount, # Amount of the final payment
                        'loan_id': loan.id,
                        'member': borrower_name,
                        'date': datetime.utcnow().isoformat(),
                        'recorded_by': current_user.full_name
                    }
                    digital_receipt = DigitalReceipt(
                        payment_id=None, # Not from Payment table directly
                        loan_repayment_id=repayment.id, # Link to the repayment record
                        receipt_number=receipt_number,
                        qr_code_data=json.dumps(qr_data),
                        generated_at=datetime.utcnow(),
                        group_id=loan.member.group_id if loan.member else (
                            loan.guarantor.group_id if getattr(loan, 'guarantor', None) else None
                        ),
                    )
                    db.session.add(digital_receipt)
                    db.session.commit()
                    flash(f'Loan settled successfully. Receipt #{receipt_number} generated.', 'success')
                except Exception as e:
                    flash(f'Loan repayment recorded, but settlement receipt generation failed: {str(e)}', 'warning')

            flash(f'Repayment of {format_currency(repayment_amount)} recorded for {borrower_name}', 'success')
            return redirect(url_for('loans'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error recording repayment: {str(e)}', 'error')

    return render_template('loans.html', form=form, action='Repayment', loans=[], is_member_view=False)

@app.route('/fines', methods=['GET', 'POST'])
@login_required
def fines():
    """Fines management page."""
    if current_user.role == 'Member':
        # Members see only their own unpaid fines (settled fines disappear from view)
        user_fines = Fine.query.filter_by(member_id=current_user.id, is_paid=False, is_deleted=False).order_by(Fine.date_issued.desc()).all()
        return render_template('contributions.html', fines=user_fines, is_member_view=True, show_fines=True)
    elif has_permission(current_user, 'issue_fines'):
        form = FineForm()

        # Populate member choices - group-filtered
        active_gid = get_active_group_id()
        if active_gid:
            active_members = User.query.filter_by(is_active=True, group_id=active_gid).filter(User.is_super_admin == False).all()
        else:
            active_members = User.query.filter_by(is_active=True).filter(User.is_super_admin == False).all()
        form.member_id.choices = [(member.id, member.full_name) for member in active_members]

        if form.validate_on_submit():
            fine = Fine(
                member_id=form.member_id.data,
                amount=form.amount.data,
                fine_type=form.fine_type.data,
                reason=form.reason.data,
                recorded_by=current_user.id
            )

            db.session.add(fine)
            db.session.commit()

            member = User.query.get(form.member_id.data)
            flash(f'Fine of {format_currency(form.amount.data)} issued to {member.full_name}', 'success')
            
            # Create notification for fine issuance
            try:
                create_payment_notification('Fine', member.full_name, form.amount.data)
            except:
                pass # Continue even if notification fails
            
            return redirect(url_for('fines'))

        if active_gid:
            fine_member_ids = [u.id for u in User.query.filter_by(group_id=active_gid, is_active=True).all()]
            all_fines = Fine.query.filter(
                Fine.is_deleted == False,
                Fine.member_id.in_(fine_member_ids)
            ).order_by(Fine.date_issued.desc()).all()
        else:
            all_fines = Fine.query.filter_by(is_deleted=False).order_by(Fine.date_issued.desc()).all()
        return render_template('contributions.html', fines=all_fines, form=form, is_member_view=False, show_fines=True)
    else:
        flash('You do not have permission to view this page', 'error')
        return redirect(url_for('dashboard'))

@app.route('/announcements')
@login_required
def announcements():
    """Announcements page."""
    # Group-filter announcements
    if current_user.is_super_admin:
        all_announcements = Announcement.query.filter_by(is_deleted=False).order_by(Announcement.date_created.desc()).all()
    elif current_user.group_id:
        all_announcements = Announcement.query.filter(
            Announcement.is_deleted == False,
            db.or_(Announcement.group_id == current_user.group_id, Announcement.group_id == None)
        ).order_by(Announcement.date_created.desc()).all()
    else:
        all_announcements = Announcement.query.filter_by(is_deleted=False).order_by(Announcement.date_created.desc()).all()
    return render_template('announcements.html', announcements=all_announcements)

@app.route('/announcements/add', methods=['GET', 'POST'])
@login_required
def add_announcement():
    """Add new announcement (Secretary/Admin only)."""
    if not has_permission(current_user, 'manage_announcements'):
        flash('You do not have permission to create announcements', 'error')
        return redirect(url_for('announcements'))

    if current_user.is_super_admin and not get_active_group_id():
        flash('Select a group before posting an announcement.', 'warning')
        return redirect(url_for('groups'))

    form = AnnouncementForm()

    if form.validate_on_submit():
        announcement = Announcement(
            title=form.title.data,
            content=form.content.data,
            is_urgent=form.is_urgent.data,
            created_by=current_user.id,
            group_id=get_active_group_id()
        )

        db.session.add(announcement)
        db.session.commit()

        flash('Announcement created successfully', 'success')
        return redirect(url_for('announcements'))

    return render_template('announcements.html', form=form, action='Add')

@app.route('/meetings')
@login_required
def meetings():
    """Meeting records page."""
    meeting_query = MeetingRecord.query.filter_by(is_deleted=False)
    group_id = get_active_group_id()
    if group_id is not None:
        meeting_query = meeting_query.filter(MeetingRecord.group_id == group_id)
    all_meetings = meeting_query.order_by(MeetingRecord.date_held.desc()).all()
    return render_template('announcements.html', meetings=all_meetings, show_meetings=True)

@app.route('/meetings/add', methods=['GET', 'POST'])
@login_required
def add_meeting():
    """Add meeting record (Secretary/Admin only)."""
    if not has_permission(current_user, 'record_meetings'):
        flash('You do not have permission to record meetings', 'error')
        return redirect(url_for('meetings'))

    form = MeetingRecordForm()
    if current_user.is_super_admin and not get_active_group_id():
        flash('Select a group before recording a meeting.', 'warning')
        return redirect(url_for('groups'))

    # Populate attendee choices from group members
    member_ids = _group_member_ids(active_only=True)
    member_query = User.query.filter_by(is_active=True).filter(User.is_super_admin.is_(False))
    if member_ids is not None:
        member_query = member_query.filter(User.id.in_(member_ids))
    group_members = member_query.all()
    form.attendee_ids.choices = [(str(m.id), m.full_name) for m in group_members]

    if form.validate_on_submit():
        # Convert selected member IDs to comma-separated full names
        selected_ids = form.attendee_ids.data or []
        if selected_ids:
            id_int_list = [int(i) for i in selected_ids if i]
            selected_members = User.query.filter(User.id.in_(id_int_list)).all()
            attendees_str = ', '.join(m.full_name for m in selected_members)
        else:
            attendees_str = ''

        meeting = MeetingRecord(
            title=form.title.data,
            date_held=form.date_held.data,
            agenda=form.agenda.data,
            minutes=form.minutes.data,
            attendees=attendees_str,
            decisions=form.decisions.data,
            recorded_by=current_user.id,
            group_id=get_active_group_id(),
        )

        db.session.add(meeting)
        db.session.commit()

        flash('Meeting record created successfully', 'success')
        return redirect(url_for('meetings'))

    return render_template('announcements.html', form=form, action='Add', show_meetings=True, group_members=group_members)

@app.route('/documents')
@login_required
def documents():
    """Documents management page."""
    document_query = Document.query
    group_id = get_active_group_id()
    if group_id is not None:
        document_query = document_query.filter(Document.group_id == group_id)
    all_documents = document_query.order_by(Document.upload_date.desc()).all()
    return render_template('documents.html', documents=all_documents)

@app.route('/documents/upload', methods=['GET', 'POST'])
@login_required
def upload_document():
    """Upload document (Admin/Secretary only)."""
    if current_user.role not in ['Admin', 'Secretary']:
        flash('You do not have permission to upload documents', 'error')
        return redirect(url_for('documents'))

    if current_user.is_super_admin and not get_active_group_id():
        flash('Select a group before uploading a group document.', 'warning')
        return redirect(url_for('groups'))

    form = DocumentForm()

    if form.validate_on_submit():
        file = form.file.data
        if file and allowed_file(file.filename):
            try:
                filename = secure_filename(file.filename)
                # Add timestamp to avoid conflicts
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_")
                filename = timestamp + filename

                # Ensure uploads directory exists
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)

                # Get file size
                file_size = os.path.getsize(file_path)

                # Get file extension
                file_type = filename.rsplit('.', 1)[1].lower()

                document = Document(
                    title=form.title.data,
                    filename=filename,
                    file_type=file_type,
                    file_size=file_size,
                    category=form.category.data,
                    description=form.description.data,
                    uploaded_by=current_user.id,
                    group_id=get_active_group_id(),
                )

                db.session.add(document)
                db.session.commit()

                flash('Document uploaded successfully', 'success')
                return redirect(url_for('documents'))
            
            except OSError as e:
                flash(f'File upload failed: Unable to save file. Please try again.', 'error')
                app.logger.error(f'File upload error: {str(e)}')
                return render_template('documents.html', form=form, action='Upload')
            except Exception as e:
                db.session.rollback()
                flash('Upload failed: An error occurred while processing your file.', 'error')
                app.logger.error(f'Document upload error: {str(e)}')
                return render_template('documents.html', form=form, action='Upload')
        else:
            flash('Invalid file type. Please upload PDF, DOC, DOCX, TXT, JPG, JPEG, or PNG files only.', 'error')

    return render_template('documents.html', form=form, action='Upload')

@app.route('/documents/<int:doc_id>/download')
@login_required
def download_document(doc_id):
    """Download document (Members only)."""
    document = Document.query.get_or_404(doc_id)
    if not _can_access_record(document):
        flash('You do not have permission to access this document.', 'error')
        return redirect(url_for('documents'))
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], document.filename)

    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True, download_name=f"{document.title}.{document.file_type}")
    else:
        flash('File not found', 'error')
        return redirect(url_for('documents'))

@app.route('/reports')
@login_required
def reports():
    """Reports and analytics page."""
    if not has_permission(current_user, 'manage_finances') and current_user.role != 'Admin':
        flash('You do not have permission to view reports', 'error')
        return redirect(url_for('dashboard'))

    report_gid = get_active_group_id()
    stats = get_group_statistics(group_id=report_gid)

    # Monthly contribution data for charts — scoped to active group
    monthly_q = db.session.query(
        db.func.date_trunc('month', Contribution.date_recorded).label('month'),
        db.func.sum(Contribution.amount).label('total')
    )
    if report_gid:
        report_member_ids = [u.id for u in User.query.filter_by(group_id=report_gid, is_active=True).all()]
        monthly_q = monthly_q.filter(Contribution.member_id.in_(report_member_ids))
    monthly_contributions = monthly_q.group_by(
        db.func.date_trunc('month', Contribution.date_recorded)
    ).order_by('month').all()

    # You can add more report generation logic here (e.g., loan performance, fine collection)

    return render_template('reports.html', stats=stats, monthly_contributions=monthly_contributions)

@app.route('/reports/export/<format>')
@login_required
def export_report(format):
    """Export reports as PDF or CSV."""
    if not has_permission(current_user, 'manage_finances') and current_user.role != 'Admin':
        flash('You do not have permission to export reports', 'error')
        return redirect(url_for('reports'))

    if format == 'pdf':
        try:
            from utils import generate_financial_report_pdf
            buffer = generate_financial_report_pdf()
            return send_file(buffer, as_attachment=True, 
                           download_name=f"pamoja_financial_report_{datetime.now().strftime('%Y%m%d')}.pdf",
                           mimetype='application/pdf')
        except Exception as e:
            flash(f'Error generating PDF report: {str(e)}', 'error')
            return redirect(url_for('reports'))

    elif format == 'csv':
        try:
            from utils import generate_financial_report_csv
            from io import BytesIO
            csv_data = generate_financial_report_csv()
            
            return send_file(BytesIO(csv_data.encode('utf-8')), as_attachment=True,
                           download_name=f"pamoja_financial_report_{datetime.now().strftime('%Y%m%d')}.csv",
                           mimetype='text/csv')
        except Exception as e:
            flash(f'Error generating CSV report: {str(e)}', 'error')
            return redirect(url_for('reports'))

    else:
        flash('Invalid export format', 'error')
        return redirect(url_for('reports'))

@app.route('/profile')
@login_required
def profile():
    """User profile page."""
    return render_template('profile.html')

@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    """Edit user profile."""
    form = MemberForm(obj=current_user)

    if form.validate_on_submit():
        try:
            # Check for username conflicts (excluding current user)
            existing_user = User.query.filter(User.username == form.username.data, User.id != current_user.id).first()
            if existing_user:
                flash('Username already exists', 'error')
                return render_template('profile.html', form=form, action='Edit')

            # Handle profile picture upload
            if form.profile_picture.data:
                file = form.profile_picture.data
                # Use existing allowed_file function but restrict to images
                if allowed_file(file.filename) and file.filename.rsplit('.', 1)[1].lower() in {'jpg', 'jpeg', 'png'}:
                    filename = secure_filename(file.filename)
                    # Add timestamp to avoid conflicts
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_")
                    filename = f"profile_{current_user.id}_{timestamp}{filename}"

                    # Ensure uploads directory exists
                    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                    
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(file_path)

                    # Delete old profile picture if it exists
                    if current_user.profile_picture:
                        old_file_path = os.path.join(app.config['UPLOAD_FOLDER'], current_user.profile_picture)
                        if os.path.exists(old_file_path):
                            os.remove(old_file_path)

                    current_user.profile_picture = filename
                else:
                    flash('Invalid file type. Please upload JPG, JPEG, or PNG images only.', 'error')
                    return render_template('profile.html', form=form, action='Edit')

            current_user.username = form.username.data
            current_user.full_name = form.full_name.data
            current_user.email = form.email.data
            current_user.phone = form.phone.data

            # Only admin can change role
            if current_user.role == 'Admin':
                current_user.role = form.role.data

            if form.password.data:  # Only update password if provided
                current_user.password_hash = generate_password_hash(form.password.data)

            db.session.commit()
            flash('Profile updated successfully', 'success')
            return redirect(url_for('profile'))
        
        except Exception as e:
            db.session.rollback()
            flash('Profile update failed. Please try again.', 'error')
            app.logger.error(f'Profile update error: {str(e)}')

    return render_template('profile.html', form=form, action='Edit')

@app.route('/profile/change-password', methods=['POST'])
@login_required
def change_password():
    """Change user password."""
    form = PasswordChangeForm()

    if form.validate_on_submit():
        if not check_password_hash(current_user.password_hash, form.current_password.data):
            flash('Current password is incorrect', 'error')
            return redirect(url_for('profile'))

        if form.new_password.data != form.confirm_password.data:
            flash('New passwords do not match', 'error')
            return redirect(url_for('profile'))

        current_user.password_hash = generate_password_hash(form.new_password.data)
        db.session.commit()

        flash('Password changed successfully', 'success')
        return redirect(url_for('profile'))

    flash('Please check your password requirements', 'error')
    return redirect(url_for('profile'))

@app.route('/payments', methods=['GET', 'POST'])
@login_required
def payments():
    """Display legacy payment rows; new entries use the linked ledger workflows."""
    if not has_permission(current_user, 'manage_finances'):
        flash('You do not have permission to process payments', 'error')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        flash(
            'Standalone payment entry is disabled because it did not update a linked group ledger. '
            'Use the contribution, loan repayment, fine, or welfare workflow instead.',
            'warning',
        )
        return redirect(url_for('payments'))

    payment_query = Payment.query
    member_ids = _group_member_ids()
    if member_ids is not None:
        payment_query = payment_query.filter(Payment.member_id.in_(member_ids))
    recent_payments = payment_query.order_by(Payment.payment_date.desc()).limit(100).all()
    return render_template('payment_history.html', payments=recent_payments)

    # Deprecated unlinked-payment implementation is intentionally unreachable.
    form = PaymentForm()

    # Populate reference choices (always, for both GET and POST re-display)
    active_loans = Loan.query.filter_by(status='Active', is_deleted=False).all()
    loan_choices = [(loan.id, f"{loan.member.full_name if loan.member else loan.borrower_name} - {format_currency(loan.remaining_amount)}") for loan in active_loans]
    form.reference_id.choices = loan_choices if loan_choices else [(0, '— None —')]

    if form.validate_on_submit():
        payment = Payment(
            member_id=current_user.id, # Assuming the logged-in user is making the payment
            payment_type=form.payment_type.data,
            reference_id=form.reference_id.data, # e.g., loan_id, fine_id, contribution_id
            amount=form.amount.data,
            payment_method=form.payment_method.data,
            transaction_reference=form.transaction_reference.data,
            processed_by=current_user.id,
            status='Approved' # Assuming payments are automatically approved or handled by another process
        )

        db.session.add(payment)
        db.session.commit() # Commit to get payment.id

        # Generate receipt
        receipt_number = f"PAM{datetime.now().strftime('%Y%m%d')}{payment.id:04d}"
        qr_data = {
            'receipt_number': receipt_number,
            'amount': payment.amount,
            'payment_type': payment.payment_type,
            'date': payment.payment_date.isoformat(),
            'member': current_user.full_name
        }

        receipt = DigitalReceipt(
            payment_id=payment.id,
            receipt_number=receipt_number,
            qr_code_data=json.dumps(qr_data)
        )

        db.session.add(receipt)
        db.session.commit()

        # Update payment to indicate receipt was generated
        payment.receipt_generated = True
        db.session.commit()

        # Create notification for payment recording
        try:
            create_payment_notification(payment.payment_type, current_user.full_name, payment.amount)
        except:
            pass # Continue even if notification fails

        # Potentially award badges based on payment type/consistency
        if payment.payment_type.lower() == 'loan repayment':
             try:
                check_and_award_badges(current_user.id, 'loan_repayment')
             except:
                 pass

        flash(f'Payment of {format_currency(payment.amount)} recorded successfully. Receipt #{receipt_number} generated.', 'success')
        return redirect(url_for('payments'))

    # Get recent payments
    recent_payments = Payment.query.order_by(Payment.payment_date.desc()).limit(20).all()

    return render_template('payments.html', form=form, payments=recent_payments)

@app.route('/welfare')
@login_required
def welfare():
    """Welfare management page."""
    if current_user.role == 'Member':
        # Members see only their welfare contributions
        user_welfare = WelfareContribution.query.filter_by(member_id=current_user.id).all()
        return render_template('welfare.html', welfare_contributions=user_welfare, is_member_view=True)

    # Admin/Treasurer see all welfare data
    contribution_query, expense_query = _welfare_queries()
    welfare_contributions = contribution_query.all()
    welfare_expenses = expense_query.all()

    total_contributions = sum(w.amount for w in welfare_contributions)
    total_expenses = sum(w.amount for w in welfare_expenses)
    balance = total_contributions - total_expenses

    stats = {
        'total_contributions': total_contributions,
        'total_expenses': total_expenses,
        'balance': balance,
        'beneficiaries': len(set(w.beneficiary_id for w in welfare_expenses))
    }

    return render_template('welfare.html', 
                         welfare_contributions=welfare_contributions,
                         welfare_expenses=welfare_expenses,
                         stats=stats,
                         is_member_view=False)

@app.route('/welfare/contribute', methods=['GET', 'POST'])
@login_required
def welfare_contribute():
    """Add welfare contribution."""
    if not has_permission(current_user, 'record_contributions'):
        flash('You do not have permission to record welfare contributions', 'error')
        return redirect(url_for('welfare'))

    form = WelfareContributionForm()
    if current_user.is_super_admin and not get_active_group_id():
        flash('Select a group before recording a welfare contribution.', 'warning')
        return redirect(url_for('groups'))

    # Populate member choices
    member_ids = _group_member_ids(active_only=True)
    member_query = User.query.filter_by(is_active=True, is_super_admin=False)
    if member_ids is not None:
        member_query = member_query.filter(User.id.in_(member_ids))
    active_members = member_query.all()
    form.member_id.choices = [(member.id, member.full_name) for member in active_members]

    if form.validate_on_submit():
        member = User.query.filter_by(
            id=form.member_id.data,
            is_active=True,
            is_super_admin=False,
        ).first()
        if not member or not _can_access_member(member.id):
            flash('Select an active member in the permitted group.', 'error')
            return redirect(url_for('welfare'))

        welfare = WelfareContribution(
            member_id=form.member_id.data,
            amount=form.amount.data,
            notes=form.notes.data,
            recorded_by=current_user.id
        )

        db.session.add(welfare)
        db.session.commit()

        flash(f'Welfare contribution of {format_currency(form.amount.data)} recorded for {member.full_name}', 'success')
        try:
            from activity_logger import log_activity
            log_activity(
                'recorded', 'welfare_contribution', welfare.id,
                f'Recorded welfare contribution of {format_currency(welfare.amount)} for {member.full_name}',
                group_id=member.group_id,
            )
        except Exception:
            app.logger.exception('Could not audit welfare contribution.')

        # Create notification for welfare contribution
        try:
            create_payment_notification('Welfare Contribution', member.full_name, form.amount.data)
        except:
            pass # Continue even if notification fails

        # Generate digital receipt for welfare contribution
        try:
            receipt_number = f"WELFARE{datetime.now().strftime('%Y%m%d')}{welfare.id:04d}"
            qr_data = {
                'receipt_number': receipt_number,
                'type': 'welfare_contribution',
                'amount': welfare.amount,
                'member': member.full_name,
                'date': welfare.date_recorded.isoformat(),
                'recorded_by': current_user.full_name
            }
            digital_receipt = DigitalReceipt(
                payment_id=None, # Not from Payment table directly
                welfare_contribution_id=welfare.id, # Link to welfare contribution
                receipt_number=receipt_number,
                qr_code_data=json.dumps(qr_data),
                generated_at=datetime.utcnow(),
                group_id=member.group_id,
            )
            db.session.add(digital_receipt)
            db.session.commit()
            flash(f'Welfare contribution recorded. Receipt #{receipt_number} generated.', 'success')
        except Exception as e:
            flash(f'Welfare contribution recorded, but receipt generation failed: {str(e)}', 'warning')
            
        # Award badges for consistent saving
        try:
            check_and_award_badges(member.id, 'contribution')
        except:
            pass

        return redirect(url_for('welfare'))

    # Get the same data as the main welfare view
    if current_user.role == 'Member':
        user_welfare = WelfareContribution.query.filter_by(member_id=current_user.id).all()
        return render_template('welfare.html', welfare_contributions=user_welfare, is_member_view=True, form=form, action='Contribute')
    
    # Admin/Treasurer see all welfare data
    contribution_query, expense_query = _welfare_queries()
    welfare_contributions = contribution_query.all()
    welfare_expenses = expense_query.all()

    total_contributions = sum(w.amount for w in welfare_contributions)
    total_expenses = sum(w.amount for w in welfare_expenses)
    balance = total_contributions - total_expenses

    stats = {
        'total_contributions': total_contributions,
        'total_expenses': total_expenses,
        'balance': balance,
        'beneficiaries': len(set(w.beneficiary_id for w in welfare_expenses))
    }

    return render_template('welfare.html', 
                         welfare_contributions=welfare_contributions,
                         welfare_expenses=welfare_expenses,
                         stats=stats,
                         is_member_view=False,
                         form=form,
                         action='Contribute')

@app.route('/welfare/expense', methods=['GET', 'POST'])
@login_required
def welfare_expense():
    """Add welfare expense."""
    if not has_permission(current_user, 'manage_finances'):
        flash('You do not have permission to record welfare expenses', 'error')
        return redirect(url_for('welfare'))

    form = WelfareExpenseForm()
    if current_user.is_super_admin and not get_active_group_id():
        flash('Select a group before recording a welfare expense.', 'warning')
        return redirect(url_for('groups'))

    # Populate beneficiary choices
    member_ids = _group_member_ids(active_only=True)
    member_query = User.query.filter_by(is_active=True, is_super_admin=False)
    if member_ids is not None:
        member_query = member_query.filter(User.id.in_(member_ids))
    active_members = member_query.all()
    form.beneficiary_id.choices = [(member.id, member.full_name) for member in active_members]

    if form.validate_on_submit():
        group_id = get_active_group_id()
        if group_id:
            Group.query.filter_by(id=group_id).with_for_update().first()

        # Check available welfare funds
        contribution_query, expense_query = _welfare_queries()
        total_contributions = sum(w.amount for w in contribution_query.all())
        total_expenses = sum(w.amount for w in expense_query.all())
        available_funds = total_contributions - total_expenses

        if form.amount.data > available_funds:
            flash(f'Insufficient welfare funds. Available: {format_currency(available_funds)}, Requested: {format_currency(form.amount.data)}', 'error')
            return render_template('welfare.html', form=form, action='Expense')

        beneficiary = User.query.get(form.beneficiary_id.data)
        if not beneficiary or not _can_access_member(beneficiary.id):
            flash('Select an active beneficiary in the permitted group.', 'error')
            return redirect(url_for('welfare'))

        expense = WelfareExpense(
            beneficiary_id=form.beneficiary_id.data,
            amount=form.amount.data,
            expense_type=form.expense_type.data,
            description=form.description.data,
            approved_by=current_user.id
        )

        db.session.add(expense)
        db.session.commit()

        flash(f'Welfare expense of {format_currency(form.amount.data)} recorded for {beneficiary.full_name}', 'success')
        try:
            from activity_logger import log_activity
            log_activity(
                'recorded', 'welfare_expense', expense.id,
                f'Recorded welfare expense of {format_currency(expense.amount)} for {beneficiary.full_name}; purpose: {expense.description}',
                group_id=beneficiary.group_id,
            )
        except Exception:
            app.logger.exception('Could not audit welfare expense.')

        # Create notification for welfare expense
        try:
            create_payment_notification('Welfare Expense', beneficiary.full_name, form.amount.data)
        except:
            pass # Continue even if notification fails

        return redirect(url_for('welfare'))

    # Get the same data as the main welfare view
    contribution_query, expense_query = _welfare_queries()
    welfare_contributions = contribution_query.all()
    welfare_expenses = expense_query.all()

    total_contributions = sum(w.amount for w in welfare_contributions)
    total_expenses = sum(w.amount for w in welfare_expenses)
    balance = total_contributions - total_expenses

    stats = {
        'total_contributions': total_contributions,
        'total_expenses': total_expenses,
        'balance': balance,
        'beneficiaries': len(set(w.beneficiary_id for w in welfare_expenses))
    }

    return render_template('welfare.html', 
                         welfare_contributions=welfare_contributions,
                         welfare_expenses=welfare_expenses,
                         stats=stats,
                         is_member_view=False,
                         form=form,
                         action='Expense')

@app.route('/voting')
@login_required
def voting():
    """Voting and proposals page."""
    group_id = get_active_group_id()
    active_query = VotingProposal.query.filter_by(status='Active')
    recent_query = VotingProposal.query.filter(VotingProposal.status.in_(['Closed', 'Implemented']))
    if group_id is not None:
        active_query = active_query.filter(db.or_(
            VotingProposal.group_id == group_id,
            VotingProposal.group_id.is_(None),
        ))
        recent_query = recent_query.filter(db.or_(
            VotingProposal.group_id == group_id,
            VotingProposal.group_id.is_(None),
        ))
    active_proposals = active_query.all()
    recent_proposals = recent_query.order_by(VotingProposal.created_date.desc()).limit(10).all()

    # Calculate results for active proposals if needed for real-time view
    proposal_results = {}
    for proposal in active_proposals:
        votes = Vote.query.filter_by(proposal_id=proposal.id).all()
        results = {}
        total_votes = len(votes)
        for vote in votes:
            results[vote.vote_choice] = results.get(vote.vote_choice, 0) + 1
        proposal_results[proposal.id] = {'results': results, 'total_votes': total_votes}
        
    return render_template('voting.html', 
                         active_proposals=active_proposals,
                         recent_proposals=recent_proposals,
                         proposal_results=proposal_results)

@app.route('/voting/propose', methods=['GET', 'POST'])
@login_required
def create_proposal():
    """Create voting proposal."""
    if current_user.role not in ['Admin', 'Chairman', 'Secretary']:
        flash('You do not have permission to create proposals', 'error')
        return redirect(url_for('voting'))

    if current_user.is_super_admin and not get_active_group_id():
        flash('Select a group before creating a group proposal.', 'warning')
        return redirect(url_for('groups'))

    form = VotingProposalForm()

    if form.validate_on_submit():
        proposal = VotingProposal(
            title=form.title.data,
            description=form.description.data,
            proposal_type=form.proposal_type.data,
            voting_start=form.voting_start.data,
            voting_end=form.voting_end.data,
            minimum_participation=form.minimum_participation.data,
            created_by=current_user.id,
            status='Active' if form.voting_start.data <= datetime.utcnow() else 'Draft',
            group_id=get_active_group_id(),
        )

        db.session.add(proposal)
        db.session.commit()

        flash('Proposal created successfully', 'success')
        return redirect(url_for('voting'))

    return render_template('voting.html', form=form, action='Propose')

@app.route('/voting/<int:proposal_id>/vote', methods=['GET', 'POST'])
@login_required
def cast_vote(proposal_id):
    """Cast vote on proposal."""
    proposal = VotingProposal.query.get_or_404(proposal_id)
    if not current_user.is_super_admin and proposal.group_id not in (None, current_user.group_id):
        flash('This proposal belongs to another group.', 'error')
        return redirect(url_for('voting'))

    # Check if user has already voted
    existing_vote = Vote.query.filter_by(proposal_id=proposal_id, member_id=current_user.id).first()
    if existing_vote:
        flash('You have already voted on this proposal', 'info')
        return redirect(url_for('voting'))

    # Check if voting is still active
    if proposal.status != 'Active' or datetime.utcnow() > proposal.voting_end:
        flash('Voting for this proposal has ended', 'error')
        return redirect(url_for('voting'))

    form = VoteForm()

    if form.validate_on_submit():
        vote = Vote(
            proposal_id=proposal_id,
            member_id=current_user.id,
            vote_choice=form.vote_choice.data,
            comment=form.comment.data
        )

        db.session.add(vote)
        db.session.commit()

        flash('Your vote has been recorded successfully', 'success')
        return redirect(url_for('voting'))

    return render_template('voting.html', form=form, proposal=proposal, action='Vote')

@app.route('/members/directory')
@login_required
def member_directory():
    """Enhanced member directory with full details."""
    if not has_permission(current_user, 'view_members'):
        flash('You do not have permission to view member directory', 'error')
        return redirect(url_for('dashboard'))

    member_ids = _group_member_ids(active_only=True)
    member_query = User.query.filter_by(is_active=True, is_super_admin=False)
    if member_ids is not None:
        member_query = member_query.filter(User.id.in_(member_ids))
    members = member_query.all()

    # Enhanced member data with statistics
    enhanced_members = []
    for member in members:
        member_data = {
            'member': member,
            'total_contributions': member.get_total_contributions(),
            'total_welfare': sum(w.amount for w in WelfareContribution.query.filter_by(member_id=member.id)),
            'active_loans': len(member.get_active_loans()),
            'loan_balance': member.get_total_loan_balance(),
            'unpaid_fines': member.get_total_unpaid_fines(),
            'points': MemberPoints.query.filter_by(member_id=member.id).first(),
            'badges': UserBadge.query.filter_by(member_id=member.id).all()
        }
        enhanced_members.append(member_data)

    return render_template('member_directory.html', members=enhanced_members)

@app.route('/gamification')
@login_required
def gamification():
    """Gamification page showing badges and points."""
    user_badges = UserBadge.query.filter_by(member_id=current_user.id).all()
    user_points = MemberPoints.query.filter_by(member_id=current_user.id).first()
    all_badges = Badge.query.all()
    
    if not user_points:
        user_points = MemberPoints(member_id=current_user.id, total_points=0, level='Bronze')
        db.session.add(user_points)
        db.session.commit()
    
    return render_template('gamification.html', 
                         user_badges=user_badges,
                         user_points=user_points,
                         all_badges=all_badges)

@app.route('/receipts')
@login_required
def receipts():
    """View member's digital receipts."""
    if current_user.role == 'Member':
        member_ids = [current_user.id]
    elif has_permission(current_user, 'manage_finances'):
        member_ids = _group_member_ids()
    else:
        flash('You do not have permission to view receipts', 'error')
        return redirect(url_for('dashboard'))

    if member_ids is None:
        all_receipts = DigitalReceipt.query.order_by(DigitalReceipt.generated_at.desc()).all()
    else:
        contributions = Contribution.query.filter(Contribution.member_id.in_(member_ids)).with_entities(Contribution.id)
        loans = Loan.query.filter(Loan.member_id.in_(member_ids)).with_entities(Loan.id)
        repayments = LoanRepayment.query.filter(LoanRepayment.loan_id.in_(loans)).with_entities(LoanRepayment.id)
        welfare = WelfareContribution.query.filter(WelfareContribution.member_id.in_(member_ids)).with_entities(WelfareContribution.id)
        payments = Payment.query.filter(Payment.member_id.in_(member_ids)).with_entities(Payment.id)
        conditions = [
            DigitalReceipt.contribution_id.in_(contributions),
            DigitalReceipt.loan_repayment_id.in_(repayments),
            DigitalReceipt.welfare_contribution_id.in_(welfare),
            DigitalReceipt.payment_id.in_(payments),
        ]
        group_id = get_active_group_id()
        if group_id is not None:
            conditions.append(DigitalReceipt.group_id == group_id)
        all_receipts = DigitalReceipt.query.filter(
            db.or_(*conditions)
        ).order_by(DigitalReceipt.generated_at.desc()).all()
    
    return render_template('receipts.html', receipts=all_receipts)

@app.route('/receipts/<int:receipt_id>/download')
@login_required
def download_receipt(receipt_id):
    """Download a digital receipt as PDF."""
    receipt = DigitalReceipt.query.get_or_404(receipt_id)
    
    if current_user.role != 'Member' and not has_permission(current_user, 'manage_finances'):
        flash('You do not have permission to access this receipt.', 'error')
        return redirect(url_for('receipts'))
    if not _can_access_record(receipt):
        flash('You do not have permission to access this receipt', 'error')
        return redirect(url_for('receipts'))
    
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.units import inch
        from io import BytesIO
        import json
        
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=1*inch)
        
        styles = getSampleStyleSheet()
        story = []
        
        # Header
        title = Paragraph("Pamoja Agencies SHG", styles['Title'])
        subtitle = Paragraph("Official Digital Receipt", styles['Heading2'])
        story.append(title)
        story.append(subtitle)
        story.append(Spacer(1, 20))
        
        # Receipt details
        qr_data = json.loads(receipt.qr_code_data) if receipt.qr_code_data else {}
        
        receipt_data = [
            ['Receipt Number:', receipt.receipt_number],
            ['Date:', format_datetime(receipt.generated_at)],
            ['Member:', qr_data.get('member', current_user.full_name)],
            ['Payment Type:', qr_data.get('type', 'Payment').replace('_', ' ').title()],
            ['Amount:', format_currency(qr_data.get('amount', 0))],
        ]
        
        if qr_data.get('recorded_by'):
            receipt_data.append(['Recorded By:', qr_data.get('recorded_by')])
        
        receipt_table = Table(receipt_data, colWidths=[2*inch, 3*inch])
        receipt_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(receipt_table)
        story.append(Spacer(1, 30))
        
        # Footer
        footer = Paragraph("This is an official digital receipt from Pamoja Agencies SHG", styles['Normal'])
        story.append(footer)
        
        doc.build(story)
        buffer.seek(0)
        
        # Update download count
        receipt.download_count += 1
        receipt.downloaded = True
        db.session.commit()
        
        return send_file(buffer, as_attachment=True, 
                        download_name=f"receipt_{receipt.receipt_number}.pdf",
                        mimetype='application/pdf')
        
    except Exception as e:
        flash(f'Error generating receipt PDF: {str(e)}', 'error')
        return redirect(url_for('receipts'))

@app.route('/offline-sync')
@login_required
def offline_sync():
    """Sync offline data for current user."""
    try:
        # Get user data safely
        total_contributions = 0
        active_loans = []
        unpaid_fines = []
        
        try:
            total_contributions = current_user.get_total_contributions() or 0
        except:
            pass
            
        try:
            loans = current_user.get_active_loans() or []
            active_loans = [{
                'amount': float(loan.amount) if loan.amount else 0,
                'remaining': float(loan.remaining_amount) if loan.remaining_amount else 0,
                'due_date': loan.due_date.isoformat() if loan.due_date else None,
                'status': loan.status or 'Unknown'
            } for loan in loans]
        except:
            active_loans = []
            
        try:
            fines = current_user.get_unpaid_fines() or []
            unpaid_fines = [{
                'amount': float(fine.amount) if fine.amount else 0,
                'type': fine.fine_type or 'Unknown',
                'date': fine.date_issued.isoformat() if fine.date_issued else datetime.utcnow().isoformat(),
                'paid': bool(fine.is_paid)
            } for fine in fines]
        except:
            unpaid_fines = []

        # Prepare user data for offline access
        user_data = {
            'balance': float(total_contributions),
            'loans': active_loans,
            'fines': unpaid_fines,
            'last_sync': datetime.utcnow().isoformat(),
            'user_id': current_user.id,
            'user_name': current_user.full_name
        }

        return jsonify({
            'success': True,
            'data': user_data,
            'message': 'Data synced successfully'
        })

    except Exception as e:
        app.logger.error(f'Offline sync error: {str(e)}')
        return jsonify({
            'success': False,
            'message': 'Sync failed',
            'data': {
                'balance': 0,
                'loans': [],
                'fines': [],
                'last_sync': datetime.utcnow().isoformat()
            }
        }), 200  # Return 200 instead of 500 to prevent errors

@app.route('/announcements/<int:announcement_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_announcement(announcement_id):
    """Edit announcement (Secretary/Admin only)."""
    if not has_permission(current_user, 'manage_announcements'):
        flash('You do not have permission to edit announcements', 'error')
        return redirect(url_for('announcements'))

    announcement = Announcement.query.get_or_404(announcement_id)
    if not _can_access_record(announcement):
        flash('You do not have permission to edit this announcement.', 'error')
        return redirect(url_for('announcements'))
    form = AnnouncementForm(obj=announcement)

    if form.validate_on_submit():
        announcement.title = form.title.data
        announcement.content = form.content.data
        announcement.is_urgent = form.is_urgent.data

        db.session.commit()
        flash('Announcement updated successfully', 'success')
        return redirect(url_for('announcements'))

    return render_template('announcements.html', form=form, action='Edit', announcement=announcement)

@app.route('/announcements/<int:announcement_id>/view')
@login_required
def view_announcement(announcement_id):
    """View single announcement."""
    announcement = Announcement.query.get_or_404(announcement_id)
    if not current_user.is_super_admin and announcement.group_id not in (None, current_user.group_id):
        flash('This announcement belongs to another group.', 'error')
        return redirect(url_for('announcements'))
    return render_template('announcements.html', announcement=announcement, action='View')

@app.route('/meetings/<int:meeting_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_meeting(meeting_id):
    """Edit meeting record (Secretary/Admin only)."""
    if not has_permission(current_user, 'record_meetings'):
        flash('You do not have permission to edit meetings', 'error')
        return redirect(url_for('meetings'))

    meeting = MeetingRecord.query.get_or_404(meeting_id)
    if not _can_access_record(meeting):
        flash('You do not have permission to access this meeting.', 'error')
        return redirect(url_for('meetings'))
    form = MeetingRecordForm(obj=meeting)

    # Populate attendee choices from group members
    member_ids = _group_member_ids(active_only=True)
    member_query = User.query.filter_by(is_active=True).filter(User.is_super_admin.is_(False))
    if member_ids is not None:
        member_query = member_query.filter(User.id.in_(member_ids))
    group_members = member_query.all()
    form.attendee_ids.choices = [(str(m.id), m.full_name) for m in group_members]

    if form.validate_on_submit():
        selected_ids = form.attendee_ids.data or []
        if selected_ids:
            id_int_list = [int(i) for i in selected_ids if i]
            selected_members = User.query.filter(User.id.in_(id_int_list)).all()
            attendees_str = ', '.join(m.full_name for m in selected_members)
        else:
            attendees_str = ''

        meeting.title = form.title.data
        meeting.date_held = form.date_held.data
        meeting.agenda = form.agenda.data
        meeting.minutes = form.minutes.data
        meeting.attendees = attendees_str
        meeting.decisions = form.decisions.data

        db.session.commit()
        flash('Meeting record updated successfully', 'success')
        return redirect(url_for('meetings'))

    return render_template('announcements.html', form=form, meeting=meeting, action='Edit', show_meetings=True, group_members=group_members)

@app.route('/meetings/<int:meeting_id>/view')
@login_required
def view_meeting(meeting_id):
    """View single meeting record."""
    meeting = MeetingRecord.query.get_or_404(meeting_id)
    if not _can_access_record(meeting):
        flash('You do not have permission to access this meeting.', 'error')
        return redirect(url_for('meetings'))
    return render_template('announcements.html', meeting=meeting, action='View', show_meetings=True)

@app.route('/meetings/<int:meeting_id>/delete', methods=['POST'])
@login_required
def delete_meeting(meeting_id):
    """Delete meeting record with reason (Admin/Chairman only)."""
    if current_user.role not in ['Admin', 'Chairman']:
        flash('Only admins can delete meeting records', 'error')
        return redirect(url_for('meetings'))

    meeting = MeetingRecord.query.get_or_404(meeting_id)
    if not _can_access_record(meeting):
        flash('You do not have permission to access this meeting.', 'error')
        return redirect(url_for('meetings'))
    reason = request.form.get('reason', '').strip()

    if not reason:
        flash('Deletion reason is required', 'error')
        return redirect(url_for('meetings'))

    # Use the helper function
    delete_record_with_reason(meeting, 'meeting', reason, current_user.id)

    flash('Meeting record has been deleted successfully', 'success')
    return redirect(url_for('meetings'))

@app.route('/announcements/<int:announcement_id>/delete', methods=['POST'])
@login_required
def delete_announcement(announcement_id):
    """Delete announcement with reason (Admin/Chairman only)."""
    if current_user.role not in ['Admin', 'Chairman']:
        flash('Only admins and chairpersons can delete announcements', 'error')
        return redirect(url_for('announcements'))

    announcement = Announcement.query.get_or_404(announcement_id)
    if not _can_access_record(announcement):
        flash('You do not have permission to delete this announcement.', 'error')
        return redirect(url_for('announcements'))
    reason = request.form.get('reason', '').strip()

    if not reason:
        flash('Deletion reason is required', 'error')
        return redirect(url_for('announcements'))

    # Use the helper function
    delete_record_with_reason(announcement, 'announcement', reason, current_user.id)

    flash('Announcement has been deleted successfully', 'success')
    return redirect(url_for('announcements'))

@app.route('/fines/<int:fine_id>/delete', methods=['POST'])
@login_required
def delete_fine(fine_id):
    """Delete fine with reason (Admin/Chairman only)."""
    if current_user.role not in ['Admin', 'Chairman']:
        flash('Only admins and chairpersons can delete fines', 'error')
        return redirect(url_for('fines'))

    fine = Fine.query.get_or_404(fine_id)
    if not _can_access_record(fine):
        flash('You do not have permission to access this fine.', 'error')
        return redirect(url_for('fines'))
    reason = request.form.get('reason', '').strip()

    if not reason:
        flash('Deletion reason is required', 'error')
        return redirect(url_for('fines'))

    # Use the helper function
    delete_record_with_reason(fine, 'fine', reason, current_user.id)

    flash('Fine has been deleted successfully', 'success')
    return redirect(url_for('fines'))

@app.route('/fines/<int:fine_id>/pay', methods=['POST'])
@login_required
def pay_fine(fine_id):
    """Mark fine as paid (Admin/Chairman only)."""
    if current_user.role not in ['Admin', 'Chairman']:
        flash('Only admins and chairpersons can settle fines', 'error')
        return redirect(url_for('fines'))

    fine = Fine.query.get_or_404(fine_id)
    if not _can_access_record(fine):
        flash('You do not have permission to access this fine.', 'error')
        return redirect(url_for('fines'))
    
    if fine.is_paid:
        flash('Fine is already paid', 'warning')
        return redirect(url_for('fines'))
    
    notes = request.form.get('notes', '').strip()
    
    # Mark fine as paid
    fine.is_paid = True
    fine.date_paid = datetime.utcnow()
    fine.payment_notes = getattr(fine, 'payment_notes', '') or notes
    
    db.session.commit()
    
    # Log activity
    try:
        from activity_logger import log_activity
        log_activity('settled', 'fine', fine.id, 
                   f'Marked fine as paid for {fine.member.full_name}. Amount: {format_currency(fine.amount)}')
    except:
        pass
    
    flash(f'Fine of {format_currency(fine.amount)} for {fine.member.full_name} has been marked as paid', 'success')
    return redirect(url_for('fines'))

@app.route('/membership-applications/<int:app_id>/delete', methods=['POST'])
@login_required
def delete_membership_application(app_id):
    """Delete membership application with reason (Admin only)."""
    if current_user.role != 'Admin':
        flash('Only admins can delete membership applications', 'error')
        return redirect(url_for('membership_applications'))

    application = MembershipApplication.query.get_or_404(app_id)
    if not _can_access_record(application):
        flash('You do not have permission to access this application.', 'error')
        return redirect(url_for('membership_applications'))
    reason = request.form.get('reason', '').strip()

    if not reason:
        flash('Deletion reason is required', 'error')
        return redirect(url_for('membership_applications'))

    # Log activity before deletion
    try:
        from activity_logger import log_activity
        log_activity('deleted', 'membership_application', application.id, 
                   f'Deleted membership application for {application.full_name} - Reason: {reason}')
    except:
        pass

    db.session.delete(application)
    db.session.commit()

    flash('Membership application has been deleted successfully', 'success')
    return redirect(url_for('membership_applications'))

@app.route('/apply-membership', methods=['GET', 'POST'])
def apply_membership():
    """Membership application for non-members."""
    # Load available groups for the form
    groups = Group.query.filter_by(is_active=True).order_by(Group.name).all()
    form = MembershipApplicationForm()

    if form.validate_on_submit():
        # Check if email already exists as a user
        existing_user = User.query.filter_by(email=form.email.data).first()
        if existing_user:
            flash('This email is already registered. Please contact us if you need assistance.', 'error')
            return render_template('membership_application.html', form=form, groups=groups)

        # Check if application already exists for this email
        existing_app = MembershipApplication.query.filter_by(email=form.email.data, status='Pending').first()
        if existing_app:
            flash('An application with this email already exists and is pending review. Please wait.', 'error')
            return render_template('membership_application.html', form=form, groups=groups)

        # Determine which group this application is for
        target_group_id = None
        group_code = form.group_code.data.strip() if hasattr(form, 'group_code') and form.group_code.data else None
        if group_code:
            grp = Group.query.filter_by(registration_code=group_code, is_active=True).first()
            if grp:
                target_group_id = grp.id
            else:
                flash('Invalid group registration code. Please check and try again.', 'error')
                return render_template('membership_application.html', form=form, groups=groups)
        else:
            # Default to first group if only one exists
            if len(groups) == 1:
                target_group_id = groups[0].id

        # Handle ID document upload
        id_document_filename = None
        if hasattr(form, 'id_document') and form.id_document.data and form.id_document.data.filename:
            id_file = form.id_document.data
            try:
                from werkzeug.utils import secure_filename as wz_secure_filename
                filename = wz_secure_filename(id_file.filename)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_")
                id_document_filename = f"id_doc_{timestamp}{filename}"
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                id_file.save(os.path.join(app.config['UPLOAD_FOLDER'], id_document_filename))
            except Exception as e:
                app.logger.error(f'ID document upload error: {e}')

        application = MembershipApplication(
            full_name=form.full_name.data,
            email=form.email.data,
            phone=form.phone.data,
            id_number=form.id_number.data,
            location=form.location.data,
            occupation=form.occupation.data,
            reason_for_joining=form.reason_for_joining.data,
            id_document=id_document_filename,
            group_id=target_group_id
        )

        db.session.add(application)
        db.session.commit()

        # Notify officials of this group (or all officials if no group).
        # CONNECT super admins must also see applications submitted to a
        # specific group so they can oversee every group from one account.
        query = User.query.filter(
            User.role.in_(['Admin', 'Chairman', 'Secretary']),
            User.is_active == True
        )
        if target_group_id:
            query = query.filter(User.group_id == target_group_id)
        notification_users = query.all()

        super_admins = User.query.filter_by(
            is_super_admin=True, is_active=True
        ).all()
        notification_users_by_id = {user.id: user for user in notification_users}
        notification_users_by_id.update({user.id: user for user in super_admins})

        for user in notification_users_by_id.values():
            notification = Notification(
                user_id=user.id,
                title='New Membership Application',
                message=f'{form.full_name.data} has applied for membership. ID: {form.id_number.data}. Phone: {form.phone.data}.',
                notification_type='membership_application',
                link_url='/membership-applications'
            )
            db.session.add(notification)
        db.session.commit()

        flash('Your membership application has been submitted successfully! We will review it and get back to you soon.', 'success')
        return redirect(url_for('index'))

    return render_template('membership_application.html', form=form, groups=groups)

@app.route('/membership-applications')
@login_required
def membership_applications():
    """View membership applications (Admin/Chairman only)."""
    if current_user.role not in ['Admin', 'Chairman']:
        flash('You do not have permission to view membership applications', 'error')
        return redirect(url_for('dashboard'))

    application_query = MembershipApplication.query
    if not current_user.is_super_admin:
        application_query = application_query.filter(
            MembershipApplication.group_id == current_user.group_id
        )
    applications = application_query.order_by(
        MembershipApplication.application_date.desc()
    ).all()
    return render_template('membership_applications.html', applications=applications)

@app.route('/membership-applications/<int:app_id>/review', methods=['POST'])
@login_required
def review_membership_application(app_id):
    """Review membership application (Admin/Chairman only)."""
    if current_user.role not in ['Admin', 'Chairman']:
        flash('You do not have permission to review membership applications', 'error')
        return redirect(url_for('dashboard'))

    try:
        application = MembershipApplication.query.get_or_404(app_id)
        if not _can_access_record(application):
            flash('You do not have permission to review this application.', 'error')
            return redirect(url_for('membership_applications'))
        action = request.form.get('action')

        if application.status in ('Approved', 'Rejected'):
            flash(f'This application was already {application.status.lower()}.', 'info')
            return redirect(url_for('membership_applications'))

        if action == 'approve':
            # Determine which group to add the member to
            target_group_id = application.group_id or current_user.group_id
            if not target_group_id:
                flash('This application is not assigned to a group and cannot be approved.', 'error')
                return redirect(url_for('membership_applications'))

            existing = User.query.filter(db.func.lower(User.email) == (application.email or '').strip().lower()).first()
            if existing:
                flash('This email already belongs to an existing member, so nothing was created. Check the members list, or reject this duplicate application.', 'error')
                return redirect(url_for('membership_applications'))

            # Check if username already exists - use full name based username
            base_username = application.full_name.upper().replace(' ', '_')[:30]
            username = base_username
            counter = 1
            while User.query.filter_by(username=username).first():
                username = f"{base_username}_{counter}"
                counter += 1

            temporary_password = secrets.token_urlsafe(32)
            new_user = User(
                username=username,
                full_name=application.full_name,
                email=application.email,
                phone=application.phone,
                role='Member',
                password_hash=generate_password_hash(temporary_password),
                is_active=True,
                two_factor_enabled=False,
                group_id=target_group_id
            )

            db.session.add(new_user)
            application.status = 'Approved'
            application.reviewed_by = current_user.id
            application.review_date = datetime.utcnow()
            application.review_notes = request.form.get('review_notes', '')
            db.session.commit()

            # Notify all relevant officials
            try:
                group_name = new_user.group.name if new_user.group else 'the group'
                notify_q = User.query.filter(
                    User.role.in_(['Admin', 'Chairman', 'Secretary', 'Treasurer']),
                    User.is_active == True,
                    User.group_id == target_group_id
                )
                for u in notify_q.all():
                    if u.id != current_user.id:
                        db.session.add(Notification(
                            user_id=u.id,
                            title='New Member Approved',
                            message=f'{application.full_name} has been approved as a member by {current_user.full_name}.',
                            notification_type='member_approved',
                            link_url='/members'
                        ))
                db.session.commit()
            except Exception:
                pass

            try:
                from activity_logger import log_activity
                log_activity('approved', 'membership_application', application.id,
                           f'Approved membership for {application.full_name} → username: {username}')
            except Exception:
                pass

            flash(
                f'{application.full_name} was approved and added as a member. '
                f'Username: {username}. Ask them to use the password-reset link on their group login page.',
                'success'
            )

        elif action == 'reject':
            rejection_reason = request.form.get('rejection_reason', '').strip()
            application.status = 'Rejected'
            application.reviewed_by = current_user.id
            application.review_date = datetime.utcnow()
            application.review_notes = rejection_reason
            application.rejection_reason = rejection_reason
            db.session.commit()

            # Notify other officials
            try:
                target_group_id = application.group_id or current_user.group_id
                notify_q = User.query.filter(
                    User.role.in_(['Admin', 'Chairman', 'Secretary']),
                    User.is_active == True,
                    User.group_id == target_group_id
                )
                for u in notify_q.all():
                    if u.id != current_user.id:
                        db.session.add(Notification(
                            user_id=u.id,
                            title='Membership Application Rejected',
                            message=f'{application.full_name}\'s membership application was rejected by {current_user.full_name}. Reason: {rejection_reason or "Not specified"}',
                            notification_type='member_rejected',
                            link_url='/membership-applications'
                        ))
                db.session.commit()
            except Exception:
                pass

            try:
                from activity_logger import log_activity
                log_activity('rejected', 'membership_application', application.id,
                           f'Rejected membership for {application.full_name}. Reason: {rejection_reason}')
            except Exception:
                pass

            flash(f'❌ Membership application for {application.full_name} has been rejected.', 'info')

        return redirect(url_for('membership_applications'))

    except Exception as e:
        db.session.rollback()
        app.logger.exception('Error processing application')
        flash('Something went wrong processing this application. Please try again.', 'error')
        return redirect(url_for('membership_applications'))

# ─── PWA / Offline ───────────────────────────────────────────────────────────

@app.route('/sw.js')
def service_worker():
    """Serve service worker from root scope so it can intercept all pages."""
    import os
    sw_path = os.path.join(app.root_path, 'static', 'sw.js')
    with open(sw_path, 'r') as f:
        content = f.read()
    response = app.response_class(content, mimetype='application/javascript')
    response.headers['Service-Worker-Allowed'] = '/'
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response

@app.route('/offline')
def offline():
    return render_template('offline.html')

# ─── Error handlers ─────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

# ─── Group Filtering Helpers ─────────────────────────────────────────────────

def get_group_filter_users():
    """Return a query base filtering users to current user's group (or all for super admin)."""
    if current_user.is_super_admin:
        return User.query.filter_by(is_active=True)
    if current_user.group_id:
        return User.query.filter_by(is_active=True, group_id=current_user.group_id)
    return User.query.filter_by(is_active=True)

def get_group_member_ids():
    """Return list of member IDs in current user's group."""
    users = get_group_filter_users().all()
    return [u.id for u in users]

# ─── Group Management Routes ─────────────────────────────────────────────────

@app.route('/groups')
@login_required
def groups():
    """Group management - super admin only sees all groups, group admin sees own."""
    if current_user.is_super_admin:
        all_groups = Group.query.order_by(Group.created_at.desc()).all()
        group_stats = []
        for g in all_groups:
            members = User.query.filter_by(group_id=g.id, is_active=True).count()
            contributions = db.session.query(db.func.sum(Contribution.amount)).join(
                User, Contribution.member_id == User.id
            ).filter(User.group_id == g.id, Contribution.is_deleted == False).scalar() or 0
            active_loans = db.session.query(db.func.sum(Loan.remaining_amount)).join(
                User, Loan.member_id == User.id
            ).filter(User.group_id == g.id, Loan.status == 'Active').scalar() or 0
            group_stats.append({
                'group': g,
                'members': members,
                'contributions': contributions,
                'active_loans': active_loans
            })
        return render_template('groups.html', group_stats=group_stats, is_super_admin=True)
    elif current_user.role == 'Admin' and current_user.group_id:
        grp = Group.query.get(current_user.group_id)
        return render_template('groups.html', group=grp, is_super_admin=False)
    else:
        flash('You do not have permission to view this page.', 'error')
        return redirect(url_for('dashboard'))


@app.route('/super-admin')
@login_required
def super_admin_dashboard():
    """Platform overview backed only by records currently stored in CONNECT."""
    if not current_user.is_super_admin:
        flash('Permission denied.', 'error')
        return redirect(url_for('dashboard'))

    search = (request.args.get('q') or '').strip()
    group_query = Group.query
    if search:
        pattern = f'%{search}%'
        group_query = group_query.filter(
            db.or_(Group.name.ilike(pattern), Group.location.ilike(pattern))
        )
    directory_groups = group_query.order_by(Group.name.asc()).limit(100).all()

    total_groups = Group.query.count()
    active_groups = Group.query.filter_by(is_active=True).count()
    suspended_groups = Group.query.filter_by(is_active=False).count()
    total_users = User.query.filter(User.is_super_admin.is_(False)).count()
    active_users = User.query.filter(
        User.is_super_admin.is_(False), User.is_active.is_(True)
    ).count()
    pending_applications = MembershipApplication.query.filter_by(status='Pending').count()
    pending_loans = Loan.query.filter_by(status='Pending', is_deleted=False).count()
    recent_audit = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(12).all()

    return render_template(
        'super_admin_dashboard.html',
        search=search,
        groups=directory_groups,
        total_groups=total_groups,
        active_groups=active_groups,
        suspended_groups=suspended_groups,
        total_users=total_users,
        active_users=active_users,
        pending_applications=pending_applications,
        pending_loans=pending_loans,
        recent_audit=recent_audit,
    )


@app.route('/groups/register', methods=['GET', 'POST'])
def register_group():
    """Register a new group — publicly accessible (any group can self-register)."""

    form = GroupRegistrationForm()
    if form.validate_on_submit():
        try:
            # Handle logo upload
            logo_filename = None
            if form.logo.data and form.logo.data.filename:
                from werkzeug.utils import secure_filename as wz_secure
                logo_fn = wz_secure(form.logo.data.filename)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S_")
                logo_filename = f"group_logo_{ts}{logo_fn}"
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                form.logo.data.save(os.path.join(app.config['UPLOAD_FOLDER'], logo_filename))

            # Create the group
            new_group = Group(
                name=form.name.data,
                description=form.description.data,
                contact_email=form.contact_email.data,
                contact_phone=form.contact_phone.data,
                location=form.location.data,
                year_established=form.year_established.data or str(datetime.now().year),
                logo=logo_filename,
            )
            db.session.add(new_group)
            db.session.flush()

            # Check admin email uniqueness
            existing = User.query.filter_by(email=form.admin_email.data).first()
            if existing:
                flash(f'Email {form.admin_email.data} already in use.', 'error')
                db.session.rollback()
                return render_template('groups.html', form=form, action='Register')

            # Create group admin
            base_uname = form.admin_full_name.data.upper().replace(' ', '_')[:30]
            uname = base_uname
            c = 1
            while User.query.filter_by(username=uname).first():
                uname = f"{base_uname}_{c}"
                c += 1

            group_admin = User(
                username=uname,
                full_name=form.admin_full_name.data,
                email=form.admin_email.data,
                phone=form.admin_phone.data,
                role='Admin',
                password_hash=generate_password_hash(form.admin_password.data),
                is_active=True,
                group_id=new_group.id
            )
            db.session.add(group_admin)
            db.session.commit()

            flash(f'Group "{new_group.name}" registered! Your admin username is <strong>{uname}</strong>. Registration code: <code>{new_group.registration_code}</code>. Please save these details.', 'success')
            if current_user.is_authenticated and current_user.is_super_admin:
                return redirect(url_for('groups'))
            else:
                # Redirect to group login page so the new admin can immediately log in
                return redirect(url_for('login') + f'?group={new_group.id}')
        except Exception as e:
            db.session.rollback()
            flash(f'Error registering group: {str(e)}', 'error')

    return render_template('groups.html', form=form, action='Register')

@app.route('/groups/<int:group_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_group(group_id):
    """Edit group details."""
    grp = Group.query.get_or_404(group_id)
    if not current_user.is_super_admin and current_user.group_id != group_id:
        flash('You do not have permission to edit this group.', 'error')
        return redirect(url_for('dashboard'))

    form = GroupEditForm(obj=grp)
    if form.validate_on_submit():
        grp.name = form.name.data
        grp.description = form.description.data
        grp.contact_email = form.contact_email.data
        grp.contact_phone = form.contact_phone.data
        grp.location = form.location.data
        grp.year_established = form.year_established.data

        if form.logo.data and form.logo.data.filename:
            from werkzeug.utils import secure_filename as wz_secure
            logo_fn = wz_secure(form.logo.data.filename)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_")
            logo_filename = f"group_logo_{ts}{logo_fn}"
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            form.logo.data.save(os.path.join(app.config['UPLOAD_FOLDER'], logo_filename))
            grp.logo = logo_filename

        db.session.commit()
        flash('Group details updated successfully.', 'success')
        return redirect(url_for('groups'))

    return render_template('groups.html', form=form, group=grp, action='Edit')

@app.route('/groups/<int:group_id>/toggle', methods=['POST'])
@login_required
def toggle_group(group_id):
    """Activate/deactivate a group - super admin only."""
    if not current_user.is_super_admin:
        flash('Permission denied.', 'error')
        return redirect(url_for('groups'))
    grp = Group.query.get_or_404(group_id)
    reason = (request.form.get('reason') or '').strip()
    if len(reason) < 5:
        flash('Enter a reason of at least five characters for this access change.', 'error')
        return redirect(url_for('super_admin_dashboard'))
    grp.is_active = not grp.is_active
    db.session.commit()
    status = 'activated' if grp.is_active else 'deactivated'
    try:
        from activity_logger import log_activity
        log_activity(
            status, 'group', grp.id,
            f'Group "{grp.name}" was {status}. Reason: {reason}',
            group_id=grp.id,
        )
    except Exception:
        pass
    flash(f'Group "{grp.name}" has been {status}.', 'success')
    return redirect(url_for('super_admin_dashboard'))

# ─── Messaging Routes ─────────────────────────────────────────────────────────

@app.route('/messages')
@login_required
def messages():
    """In-app message inbox."""
    inbox = InAppMessage.query.filter_by(recipient_id=current_user.id).order_by(InAppMessage.created_at.desc()).all()
    sent = InAppMessage.query.filter_by(sender_id=current_user.id).order_by(InAppMessage.created_at.desc()).all()
    unread_count = InAppMessage.query.filter_by(recipient_id=current_user.id, is_read=False).count()
    return render_template('messages.html', inbox=inbox, sent=sent, unread_count=unread_count)

@app.route('/messages/compose', methods=['GET', 'POST'])
@login_required
def compose_message():
    """Compose and send a message."""
    # Determine who can send messages (admin/chairman/treasurer/secretary or anyone)
    can_send_to_all = current_user.role in ['Admin', 'Chairman', 'Treasurer', 'Secretary'] or current_user.is_super_admin

    form = InAppMessageForm()

    # Populate recipient choices based on role
    if current_user.is_super_admin:
        recipients = User.query.filter(User.is_active == True, User.id != current_user.id).all()
    elif current_user.group_id:
        recipients = User.query.filter(
            User.is_active == True,
            User.id != current_user.id,
            User.group_id == current_user.group_id
        ).all()
    else:
        recipients = []

    form.recipient_id.choices = [(str(u.id), f'{u.full_name} ({u.role})') for u in recipients]

    # Pre-populate recipient from query param
    recipient_id = request.args.get('to')
    if recipient_id and request.method == 'GET':
        form.recipient_id.data = recipient_id

    if form.validate_on_submit():
        try:
            recipient = User.query.get(int(form.recipient_id.data))
            if not recipient:
                flash('Recipient not found.', 'error')
                return render_template('messages.html', form=form, action='Compose')

            msg = InAppMessage(
                sender_id=current_user.id,
                recipient_id=recipient.id,
                subject=form.subject.data,
                body=form.body.data,
                message_type=form.message_type.data,
                group_id=current_user.group_id
            )
            db.session.add(msg)

            # Create a notification for the recipient
            notif = Notification(
                user_id=recipient.id,
                title=f'New Message from {current_user.full_name}',
                message=f'Subject: {form.subject.data}',
                notification_type='message',
                link_url='/messages'
            )
            db.session.add(notif)
            db.session.commit()

            flash(f'Message sent to {recipient.full_name} successfully.', 'success')
            return redirect(url_for('messages'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error sending message: {str(e)}', 'error')

    return render_template('messages.html', form=form, action='Compose')

@app.route('/messages/<int:msg_id>')
@login_required
def view_message(msg_id):
    """View a message and mark it read."""
    msg = InAppMessage.query.get_or_404(msg_id)
    if msg.recipient_id != current_user.id and msg.sender_id != current_user.id:
        flash('You do not have permission to view this message.', 'error')
        return redirect(url_for('messages'))
    if msg.recipient_id == current_user.id and not msg.is_read:
        msg.is_read = True
        db.session.commit()
    return render_template('messages.html', message=msg, action='View')

@app.route('/messages/<int:msg_id>/delete', methods=['POST'])
@login_required
def delete_message(msg_id):
    """Delete a message."""
    msg = InAppMessage.query.get_or_404(msg_id)
    if msg.recipient_id != current_user.id and msg.sender_id != current_user.id:
        flash('Permission denied.', 'error')
        return redirect(url_for('messages'))
    db.session.delete(msg)
    db.session.commit()
    flash('Message deleted.', 'success')
    return redirect(url_for('messages'))


@app.route('/messages/mark-all-read', methods=['POST'])
@login_required
def mark_all_messages_read():
    """Mark all inbox messages as read."""
    InAppMessage.query.filter_by(recipient_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify({'success': True, 'message': 'All messages marked as read'})

# ─── Notifications Routes ─────────────────────────────────────────────────────

@app.route('/notifications')
@login_required
def notifications():
    """View all notifications."""
    all_notifs = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(50).all()
    # Mark all as read
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return render_template('notifications.html', notifications=all_notifs)

@app.route('/api/notifications')
@login_required
def api_notifications():
    """API endpoint to get unread notifications count and recent list."""
    unread = Notification.query.filter_by(user_id=current_user.id, is_read=False).order_by(Notification.created_at.desc()).limit(10).all()
    unread_msgs = InAppMessage.query.filter_by(recipient_id=current_user.id, is_read=False).count()
    return jsonify({
        'count': len(unread),
        'messages_count': unread_msgs,
        'notifications': [{
            'id': n.id,
            'title': n.title,
            'message': n.message[:80] + '...' if len(n.message) > 80 else n.message,
            'type': n.notification_type,
            'created_at': n.created_at.strftime('%d/%m/%y %H:%M'),
            'link_url': n.link_url or '#',
            'transaction_reference': n.transaction_reference,
            'payment_method': n.payment_method
        } for n in unread]
    })

@app.route('/api/notifications/mark-read', methods=['POST'])
@login_required
def mark_notifications_read():
    """Mark notifications as read."""
    payload = request.get_json(silent=True) or {}
    notif_ids = payload.get('ids', [])
    if notif_ids:
        Notification.query.filter(
            Notification.id.in_(notif_ids),
            Notification.user_id == current_user.id
        ).update({'is_read': True}, synchronize_session=False)
    else:
        Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    if not request.is_json:
        return redirect(url_for('notifications'))
    return jsonify({'success': True})

# ─── Projects Routes ─────────────────────────────────────────────────────────

@app.route('/projects')
@login_required
def projects():
    """Group projects and activities."""
    if current_user.group_id:
        group_projects = Project.query.filter_by(group_id=current_user.group_id).order_by(Project.created_date.desc()).all()
    elif current_user.is_super_admin:
        group_projects = Project.query.order_by(Project.created_date.desc()).all()
    else:
        group_projects = []
    return render_template('projects.html', projects=group_projects)

@app.route('/projects/add', methods=['GET', 'POST'])
@login_required
def add_project():
    """Add a new group project."""
    if current_user.role not in ['Admin', 'Chairman', 'Secretary'] and not current_user.is_super_admin:
        flash('You do not have permission to add projects.', 'error')
        return redirect(url_for('projects'))

    form = ProjectForm()
    if current_user.is_super_admin and not get_active_group_id():
        flash('Select a group before adding a project.', 'warning')
        return redirect(url_for('groups'))

    if form.validate_on_submit():
        project = Project(
            name=form.name.data,
            description=form.description.data,
            status=form.status.data,
            budget=form.budget.data or 0.0,
            start_date=form.start_date.data,
            end_date=form.end_date.data,
            created_by=current_user.id,
            group_id=get_active_group_id()
        )
        db.session.add(project)

        # Notify group members
        try:
            grp_users = get_group_filter_users().filter(User.id != current_user.id).all()
            for u in grp_users:
                db.session.add(Notification(
                    user_id=u.id,
                    title='New Group Activity/Project',
                    message=f'A new project "{form.name.data}" has been added by {current_user.full_name}. Status: {form.status.data}',
                    notification_type='project',
                    link_url='/projects'
                ))
        except Exception:
            pass

        db.session.commit()
        flash(f'Project "{form.name.data}" added successfully.', 'success')
        return redirect(url_for('projects'))

    return render_template('projects.html', form=form, action='Add')

@app.route('/projects/<int:project_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_project(project_id):
    """Edit a project."""
    project = Project.query.get_or_404(project_id)
    if current_user.role not in ['Admin', 'Chairman', 'Secretary'] and not current_user.is_super_admin:
        flash('You do not have permission to edit projects.', 'error')
        return redirect(url_for('projects'))
    if not _can_access_record(project):
        flash('You do not have permission to edit this project.', 'error')
        return redirect(url_for('projects'))

    form = ProjectForm(obj=project)
    if form.validate_on_submit():
        project.name = form.name.data
        project.description = form.description.data
        project.status = form.status.data
        project.budget = form.budget.data or 0.0
        project.start_date = form.start_date.data
        project.end_date = form.end_date.data
        db.session.commit()
        flash('Project updated successfully.', 'success')
        return redirect(url_for('projects'))

    return render_template('projects.html', form=form, project=project, action='Edit')

# ─── Add member with group assignment ────────────────────────────────────────

@app.route('/members/add-to-group', methods=['GET', 'POST'])
@login_required
def add_member_to_group():
    """Add a new member directly (Admin only) with group assignment."""
    if current_user.role != 'Admin' and not current_user.is_super_admin:
        flash('Only admins can add new members', 'error')
        return redirect(url_for('members'))
    return redirect(url_for('add_member'))



@app.route('/groups/<int:group_id>/delete', methods=['POST'])
@login_required
def delete_group(group_id):
    """Legacy endpoint intentionally disabled to preserve group and financial history."""
    if not current_user.is_super_admin:
        flash('Permission denied.', 'error')
        return redirect(url_for('groups'))
    flash('Permanent group deletion is disabled. Suspend or restore access instead.', 'warning')
    return redirect(url_for('super_admin_dashboard'))

    # Legacy deletion implementation retained below only as migration context;
    # the early return above prevents it from running.
    import json
    from flask import Response
    from sqlalchemy import select, delete as sa_delete, or_
    from datetime import datetime

    if not current_user.is_super_admin:
        flash('Permission denied.', 'error')
        return redirect(url_for('groups'))
    grp = Group.query.get_or_404(group_id)
    if grp.is_active:
        flash('Deactivate the group first, then delete it.', 'error')
        return redirect(url_for('groups'))
    if request.form.get('confirm_name', '').strip() != grp.name:
        flash('The group name you typed does not match. Nothing was deleted.', 'error')
        return redirect(url_for('groups'))
    if User.query.filter_by(group_id=grp.id, is_super_admin=True).count():
        flash('A platform administrator account belongs to this group. Move it to another group first.', 'error')
        return redirect(url_for('groups'))

    def single_pk(t):
        cols = list(t.primary_key.columns)
        return cols[0] if len(cols) == 1 else None

    try:
        gname = Group.__table__.name
        ids = {gname: {grp.id}}
        skipped = []
        changed = True
        while changed:
            changed = False
            for t in db.metadata.sorted_tables:
                if t.name == gname:
                    continue
                pk = single_pk(t)
                conds = []
                if 'group_id' in t.c:
                    conds.append(t.c.group_id == grp.id)
                else:
                    for fk in t.foreign_keys:
                        parent = fk.column.table
                        if parent is t or parent.name not in ids:
                            continue
                        if single_pk(parent) is not fk.column:
                            continue
                        conds.append(fk.parent.in_(list(ids[parent.name])))
                if not conds:
                    continue
                if pk is None:
                    if t.name not in skipped:
                        skipped.append(t.name)
                    continue
                found = {r[0] for r in db.session.execute(select(pk).where(or_(*conds)))}
                known = ids.setdefault(t.name, set())
                if not found <= known:
                    known |= found
                    changed = True
        if skipped:
            flash('Not deleted. These tables have no simple id: ' + ', '.join(skipped), 'error')
            return redirect(url_for('groups'))

        counts = {n: len(v) for n, v in ids.items() if v}
        if request.form.get('dry_run'):
            flash('Preview, would delete: ' + ', '.join(f'{n}: {c}' for n, c in sorted(counts.items())), 'info')
            return redirect(url_for('groups'))

        by_name = {t.name: t for t in db.metadata.sorted_tables}
        backup = {'group': grp.name, 'group_id': grp.id,
                  'deleted_at': datetime.utcnow().isoformat(),
                  'deleted_by': current_user.full_name, 'tables': {}}
        for n, v in ids.items():
            if not v:
                continue
            t = by_name[n]
            rows = db.session.execute(select(t).where(single_pk(t).in_(list(v)))).all()
            backup['tables'][n] = [{k: val for k, val in r._mapping.items() if k != 'password_hash'} for r in rows]
        payload = json.dumps(backup, default=str, indent=1)

        for t in reversed(db.metadata.sorted_tables):
            if ids.get(t.name):
                db.session.execute(sa_delete(t).where(single_pk(t).in_(list(ids[t.name]))))
        db.session.commit()

        from activity_logger import log_activity
        log_activity('deleted', 'group', group_id,
                     f'Deleted group "{backup["group"]}" ({sum(counts.values())} records)', group_id=None)
        return Response(payload, mimetype='application/json',
                        headers={'Content-Disposition': f'attachment; filename=group-{group_id}-backup.json'})
    except Exception:
        db.session.rollback()
        app.logger.exception('Group delete failed')
        flash('The group could not be deleted, so nothing was removed.', 'error')
        return redirect(url_for('groups'))


@app.route('/admin/activity-log')
@login_required
def admin_activity_log():
    if not current_user.is_super_admin and current_user.role != 'Admin':
        flash('Permission denied.', 'error')
        return redirect(url_for('dashboard'))
    from models import ActivityLog
    q = ActivityLog.query
    if current_user.is_super_admin:
        gid = request.args.get('group_id', type=int)
        if gid:
            q = q.filter(ActivityLog.group_id == gid)
    else:
        gid = current_user.group_id
        q = q.filter(ActivityLog.group_id == gid)
    rows = q.order_by(ActivityLog.id.desc()).limit(200).all()
    uids = list({r.user_id for r in rows if r.user_id})
    users = {u.id: u.full_name for u in User.query.filter(User.id.in_(uids)).all()} if uids else {}
    groups_list = Group.query.order_by(Group.name).all()
    if not current_user.is_super_admin:
        groups_list = [group for group in groups_list if group.id == current_user.group_id]
    gnames = {g.id: g.name for g in groups_list}
    return render_template('activity_log.html', rows=rows, users=users,
                           gnames=gnames, groups=groups_list, selected=gid)
