import os
import json
from datetime import datetime, timedelta
from flask import render_template, request, redirect, url_for, flash, jsonify, send_file, make_response
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from app import app, db
from models import User, Contribution, Loan, LoanRepayment, Fine, Announcement, MeetingRecord, Document, Project, Notification, MembershipApplication, OfflineData, MemberPoints, UserBadge, Badge, Vote, VotingProposal, Payment, DigitalReceipt, WelfareContribution, WelfareExpense
from forms import *
from utils import *
from utils import format_date, format_datetime

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

def create_payment_notification(payment_type, member_name, amount):
    """Create notification for payments."""
    notification_users = User.query.filter(User.role.in_(['Admin', 'Treasurer', 'Secretary', 'Chairman']), User.is_active == True).all()

    for user in notification_users:
        notification = Notification(
            user_id=user.id,
            title=f'New {payment_type} Payment',
            message=f'{member_name} has made a {payment_type.lower()} payment of {format_currency(amount)}',
            notification_type='payment_recorded'
        )
        db.session.add(notification)
    db.session.commit()

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

# Make utility functions available in templates
@app.context_processor
def utility_processor():
    return dict(has_permission=has_permission, format_currency=format_currency, format_date=format_date, format_datetime=format_datetime, datetime=datetime)

@app.route('/')
def index():
    """Public landing page."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    # Get basic group info for public view
    try:
        total_contributions = db.session.query(db.func.sum(Contribution.amount)).scalar() or 0
    except:
        total_contributions = 0

    stats = {
        'total_members': User.query.filter_by(is_active=True).count(),
        'group_established': '2023',
        'total_contributions': total_contributions
    }

    return render_template('index.html', stats=stats)

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page with username dropdown."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    form = LoginForm()

    # Populate username choices
    active_users = User.query.filter_by(is_active=True).all()
    form.username.choices = [(user.username, user.username) for user in active_users]

    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data, is_active=True).first()

        if user and check_password_hash(user.password_hash, form.password.data):
            # 2FA temporarily disabled - to be implemented in future
            # if user.two_factor_enabled:
            #     return redirect(url_for('verify_2fa', user_id=user.id, next_url=request.args.get('next')))
            
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'error')

    return render_template('login.html', form=form)

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
    logout_user()
    flash('You have been logged out successfully', 'success')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard - role-based content."""
    stats = get_group_statistics()

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

    # Recent announcements
    recent_announcements = Announcement.query.order_by(Announcement.date_created.desc()).limit(3).all()

    # Pending loan applications (for Treasurer/Admin)
    pending_loans = []
    if has_permission(current_user, 'approve_loans'):
        pending_loans = Loan.query.filter_by(status='Pending').order_by(Loan.application_date.desc()).all()

    # Active proposals for voting
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

    all_members = User.query.filter_by(is_active=True).all()
    return render_template('members.html', members=all_members)

@app.route('/members/add', methods=['GET', 'POST'])
@login_required
def add_member():
    """Add new member (Admin only)."""
    if current_user.role != 'Admin':
        flash('Only admins can add new members', 'error')
        return redirect(url_for('members'))

    form = MemberForm()

    if form.validate_on_submit():
        # Check if username already exists
        existing_user = User.query.filter_by(username=form.username.data).first()
        if existing_user:
            flash('Username already exists', 'error')
            return render_template('members.html', form=form, action='Add')

        # Check if email already exists
        existing_email = User.query.filter_by(email=form.email.data).first()
        if existing_email:
            flash('Email already exists', 'error')
            return render_template('members.html', form=form, action='Add')

        new_member = User(
            username=form.username.data,
            full_name=form.full_name.data,
            email=form.email.data,
            phone=form.phone.data,
            role=form.role.data,
            password_hash=generate_password_hash(form.password.data),
            is_active=True
        )

        db.session.add(new_member)
        db.session.commit()

        flash(f'Member {form.full_name.data} has been added successfully', 'success')
        return redirect(url_for('members'))

    return render_template('members.html', form=form, action='Add')

@app.route('/members/<int:member_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_member(member_id):
    """Edit member details (Admin only)."""
    if current_user.role != 'Admin':
        flash('Only admins can edit member details', 'error')
        return redirect(url_for('members'))

    member = User.query.get_or_404(member_id)
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

@app.route('/members/<int:member_id>/deactivate')
@login_required
def deactivate_member(member_id):
    """Deactivate member (Admin only)."""
    if current_user.role != 'Admin':
        flash('Only admins can deactivate members', 'error')
        return redirect(url_for('members'))

    member = User.query.get_or_404(member_id)
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
        # Treasurer/Admin see all contributions (excluding deleted ones)
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

    # Populate member choices
    active_members = User.query.filter_by(is_active=True).all()
    form.member_id.choices = [(member.id, member.full_name) for member in active_members]

    if form.validate_on_submit():
        contribution = Contribution(
            member_id=form.member_id.data,
            amount=form.amount.data,
            contribution_type=form.contribution_type.data,
            notes=form.notes.data,
            recorded_by=current_user.id
        )

        db.session.add(contribution)
        db.session.commit()

        member = User.query.get(form.member_id.data)

        # Create notification for payment recording
        try:
            create_payment_notification('Contribution', member.full_name, form.amount.data)
        except:
            pass  # Continue even if notification fails

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
                generated_at=datetime.utcnow()
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
        # Admin View: Applied, Existing, Expired Loans
        applied_loans = Loan.query.filter_by(status='Pending', is_deleted=False).order_by(Loan.application_date.desc()).all()
        existing_loans = Loan.query.filter_by(status='Active', is_deleted=False).order_by(Loan.approval_date.desc()).all()
        expired_loans = Loan.query.filter_by(status='Expired', is_deleted=False).order_by(Loan.due_date.desc()).all()
        
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
    active_members = User.query.filter_by(is_active=True).all()
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

            db.session.commit()

            # Log activity
            try:
                from activity_logger import log_activity
                status_text = 'approved' if form.status.data == 'Active' else 'rejected'
                borrower_name = loan.borrower_name if loan.loan_type == 'External' else loan.member.full_name
                log_activity(status_text, 'loan', loan.id, f'{status_text.title()} loan for {borrower_name} - Amount: {format_currency(loan.amount)}')
            except:
                pass  # Continue even if logging fails

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
    reason = request.form.get('reason', '').strip()

    if not reason:
        flash('Deletion reason is required', 'error')
        return redirect(url_for('contributions'))

    # Use the helper function
    delete_record_with_reason(contribution, 'contribution', reason, current_user.id)

    flash('Contribution has been deleted successfully', 'success')
    return redirect(url_for('contributions'))

@app.route('/admin/activity-log')
@login_required
def activity_log():
    """View system activity log (Admin only)."""
    if current_user.role != 'Admin':
        flash('You do not have permission to view activity logs', 'error')
        return redirect(url_for('dashboard'))

    from activity_logger import get_recent_activities
    activities = get_recent_activities(100)
    return render_template('activity_log.html', activities=activities)

@app.route('/admin/clear-activity-log', methods=['POST'])
@login_required
def clear_activity_log():
    """Clear activity log (Admin only)."""
    if current_user.role != 'Admin':
        flash('You do not have permission to clear activity logs', 'error')
        return redirect(url_for('dashboard'))

    from activity_logger import clear_activity_log
    if clear_activity_log():
        flash('Activity log cleared successfully', 'success')
    else:
        flash('Failed to clear activity log', 'error')
    
    return redirect(url_for('activity_log'))

@app.route('/loans/repayment', methods=['GET', 'POST'])
@login_required
def loan_repayment():
    """Record loan repayment (Treasurer/Admin only)."""
    if not has_permission(current_user, 'manage_finances'):
        flash('You do not have permission to record loan repayments', 'error')
        return redirect(url_for('loans'))

    form = LoanRepaymentForm()

    # Populate active loan choices
    active_loans = Loan.query.filter_by(status='Active', is_deleted=False).all()
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
            loan = Loan.query.get(form.loan_id.data)
            if not loan:
                flash('Loan not found', 'error')
                return render_template('loans.html', form=form, action='Repayment', loans=[], is_member_view=False)

            repayment_amount = form.amount.data

            if repayment_amount > loan.remaining_amount:
                flash('Repayment amount cannot exceed remaining loan balance', 'error')
                return render_template('loans.html', form=form, action='Repayment', loans=[], is_member_view=False)

            # Record repayment
            repayment = LoanRepayment(
                loan_id=loan.id,
                amount=repayment_amount,
                recorded_by=current_user.id
            )

            # Update loan balance
            loan.remaining_amount -= repayment_amount

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
                        generated_at=datetime.utcnow()
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

        # Populate member choices
        active_members = User.query.filter_by(is_active=True).all()
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

        all_fines = Fine.query.filter_by(is_deleted=False).order_by(Fine.date_issued.desc()).all()
        return render_template('contributions.html', fines=all_fines, form=form, is_member_view=False, show_fines=True)
    else:
        flash('You do not have permission to view this page', 'error')
        return redirect(url_for('dashboard'))

@app.route('/announcements')
@login_required
def announcements():
    """Announcements page."""
    all_announcements = Announcement.query.filter_by(is_deleted=False).order_by(Announcement.date_created.desc()).all()
    return render_template('announcements.html', announcements=all_announcements)

@app.route('/announcements/add', methods=['GET', 'POST'])
@login_required
def add_announcement():
    """Add new announcement (Secretary/Admin only)."""
    if not has_permission(current_user, 'manage_announcements'):
        flash('You do not have permission to create announcements', 'error')
        return redirect(url_for('announcements'))

    form = AnnouncementForm()

    if form.validate_on_submit():
        announcement = Announcement(
            title=form.title.data,
            content=form.content.data,
            is_urgent=form.is_urgent.data,
            created_by=current_user.id
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
    all_meetings = MeetingRecord.query.order_by(MeetingRecord.date_held.desc()).all()
    return render_template('announcements.html', meetings=all_meetings, show_meetings=True)

@app.route('/meetings/add', methods=['GET', 'POST'])
@login_required
def add_meeting():
    """Add meeting record (Secretary/Admin only)."""
    if not has_permission(current_user, 'record_meetings'):
        flash('You do not have permission to record meetings', 'error')
        return redirect(url_for('meetings'))

    form = MeetingRecordForm()

    if form.validate_on_submit():
        meeting = MeetingRecord(
            title=form.title.data,
            date_held=form.date_held.data,
            agenda=form.agenda.data,
            minutes=form.minutes.data,
            attendees=form.attendees.data,
            decisions=form.decisions.data,
            recorded_by=current_user.id
        )

        db.session.add(meeting)
        db.session.commit()

        flash('Meeting record created successfully', 'success')
        return redirect(url_for('meetings'))

    return render_template('announcements.html', form=form, action='Add', show_meetings=True)

@app.route('/documents')
@login_required
def documents():
    """Documents management page."""
    all_documents = Document.query.order_by(Document.upload_date.desc()).all()
    return render_template('documents.html', documents=all_documents)

@app.route('/documents/upload', methods=['GET', 'POST'])
@login_required
def upload_document():
    """Upload document (Admin/Secretary only)."""
    if current_user.role not in ['Admin', 'Secretary']:
        flash('You do not have permission to upload documents', 'error')
        return redirect(url_for('documents'))

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
                    uploaded_by=current_user.id
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

    stats = get_group_statistics()

    # Monthly contribution data for charts
    monthly_contributions = db.session.query(
        db.func.date_trunc('month', Contribution.date_recorded).label('month'),
        db.func.sum(Contribution.amount).label('total')
    ).group_by(db.func.date_trunc('month', Contribution.date_recorded)).order_by('month').all()

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
    """Payment processing page."""
    if not has_permission(current_user, 'manage_finances'):
        flash('You do not have permission to process payments', 'error')
        return redirect(url_for('dashboard'))

    form = PaymentForm()

    # Populate reference choices based on payment type
    if request.method == 'GET':
        # Default to loan repayments
        active_loans = Loan.query.filter_by(status='Active', is_deleted=False).all()
        form.reference_id.choices = [(loan.id, f"{loan.member.full_name if loan.member else loan.borrower_name} - {format_currency(loan.remaining_amount)}") for loan in active_loans]

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
    welfare_contributions = WelfareContribution.query.filter_by(is_deleted=False).all()
    welfare_expenses = WelfareExpense.query.all()

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

    # Populate member choices
    active_members = User.query.filter_by(is_active=True).all()
    form.member_id.choices = [(member.id, member.full_name) for member in active_members]

    if form.validate_on_submit():
        welfare = WelfareContribution(
            member_id=form.member_id.data,
            amount=form.amount.data,
            notes=form.notes.data,
            recorded_by=current_user.id
        )

        db.session.add(welfare)
        db.session.commit()

        member = User.query.get(form.member_id.data)
        flash(f'Welfare contribution of {format_currency(form.amount.data)} recorded for {member.full_name}', 'success')

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
                generated_at=datetime.utcnow()
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
    welfare_contributions = WelfareContribution.query.filter_by(is_deleted=False).all()
    welfare_expenses = WelfareExpense.query.all()

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

    # Populate beneficiary choices
    active_members = User.query.filter_by(is_active=True).all()
    form.beneficiary_id.choices = [(member.id, member.full_name) for member in active_members]

    if form.validate_on_submit():
        # Check available welfare funds
        total_contributions = sum(w.amount for w in WelfareContribution.query.filter_by(is_deleted=False).all())
        total_expenses = sum(w.amount for w in WelfareExpense.query.all())
        available_funds = total_contributions - total_expenses

        if form.amount.data > available_funds:
            flash(f'Insufficient welfare funds. Available: {format_currency(available_funds)}, Requested: {format_currency(form.amount.data)}', 'error')
            return render_template('welfare.html', form=form, action='Expense')

        expense = WelfareExpense(
            beneficiary_id=form.beneficiary_id.data,
            amount=form.amount.data,
            expense_type=form.expense_type.data,
            description=form.description.data,
            approved_by=current_user.id
        )

        db.session.add(expense)
        db.session.commit()

        beneficiary = User.query.get(form.beneficiary_id.data)
        flash(f'Welfare expense of {format_currency(form.amount.data)} recorded for {beneficiary.full_name}', 'success')

        # Create notification for welfare expense
        try:
            create_payment_notification('Welfare Expense', beneficiary.full_name, form.amount.data)
        except:
            pass # Continue even if notification fails

        return redirect(url_for('welfare'))

    # Get the same data as the main welfare view
    welfare_contributions = WelfareContribution.query.filter_by(is_deleted=False).all()
    welfare_expenses = WelfareExpense.query.all()

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
    active_proposals = VotingProposal.query.filter_by(status='Active').all()
    recent_proposals = VotingProposal.query.filter(VotingProposal.status.in_(['Closed', 'Implemented'])).order_by(VotingProposal.created_date.desc()).limit(10).all()

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
            status='Active' if form.voting_start.data <= datetime.utcnow() else 'Draft'
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

    members = User.query.filter_by(is_active=True).all()

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
        # Get receipts for contributions made by this member
        contribution_receipts = DigitalReceipt.query.join(Contribution).filter(
            Contribution.member_id == current_user.id
        ).all()
        
        # Get receipts for loan repayments (if any)
        loan_repayment_receipts = DigitalReceipt.query.join(LoanRepayment).join(Loan).filter(
            Loan.member_id == current_user.id
        ).all()
        
        # Get receipts for welfare contributions
        welfare_receipts = DigitalReceipt.query.join(WelfareContribution).filter(
            WelfareContribution.member_id == current_user.id
        ).all()
        
        # Get receipts for payments made by this member
        payment_receipts = DigitalReceipt.query.join(Payment).filter(
            Payment.member_id == current_user.id
        ).all()
        
        # Combine all receipts
        all_receipts = contribution_receipts + loan_repayment_receipts + welfare_receipts + payment_receipts
        
        # Sort by date (newest first)
        all_receipts.sort(key=lambda x: x.generated_at, reverse=True)
        
    elif has_permission(current_user, 'manage_finances'):
        # Admin/Treasurer can see all receipts
        all_receipts = DigitalReceipt.query.order_by(DigitalReceipt.generated_at.desc()).all()
    else:
        flash('You do not have permission to view receipts', 'error')
        return redirect(url_for('dashboard'))
    
    return render_template('receipts.html', receipts=all_receipts)

@app.route('/receipts/<int:receipt_id>/download')
@login_required
def download_receipt(receipt_id):
    """Download a digital receipt as PDF."""
    receipt = DigitalReceipt.query.get_or_404(receipt_id)
    
    # Check permissions
    can_access = False
    if current_user.role == 'Member':
        # Check if this receipt belongs to the current member
        if receipt.contribution_id:
            contribution = Contribution.query.get(receipt.contribution_id)
            if contribution and contribution.member_id == current_user.id:
                can_access = True
        elif receipt.loan_repayment_id:
            loan_repayment = LoanRepayment.query.get(receipt.loan_repayment_id)
            if loan_repayment and loan_repayment.loan.member_id == current_user.id:
                can_access = True
        elif receipt.welfare_contribution_id:
            welfare = WelfareContribution.query.get(receipt.welfare_contribution_id)
            if welfare and welfare.member_id == current_user.id:
                can_access = True
        elif receipt.payment_id:
            payment = Payment.query.get(receipt.payment_id)
            if payment and payment.member_id == current_user.id:
                can_access = True
    elif has_permission(current_user, 'manage_finances'):
        can_access = True
    
    if not can_access:
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
    return render_template('announcements.html', announcement=announcement, action='View')

@app.route('/meetings/<int:meeting_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_meeting(meeting_id):
    """Edit meeting record (Secretary/Admin only)."""
    if not has_permission(current_user, 'record_meetings'):
        flash('You do not have permission to edit meetings', 'error')
        return redirect(url_for('meetings'))

    meeting = MeetingRecord.query.get_or_404(meeting_id)
    form = MeetingRecordForm(obj=meeting)

    if form.validate_on_submit():
        meeting.title = form.title.data
        meeting.date_held = form.date_held.data
        meeting.agenda = form.agenda.data
        meeting.minutes = form.minutes.data
        meeting.attendees = form.attendees.data
        meeting.decisions = form.decisions.data

        db.session.commit()
        flash('Meeting record updated successfully', 'success')
        return redirect(url_for('meetings'))

    return render_template('announcements.html', form=form, meeting=meeting, action='Edit', show_meetings=True)

@app.route('/meetings/<int:meeting_id>/view')
@login_required
def view_meeting(meeting_id):
    """View single meeting record."""
    meeting = MeetingRecord.query.get_or_404(meeting_id)
    return render_template('announcements.html', meeting=meeting, action='View', show_meetings=True)

@app.route('/meetings/<int:meeting_id>/delete', methods=['POST'])
@login_required
def delete_meeting(meeting_id):
    """Delete meeting record with reason (Admin only)."""
    if current_user.role != 'Admin':
        flash('Only admins can delete meeting records', 'error')
        return redirect(url_for('meetings'))

    meeting = MeetingRecord.query.get_or_404(meeting_id)
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
    """Delete announcement with reason (Admin only)."""
    if current_user.role != 'Admin':
        flash('Only admins can delete announcements', 'error')
        return redirect(url_for('announcements'))

    announcement = Announcement.query.get_or_404(announcement_id)
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
    """Delete fine with reason (Admin only)."""
    if current_user.role != 'Admin':
        flash('Only admins can delete fines', 'error')
        return redirect(url_for('fines'))

    fine = Fine.query.get_or_404(fine_id)
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
    """Mark fine as paid (Admin only)."""
    if current_user.role != 'Admin':
        flash('Only admins can settle fines', 'error')
        return redirect(url_for('fines'))

    fine = Fine.query.get_or_404(fine_id)
    
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
    form = MembershipApplicationForm()

    if form.validate_on_submit():
        # Check if email already exists as a user
        existing_user = User.query.filter_by(email=form.email.data).first()
        if existing_user:
            flash('This email is already registered. Please contact us if you need assistance.', 'error')
            return render_template('membership_application.html', form=form)

        # Check if application already exists for this email
        existing_app = MembershipApplication.query.filter_by(email=form.email.data, status='Pending').first()
        if existing_app:
            flash('An application with this email already exists and is pending review. Please wait.', 'error')
            return render_template('membership_application.html', form=form)

        application = MembershipApplication(
            full_name=form.full_name.data,
            email=form.email.data,
            phone=form.phone.data,
            id_number=form.id_number.data,
            location=form.location.data,
            occupation=form.occupation.data,
            reason_for_joining=form.reason_for_joining.data
        )

        db.session.add(application)
        db.session.commit()

        # Create notification for admins and chairman
        notification_users = User.query.filter(User.role.in_(['Admin', 'Chairman']), User.is_active == True).all()
        for user in notification_users:
            notification = Notification(
                user_id=user.id,
                title='New Membership Application',
                message=f'{form.full_name.data} has applied for membership in the group',
                notification_type='membership_application'
            )
            db.session.add(notification)
        db.session.commit()

        flash('Your membership application has been submitted successfully. We will review and get back to you soon.', 'success')
        return redirect(url_for('index'))

    return render_template('membership_application.html', form=form)

@app.route('/membership-applications')
@login_required
def membership_applications():
    """View membership applications (Admin/Chairman only)."""
    if current_user.role not in ['Admin', 'Chairman']:
        flash('You do not have permission to view membership applications', 'error')
        return redirect(url_for('dashboard'))

    applications = MembershipApplication.query.order_by(MembershipApplication.application_date.desc()).all()
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
        action = request.form.get('action')

        if action == 'approve':
            # Check if username already exists
            base_username = application.email.split('@')[0]
            username = base_username
            counter = 1
            while User.query.filter_by(username=username).first():
                username = f"{base_username}{counter}"
                counter += 1

            # Create new user account
            new_user = User(
                username=username,
                full_name=application.full_name,
                email=application.email,
                phone=application.phone,
                role='Member',
                password_hash=generate_password_hash('pamoja123'),  # Default password
                is_active=True,
                two_factor_enabled=False # 2FA temporarily disabled
            )

            db.session.add(new_user)
            application.status = 'Approved'
            application.reviewed_by = current_user.id
            application.review_date = datetime.utcnow()

            # Commit first to prevent freezing
            db.session.commit()
            
            # Log activity (after commit to prevent blocking)
            try:
                from activity_logger import log_activity
                log_activity('approved', 'membership_application', application.id, 
                           f'Approved membership application for {application.full_name}')
            except:
                pass

            flash(f'Membership application approved. {application.full_name} has been added as a member with username "{username}" and default password "pamoja123". Please advise them to change their password and set up 2FA.', 'success')

        elif action == 'reject':
            rejection_reason = request.form.get('rejection_reason', '').strip()
            application.status = 'Rejected'
            application.reviewed_by = current_user.id
            application.review_date = datetime.utcnow()
            application.review_notes = rejection_reason

            # Commit first to prevent freezing
            db.session.commit()
            
            # Log activity (after commit to prevent blocking)
            try:
                from activity_logger import log_activity
                log_activity('rejected', 'membership_application', application.id, 
                           f'Rejected membership application for {application.full_name}. Reason: {rejection_reason}')
            except:
                pass

            flash(f'Membership application for {application.full_name} has been rejected', 'info')

        return redirect(url_for('membership_applications'))

    except Exception as e:
        db.session.rollback()
        flash(f'Error processing application: {str(e)}', 'error')
        return redirect(url_for('membership_applications'))

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

# Context processors
@app.context_processor
def utility_processor():
    return dict(
        format_currency=format_currency,
        format_date=format_date,
        format_datetime=format_datetime,
        has_permission=has_permission,
        datetime=datetime
    )

@app.context_processor
def inject_csrf_token():
    from flask_wtf.csrf import generate_csrf
    return dict(csrf_token=generate_csrf)
