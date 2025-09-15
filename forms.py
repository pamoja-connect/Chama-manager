
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, TextAreaField, FloatField, SelectField, DateTimeField, BooleanField, PasswordField, DateField, IntegerField
from wtforms.validators import DataRequired, Email, Length, NumberRange, Optional, ValidationError
from wtforms.widgets import TextArea
from models import User

class LoginForm(FlaskForm):
    username = SelectField('Username', choices=[], validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])

class DeletionForm(FlaskForm):
    reason = TextAreaField('Reason for Deletion', validators=[DataRequired(), Length(min=10, max=500)],
                          render_kw={"placeholder": "Please provide a detailed reason for deletion..."})
    confirm_deletion = BooleanField('I confirm this deletion', validators=[DataRequired()])

class VotingProposalForm(FlaskForm):
    title = StringField('Proposal Title', validators=[DataRequired(), Length(min=5, max=200)])
    description = TextAreaField('Proposal Description', validators=[DataRequired(), Length(min=20, max=1000)])
    proposal_type = SelectField('Proposal Type', choices=[
        ('policy', 'Policy Change'),
        ('financial', 'Financial Decision'),
        ('member', 'Member-related'),
        ('project', 'Project Proposal')
    ], validators=[DataRequired()])
    voting_start = DateTimeField('Voting Start', validators=[DataRequired()])
    voting_end = DateTimeField('Voting End', validators=[DataRequired()])
    minimum_participation = FloatField('Minimum Participation (%)', validators=[DataRequired(), NumberRange(min=1, max=100)])

class VoteForm(FlaskForm):
    vote_choice = SelectField('Your Vote', choices=[
        ('yes', 'Yes - I support this proposal'),
        ('no', 'No - I oppose this proposal'),
        ('abstain', 'Abstain - I prefer not to vote')
    ], validators=[DataRequired()])
    comment = TextAreaField('Comment (Optional)', validators=[Optional(), Length(max=500)])

class LoanApplicationForm(FlaskForm):
    amount = FloatField('Loan Amount (KSh)', validators=[DataRequired(), NumberRange(min=1000)])
    purpose = TextAreaField('Purpose of Loan', validators=[DataRequired(), Length(min=10, max=500)])
    duration_months = SelectField('Duration (Months)', choices=[
        ('3', '3 Months'),
        ('6', '6 Months'),
        ('12', '12 Months'),
        ('18', '18 Months'),
        ('24', '24 Months')
    ], validators=[DataRequired()])
    loan_type = SelectField('Loan Type', choices=[
        ('Internal', 'Internal (Member)'),
        ('External', 'External (Non-member)')
    ], default='Internal', validators=[DataRequired()])
    loan_category = SelectField('Loan Category', choices=[
        ('Short-term', 'Short-term (≤ 6 months)'),
        ('Long-term', 'Long-term (> 6 months)'),
        ('Emergency', 'Emergency Loan')
    ], default='Short-term', validators=[DataRequired()])
    emergency_type = SelectField('Emergency Type', choices=[
        ('', 'Select Emergency Type'),
        ('Medical', 'Medical Emergency'),
        ('Family', 'Family Emergency'),
        ('Business', 'Business Emergency'),
        ('Education', 'Education Emergency'),
        ('Other', 'Other Emergency')
    ], validators=[Optional()])
    repayment_mode = SelectField('Preferred Repayment Mode', choices=[
        ('monthly', 'Monthly'),
        ('weekly', 'Weekly'),
        ('lump_sum', 'Lump Sum')
    ], default='monthly', validators=[DataRequired()])
    guarantor_id = SelectField('Guarantor (External Loans)', choices=[], validators=[Optional()])
    occupation = StringField('Occupation', validators=[Optional(), Length(max=100)])
    monthly_income = FloatField('Monthly Income (KSh)', validators=[Optional(), NumberRange(min=0)])
    
class LoanApprovalForm(FlaskForm):
    amount = FloatField('Approved Amount (KSh)', validators=[DataRequired(), NumberRange(min=1000)])
    interest_rate = FloatField('Interest Rate (%)', validators=[DataRequired(), NumberRange(min=0, max=50)])
    duration_months = SelectField('Duration (Months)', choices=[
        ('3', '3 Months'),
        ('6', '6 Months'),
        ('12', '12 Months'),
        ('18', '18 Months'),
        ('24', '24 Months')
    ], validators=[DataRequired()])
    status = SelectField('Decision', choices=[
        ('Active', 'Approve'),
        ('Rejected', 'Reject')
    ], validators=[DataRequired()])
    approval_notes = TextAreaField('Approval Notes', validators=[Optional(), Length(max=500)])

class LoanRepaymentForm(FlaskForm):
    loan_id = SelectField('Select Loan', choices=[], validators=[DataRequired()])
    amount = FloatField('Repayment Amount (KSh)', validators=[DataRequired(), NumberRange(min=1)])

class ContributionForm(FlaskForm):
    member_id = SelectField('Member', choices=[], validators=[DataRequired()])
    amount = FloatField('Amount (KSh)', validators=[DataRequired(), NumberRange(min=1)])
    contribution_type = SelectField('Type', choices=[
        ('Regular', 'Regular Contribution'),
        ('Special', 'Special Contribution')
    ], validators=[DataRequired()])
    notes = TextAreaField('Notes', validators=[Optional(), Length(max=200)])

class FineForm(FlaskForm):
    member_id = SelectField('Member', choices=[], validators=[DataRequired()])
    amount = FloatField('Fine Amount (KSh)', validators=[DataRequired(), NumberRange(min=1)])
    fine_type = SelectField('Fine Type', choices=[
        ('Absence', 'Meeting Absence'),
        ('Lateness', 'Lateness'),
        ('Misconduct', 'Misconduct'),
        ('Late Payment', 'Late Payment'),
        ('Other', 'Other')
    ], validators=[DataRequired()])
    reason = SelectField('Reason', choices=[
        ('With Apology', 'With Apology'),
        ('Without Apology', 'Without Apology'),
        ('Repeat Offense', 'Repeat Offense'),
        ('Other', 'Other')
    ], validators=[DataRequired()])

class AnnouncementForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(min=5, max=200)])
    content = TextAreaField('Content', validators=[DataRequired(), Length(min=10, max=2000)])
    is_urgent = BooleanField('Mark as Urgent')

class MeetingRecordForm(FlaskForm):
    title = StringField('Meeting Title', validators=[DataRequired(), Length(min=5, max=200)])
    date_held = DateField('Date Held', validators=[DataRequired()])
    agenda = TextAreaField('Agenda', validators=[Optional(), Length(max=1000)])
    minutes = TextAreaField('Meeting Minutes', validators=[DataRequired(), Length(min=20, max=2000)])
    attendees = TextAreaField('Attendees', validators=[Optional(), Length(max=1000)],
                             render_kw={"placeholder": "List of member names who attended..."})
    decisions = TextAreaField('Decisions Made', validators=[Optional(), Length(max=1000)])

class DocumentForm(FlaskForm):
    title = StringField('Document Title', validators=[DataRequired(), Length(min=3, max=200)])
    description = TextAreaField('Description', validators=[Optional(), Length(max=500)])
    category = SelectField('Category', choices=[
        ('General', 'General'),
        ('Financial', 'Financial'),
        ('Legal', 'Legal'),
        ('Meeting', 'Meeting Records'),
        ('Policy', 'Policy Documents')
    ], validators=[DataRequired()])
    file = FileField('File', validators=[DataRequired(), FileAllowed(['pdf', 'doc', 'docx', 'txt', 'jpg', 'jpeg', 'png'])])

class PasswordChangeForm(FlaskForm):
    current_password = PasswordField('Current Password', validators=[DataRequired()])
    new_password = PasswordField('New Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm New Password', validators=[DataRequired()])

class PaymentForm(FlaskForm):
    payment_type = SelectField('Payment Type', choices=[
        ('loan_repayment', 'Loan Repayment'),
        ('fine_payment', 'Fine Payment'),
        ('contribution', 'Contribution')
    ], validators=[DataRequired()])
    reference_id = SelectField('Reference', choices=[], validators=[DataRequired()])
    amount = FloatField('Amount (KSh)', validators=[DataRequired(), NumberRange(min=1)])
    payment_method = SelectField('Payment Method', choices=[
        ('cash', 'Cash'),
        ('mpesa', 'M-Pesa'),
        ('bank_transfer', 'Bank Transfer')
    ], validators=[DataRequired()])
    transaction_reference = StringField('Transaction Reference', validators=[Optional(), Length(max=100)])

class WelfareContributionForm(FlaskForm):
    member_id = SelectField('Member', choices=[], validators=[DataRequired()])
    amount = FloatField('Amount (KSh)', validators=[DataRequired(), NumberRange(min=1)])
    notes = TextAreaField('Notes', validators=[Optional(), Length(max=200)])

class MembershipApplicationForm(FlaskForm):
    full_name = StringField('Full Name', validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField('Email Address', validators=[DataRequired(), Email()])
    phone = StringField('Phone Number', validators=[DataRequired(), Length(min=10, max=20)])
    id_number = StringField('ID Number', validators=[DataRequired(), Length(min=7, max=10)])
    location = StringField('Location/Address', validators=[DataRequired(), Length(min=5, max=200)])
    occupation = StringField('Occupation', validators=[DataRequired(), Length(min=2, max=100)])
    reason_for_joining = TextAreaField('Why do you want to join our group?', 
                                     validators=[DataRequired(), Length(min=20, max=500)])

class TwoFactorForm(FlaskForm):
    otp_code = StringField('Enter 6-digit OTP Code', validators=[DataRequired(), Length(min=6, max=6)])

class TwoFactorSetupForm(FlaskForm):
    phone_number = StringField('Phone Number for OTP', validators=[DataRequired(), Length(min=10, max=20)])
    email = StringField('Email for OTP', validators=[Optional(), Email()])

class MemberForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=100)])
    full_name = StringField('Full Name', validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    phone = StringField('Phone Number', validators=[DataRequired(), Length(min=10, max=20)])
    role = SelectField('Role', choices=[
        ('Member', 'Member'),
        ('Secretary', 'Secretary'),
        ('Treasurer', 'Treasurer'),
        ('Chairman', 'Chairman'),
        ('Admin', 'Admin')
    ], validators=[DataRequired()])
    password = PasswordField('Password', validators=[Optional(), Length(min=6)])
    profile_picture = FileField('Profile Picture', validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png'], 'Only JPG, JPEG, and PNG images are allowed!')
    ])

class ContributionForm(FlaskForm):
    member_id = SelectField('Member', choices=[], validators=[DataRequired()], coerce=int)
    amount = FloatField('Amount', validators=[DataRequired(), NumberRange(min=0.01)])
    contribution_type = SelectField('Type', choices=[
        ('Regular', 'Regular Savings'),
        ('Special', 'Special Savings')
    ], default='Regular')
    notes = TextAreaField('Notes', validators=[Optional()])

class LoanApplicationForm(FlaskForm):
    loan_type = SelectField('Loan Type', choices=[
        ('Internal', 'Internal Loan (Member)'),
        ('External', 'External Loan (Non-Member)')
    ], validators=[DataRequired()])
    loan_category = SelectField('Loan Category', choices=[
        ('Short-term', 'Short-term (1-6 months) - 15% Interest'),
        ('Long-term', 'Long-term (7-24 months) - 20% Interest'),
        ('Emergency', 'Emergency Loan - 10% Interest')
    ], validators=[DataRequired()])
    emergency_type = SelectField('Emergency Type', choices=[
        ('', 'Select Emergency Type'),
        ('Medical', 'Medical Emergency'),
        ('Family', 'Family Emergency'),
        ('Business', 'Business Emergency'),
        ('Education', 'Education Emergency')
    ], validators=[Optional()])
    amount = FloatField('Loan Amount (KSh)', validators=[DataRequired(), NumberRange(min=1, max=1000000)], 
                       render_kw={"placeholder": "Enter amount between 1 and 1,000,000"})
    purpose = TextAreaField('Purpose of Loan', validators=[DataRequired(), Length(min=20)], 
                           render_kw={"placeholder": "Explain in detail how you plan to use this loan and how you will repay it", "rows": 4})
    duration_months = SelectField('Repayment Duration', choices=[
        ('1', '1 Month'),
        ('2', '2 Months'), 
        ('3', '3 Months'),
        ('6', '6 Months'),
        ('12', '12 Months'),
        ('18', '18 Months'),
        ('24', '24 Months')
    ], default='3', validators=[DataRequired()])
    
    # Personal Information
    occupation = StringField('Occupation', validators=[Optional(), Length(max=100)])
    monthly_income = FloatField('Monthly Income (KSh)', validators=[Optional(), NumberRange(min=0)])
    
    # External loan fields
    guarantor_id = SelectField('Guarantor (Member)', choices=[], validators=[Optional()], coerce=int)
    kra_pin = StringField('KRA PIN', validators=[Optional(), Length(max=11)], 
                         render_kw={"placeholder": "A123456789B"})
    id_number = StringField('ID Number', validators=[Optional(), Length(max=10)], 
                           render_kw={"placeholder": "12345678"})
    borrower_phone = StringField('Phone Number', validators=[Optional(), Length(min=10, max=15)], 
                                render_kw={"placeholder": "254700000000"})
    borrower_name = StringField('Borrower Full Name', validators=[Optional(), Length(max=100)])
    borrower_address = TextAreaField('Physical Address', validators=[Optional()],
                                   render_kw={"placeholder": "Complete physical address"})
    signature_consent = BooleanField('I consent to this loan application and agree to the terms and conditions', 
                                   validators=[DataRequired(message="You must consent to proceed")])

    def validate_guarantor_id(self, field):
        if self.loan_type.data == 'External' and (not field.data or field.data == 0):
            raise ValidationError('A guarantor is required for external loans')

class LoanApprovalForm(FlaskForm):
    amount = FloatField('Approved Amount', validators=[DataRequired(), NumberRange(min=1)])
    interest_rate = FloatField('Interest Rate (%)', validators=[DataRequired(), NumberRange(min=0, max=100)], default=20.0)
    duration_months = SelectField('Duration', choices=[
        ('1', '1 Month'),
        ('2', '2 Months'),
        ('3', '3 Months'),
        ('6', '6 Months'),
        ('12', '12 Months')
    ], default='3', validators=[DataRequired()])
    status = SelectField('Decision', choices=[
        ('Active', 'Approve Loan'),
        ('Rejected', 'Reject Loan')
    ], validators=[DataRequired()])
    approval_notes = TextAreaField('Approval/Rejection Notes', validators=[Optional()],
                                 render_kw={"placeholder": "Add any notes about this decision"})

class LoanRepaymentForm(FlaskForm):
    loan_id = SelectField('Loan', choices=[], validators=[DataRequired()], coerce=int)
    amount = FloatField('Repayment Amount', validators=[DataRequired(), NumberRange(min=0.01)])

class FineForm(FlaskForm):
    member_id = SelectField('Member', choices=[], validators=[DataRequired()], coerce=int)
    amount = FloatField('Fine Amount', validators=[DataRequired(), NumberRange(min=0.01)])
    fine_type = SelectField('Type', choices=[
        ('Absence', 'Absence from Meeting'),
        ('Lateness', 'Lateness to Meeting'),
        ('Loan Default', 'Loan Default'),
        ('Other', 'Other')
    ], validators=[DataRequired()])
    reason = SelectField('Reason', choices=[
        ('Without Apology', 'Without Apology'),
        ('With Apology', 'With Apology'),
        ('Repeated Offense', 'Repeated Offense')
    ], validators=[DataRequired()])

class AnnouncementForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(min=5, max=200)])
    content = TextAreaField('Content', validators=[DataRequired(), Length(min=10)], widget=TextArea())
    is_urgent = BooleanField('Mark as Urgent')

class MeetingRecordForm(FlaskForm):
    title = StringField('Meeting Title', validators=[DataRequired(), Length(min=5, max=200)])
    date_held = DateField('Date Held', validators=[DataRequired()])
    agenda = TextAreaField('Agenda', validators=[Optional()], widget=TextArea())
    minutes = TextAreaField('Meeting Minutes', validators=[DataRequired(), Length(min=10)], widget=TextArea())
    attendees = TextAreaField('Attendees', validators=[Optional()], widget=TextArea())
    decisions = TextAreaField('Decisions Made', validators=[Optional()], widget=TextArea())

class SettlementForm(FlaskForm):
    amount = FloatField('Settlement Amount', validators=[DataRequired(), NumberRange(min=0.01)])
    payment_method = SelectField('Payment Method', choices=[
        ('cash', 'Cash'),
        ('mpesa', 'M-Pesa'),
        ('bank_transfer', 'Bank Transfer')
    ], validators=[DataRequired()])
    transaction_reference = StringField('Transaction Reference', validators=[Optional(), Length(max=100)])

class WelfareContributionForm(FlaskForm):
    member_id = SelectField('Member', choices=[], validators=[DataRequired()], coerce=int)
    amount = FloatField('Welfare Contribution Amount', validators=[DataRequired(), NumberRange(min=0.01)])
    notes = TextAreaField('Notes', validators=[Optional()])

class VotingProposalForm(FlaskForm):
    title = StringField('Proposal Title', validators=[DataRequired(), Length(min=5, max=200)])
    description = TextAreaField('Description', validators=[DataRequired(), Length(min=10)], widget=TextArea())
    proposal_type = SelectField('Type', choices=[
        ('policy', 'Policy Change'),
        ('financial', 'Financial Decision'),
        ('member', 'Member Issue'),
        ('project', 'New Project')
    ], validators=[DataRequired()])
    voting_start = DateTimeField('Voting Start', validators=[DataRequired()], format='%Y-%m-%dT%H:%M')
    voting_end = DateTimeField('Voting End', validators=[DataRequired()], format='%Y-%m-%dT%H:%M')
    minimum_participation = FloatField('Minimum Participation (%)', validators=[DataRequired(), NumberRange(min=1, max=100)], default=50.0)

class VoteForm(FlaskForm):
    vote_choice = SelectField('Your Vote', choices=[
        ('yes', 'Yes'),
        ('no', 'No'),
        ('abstain', 'Abstain')
    ], validators=[DataRequired()])
    comment = TextAreaField('Comment (Optional)', validators=[Optional()], widget=TextArea())

class DocumentForm(FlaskForm):
    title = StringField('Document Title', validators=[DataRequired(), Length(min=3, max=200)])
    file = FileField('File', validators=[
        DataRequired(),
        FileAllowed(['pdf', 'doc', 'docx', 'txt', 'jpg', 'jpeg', 'png'], 'Invalid file type!')
    ])
    category = SelectField('Category', choices=[
        ('Constitution', 'Constitution'),
        ('Certificate', 'Certificate'),
        ('Forms', 'Forms'),
        ('Reports', 'Reports'),
        ('General', 'General')
    ], default='General')
    description = TextAreaField('Description', validators=[Optional()], widget=TextArea())

class ProjectForm(FlaskForm):
    name = StringField('Project Name', validators=[DataRequired(), Length(min=3, max=200)])
    description = TextAreaField('Description', validators=[DataRequired(), Length(min=10)], widget=TextArea())
    status = SelectField('Status', choices=[
        ('Planned', 'Planned'),
        ('Ongoing', 'Ongoing'),
        ('Completed', 'Completed')
    ], default='Planned')
    budget = FloatField('Budget', validators=[Optional(), NumberRange(min=0)], default=0.0)
    start_date = DateField('Start Date', validators=[Optional()])
    end_date = DateField('End Date', validators=[Optional()])

class PasswordChangeForm(FlaskForm):
    current_password = PasswordField('Current Password', validators=[DataRequired()])
    new_password = PasswordField('New Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm New Password', validators=[DataRequired()])

class MembershipApplicationForm(FlaskForm):
    full_name = StringField('Full Name', validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField('Email Address', validators=[DataRequired(), Email()])
    phone = StringField('Phone Number', validators=[DataRequired(), Length(min=10, max=20)])
    id_number = StringField('ID Number', validators=[DataRequired(), Length(min=7, max=10)])
    location = StringField('Location/Address', validators=[DataRequired(), Length(min=5, max=200)])
    occupation = StringField('Occupation', validators=[DataRequired(), Length(min=2, max=100)])
    reason_for_joining = TextAreaField('Why do you want to join our SHG?', 
                                     validators=[DataRequired(), Length(min=20)], 
                                     widget=TextArea())

class DeletionForm(FlaskForm):
    reason = TextAreaField('Reason for Deletion', validators=[DataRequired(), Length(min=10)],
                         render_kw={"placeholder": "Provide a detailed reason for this deletion"})
    confirm_deletion = BooleanField('I confirm this deletion', validators=[DataRequired()])

class PaymentForm(FlaskForm):
    payment_type = SelectField('Payment Type', choices=[
        ('loan_repayment', 'Loan Repayment'),
        ('fine_payment', 'Fine Payment'),
        ('contribution', 'Contribution Payment')
    ], validators=[DataRequired()])
    reference_id = SelectField('Reference', choices=[], validators=[DataRequired()], coerce=int)
    amount = FloatField('Amount', validators=[DataRequired(), NumberRange(min=0.01)])
    payment_method = SelectField('Payment Method', choices=[
        ('cash', 'Cash'),
        ('mpesa', 'M-Pesa'),
        ('bank_transfer', 'Bank Transfer')
    ], validators=[DataRequired()])
    transaction_reference = StringField('Transaction Reference', validators=[Optional()],
                                      render_kw={"placeholder": "M-Pesa code, bank reference, etc."})

class WelfareContributionForm(FlaskForm):
    member_id = SelectField('Member', choices=[], validators=[DataRequired()], coerce=int)
    amount = FloatField('Amount', validators=[DataRequired(), NumberRange(min=0.01)])
    notes = TextAreaField('Notes', validators=[Optional()])

class WelfareExpenseForm(FlaskForm):
    beneficiary_id = SelectField('Beneficiary', choices=[], validators=[DataRequired()], coerce=int)
    amount = FloatField('Amount', validators=[DataRequired(), NumberRange(min=0.01)])
    expense_type = SelectField('Expense Type', choices=[
        ('funeral', 'Funeral Support'),
        ('medical', 'Medical Emergency'),
        ('education', 'Education Support'),
        ('business', 'Business Emergency'),
        ('family', 'Family Emergency'),
        ('other', 'Other')
    ], validators=[DataRequired()])
    description = TextAreaField('Description', validators=[DataRequired(), Length(min=10)])

class VotingProposalForm(FlaskForm):
    title = StringField('Proposal Title', validators=[DataRequired(), Length(min=5, max=200)])
    description = TextAreaField('Proposal Description', validators=[DataRequired(), Length(min=20)])
    proposal_type = SelectField('Type', choices=[
        ('policy', 'Policy Change'),
        ('financial', 'Financial Decision'),
        ('member', 'Member Related'),
        ('project', 'Project Proposal')
    ], validators=[DataRequired()])
    voting_start = DateTimeField('Voting Start', validators=[DataRequired()])
    voting_end = DateTimeField('Voting End', validators=[DataRequired()])
    minimum_participation = FloatField('Minimum Participation (%)', 
                                     validators=[DataRequired(), NumberRange(min=10, max=100)], 
                                     default=50.0)

class VoteForm(FlaskForm):
    vote_choice = SelectField('Your Vote', choices=[
        ('yes', 'Yes - I Support'),
        ('no', 'No - I Oppose'),
        ('abstain', 'Abstain')
    ], validators=[DataRequired()])
    comment = TextAreaField('Comment (Optional)', validators=[Optional()])
