---
name: CONNECT Platform Setup
description: Key facts about the CONNECT multi-group SHG management platform built on Flask + PostgreSQL.
---

## Architecture
- Flask 3.1 + Flask-SQLAlchemy + PostgreSQL (DATABASE_URL env var)
- Gunicorn on port 5000, 1 worker
- PWA: static/manifest.json + static/sw.js

## Multi-group model
- `Group` table holds each SHG group; default group = "Pamoja Agencies SHG" (id=1)
- Every `User` has `group_id` (FK to Group) and `is_super_admin` boolean
- Super admin (CONNECT_ADMIN) has `is_super_admin=True`, `group_id=NULL` — sees all groups
- Group admins have `group_id` set — queries must filter by group_id

## Schema migration
- `migrate.py` at project root adds all new columns to existing tables via ALTER TABLE
- Must be run whenever models.py adds new columns (db.create_all() only adds new tables, not columns)
- Key new columns: user.group_id, user.is_super_admin, contribution.payment_method/transaction_reference, notification.link_url/transaction_reference/payment_method, membership_application.id_document/group_id/rejection_reason, loan.rejection_reason

## Credentials (dev/default)
- Super admin: username=CONNECT_ADMIN, password=connect@admin2024
- Default group admin: username=SALIM TUVA KARISA, password=34338006tuva, group_id=1

## Context processor (app.py)
- Injects: current_group, unread_notifications, unread_messages, app_name='CONNECT', format_currency, datetime
- The context_processor lives ONLY in app.py — do not duplicate in routes.py

## Group-filtering pattern
- For each route that lists users/contributions/loans/fines/announcements:
  - `if current_user.is_super_admin:` → no filter
  - `elif current_user.group_id:` → filter by group_id
  - `else:` → fallback (no filter or empty)
- `utils.get_group_statistics(group_id=None)` accepts optional group_id for scoped stats

**Why:** Each group must be data-isolated; super admin sees everything for cross-group oversight.

## Member creation context
- Super admins must select an active group before adding a member; new members must always receive the active group assignment.

**Why:** An unassigned non-super-admin is hidden from every group member list and cannot log in through a group-specific login.

## Membership application notifications
- Group-targeted membership applications notify that group’s officials and CONNECT super admins; notification links should open the applications review page.

**Why:** Super admins oversee all groups, while group officials need only their own group’s applications.

## Mobile navigation links
- Mobile offcanvas page links must use normal anchor navigation without `data-bs-dismiss="offcanvas"`.

**Why:** In the proxied preview, Bootstrap’s dismissal handler can consume the click and leave the page unchanged; navigation naturally closes the menu during the page load.
