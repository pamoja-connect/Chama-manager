
import requests
from datetime import datetime, timedelta
from models import User, Loan, Fine
from utils import format_currency

def send_whatsapp_reminder(phone_number, message):
    """Send WhatsApp reminder (placeholder for actual WhatsApp API integration)."""
    # This would integrate with a WhatsApp Business API service
    # For now, we'll just log the reminder
    print(f"WhatsApp Reminder to {phone_number}: {message}")
    return True

def send_debt_reminders():
    """Send WhatsApp reminders to members with outstanding debts."""
    # Find members with active loans
    active_loans = Loan.query.filter_by(status='Active').all()
    
    for loan in active_loans:
        if loan.member and loan.due_date:
            days_until_due = (loan.due_date - datetime.now().date()).days
            
            if days_until_due <= 7 and days_until_due >= 0:  # Remind 7 days before due
                message = f"Dear {loan.member.full_name}, your loan of {format_currency(loan.remaining_amount)} is due in {days_until_due} days. Please arrange for repayment. - Pamoja Agencies SHG"
                send_whatsapp_reminder(loan.member.phone, message)
    
    # Find members with unpaid fines
    unpaid_fines = Fine.query.filter_by(is_paid=False).all()
    
    for fine in unpaid_fines:
        if fine.member:
            days_overdue = (datetime.now().date() - fine.date_issued.date()).days
            
            if days_overdue > 0:  # Send reminder for overdue fines
                message = f"Dear {fine.member.full_name}, you have an unpaid fine of {format_currency(fine.amount)} for {fine.fine_type}. Please settle this amount. - Pamoja Agencies SHG"
                send_whatsapp_reminder(fine.member.phone, message)

def schedule_daily_reminders():
    """This would be called by a cron job or scheduler."""
    send_debt_reminders()
