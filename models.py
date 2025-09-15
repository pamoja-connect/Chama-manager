
from datetime import datetime, timedelta
from app import db
from flask_login import UserMixin
from sqlalchemy.sql import func

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # Admin, Treasurer, Secretary, Chairman, Member
    password_hash = db.Column(db.String(256), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    date_joined = db.Column(db.DateTime, default=datetime.utcnow)
    two_factor_enabled = db.Column(db.Boolean, default=False)
    profile_picture = db.Column(db.String(255), nullable=True)  # Filename of uploaded profile picture
    
    # Relationships - specify foreign keys to avoid ambiguity
    contributions = db.relationship('Contribution', foreign_keys='Contribution.member_id', lazy=True, cascade='all, delete-orphan', overlaps="member")
    loans = db.relationship('Loan', foreign_keys='Loan.member_id', lazy=True, cascade='all, delete-orphan', overlaps="member")
    fines = db.relationship('Fine', foreign_keys='Fine.member_id', lazy=True, cascade='all, delete-orphan', overlaps="member")
    
    def get_total_contributions(self):
        return sum(c.amount for c in self.contributions) if self.contributions else 0.0
    
    def get_active_loans(self):
        return [loan for loan in self.loans if loan.status == 'Active'] if self.loans else []
    
    def get_total_loan_balance(self):
        active_loans = self.get_active_loans()
        return sum(loan.remaining_amount for loan in active_loans) if active_loans else 0.0
    
    def get_unpaid_fines(self):
        return [fine for fine in self.fines if not fine.is_paid] if self.fines else []
    
    def get_total_unpaid_fines(self):
        unpaid_fines = self.get_unpaid_fines()
        return sum(fine.amount for fine in unpaid_fines) if unpaid_fines else 0.0
    
    def __repr__(self):
        return f'<User {self.username}>'

class Contribution(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    contribution_type = db.Column(db.String(50), default='Regular')  # Regular, Special
    date_recorded = db.Column(db.DateTime, default=datetime.utcnow)
    recorded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    notes = db.Column(db.Text)
    is_deleted = db.Column(db.Boolean, default=False)
    deletion_reason = db.Column(db.Text)
    deleted_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    deleted_at = db.Column(db.DateTime)
    
    # Set up relationships with explicit foreign keys
    member = db.relationship('User', foreign_keys=[member_id], overlaps="contributions")
    recorder = db.relationship('User', foreign_keys=[recorded_by])
    deleter = db.relationship('User', foreign_keys=[deleted_by])

class Loan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # Nullable for external loans
    amount = db.Column(db.Float, nullable=False)
    remaining_amount = db.Column(db.Float, nullable=False)
    interest_rate = db.Column(db.Float, default=20.0)  # Percentage
    status = db.Column(db.String(20), default='Pending')  # Pending, Active, Completed, Rejected
    application_date = db.Column(db.DateTime, default=datetime.utcnow)
    approval_date = db.Column(db.DateTime)
    due_date = db.Column(db.DateTime)
    approved_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    purpose = db.Column(db.Text, nullable=False)
    duration_months = db.Column(db.Integer, default=3)
    
    # Enhanced loan types
    loan_category = db.Column(db.String(20), default='Short-term')  # Short-term, Long-term, Emergency
    emergency_type = db.Column(db.String(50))  # Medical, Family, Business, etc.
    
    # Auto-fine calculation
    grace_period_days = db.Column(db.Integer, default=7)  # Days before fine is applied
    late_fee_percentage = db.Column(db.Float, default=5.0)  # Percentage of outstanding amount
    is_overdue = db.Column(db.Boolean, default=False)
    overdue_since = db.Column(db.DateTime)
    auto_fine_applied = db.Column(db.Boolean, default=False)
    
    # Additional loan details
    occupation = db.Column(db.String(100))
    monthly_income = db.Column(db.Float)
    
    # External loan fields
    loan_type = db.Column(db.String(10), default='Internal')  # Internal, External
    guarantor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    kra_pin = db.Column(db.String(11), nullable=True)
    id_number = db.Column(db.String(10), nullable=True)
    borrower_phone = db.Column(db.String(15), nullable=True)
    borrower_name = db.Column(db.String(100), nullable=True)
    borrower_address = db.Column(db.Text, nullable=True)
    total_repayment = db.Column(db.Float, nullable=True)
    
    # Repayment mode
    repayment_mode = db.Column(db.String(20), default='monthly')  # weekly, monthly, lump_sum
    
    # Administrative fields
    approval_notes = db.Column(db.Text)
    is_deleted = db.Column(db.Boolean, default=False)
    deletion_reason = db.Column(db.Text)
    deleted_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    deleted_at = db.Column(db.DateTime)
    
    # Set up relationships with explicit foreign keys
    member = db.relationship('User', foreign_keys=[member_id], overlaps="loans")
    approver = db.relationship('User', foreign_keys=[approved_by])
    guarantor = db.relationship('User', foreign_keys=[guarantor_id])
    deleter = db.relationship('User', foreign_keys=[deleted_by])
    repayments = db.relationship('LoanRepayment', backref='loan', lazy=True, cascade='all, delete-orphan')
    
    def calculate_interest(self):
        """Calculate total interest for the loan"""
        return self.amount * (self.interest_rate / 100) * (self.duration_months / 12)
    
    def calculate_total_repayment(self):
        """Calculate total amount to be repaid"""
        return self.amount + self.calculate_interest()
    
    def calculate_monthly_payment(self):
        """Calculate monthly payment amount"""
        if self.duration_months > 0:
            return self.calculate_total_repayment() / self.duration_months
        return self.calculate_total_repayment()
    
    def calculate_late_fee(self):
        """Calculate late fee for overdue loans"""
        if self.is_overdue and self.overdue_since:
            days_overdue = (datetime.utcnow() - self.overdue_since).days
            if days_overdue > self.grace_period_days:
                return self.remaining_amount * (self.late_fee_percentage / 100)
        return 0.0
    
    def check_and_mark_overdue(self):
        """Check if loan is overdue and mark accordingly"""
        if self.status == 'Active' and self.due_date and datetime.utcnow() > self.due_date:
            if not self.is_overdue:
                self.is_overdue = True
                self.overdue_since = datetime.utcnow()
                return True
        return False

class LoanRepayment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey('loan.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    date_paid = db.Column(db.DateTime, default=datetime.utcnow)
    recorded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    recorder = db.relationship('User', foreign_keys=[recorded_by])

class Fine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    fine_type = db.Column(db.String(50), nullable=False)  # Absence, Lateness, etc.
    reason = db.Column(db.String(100))  # With Apology, Without Apology
    date_issued = db.Column(db.DateTime, default=datetime.utcnow)
    is_paid = db.Column(db.Boolean, default=False)
    date_paid = db.Column(db.DateTime)
    payment_notes = db.Column(db.Text)
    recorded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    is_deleted = db.Column(db.Boolean, default=False)
    deletion_reason = db.Column(db.Text)
    deleted_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    deleted_at = db.Column(db.DateTime)
    
    # Set up relationships with explicit foreign keys
    member = db.relationship('User', foreign_keys=[member_id], overlaps="fines")
    recorder = db.relationship('User', foreign_keys=[recorded_by])
    deleter = db.relationship('User', foreign_keys=[deleted_by])

class Announcement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    is_urgent = db.Column(db.Boolean, default=False)
    is_deleted = db.Column(db.Boolean, default=False)
    deletion_reason = db.Column(db.Text)
    deleted_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    deleted_at = db.Column(db.DateTime)
    
    creator = db.relationship('User', foreign_keys=[created_by])
    deleter = db.relationship('User', foreign_keys=[deleted_by])

class MeetingRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    date_held = db.Column(db.Date, nullable=False)
    agenda = db.Column(db.Text)
    minutes = db.Column(db.Text, nullable=False)
    attendees = db.Column(db.Text)  # JSON string of attendee IDs
    decisions = db.Column(db.Text)
    date_recorded = db.Column(db.DateTime, default=datetime.utcnow)
    recorded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    is_deleted = db.Column(db.Boolean, default=False)
    deletion_reason = db.Column(db.Text)
    deleted_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    deleted_at = db.Column(db.DateTime)
    
    recorder = db.relationship('User', foreign_keys=[recorded_by])
    deleter = db.relationship('User', foreign_keys=[deleted_by])

class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(10), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(50), default='General')
    
    uploader = db.relationship('User', foreign_keys=[uploaded_by])

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='Planned')
    budget = db.Column(db.Float, default=0.0)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    created_date = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    creator = db.relationship('User', foreign_keys=[created_by])

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(50), nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', foreign_keys=[user_id])

class MembershipApplication(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    id_number = db.Column(db.String(10), nullable=False)
    location = db.Column(db.String(200), nullable=False)
    occupation = db.Column(db.String(100), nullable=False)
    reason_for_joining = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='Pending')  # Pending, Approved, Rejected
    application_date = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    review_date = db.Column(db.DateTime, nullable=True)
    review_notes = db.Column(db.Text)
    
    reviewer = db.relationship('User', foreign_keys=[reviewed_by])

class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action = db.Column(db.String(100), nullable=False)  # 'created', 'updated', 'deleted', etc.
    entity_type = db.Column(db.String(50), nullable=False)  # 'loan', 'contribution', etc.
    entity_id = db.Column(db.Integer, nullable=True)  # ID of the affected entity
    description = db.Column(db.Text, nullable=False)  # Human readable description
    ip_address = db.Column(db.String(45))  # User's IP address
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    additional_data = db.Column(db.Text)  # JSON data for extra details
    
    user = db.relationship('User', foreign_keys=[user_id])

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    payment_type = db.Column(db.String(20), nullable=False)  # loan_repayment, fine_payment, contribution
    reference_id = db.Column(db.Integer, nullable=False)  # ID of loan, fine, or contribution
    amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(20), nullable=False)  # cash, mpesa, bank_transfer
    transaction_reference = db.Column(db.String(100))
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)
    processed_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    status = db.Column(db.String(20), default='Pending')  # Pending, Approved, Rejected
    receipt_generated = db.Column(db.Boolean, default=False)
    qr_code_path = db.Column(db.String(255))
    
    member = db.relationship('User', foreign_keys=[member_id])
    processor = db.relationship('User', foreign_keys=[processed_by])

class DigitalReceipt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    payment_id = db.Column(db.Integer, db.ForeignKey('payment.id'), nullable=True)
    contribution_id = db.Column(db.Integer, db.ForeignKey('contribution.id'), nullable=True)
    loan_repayment_id = db.Column(db.Integer, db.ForeignKey('loan_repayment.id'), nullable=True)
    welfare_contribution_id = db.Column(db.Integer, db.ForeignKey('welfare_contribution.id'), nullable=True)
    receipt_number = db.Column(db.String(50), unique=True, nullable=False)
    qr_code_data = db.Column(db.Text)  # JSON data for QR code
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)
    downloaded = db.Column(db.Boolean, default=False)
    download_count = db.Column(db.Integer, default=0)
    
    payment = db.relationship('Payment', backref='receipt')
    contribution = db.relationship('Contribution', backref='receipt')
    loan_repayment = db.relationship('LoanRepayment', backref='receipt')
    welfare_contribution = db.relationship('WelfareContribution', backref='receipt')

class WelfareContribution(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    date_recorded = db.Column(db.DateTime, default=datetime.utcnow)
    recorded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    notes = db.Column(db.Text)
    is_deleted = db.Column(db.Boolean, default=False)
    
    member = db.relationship('User', foreign_keys=[member_id])
    recorder = db.relationship('User', foreign_keys=[recorded_by])

class WelfareExpense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    beneficiary_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    expense_type = db.Column(db.String(50), nullable=False)  # funeral, emergency, medical, etc.
    description = db.Column(db.Text, nullable=False)
    date_disbursed = db.Column(db.DateTime, default=datetime.utcnow)
    approved_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    documentation = db.Column(db.String(255))  # Path to supporting documents
    
    beneficiary = db.relationship('User', foreign_keys=[beneficiary_id])
    approver = db.relationship('User', foreign_keys=[approved_by])

class VotingProposal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    proposal_type = db.Column(db.String(50), nullable=False)  # policy, financial, member, project
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_date = db.Column(db.DateTime, default=datetime.utcnow)
    voting_start = db.Column(db.DateTime, nullable=False)
    voting_end = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='Draft')  # Draft, Active, Closed, Implemented
    requires_majority = db.Column(db.Boolean, default=True)
    minimum_participation = db.Column(db.Float, default=50.0)  # Percentage
    
    creator = db.relationship('User', foreign_keys=[created_by])
    votes = db.relationship('Vote', backref='proposal', lazy=True, cascade='all, delete-orphan')

class Vote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    proposal_id = db.Column(db.Integer, db.ForeignKey('voting_proposal.id'), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    vote_choice = db.Column(db.String(20), nullable=False)  # yes, no, abstain
    vote_date = db.Column(db.DateTime, default=datetime.utcnow)
    comment = db.Column(db.Text)
    
    member = db.relationship('User', foreign_keys=[member_id])

class Badge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    icon = db.Column(db.String(100))  # Font Awesome icon class
    category = db.Column(db.String(50))  # payments, attendance, savings, leadership
    criteria = db.Column(db.Text)  # JSON criteria for earning badge
    points_value = db.Column(db.Integer, default=10)
    
class UserBadge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    badge_id = db.Column(db.Integer, db.ForeignKey('badge.id'), nullable=False)
    earned_date = db.Column(db.DateTime, default=datetime.utcnow)
    points_earned = db.Column(db.Integer, default=0)
    
    member = db.relationship('User', foreign_keys=[member_id])
    badge = db.relationship('Badge', foreign_keys=[badge_id])

class MemberPoints(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    total_points = db.Column(db.Integer, default=0)
    level = db.Column(db.String(50), default='Bronze')  # Bronze, Silver, Gold, Platinum
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    
    member = db.relationship('User', foreign_keys=[member_id])

class LoanSettlement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey('loan.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(20), nullable=False)  # cash, mpesa, bank_transfer
    transaction_reference = db.Column(db.String(100))
    settlement_date = db.Column(db.DateTime, default=datetime.utcnow)
    processed_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='Approved')  # Pending, Approved, Rejected
    receipt_generated = db.Column(db.Boolean, default=False)
    
    loan = db.relationship('Loan', foreign_keys=[loan_id])
    processor = db.relationship('User', foreign_keys=[processed_by])

class FineSettlement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fine_id = db.Column(db.Integer, db.ForeignKey('fine.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(20), nullable=False)  # cash, mpesa, bank_transfer
    transaction_reference = db.Column(db.String(100))
    settlement_date = db.Column(db.DateTime, default=datetime.utcnow)
    processed_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='Approved')
    receipt_generated = db.Column(db.Boolean, default=False)
    
    fine = db.relationship('Fine', foreign_keys=[fine_id])
    processor = db.relationship('User', foreign_keys=[processed_by])

class OfflineData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    data_type = db.Column(db.String(50), nullable=False)  # balance, transactions, loans, etc.
    data_content = db.Column(db.Text, nullable=False)  # JSON data
    last_sync = db.Column(db.DateTime, default=datetime.utcnow)
    device_id = db.Column(db.String(100))
    
    member = db.relationship('User', foreign_keys=[member_id])

class TwoFactorAuth(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    otp_secret = db.Column(db.String(32))  # Base32 encoded secret
    phone_number = db.Column(db.String(20))
    email = db.Column(db.String(120))
    is_enabled = db.Column(db.Boolean, default=False)
    backup_codes = db.Column(db.Text)  # JSON array of backup codes
    last_used = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', foreign_keys=[user_id])

class OTPVerification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    otp_code = db.Column(db.String(6), nullable=False)
    verification_type = db.Column(db.String(20), nullable=False)  # login, reset_password, etc.
    expires_at = db.Column(db.DateTime, nullable=False)
    is_used = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', foreign_keys=[user_id])
