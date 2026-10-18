import os
import csv
from io import StringIO
from datetime import datetime
from flask import current_app, make_response
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.units import inch
from models import User, Contribution, Loan, Fine

def allowed_file(filename):
    """Check if file extension is allowed."""
    ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'txt', 'jpg', 'jpeg', 'png'}
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def secure_filename(filename):
    """Secure a filename by removing unsafe characters."""
    import re
    filename = re.sub(r'[^\w\-_\.]', '', filename)
    return filename

def format_currency(amount):
    """Format amount as currency."""
    try:
        if amount is None or amount == '':
            return "KSh 0.00"
        # Handle string inputs
        if isinstance(amount, str):
            amount = float(amount.replace(',', '').replace('KSh', '').strip())
        return f"KSh {float(amount):,.2f}"
    except (ValueError, TypeError):
        return "KSh 0.00"

def format_date(date_obj):
    """Format date as dd/mm/yy."""
    try:
        if date_obj is None:
            return ""
        if isinstance(date_obj, str):
            return date_obj
        return date_obj.strftime("%d/%m/%y")
    except:
        return ""

def format_datetime(datetime_obj):
    """Format datetime as dd/mm/yy HH:MM."""
    try:
        if datetime_obj is None:
            return ""
        if isinstance(datetime_obj, str):
            return datetime_obj
        return datetime_obj.strftime("%d/%m/%y %H:%M")
    except:
        return ""

def generate_financial_report_pdf():
    """Generate PDF financial report."""
    from io import BytesIO
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    
    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.darkblue,
        alignment=1,  # Center alignment
        spaceAfter=30
    )
    
    # Content
    story = []
    
    # Try to add logo
    try:
        # Try the main logo first
        logo_path = os.path.join(current_app.root_path, 'static', 'uploads', 'pamoja_logo.png')
        if not os.path.exists(logo_path):
            # Fallback to the other uploaded logo
            logo_path = os.path.join(current_app.root_path, 'static', 'uploads', '20250909_175634_IMG-20250909-WA0031.jpg')
        if not os.path.exists(logo_path):
            # Final fallback to the logo in root directory
            logo_path = os.path.join(current_app.root_path, 'InShot_20250326_115857211.png')
        
        if os.path.exists(logo_path):
            logo = Image(logo_path, width=2*inch, height=1*inch)
            story.append(logo)
            story.append(Spacer(1, 10))
    except:
        pass  # Continue without logo if there's an issue
    
    # Title
    title = Paragraph("Pamoja Agencies SHG - Financial Report", title_style)
    story.append(title)
    story.append(Spacer(1, 20))
    
    # Date
    date_para = Paragraph(f"Generated on: {datetime.now().strftime('%B %d, %Y')}", styles['Normal'])
    story.append(date_para)
    story.append(Spacer(1, 20))
    
    # Summary Statistics
    total_contributions = sum(c.amount for c in Contribution.query.all())
    total_loans = sum(l.amount for l in Loan.query.filter_by(status='Active').all())
    total_fines = sum(f.amount for f in Fine.query.filter_by(is_paid=False).all())
    
    summary_data = [
        ['Total Member Contributions', format_currency(total_contributions)],
        ['Active Loans Outstanding', format_currency(total_loans)],
        ['Unpaid Fines', format_currency(total_fines)],
        ['Group Balance', format_currency(total_contributions - total_loans)]
    ]
    
    summary_table = Table(summary_data, colWidths=[3*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    story.append(summary_table)
    story.append(Spacer(1, 30))
    
    # Member Contributions Table
    contrib_title = Paragraph("Member Contributions Summary", styles['Heading2'])
    story.append(contrib_title)
    story.append(Spacer(1, 10))
    
    # Get member contribution data
    members = User.query.filter_by(is_active=True).all()
    contrib_data = [['Member Name', 'Total Contributions', 'Number of Contributions']]
    
    for member in members:
        total_contrib = member.get_total_contributions()
        num_contrib = len(member.contributions)
        contrib_data.append([member.full_name, format_currency(total_contrib), str(num_contrib)])
    
    contrib_table = Table(contrib_data, colWidths=[2.5*inch, 1.5*inch, 1.5*inch])
    contrib_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    story.append(contrib_table)
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    return buffer

def generate_financial_report_csv():
    """Generate CSV financial report."""
    output = StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow(['Pamoja Agencies SHG - Financial Report'])
    writer.writerow([f'Generated on: {datetime.now().strftime("%B %d, %Y")}'])
    writer.writerow([])  # Empty row
    
    # Summary
    writer.writerow(['FINANCIAL SUMMARY'])
    total_contributions = sum(c.amount for c in Contribution.query.all())
    total_loans = sum(l.amount for l in Loan.query.filter_by(status='Active').all())
    total_fines = sum(f.amount for f in Fine.query.filter_by(is_paid=False).all())
    
    writer.writerow(['Total Member Contributions', total_contributions])
    writer.writerow(['Active Loans Outstanding', total_loans])
    writer.writerow(['Unpaid Fines', total_fines])
    writer.writerow(['Group Balance', total_contributions - total_loans])
    writer.writerow([])  # Empty row
    
    # Member details
    writer.writerow(['MEMBER CONTRIBUTIONS'])
    writer.writerow(['Member Name', 'Email', 'Total Contributions', 'Number of Contributions'])
    
    members = User.query.filter_by(is_active=True).all()
    for member in members:
        total_contrib = member.get_total_contributions()
        num_contrib = len(member.contributions)
        writer.writerow([member.full_name, member.email, total_contrib, num_contrib])
    
    output.seek(0)
    return output.getvalue()

def get_group_statistics(group_id=None):
    """Get comprehensive statistics, optionally scoped to a group."""
    from sqlalchemy import func
    stats = {}

    def member_ids():
        if group_id is None:
            return None
        return [u.id for u in User.query.filter_by(group_id=group_id, is_active=True).all()]

    mids = member_ids()

    def u_q(**kw):
        q = User.query.filter_by(is_active=True, **kw)
        if mids is not None:
            q = q.filter(User.id.in_(mids))
        return q

    def c_q(**kw):
        q = Contribution.query.filter_by(**kw)
        if mids is not None:
            q = q.filter(Contribution.member_id.in_(mids))
        return q

    def l_q(**kw):
        q = Loan.query.filter_by(**kw)
        if mids is not None:
            q = q.filter(Loan.member_id.in_(mids))
        return q

    def f_q(**kw):
        q = Fine.query.filter_by(**kw)
        if mids is not None:
            q = q.filter(Fine.member_id.in_(mids))
        return q

    # Member statistics
    stats['total_members'] = u_q().count()
    stats['total_admins'] = u_q(role='Admin').count()
    stats['total_treasurers'] = u_q(role='Treasurer').count()
    stats['total_secretaries'] = u_q(role='Secretary').count()

    # Financial statistics
    stats['total_contributions'] = sum(c.amount for c in c_q().all()) or 0
    stats['total_loans_issued'] = sum(l.amount for l in l_q().filter(
        Loan.status.in_(['Active', 'Completed'])).all()) or 0
    stats['active_loans_amount'] = sum(l.remaining_amount for l in l_q(status='Active').all()) or 0
    stats['total_fines'] = sum(f.amount for f in f_q().all()) or 0
    stats['unpaid_fines'] = sum(f.amount for f in f_q(is_paid=False).all()) or 0

    # Group balance
    stats['group_balance'] = stats['total_contributions'] - stats['active_loans_amount']

    # Recent activity
    stats['pending_loans'] = l_q(status='Pending').count()
    stats['recent_contributions'] = c_q().filter(
        Contribution.date_recorded >= datetime.now().replace(day=1)
    ).count()

    return stats

def get_active_group_id():
    """Return the active group ID for the current request.
    Super admins use session['active_group_id'] if set; regular users always use their own group_id.
    """
    from flask_login import current_user
    from flask import session
    if not current_user or not current_user.is_authenticated:
        return None
    if current_user.is_super_admin:
        return session.get('active_group_id')
    return current_user.group_id


def has_permission(user, action):
    """Check if user has permission for specific action."""
    permissions = {
        'Admin': ['all'],
        'Chairman': ['manage_finances', 'view_members', 'approve_loans', 'record_contributions', 'issue_fines', 'manage_announcements', 'record_meetings', 'review_membership'],
        'Treasurer': ['manage_finances', 'view_members', 'approve_loans', 'record_contributions', 'issue_fines'],
        'Secretary': ['manage_announcements', 'record_meetings', 'view_members'],
        'Member': ['view_own_data', 'apply_loan', 'view_announcements']
    }
    
    if user.role == 'Admin':
        return True
    
    return action in permissions.get(user.role, [])
