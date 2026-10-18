---
name: CONNECT template safety patterns
description: Non-obvious Jinja2/template bugs and fixes for the CONNECT SHG platform
---

## List vs integer comparisons in Jinja2
When a route passes a list (e.g. `badges = UserBadge.query...all()`), never compare with `> 0` directly.
- WRONG: `{% if member_data.badges > 0 %}`
- RIGHT: `{% if member_data.badges|length > 0 %}`
- Display count: `{{ member_data.badges|length }}` not `{{ member_data.badges }}`
**Why:** In Python 3, comparing a list to an integer raises TypeError in strict mode, and in Jinja2 always evaluates False (hides content silently).
**How to apply:** Any template variable that comes from `.query.filter_by(...).all()` is a list — use `|length` for numeric comparisons.

## Nullable SQLAlchemy relationships in templates
When a SQLAlchemy relationship FK is NOT NULL at DB level but the related record could be soft-deleted or missing:
- WRONG: `{{ expense.beneficiary.full_name }}`
- RIGHT: `{{ expense.beneficiary.full_name if expense.beneficiary else '—' }}`
**Why:** Even with NOT NULL FK, if the related User is deactivated or the ORM session is stale, accessing `.full_name` on None crashes.
**How to apply:** Add null guard for any `.related_object.attribute` in templates, especially for WelfareExpense.beneficiary, Payment.member, etc.

## SelectField validate_choice=False for dynamic choices
When a SelectField's choices are populated dynamically (e.g. from DB query only on GET, not on POST):
```python
reference_id = SelectField('...', choices=[], coerce=int, validators=[Optional()], validate_choice=False)
```
And always populate choices before `validate_on_submit()` call (not just on GET).
**Why:** WTForms 3.x SelectField validates submitted value against the choices list. If choices are empty on POST (validation error re-display), every value fails with "Not a valid choice."
**How to apply:** Set `validate_choice=False` on any SelectField populated from DB queries.

## Bootstrap modal + browser confirm() = backdrop lock
Never use `onclick="return confirm(...)"` on submit buttons inside Bootstrap modals.
- The native browser confirm() dialog can lock the modal backdrop in some browsers.
- Fix: Remove confirm() and rely on the modal as the confirmation step. Make button text clear ("Approve Member", "Confirm Rejection").
**Why:** Bootstrap 5 modals use z-index stacking. Native dialogs can interrupt the modal's show/hide cycle.
**How to apply:** For approve/reject workflows inside modals, use clear button labels instead of nested confirm() dialogs.

## showRejectForm JS: hide/show defaultActions div
When toggling between "main actions" and "rejection form" in a modal footer:
```js
function showRejectForm(appId) {
    document.getElementById('defaultActions' + appId).style.display = 'none';
    document.getElementById('rejectForm' + appId).style.display = 'block';
}
function hideRejectForm(appId) {
    document.getElementById('rejectForm' + appId).style.display = 'none';
    document.getElementById('defaultActions' + appId).style.display = 'flex';
}
```
Use `display = 'flex'` (not 'block') to restore a flex container.
**Why:** If the container was `d-flex`, restoring with `display = 'block'` breaks alignment.

## url_for validation — both forms of call
The simple regex `url_for('name')` misses calls with arguments: `url_for('name', id=x)`.
Use both patterns: `url_for\('(\w+)'[,)]` and `url_for\("(\w+)"[,)]` to catch all.
**Why:** BuildError for undefined routes only triggers at render time, not at import time.

## External loan member guard in templates
For External loans, `loan.member` is None. All accesses must be guarded:
- WRONG: `{{ loan.member.full_name }}`
- RIGHT: `{{ loan.borrower_name if loan.loan_type == 'External' else loan.member.full_name }}`
Or inside `{% if loan.loan_type == 'Internal' %}` block.
**Why:** External loans have member_id=NULL; the ORM relationship returns None.
