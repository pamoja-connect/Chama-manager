
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (StringField, TextAreaField, FloatField, SelectField,
                     DateTimeField, BooleanField, PasswordField, DateField,
                     IntegerField, SelectMultipleField)
from wtforms.validators import DataRequired, Email, EqualTo, Length, NumberRange, Optional, ValidationError
from wtforms.widgets import TextArea


class LoginForm(FlaskForm):
    username = SelectField('Username', choices=[], validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])


class PasswordResetRequestForm(FlaskForm):
    email = StringField('Email address', validators=[DataRequired(), Email(), Length(max=120)])


class PasswordResetForm(FlaskForm):
    password = PasswordField(
        'New password',
        validators=[DataRequired(), Length(min=12, max=128)],
        render_kw={"autocomplete": "new-password"},
    )
    confirm_password = PasswordField(
        'Confirm new password',
        validators=[DataRequired(), EqualTo('password', message='Passwords must match.')],
        render_kw={"autocomplete": "new-password"},
    )


class DeletionForm(FlaskForm):
    reason = TextAreaField('Reason for Deletion', validators=[DataRequired(), Length(min=5, max=500)],
                           render_kw={"placeholder": "Please provide a reason for deletion..."})
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
    # Accept both HTML datetime-local format and ISO format
    voting_start = DateTimeField('Voting Start', format=['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'],
                                  validators=[DataRequired()])
    voting_end = DateTimeField('Voting End', format=['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'],
                                validators=[DataRequired()])
    minimum_participation = FloatField('Minimum Participation (%)', validators=[DataRequired(), NumberRange(min=1, max=100)])


class VoteForm(FlaskForm):
    vote_choice = SelectField('Your Vote', choices=[
        ('yes', 'Yes - I support this proposal'),
        ('no', 'No - I oppose this proposal'),
        ('abstain', 'Abstain - I prefer not to vote')
    ], validators=[DataRequired()])
    comment = TextAreaField('Comment (Optional)', validators=[Optional(), Length(max=500)])


class LoanApplicationForm(FlaskForm):
    amount = FloatField('Loan Amount (KSh)', validators=[DataRequired(), NumberRange(min=100)])
    purpose = TextAreaField('Purpose of Loan', validators=[DataRequired(), Length(min=10, max=500)])
    duration_months = SelectField('Duration (Months)', choices=[
        ('3', '3 Months'), ('6', '6 Months'), ('12', '12 Months'),
        ('18', '18 Months'), ('24', '24 Months')
    ], validators=[DataRequired()])
    loan_type = SelectField('Loan Type', choices=[
        ('Internal', 'Internal (Member)'), ('External', 'External (Non-member)')
    ], default='Internal', validators=[DataRequired()])
    loan_category = SelectField('Loan Category', choices=[
        ('Short-term', 'Short-term (≤ 6 months)'), ('Long-term', 'Long-term (> 6 months)'),
        ('Emergency', 'Emergency Loan')
    ], default='Short-term', validators=[DataRequired()])
    emergency_type = SelectField('Emergency Type', choices=[
        ('', 'Select Emergency Type'), ('Medical', 'Medical Emergency'),
        ('Family', 'Family Emergency'), ('Business', 'Business Emergency'),
        ('Education', 'Education Emergency'), ('Other', 'Other Emergency')
    ], validators=[Optional()])
    repayment_mode = SelectField('Preferred Repayment Mode', choices=[
        ('monthly', 'Monthly'), ('weekly', 'Weekly'), ('lump_sum', 'Lump Sum')
    ], default='monthly', validators=[DataRequired()])
    guarantor_id = SelectField('Guarantor (External Loans)', choices=[], validators=[Optional()])
    occupation = StringField('Occupation', validators=[Optional(), Length(max=100)])
    monthly_income = FloatField('Monthly Income (KSh)', validators=[Optional(), NumberRange(min=0)])


class LoanApprovalForm(FlaskForm):
    amount = FloatField('Approved Amount (KSh)', validators=[DataRequired(), NumberRange(min=100)])
    interest_rate = FloatField('Interest Rate (%)', validators=[DataRequired(), NumberRange(min=0, max=50)])
    duration_months = SelectField('Duration (Months)', choices=[
        ('3', '3 Months'), ('6', '6 Months'), ('12', '12 Months'),
        ('18', '18 Months'), ('24', '24 Months')
    ], validators=[DataRequired()])
    repayment_mode = SelectField('Repayment Mode', choices=[
        ('monthly', 'Monthly'), ('weekly', 'Weekly'), ('lump_sum', 'Lump Sum')
    ], default='monthly', validators=[DataRequired()])
    status = SelectField('Decision', choices=[
        ('Active', 'Approve'), ('Rejected', 'Reject')
    ], validators=[DataRequired()])
    approval_notes = TextAreaField('Approval Notes / Terms', validators=[Optional(), Length(max=1000)])
    rejection_reason = TextAreaField('Rejection Reason', validators=[Optional(), Length(max=500)])


class LoanRepaymentForm(FlaskForm):
    loan_id = SelectField('Select Loan', choices=[], validators=[DataRequired()])
    amount = FloatField('Repayment Amount (KSh)', validators=[DataRequired(), NumberRange(min=1)])
    payment_method = SelectField('Payment Method', choices=[
        ('cash', 'Cash'), ('mpesa', 'M-Pesa'), ('bank_transfer', 'Bank Transfer')
    ], default='cash', validators=[DataRequired()])
    bank_name = StringField('Bank Name', validators=[Optional(), Length(max=100)])
    transaction_reference = StringField('M-Pesa / Bank Reference', validators=[Optional(), Length(max=100)])


class ContributionForm(FlaskForm):
    member_id = SelectField('Member', choices=[], validators=[DataRequired()])
    amount = FloatField('Amount (KSh)', validators=[DataRequired(), NumberRange(min=1)])
    contribution_type = SelectField('Type', choices=[
        ('Regular', 'Regular Contribution'), ('Special', 'Special Contribution')
    ], validators=[DataRequired()])
    payment_method = SelectField('Payment Method', choices=[
        ('cash', 'Cash'), ('mpesa', 'M-Pesa'), ('bank_transfer', 'Bank Transfer')
    ], default='cash', validators=[DataRequired()])
    bank_name = StringField('Bank Name', validators=[Optional(), Length(max=100)])
    transaction_reference = StringField('M-Pesa / Bank Reference No.', validators=[Optional(), Length(max=100)])
    notes = TextAreaField('Notes', validators=[Optional(), Length(max=200)])


class FineForm(FlaskForm):
    member_id = SelectField('Member', choices=[], validators=[DataRequired()])
    amount = FloatField('Fine Amount (KSh)', validators=[DataRequired(), NumberRange(min=1)])
    fine_type = SelectField('Fine Type', choices=[
        ('Absence', 'Meeting Absence'), ('Lateness', 'Lateness'),
        ('Misconduct', 'Misconduct'), ('Late Payment', 'Late Payment'), ('Other', 'Other')
    ], validators=[DataRequired()])
    reason = SelectField('Reason', choices=[
        ('With Apology', 'With Apology'), ('Without Apology', 'Without Apology'),
        ('Repeat Offense', 'Repeat Offense'), ('Other', 'Other')
    ], validators=[DataRequired()])


class AnnouncementForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(min=5, max=200)])
    content = TextAreaField('Content', validators=[DataRequired(), Length(min=10, max=2000)])
    is_urgent = BooleanField('Mark as Urgent')


class MeetingRecordForm(FlaskForm):
    title = StringField('Meeting Title', validators=[DataRequired(), Length(min=5, max=200)])
    date_held = DateField('Date Held', validators=[DataRequired()])
    agenda = TextAreaField('Agenda', validators=[Optional(), Length(max=1000)])
    minutes = TextAreaField('Meeting Minutes', validators=[DataRequired(), Length(min=10, max=2000)])
    # Multi-select of member IDs; route converts to names
    attendee_ids = SelectMultipleField('Attendees (select members)', choices=[], validators=[Optional()])
    decisions = TextAreaField('Decisions Made', validators=[Optional(), Length(max=1000)])


class DocumentForm(FlaskForm):
    title = StringField('Document Title', validators=[DataRequired(), Length(min=3, max=200)])
    description = TextAreaField('Description', validators=[Optional(), Length(max=500)])
    category = SelectField('Category', choices=[
        ('General', 'General'), ('Financial', 'Financial'), ('Legal', 'Legal'),
        ('Meeting', 'Meeting Records'), ('Policy', 'Policy Documents')
    ], validators=[DataRequired()])
    file = FileField('File', validators=[DataRequired(), FileAllowed(['pdf', 'doc', 'docx', 'txt', 'jpg', 'jpeg', 'png'])])


class PasswordChangeForm(FlaskForm):
    current_password = PasswordField('Current Password', validators=[DataRequired()])
    new_password = PasswordField('New Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm New Password', validators=[DataRequired()])

    def validate_confirm_password(self, field):
        if field.data != self.new_password.data:
            raise ValidationError('Passwords do not match')


class MemberForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=100)])
    full_name = StringField('Full Name', validators=[DataRequired(), Length(min=3, max=100)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    phone = StringField('Phone Number', validators=[DataRequired(), Length(min=10, max=20)])
    role = SelectField('Role', choices=[
        ('Member', 'Member'), ('Secretary', 'Secretary'), ('Treasurer', 'Treasurer'),
        ('Chairman', 'Chairman'), ('Admin', 'Admin')
    ], validators=[DataRequired()])
    password = PasswordField('Password', validators=[Optional(), Length(min=6)])
    profile_picture = FileField('Profile Picture', validators=[Optional(), FileAllowed(['jpg', 'jpeg', 'png'])])


class MembershipApplicationForm(FlaskForm):
    full_name = StringField('Full Name', validators=[DataRequired(), Length(min=3, max=100)])
    email = StringField('Email Address', validators=[DataRequired(), Email()])
    phone = StringField('Phone Number', validators=[DataRequired(), Length(min=10, max=20)])
    id_number = StringField('ID Number / Passport Number', validators=[DataRequired(), Length(min=5, max=20)])
    location = StringField('Location / Address', validators=[DataRequired(), Length(min=5, max=200)])
    occupation = StringField('Occupation', validators=[DataRequired(), Length(min=2, max=100)])
    reason_for_joining = TextAreaField('Reason for Joining', validators=[DataRequired(), Length(min=10, max=1000)])
    id_document = FileField('ID/Passport Photo', validators=[
        Optional(), FileAllowed(['jpg', 'jpeg', 'png', 'pdf'], 'Images and PDF only')
    ])
    group_code = StringField('Group Registration Code (optional)', validators=[Optional(), Length(max=20)])


class GroupRegistrationForm(FlaskForm):
    name = StringField('Group Name', validators=[DataRequired(), Length(min=3, max=200)])
    description = TextAreaField('Group Description', validators=[Optional(), Length(max=1000)])
    contact_email = StringField('Contact Email', validators=[Optional(), Email()])
    contact_phone = StringField('Contact Phone', validators=[Optional(), Length(max=20)])
    location = StringField('Location', validators=[Optional(), Length(max=200)])
    year_established = StringField('Year Established', validators=[Optional(), Length(max=10)])
    logo = FileField('Group Logo', validators=[Optional(), FileAllowed(['jpg', 'jpeg', 'png'])])
    admin_full_name = StringField('Group Admin Full Name', validators=[DataRequired(), Length(min=3, max=100)])
    admin_email = StringField('Group Admin Email', validators=[DataRequired(), Email()])
    admin_phone = StringField('Group Admin Phone', validators=[DataRequired(), Length(min=10, max=20)])
    admin_password = PasswordField('Group Admin Password', validators=[DataRequired(), Length(min=6)])


class WelfareExpenseForm(FlaskForm):
    beneficiary_id = SelectField('Beneficiary Member', choices=[], validators=[DataRequired()])
    amount = FloatField('Amount (KSh)', validators=[DataRequired(), NumberRange(min=1)])
    expense_type = SelectField('Expense Type', choices=[
        ('Medical', 'Medical Assistance'), ('Funeral', 'Funeral Support'),
        ('Education', 'Education Support'), ('Emergency', 'Emergency Relief'),
        ('Other', 'Other')
    ], validators=[DataRequired()])
    description = TextAreaField('Description / Purpose', validators=[DataRequired(), Length(min=5, max=500)])


class InAppMessageForm(FlaskForm):
    recipient_id = SelectField('Send To', choices=[], validators=[DataRequired()])
    subject = StringField('Subject', validators=[DataRequired(), Length(min=3, max=200)])
    body = TextAreaField('Message', validators=[DataRequired(), Length(min=5, max=2000)])
    message_type = SelectField('Message Type', choices=[
        ('general', 'General Message'), ('savings_reminder', 'Savings Reminder'),
        ('loan_reminder', 'Loan Payment Reminder'), ('fine_reminder', 'Fine Reminder'),
        ('announcement', 'Announcement')
    ], default='general', validators=[DataRequired()])


class ProjectForm(FlaskForm):
    name = StringField('Project Name', validators=[DataRequired(), Length(min=3, max=200)])
    description = TextAreaField('Description', validators=[DataRequired(), Length(min=10, max=2000)])
    status = SelectField('Status', choices=[
        ('Planned', 'Planned'), ('Active', 'Active / In Progress'),
        ('Completed', 'Completed'), ('On Hold', 'On Hold')
    ], validators=[DataRequired()])
    budget = FloatField('Budget Amount (KSh)', validators=[Optional(), NumberRange(min=0)],
                        render_kw={"placeholder": "e.g. 50000"})
    start_date = DateField('Start Date', validators=[Optional()])
    end_date = DateField('End Date', validators=[Optional()])


class GroupEditForm(FlaskForm):
    name = StringField('Group Name', validators=[DataRequired(), Length(min=3, max=200)])
    description = TextAreaField('Group Description', validators=[Optional(), Length(max=1000)])
    contact_email = StringField('Contact Email', validators=[Optional(), Email()])
    contact_phone = StringField('Contact Phone', validators=[Optional(), Length(max=20)])
    location = StringField('Location', validators=[Optional(), Length(max=200)])
    year_established = StringField('Year Established', validators=[Optional(), Length(max=10)])
    logo = FileField('Group Logo', validators=[Optional(), FileAllowed(['jpg', 'jpeg', 'png'])])


class WelfareContributionForm(FlaskForm):
    member_id = SelectField('Member', choices=[], validators=[DataRequired()])
    amount = FloatField('Amount (KSh)', validators=[DataRequired(), NumberRange(min=1)])
    notes = TextAreaField('Notes', validators=[Optional(), Length(max=500)])


class PaymentForm(FlaskForm):
    payment_type = SelectField('Payment Type', choices=[
        ('loan_repayment', 'Loan Repayment'),
        ('contribution', 'Monthly Contribution'),
        ('fine', 'Fine Payment'),
        ('welfare', 'Welfare Contribution'),
        ('other', 'Other')
    ], validators=[DataRequired()])
    reference_id = SelectField('Reference (e.g. Loan)', choices=[], coerce=int, validators=[Optional()], validate_choice=False)
    amount = FloatField('Amount (KSh)', validators=[DataRequired(), NumberRange(min=1)])
    payment_method = SelectField('Payment Method', choices=[
        ('cash', 'Cash'), ('mpesa', 'M-Pesa'), ('bank_transfer', 'Bank Transfer')
    ], default='cash', validators=[DataRequired()])
    transaction_reference = StringField('M-Pesa / Bank Reference', validators=[Optional(), Length(max=100)])
