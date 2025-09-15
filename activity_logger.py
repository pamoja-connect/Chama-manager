import logging
import os
from datetime import datetime
from flask import request, current_app
from flask_login import current_user, login_required
from app import db
from models import ActivityLog, Loan, Contribution, Fine, Announcement, User, WelfareContribution
import json
from werkzeug.utils import secure_filename

# Configure activity logger
# activity_logger = logging.getLogger('activity')
# handler = logging.FileHandler('activity.log')
# formatter = logging.Formatter('%(asctime)s - %(message)s')
# handler.setFormatter(formatter)
# activity_logger.addHandler(handler)
# activity_logger.setLevel(logging.INFO)

# Simple file-based activity logger since ActivityLog model doesn't exist
def log_activity(action, resource_type, resource_id, details):
    """Log user activity to file."""
    try:
        # Create logs directory if it doesn't exist
        log_dir = os.path.join(current_app.root_path, 'logs')
        os.makedirs(log_dir, exist_ok=True)

        log_file = os.path.join(log_dir, 'activity.log')

        user_name = current_user.full_name if current_user.is_authenticated else 'System'
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

        log_entry = f"[{timestamp}] {user_name} {action} {resource_type} {resource_id}: {details}\n"

        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(log_entry)

    except Exception as e:
        print(f"Activity logging failed: {e}")

def get_recent_activities(limit=50):
    """Get recent activities from file."""
    try:
        log_file = os.path.join(current_app.root_path, 'logs', 'activity.log')

        if not os.path.exists(log_file):
            return []

        activities = []
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # Get last 'limit' lines
        recent_lines = lines[-limit:] if len(lines) >= limit else lines
        recent_lines.reverse()  # Most recent first

        for line in recent_lines:
            if line.strip():
                activities.append({
                    'timestamp': line[:20],  # Extract timestamp
                    'details': line[21:].strip()  # Extract details
                })

        return activities

    except Exception as e:
        print(f"Failed to read activity log: {e}")
        return []

def clear_activity_log():
    """Clear all activity logs (Admin only)."""
    try:
        log_file = os.path.join(current_app.root_path, 'logs', 'activity.log')

        if os.path.exists(log_file):
            os.remove(log_file)

        # Log the clearing action
        log_activity('cleared', 'activity_log', 'all', 'Activity log cleared by admin')
        return True

    except Exception as e:
        print(f"Failed to clear activity log: {e}")
        return False

# Placeholder for WhatsApp Reminders - To be implemented
def send_whatsapp_reminder(user_id, message):
    """Placeholder function for sending WhatsApp reminders."""
    print(f"Sending WhatsApp reminder to user {user_id}: {message}")
    # Actual WhatsApp API integration would go here

# Placeholder for deletion of data on loans
def delete_loan_data(loan_id):
    """Deletes a loan record."""
    try:
        loan = Loan.query.get(loan_id)
        if loan:
            # Log activity before deletion
            log_activity('deleted', 'Loan', loan_id, f"Loan for user {loan.user_id} deleted.")
            db.session.delete(loan)
            db.session.commit()
            return True
        return False
    except Exception as e:
        print(f"Error deleting loan data: {e}")
        return False

# Placeholder for deletion of data on contributions
def delete_contribution_data(contribution_id):
    """Deletes a contribution record."""
    try:
        contribution = Contribution.query.get(contribution_id)
        if contribution:
            # Log activity before deletion
            log_activity('deleted', 'Contribution', contribution_id, f"Contribution by user {contribution.user_id} deleted.")
            db.session.delete(contribution)
            db.session.commit()
            return True
        return False
    except Exception as e:
        print(f"Error deleting contribution data: {e}")
        return False

# Placeholder for deletion of data on fines
def delete_fine_data(fine_id):
    """Deletes a fine record."""
    try:
        fine = Fine.query.get(fine_id)
        if fine:
            # Log activity before deletion
            log_activity('deleted', 'Fine', fine_id, f"Fine for user {fine.user_id} deleted.")
            db.session.delete(fine)
            db.session.commit()
            return True
        return False
    except Exception as e:
        print(f"Error deleting fine data: {e}")
        return False

# Placeholder for deletion of data on welfare
def delete_welfare_data(welfare_id):
    """Deletes a welfare record."""
    try:
        welfare = Welfare.query.get(welfare_id)
        if welfare:
            # Log activity before deletion
            log_activity('deleted', 'Welfare', welfare_id, f"Welfare record {welfare.name} deleted.")
            db.session.delete(welfare)
            db.session.commit()
            return True
        return False
    except Exception as e:
        print(f"Error deleting welfare data: {e}")
        return False

# Placeholder for deletion of data on announcements
def delete_announcement_data(announcement_id):
    """Deletes an announcement record."""
    try:
        announcement = Announcement.query.get(announcement_id)
        if announcement:
            # Log activity before deletion
            log_activity('deleted', 'Announcement', announcement_id, f"Announcement '{announcement.title}' deleted.")
            db.session.delete(announcement)
            db.session.commit()
            return True
        return False
    except Exception as e:
        print(f"Error deleting announcement data: {e}")
        return False


def upload_document_handler():
    """Handles document uploads, including logging and error handling."""
    if 'file' not in request.files:
        return {'message': 'No file part in the request'}, 400
    file = request.files['file']
    if file.filename == '':
        return {'message': 'No selected file'}, 400

    if file:
        try:
            filename = secure_filename(file.filename)
            # Save file to a designated upload folder
            # In a real app, you'd have an upload folder configured
            upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
            os.makedirs(upload_folder, exist_ok=True)
            filepath = os.path.join(upload_folder, filename)
            file.save(filepath)

            # Log the successful upload
            log_activity('uploaded', 'Document', filename, f"Document '{filename}' uploaded successfully.")

            return {'message': 'Document uploaded successfully', 'filename': filename}, 200
        except Exception as e:
            # Log the error during upload
            log_activity('upload_failed', 'Document', file.filename or 'N/A', f"Failed to upload document: {e}")
            return {'message': f'Error uploading document: {e}'}, 500
    return {'message': 'Invalid file'}, 400

# Function to handle proposal voting dates
def parse_voting_dates(voting_start_str, voting_end_str):
    """Parses and validates voting start and end dates."""
    try:
        # Attempt to parse with common date and time formats
        # You might need to adjust these formats based on how the dates are entered
        formats_to_try = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%m/%d/%Y %H:%M:%S",
            "%m/%d/%Y %H:%M",
            "%m/%d/%Y",
        ]
        
        voting_start = None
        for fmt in formats_to_try:
            try:
                voting_start = datetime.strptime(voting_start_str, fmt)
                break
            except ValueError:
                continue
        
        if not voting_start:
            raise ValueError("Invalid format for 'Voting Start'. Please use YYYY-MM-DD HH:MM:SS or similar.")

        voting_end = None
        for fmt in formats_to_try:
            try:
                voting_end = datetime.strptime(voting_end_str, fmt)
                break
            except ValueError:
                continue
        
        if not voting_end:
            raise ValueError("Invalid format for 'Voting End'. Please use YYYY-MM-DD HH:MM:SS or similar.")

        if voting_start >= voting_end:
            raise ValueError("'Voting Start' must be before 'Voting End'.")
            
        return voting_start, voting_end

    except ValueError as ve:
        print(f"Date parsing error: {ve}")
        return None, None
    except Exception as e:
        print(f"An unexpected error occurred during date parsing: {e}")
        return None, None


# Mock function for sharing the app (e.g., via link)
def share_app_link():
    """Generates a shareable link for the application."""
    # In a real scenario, this would be a deep link or a web link to the app
    return {"link": "https://your-app-domain.com/download"}

# Mock function for prompting to install the app on a browser (PWA)
def prompt_install_app_on_browser():
    """Simulates prompting the user to install the app (PWA)."""
    # This is typically handled by service workers and manifest files for PWAs
    return {"message": "Prompt user to install app via PWA"}

# Mock function for app icon/badge visibility when downloaded
def app_icon_badge_visibility():
    """Describes how app icon/badge visibility is handled when downloaded."""
    # This is controlled by the operating system and the app's manifest/build settings
    return {"message": "App icon/badge visibility is managed by the OS and app configuration."}

# Proposal flow explanation
def proposal_flow_explanation():
    """Explains the proposal flow and voting date fields."""
    explanation = {
        "proposal_flow": "A proposal is a suggestion or plan that requires community approval. Members can create proposals, and other members can vote on them. The process typically involves creating a proposal, setting a voting period, and then tallying the votes.",
        "voting_start_field": "The 'Voting Start' field indicates the date and time when voting on a proposal officially begins. Votes cast before this time will not be counted.",
        "voting_end_field": "The 'Voting End' field indicates the date and time when voting on a proposal officially concludes. Votes cast after this time will not be counted.",
        "date_format_guidance": "Please ensure you enter dates and times in a recognized format, such as YYYY-MM-DD HH:MM:SS or MM/DD/YYYY HH:MM. The system will attempt to parse common formats."
    }
    return explanation

# Offline access check - placeholder
def check_offline_access():
    """Checks the status of offline access functionality."""
    # This would involve checking if a service worker is active and caching is working
    # For now, a simple status message
    return {"status": "Offline access functionality check required. Implementation details depend on PWA setup."}

# Mock functions for loan/request approval modals
def approve_loan(loan_id):
    """Approves a loan request."""
    try:
        loan = Loan.query.get(loan_id)
        if loan and loan.status == 'pending':
            loan.status = 'approved'
            # Log the approval action
            log_activity('approved', 'Loan', loan_id, f"Loan for user {loan.user_id} approved.")
            db.session.commit()
            return {"message": "Loan approved successfully."}
        elif loan and loan.status == 'approved':
            return {"message": "Loan is already approved."}
        else:
            return {"message": "Loan not found or in an invalid state."}, 404
    except Exception as e:
        print(f"Error approving loan: {e}")
        log_activity('approval_failed', 'Loan', loan_id, f"Failed to approve loan: {e}")
        return {"message": f"Error approving loan: {e}"}, 500

def reject_loan(loan_id, reason=""):
    """Rejects a loan request."""
    try:
        loan = Loan.query.get(loan_id)
        if loan and loan.status == 'pending':
            loan.status = 'rejected'
            loan.rejection_reason = reason
            # Log the rejection action
            log_activity('rejected', 'Loan', loan_id, f"Loan for user {loan.user_id} rejected. Reason: {reason}")
            db.session.commit()
            return {"message": "Loan rejected successfully."}
        elif loan and loan.status == 'rejected':
            return {"message": "Loan is already rejected."}
        else:
            return {"message": "Loan not found or in an invalid state."}, 404
    except Exception as e:
        print(f"Error rejecting loan: {e}")
        log_activity('rejection_failed', 'Loan', loan_id, f"Failed to reject loan: {e}")
        return {"message": f"Error rejecting loan: {e}"}, 500

def approve_new_member_request(request_id):
    """Approves a new member request."""
    try:
        user_request = User.query.get(request_id) # Assuming User model holds member requests
        if user_request and user_request.status == 'pending_approval':
            user_request.status = 'approved'
            # Log the approval action
            log_activity('approved', 'MemberRequest', request_id, f"New member request for user {user_request.username} approved.")
            db.session.commit()
            return {"message": "Member request approved successfully."}
        elif user_request and user_request.status == 'approved':
            return {"message": "Member request already approved."}
        else:
            return {"message": "Member request not found or in an invalid state."}, 404
    except Exception as e:
        print(f"Error approving new member request: {e}")
        log_activity('approval_failed', 'MemberRequest', request_id, f"Failed to approve member request: {e}")
        return {"message": f"Error approving member request: {e}"}, 500

def reject_new_member_request(request_id, reason=""):
    """Rejects a new member request."""
    try:
        user_request = User.query.get(request_id) # Assuming User model holds member requests
        if user_request and user_request.status == 'pending_approval':
            user_request.status = 'rejected'
            user_request.rejection_reason = reason
            # Log the rejection action
            log_activity('rejected', 'MemberRequest', request_id, f"New member request for user {user_request.username} rejected. Reason: {reason}")
            db.session.commit()
            return {"message": "Member request rejected successfully."}
        elif user_request and user_request.status == 'rejected':
            return {"message": "Member request already rejected."}
        else:
            return {"message": "Member request not found or in an invalid state."}, 404
    except Exception as e:
        print(f"Error rejecting new member request: {e}")
        log_activity('rejection_failed', 'MemberRequest', request_id, f"Failed to reject member request: {e}")
        return {"message": f"Error rejecting member request: {e}"}, 500

# CSRF token handling for delete actions and general form submissions
# Assumes CSRF protection is enabled in Flask app configuration
# and CSRF token is included in templates.

# Example of how a delete endpoint might use CSRF protection:
# @app.route('/delete_item/<int:item_id>', methods=['POST'])
# @login_required
# @csrf.exempt  # Temporarily exempt if CSRF token is missing, but better to fix the token issue
# def delete_item(item_id):
#     if not current_user.is_admin(): # Example admin check
#         return {"message": "Forbidden: Only admins can delete items."}, 403
#
#     # Perform deletion logic here based on item_id and entity_type
#     # e.g., delete_loan_data(item_id), delete_contribution_data(item_id), etc.
#
#     # Log the action
#     log_activity('deleted', 'Item', item_id, f"Item {item_id} deleted by admin.")
#
#     return {"message": "Item deleted successfully."}, 200

# To fix the 'CSRF token is missing' error, ensure:
# 1. CSRF token is generated and included in all forms that submit data (POST, PUT, DELETE).
# 2. The token is sent with the request, often in a hidden input field or header.
# 3. Flask-WTF or Flask-CSRFPlus is properly configured.

# If using JavaScript for AJAX requests, the token might need to be sent in headers:
# $.ajaxSetup({
#     headers: {
#         'X-CSRFToken': $('meta[name="csrf-token"]').attr('content')
#     }
# });

# For API endpoints that don't use forms, you might need to pass the CSRF token
# in the request header as well.
