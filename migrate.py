"""Database migration script — adds new columns and tables for CONNECT."""
import os
import psycopg2

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set")
    exit(1)

conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
cur = conn.cursor()

def col_exists(table, col):
    cur.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name=%s AND column_name=%s
    """, (table, col))
    return cur.fetchone() is not None

def table_exists(table):
    cur.execute("""
        SELECT 1 FROM information_schema.tables
        WHERE table_name=%s
    """, (table,))
    return cur.fetchone() is not None

def add_col(table, col, col_type, default=None):
    if not col_exists(table, col):
        default_clause = f" DEFAULT {default}" if default is not None else ""
        cur.execute(f'ALTER TABLE "{table}" ADD COLUMN "{col}" {col_type}{default_clause}')
        print(f"  + {table}.{col}")
    else:
        print(f"  . {table}.{col} already exists")

print("=== CONNECT Schema Migration ===")

# ─── Create new tables ────────────────────────────────────────────────────────

print("\n[1] Creating new tables...")

if not table_exists("group"):
    cur.execute("""
        CREATE TABLE "group" (
            id SERIAL PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            description TEXT,
            logo VARCHAR(255),
            contact_email VARCHAR(120),
            contact_phone VARCHAR(20),
            location VARCHAR(200),
            year_established VARCHAR(10) DEFAULT '2024',
            created_at TIMESTAMP DEFAULT NOW(),
            is_active BOOLEAN DEFAULT TRUE,
            registration_code VARCHAR(20) UNIQUE
        )
    """)
    print("  + group table created")
    # Create default group
    import random, string
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    cur.execute("""
        INSERT INTO "group" (name, description, contact_email, contact_phone, location, year_established, is_active, registration_code)
        VALUES (%s, %s, %s, %s, %s, %s, TRUE, %s)
        RETURNING id
    """, ('Pamoja Agencies SHG', 'Self-Help Group', 'pamojaagenciesshg@gmail.com', '254799466723', 'Kenya', '2023', code))
    group_id = cur.fetchone()[0]
    print(f"  + Default group created (id={group_id}, code={code})")
else:
    print("  . group table already exists")
    cur.execute('SELECT id FROM "group" LIMIT 1')
    row = cur.fetchone()
    group_id = row[0] if row else None
    print(f"  . Using existing group id={group_id}")

if not table_exists("in_app_message"):
    cur.execute("""
        CREATE TABLE in_app_message (
            id SERIAL PRIMARY KEY,
            sender_id INTEGER REFERENCES "user"(id),
            recipient_id INTEGER REFERENCES "user"(id),
            subject VARCHAR(200) NOT NULL,
            body TEXT NOT NULL,
            is_read BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW(),
            group_id INTEGER,
            message_type VARCHAR(50) DEFAULT 'general'
        )
    """)
    print("  + in_app_message table created")
else:
    print("  . in_app_message already exists")

if not table_exists("project"):
    cur.execute("""
        CREATE TABLE project (
            id SERIAL PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            description TEXT NOT NULL,
            status VARCHAR(20) DEFAULT 'Planned',
            budget FLOAT DEFAULT 0.0,
            start_date DATE,
            end_date DATE,
            created_date TIMESTAMP DEFAULT NOW(),
            created_by INTEGER REFERENCES "user"(id),
            group_id INTEGER
        )
    """)
    print("  + project table created")
else:
    print("  . project already exists")

# ─── User table ───────────────────────────────────────────────────────────────

print("\n[2] Updating user table...")
add_col("user", "group_id", "INTEGER")
add_col("user", "is_super_admin", "BOOLEAN", "FALSE")

# Assign all existing users (non-admins) to the default group
if group_id:
    cur.execute("""
        UPDATE "user"
        SET group_id = %s
        WHERE group_id IS NULL
    """, (group_id,))
    print(f"  → Assigned existing users to group {group_id}")

# ─── Contribution table ───────────────────────────────────────────────────────

print("\n[3] Updating contribution table...")
add_col("contribution", "payment_method", "VARCHAR(20)", "'cash'")
add_col("contribution", "transaction_reference", "VARCHAR(100)")

# ─── Notification table ───────────────────────────────────────────────────────

print("\n[4] Updating notification table...")
add_col("notification", "link_url", "VARCHAR(255)")
add_col("notification", "transaction_reference", "VARCHAR(100)")
add_col("notification", "payment_method", "VARCHAR(20)")

# ─── MembershipApplication table ─────────────────────────────────────────────

print("\n[5] Updating membership_application table...")
add_col("membership_application", "id_document", "VARCHAR(255)")
add_col("membership_application", "group_id", "INTEGER")
add_col("membership_application", "rejection_reason", "TEXT")

# ─── Loan table ───────────────────────────────────────────────────────────────

print("\n[6] Updating loan table...")
add_col("loan", "rejection_reason", "TEXT")
add_col("loan", "repayment_mode", "VARCHAR(20)", "'monthly'")

# ─── LoanRepayment table ──────────────────────────────────────────────────────

print("\n[7] Updating loan_repayment table...")
add_col("loan_repayment", "payment_method", "VARCHAR(20)", "'cash'")
add_col("loan_repayment", "transaction_reference", "VARCHAR(100)")

# ─── Announcement table ───────────────────────────────────────────────────────

print("\n[8] Updating announcement table...")
add_col("announcement", "group_id", "INTEGER")

# ─── MeetingRecord table ──────────────────────────────────────────────────────

print("\n[9] Updating meeting_record table...")
add_col("meeting_record", "group_id", "INTEGER")

# ─── Document table ───────────────────────────────────────────────────────────

print("\n[10] Updating document table...")
add_col("document", "group_id", "INTEGER")

# ─── VotingProposal table ─────────────────────────────────────────────────────

print("\n[11] Updating voting_proposal table...")
add_col("voting_proposal", "group_id", "INTEGER")

# ─── DigitalReceipt table ─────────────────────────────────────────────────────

print("\n[12] Updating digital_receipt table...")
add_col("digital_receipt", "group_id", "INTEGER")

# ─── ActivityLog table ────────────────────────────────────────────────────────

print("\n[13] Checking activity_log table...")
if not table_exists("activity_log"):
    cur.execute("""
        CREATE TABLE activity_log (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES "user"(id),
            action VARCHAR(100) NOT NULL,
            entity_type VARCHAR(50) NOT NULL,
            entity_id INTEGER,
            description TEXT NOT NULL,
            ip_address VARCHAR(45),
            timestamp TIMESTAMP DEFAULT NOW(),
            additional_data TEXT,
            group_id INTEGER
        )
    """)
    print("  + activity_log table created")
else:
    add_col("activity_log", "group_id", "INTEGER")

cur.close()
conn.close()
print("\n=== Migration Complete ===")
