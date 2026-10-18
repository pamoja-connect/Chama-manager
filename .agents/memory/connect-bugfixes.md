---
name: CONNECT bug-fix decisions
description: Key non-obvious fixes and patterns for the CONNECT SHG platform bugs
---

## email-validator package
Install via pip: `pip install email-validator`. All Email() WTForms validators crash without it.
**Why:** Flask-WTF's Email() validator delegates to email-validator which is not installed by default.
**How to apply:** If any form with Email() validator crashes on POST, check if the package is installed first.

## from_json Jinja filter
Register BOTH as a Jinja filter AND as a context_processor variable:
- Filter: `app.jinja_env.filters['from_json'] = lambda s: json.loads(s) if s else {}`  (for `| from_json` pipe syntax)
- Context: already in context_processor as a callable (for `{{ from_json(x) }}` syntax)
**Why:** receipts.html uses `| from_json` pipe syntax which requires a registered Jinja filter, not just a context variable.

## WelfareExpenseForm
Fields needed: beneficiary_id (SelectField), amount (FloatField), expense_type (SelectField), description (TextAreaField).
**Why:** Route references it but it was never added to forms.py.

## DateTimeField format for voting
Use a format list to accept HTML datetime-local inputs:
`format=['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M']`
**Why:** HTML `<input type="datetime-local">` sends `YYYY-MM-DDTHH:MM` but WTForms default expects `YYYY-MM-DD HH:MM:SS`.

## Role permissions pattern
Many routes only checked `role != 'Admin'` but should also allow Chairman. Pattern:
`if current_user.role not in ['Admin', 'Chairman']:` for delete/pay actions.
Applies to: delete_fine, pay_fine, delete_announcement, delete_meeting.

## Mobile navigation — offcanvas sidebar
On mobile (<lg), use Bootstrap Offcanvas instead of collapse to avoid content hiding:
- Hamburger button: `data-bs-toggle="offcanvas" data-bs-target="#navOffcanvas" class="d-lg-none"`
- Desktop nav div: `class="d-none d-lg-flex align-items-center w-100"` (no collapse behavior)
- Offcanvas div: `class="offcanvas offcanvas-start d-lg-none"` with `data-bs-scroll="true"`
**Why:** Bootstrap collapse expands inline pushing content down on mobile; offcanvas overlays as sidebar.

## bank_name columns
Added to both `contribution` and `loan_repayment` tables via migration.
Model fields: `bank_name = db.Column(db.String(100))`. Form fields added to ContributionForm and LoanRepaymentForm.
Toggle in template: `display:none` unless payment_method === 'bank_transfer'.

## Meeting attendees — SelectMultipleField
MeetingRecordForm uses `attendee_ids = SelectMultipleField(choices=[])`.
Route populates choices from group members and converts selected IDs to comma-separated names stored in `meeting.attendees` (Text column).
**Why:** Storing names not IDs preserves history if member is deleted.

## mark_all_messages_read route
Route: `POST /messages/mark-all-read` → `mark_all_messages_read()`.
Uses bulk update: `InAppMessage.query.filter_by(recipient_id=current_user.id, is_read=False).update({'is_read': True})`.
Called from messages.html via fetch() with CSRF token.

## receipts route simplified
Avoid complex joins with Payment model (may fail). Instead:
1. Collect IDs of contributions/repayments/welfare belonging to member
2. Use `db.or_()` with `.in_()` filters on DigitalReceipt FK columns
3. Always wrap lists with `if list else db.false()` to handle empty lists.
