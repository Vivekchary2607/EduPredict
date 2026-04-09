# database.py
import sqlite3
import json
from werkzeug.security import generate_password_hash, check_password_hash
from email_utils import send_deactivation_email
import os
import psycopg2
from urllib.parse import urlparse
from psycopg2.extras import RealDictCursor
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from urllib.parse import urlparse

# def get_connection():
#     DATABASE_URL = os.getenv("DATABASE_URL")  # ✅ only the variable name here

#     if DATABASE_URL:
#         # PostgreSQL (Production)
#         result = urlparse(DATABASE_URL)
#         conn = psycopg2.connect(
#             database=result.path[1:],   # strip leading '/'
#             user=result.username,
#             password=result.password,
#             host=result.hostname,
#             port=result.port,
#             cursor_factory=RealDictCursor
#         )
#         return conn

import psycopg2
import os
from psycopg2.extras import RealDictCursor

def get_connection():
    return psycopg2.connect(
        os.getenv("DATABASE_URL"),
        cursor_factory=RealDictCursor,
        sslmode="require"
    )
def init_db():
    conn = get_connection()
    c = conn.cursor()
    # ---------------- Organizations ----------------
    c.execute("""
    CREATE TABLE IF NOT EXISTS organizations (
        id SERIAL PRIMARY KEY,
        org_name TEXT NOT NULL,
        org_code TEXT UNIQUE NOT NULL,
        is_active BOOLEAN DEFAULT TRUE,
        admin_email TEXT 
    )
    """)

    # ---------------- Update users ----------------
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE,
        password_hash TEXT,
        role TEXT CHECK(role IN ('super_admin','admin','teacher')),
        subject TEXT,
        org_id INTEGER,
        FOREIGN KEY(org_id) REFERENCES organizations(id) ON DELETE CASCADE
    )
    """)

    # c.execute("""
    # CREATE TABLE IF NOT EXISTS users (
    #     id INTEGER PRIMARY KEY AUTOINCREMENT,
    #     username TEXT UNIQUE,
    #     password_hash TEXT,
    #     role TEXT CHECK(role IN ('admin','teacher')),
    #     subject TEXT
    # )""")
   
    # ---------------- Predictions ----------------
    c.execute("""
    CREATE TABLE IF NOT EXISTS predictions (
        id SERIAL PRIMARY KEY,
        global_student_id TEXT,
        username TEXT,
        student_name TEXT,
        class_level INTEGER,
        class_group TEXT,
        input_json TEXT,
        org_id INTEGER,
        result TEXT,
        probability REAL,
        explanation TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(org_id) REFERENCES organizations(id) ON DELETE CASCADE
    )
    """)
    # # Predictions table stays the same
    # c.execute("""
    # CREATE TABLE IF NOT EXISTS predictions (
    #     id INTEGER PRIMARY KEY AUTOINCREMENT,
    #     username TEXT,
    #     student_name TEXT,
    #     input_json TEXT,
    #     result TEXT,
    #     probability REAL,
    #     explanation TEXT,
    #     timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    # )""")
    # ---------------- Record Requests ----------------
    c.execute("""
    CREATE TABLE IF NOT EXISTS record_requests (
        id SERIAL PRIMARY KEY,
        requesting_org_id INTEGER,
        source_org_id INTEGER,
        global_student_id TEXT,
        status TEXT DEFAULT 'pending',
        requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        responded_at TIMESTAMP,
        FOREIGN KEY(requesting_org_id) REFERENCES organizations(id) ON DELETE CASCADE,
        FOREIGN KEY(source_org_id) REFERENCES organizations(id) ON DELETE CASCADE
    )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS invites (
            id SERIAL PRIMARY KEY,
            invite_token TEXT UNIQUE NOT NULL,
            email TEXT NOT NULL,
            role TEXT CHECK(role IN ('admin', 'teacher')) NOT NULL,
            subject TEXT,
            org_id INTEGER,
            used INTEGER DEFAULT 0,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS org_withdraw_requests (
                id SERIAL PRIMARY KEY,
                org_id INTEGER,
                reason TEXT,
                status TEXT DEFAULT 'pending',
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
    c.execute("""CREATE TABLE IF NOT EXISTS deactivated_organizations (
        id SERIAL PRIMARY KEY,
        org_name TEXT,
        admin_email TEXT,
        total_users INTEGER,
        total_predictions INTEGER,
        deactivated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
    conn.commit()
    conn.close()

def seed_initial_data():
    conn = get_connection()
    cur = conn.cursor()

    # ✅ Check if already initialized
    cur.execute("SELECT COUNT(*) AS count FROM organizations")
    result = cur.fetchone()

    if result["count"] > 0:
        conn.close()
        return  # Already initialized → skip

    # ✅ Create organization
    org_code = create_organization("Sample_school", "vivek@gmail.com")

    # ✅ Get org_id (important fix)
    cur.execute("SELECT id FROM organizations WHERE org_code=%s", (org_code,))
    org = cur.fetchone()
    org_id = org["id"]

    # ✅ Add users
    add_user("admin", "admin123", org_id, "admin")
    add_user("teacher1", "teach123", org_id, "teacher", "Math")
    add_user("platform_admin", "admin1234", None, "super_admin")

    conn.close()
def add_user(username, password,org_id, role, subject=None):
    
    conn = get_connection()
    c = conn.cursor()
    password_hash = generate_password_hash(password)
    c.execute("""
        INSERT INTO users (username, password_hash, role, subject, org_id)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (username) DO NOTHING
    """, (username, password_hash, role, subject,org_id))
    conn.commit()
    conn.close()

def validate_user(username, password):
    conn = get_connection()
    c = conn.cursor(cursor_factory=RealDictCursor)

    # Step 1: Get user
    c.execute("""
        SELECT password_hash, role, subject, org_id
        FROM users
        WHERE username=%s
    """, (username,))
    user = c.fetchone()

    if not user:
        conn.close()
        return None

    # Step 2: Validate password
    if not check_password_hash(user["password_hash"], password):
        conn.close()
        return None

    # Step 3: Super admin → skip org check
    if user["role"] == "super_admin":
        conn.close()
        return {
            "role": user["role"],
            "subject": user["subject"],
            "org_id": None
        }

    # Step 4: Check organization status (FIXED)
    c.execute("""
        SELECT is_active
        FROM organizations
        WHERE id=%s
    """, (user["org_id"],))

    org = c.fetchone()
    conn.close()

    if org is None:
        return "deactivated"

    # ✅ FIXED LOGIC
    if not org["is_active"]:
        return "deactivated"

    return {
        "role": user["role"],
        "subject": user["subject"],
        "org_id": user["org_id"]
    }





# def save_prediction(username, student_name, input_json, result, probability, explanation):
#     conn = sqlite3.connect(DB_PATH)
#     c = conn.cursor()
#     c.execute("""
#         INSERT INTO predictions (username, student_name, input_json, result, probability, explanation)
#         VALUES (?, ?, ?, ?, ?, ?)
#     """, (username, student_name, json.dumps(input_json), result, float(probability), explanation))
#     conn.commit()
#     conn.close()


def get_all_predictions():
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT id,global_student_id, username, student_name,class_level,class_group, input_json,org_id, result, probability, explanation, timestamp
        FROM predictions
        ORDER BY timestamp DESC
    """)
    rows = c.fetchall()
    conn.close()
    columns = ['id',"global_student_id",'username','student_name',"class_level","class_group",'input_json',"org_id",'result','probability','explanation','timestamp']
    # return [dict(zip(columns, r)) for r in rows]
    return rows

def get_all_users():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT username, role, subject FROM users")
    rows = c.fetchall()
    conn.close()
    return [{"username": r[0], "role": r[1], "subject": r[2]} for r in rows]

def delete_user(username):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE username=%s", (username,))
    conn.commit()
    conn.close()

def clear_predictions():
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM predictions")
    conn.commit()
    conn.close()

def clear_non_admins():
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE role != 'admin'")
    conn.commit()
    conn.close()

# database.py
import secrets
import string
from datetime import datetime, timedelta

def generate_invite_code(length=8):
    chars = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))

def create_invite(email, role, org_id, subject, expires_in_hours=24):
    token = generate_invite_code(8)
    expires_at = (datetime.utcnow() + timedelta(hours=expires_in_hours)).isoformat()

    conn = get_connection()
    c = conn.cursor()

    c.execute("""
    INSERT INTO invites (invite_token, email, subject, org_id, role, expires_at)
    VALUES (%s, %s, %s, %s, %s, %s)
    """, (token, email, subject, org_id, role, expires_at))


    conn.commit()
    conn.close()

    return token, expires_at



def validate_invite(token, email):
    conn = get_connection()
    c = conn.cursor(cursor_factory=RealDictCursor)

    c.execute("""
        SELECT id, role, subject, org_id, used, expires_at
        FROM invites
        WHERE invite_token=%s AND email=%s
    """, (token, email))

    row = c.fetchone()
    conn.close()

    if not row:
        return None, "❌ Invalid invite code or email mismatch."

    invite_id = row["id"]
    role = row["role"]
    subject = row["subject"]
    org_id = row["org_id"]
    used = row["used"]
    expires_at = row["expires_at"]

    if int(used) == 1:
        return None, "⚠️ This invite code has already been used."

    from datetime import datetime
    if datetime.utcnow() > expires_at:
        return None, "⌛ This invite code has expired."

    return {
        "invite_id": invite_id,
        "role": role,
        "subject": subject,
        "org_id": org_id
    }, None


def mark_invite_used(invite_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE invites SET used=1 WHERE id=%s", (invite_id,))
    conn.commit()
    conn.close()


def get_all_organizations():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT id, org_name, org_code FROM organizations")
    rows = cur.fetchall()

    conn.close()

    columns = ["id", "org_name", "org_code"]
    # return [dict(zip(columns, r)) for r in rows]
    return rows



# def save_prediction(username, student_name, input_json, result, probability, explanation):
#     conn = sqlite3.connect(DB_PATH)
#     c = conn.cursor()
#     c.execute("""
#         INSERT INTO predictions (username, student_name, input_json, result, probability, explanation)
#         VALUES (?, ?, ?, ?, ?, ?)
#     """, (username, student_name, json.dumps(input_json), result, float(probability), explanation))
#     conn.commit()
#     conn.close()

from psycopg2.extras import RealDictCursor

def get_existing_global_id(student_name, org_id, class_level):
    conn = get_connection()
    c = conn.cursor(cursor_factory=RealDictCursor)

    c.execute("""
        SELECT global_student_id
        FROM predictions
        WHERE student_name=%s AND org_id=%s AND class_level=%s
        LIMIT 1
    """, (student_name, org_id, class_level))

    row = c.fetchone()

    conn.close()

    return row["global_student_id"] if row else None

import uuid
import base64
import json
import sqlite3

def generate_short_global_id(length=12):
    raw = uuid.uuid4().bytes
    return base64.b32encode(raw).decode("utf-8").rstrip("=")[:length]

def validate_global_student_id(global_student_id, source_org_id):
    conn = get_connection()
    c = conn.cursor(cursor_factory=RealDictCursor)
    c.execute("""
        SELECT 1
        FROM predictions
        WHERE global_student_id=%s AND org_id=%s
        LIMIT 1
    """, (global_student_id, source_org_id))
    row = c.fetchone()

    conn.commit()

    return True if row else False

def is_request_already_sent(requesting_org_id, source_org_id, global_student_id):
    conn = get_connection()
    c = conn.cursor(cursor_factory=RealDictCursor)
    c.execute("""
        SELECT 1
        FROM record_requests
        WHERE requesting_org_id=%s
        AND source_org_id=%s
        AND global_student_id=%s
        AND status='pending'
        LIMIT 1
    """, (requesting_org_id, source_org_id, global_student_id))
    row = c.fetchone()

    conn.close()

    return True if row else False



def save_prediction(username, student_name, class_level, class_group,
                    input_json, result, prob, explanation, org_id):
    try:
        conn = get_connection()
        c = conn.cursor()

        # Get existing global ID
        existing_id = get_existing_global_id(student_name, org_id, class_level)
        global_id = existing_id if existing_id else generate_short_global_id()

        input_json_str = json.dumps(input_json)

        c.execute("""
            INSERT INTO predictions
            (global_student_id, username, student_name, class_level, class_group,
             input_json, org_id, result, probability, explanation)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            global_id,
            username,
            student_name,
            int(class_level),   # ✅ ensure integer
            class_group,
            input_json_str,
            int(org_id),        # ✅ ensure integer
            result,
            float(prob),        # ✅ ensure float
            explanation
        ))

        conn.commit()
        return global_id

    except Exception as e:
        print("Error saving prediction:", e)
        return None

    finally:
        c.close()
        conn.close()

def request_student_record(requesting_org_id, source_org_id, global_student_id):
    # Prevent self-request
    if requesting_org_id == source_org_id:
        return "Cannot request your own organization's student."
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO record_requests
        (requesting_org_id, source_org_id, global_student_id)
        VALUES (%s, %s, %s)
    """, (requesting_org_id, source_org_id, global_student_id))
    conn.commit()
    conn.close()
    return "success"


def get_pending_requests(org_id):
    conn = get_connection()
    c = conn.cursor(cursor_factory=RealDictCursor)
    c.execute("""
        SELECT * FROM record_requests
        WHERE source_org_id=%s AND status='pending'
    """, (org_id,))
    data = c.fetchall()
    conn.close()
    return data

def update_request_status(request_id, status):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE record_requests
        SET status=%s, responded_at=CURRENT_TIMESTAMP
        WHERE id=%s
    """, (status, request_id))
    conn.commit()
    conn.close()


def get_sent_requests(org_id):
    conn = get_connection()
    c = conn.cursor(cursor_factory=RealDictCursor)
    c.execute("""
        SELECT * FROM record_requests
        WHERE requesting_org_id=%s
        ORDER BY requested_at DESC
    """, (org_id,))
    data = c.fetchall()
    conn.close()
    columns = ['id',"requesting_org_id",'source_org_id','global_student_id','status',"requested_at",'responded_at']
    # return [dict(zip(columns, r)) for r in data]
    return data

def get_received_requests(org_id):
    conn = get_connection()
    c = conn.cursor(cursor_factory=RealDictCursor)
    c.execute("""
        SELECT * FROM record_requests
        WHERE source_org_id=%s
        ORDER BY requested_at DESC
    """, (org_id,))
    data = c.fetchall()
    conn.close()
    columns = ['id',"requesting_org_id",'source_org_id','global_student_id','status',"requested_at",'responded_at']
    return data




def get_shared_student_record(global_student_id, requesting_org_id):
    conn = get_connection()
    c = conn.cursor(cursor_factory=RealDictCursor)

    # Step 1: Check approval
    c.execute("""
        SELECT *
        FROM record_requests
        WHERE global_student_id=%s
        AND requesting_org_id=%s
        AND status='approved'
    """, (global_student_id, requesting_org_id))

    approved = c.fetchone()

    if not approved:
        conn.close()
        return None

    # Step 2: Fetch data
    c.execute("""
        SELECT *
        FROM predictions
        WHERE global_student_id=%s
    """, (global_student_id,))

    data = c.fetchall()

    conn.close()

    return data


# def create_organization(org_name, admin_email):
#     conn = get_connection()
#     org_code = generate_org_code()

#     conn.execute("""
#         INSERT INTO organizations (org_name, org_code, admin_email)
#         VALUES (%s, %s, %s)
#     """, (org_name, org_code, admin_email))

#     conn.commit()
#     conn.close()

#     return org_code
def create_organization(org_name, admin_email):
    conn = get_connection()
    cur = conn.cursor()

    import uuid
    org_code = str(uuid.uuid4())[:6]  # generate a short random code

    cur.execute("""
        INSERT INTO organizations (org_name, org_code, admin_email)
        VALUES (%s, %s, %s)
        RETURNING org_code;
    """, (org_name, org_code, admin_email))

    result = cur.fetchone()   # returns a dict if RealDictCursor is used

    conn.commit()
    cur.close()
    conn.close()

    # ✅ Access by column name, not index
    return result["org_code"]


def get_org_name(org_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT org_name
        FROM organizations
        WHERE id = %s
    """, (org_id,))

    row = cur.fetchone()
    conn.close()

    if row:
        # If using RealDictCursor, row is a dict
        return row["org_name"] if isinstance(row, dict) else row[0]
    return None


def get_prediction_count_by_org(org_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT COUNT(*) AS total
        FROM predictions
        WHERE org_id = %s
    """, (org_id,))   # ✅ pass the actual integer

    row = cur.fetchone()
    conn.close()

    if row:
        # If using RealDictCursor, row is a dict
        return row["total"] if isinstance(row, dict) else row[0]
    return 0




def get_predictions_by_org(org_id):
    conn = get_connection()
    c = conn.cursor(cursor_factory=RealDictCursor)
    c.execute("""
        SELECT id, global_student_id, username, student_name,class_level,class_group,
               input_json, org_id, result, probability,
               explanation, timestamp
        FROM predictions
        WHERE org_id=%s
        ORDER BY timestamp DESC
    """, (org_id,))
    rows = c.fetchall()
    conn.close()
    columns = ['id',"global_student_id",'username','student_name',"class_level","class_group",'input_json',"org_id",'result','probability','explanation','timestamp']
    return rows
    

def get_users_by_org(org_id):
    conn = get_connection()
    c = conn.cursor(cursor_factory=RealDictCursor)

    c.execute("""
        SELECT id, username, role, subject, org_id
        FROM users
        WHERE org_id=%s
    """, (org_id,))

    rows = c.fetchall()

    conn.close()

    return rows

import secrets
import string

def generate_org_code():
    return ''.join(
        secrets.choice(string.ascii_uppercase + string.digits)
        for _ in range(8)
    )

def validate_org_code(org_code):
    conn = get_connection()
    c = conn.cursor(cursor_factory=RealDictCursor)
    c.execute("""
        SELECT * FROM organizations WHERE org_code=%s
    """, (org_code,))
    org = c.fetchone()
    conn.close()
    return org

def get_org_admin(org_id):
    conn = get_connection()
    c = conn.cursor(cursor_factory=RealDictCursor)
    c.execute("""
        SELECT * FROM users
        WHERE org_id=%s AND role='admin'
    """, (org_id,))
    user = c.fetchone()
    conn.close()
    return user

def clear_predictions_by_org(org_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        DELETE FROM predictions
        WHERE org_id=%s
    """, (org_id,))
    conn.commit()
    conn.close()


# Organization  withdraw

def raise_withdraw_request(org_id, reason):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO org_withdraw_requests (org_id, reason)
        VALUES (%s, %s)
    """, (org_id, reason))

    conn.commit()
    conn.close()

def get_withdraw_requests():
    try:
        conn = get_connection()
        c = conn.cursor(cursor_factory=RealDictCursor)

        c.execute("""
            SELECT wr.id, wr.org_id, o.org_name,
                   wr.reason, wr.status, wr.timestamp
            FROM org_withdraw_requests wr
            JOIN organizations o ON wr.org_id = o.id
            WHERE wr.status = %s
        """, ("pending",))

        rows = c.fetchall()
        return rows

    except Exception as e:
        print("Error:", e)
        return []

    finally:
        c.close()
        conn.close()



def get_org_admin_email(org_id):
    conn = get_connection()
    # conn.row_factory = sqlite3.Row
    c = conn.cursor()
    row = c.execute("""
        SELECT admin_email
        FROM organizations
        WHERE id=%s
    """, (org_id,)).fetchone()

    conn.close()

    if row:
        return row["admin_email"]
    return None


from psycopg2.extras import RealDictCursor
from email_utils import send_deactivation_email

def approve_withdraw_request(request_id, org_id):
    try:
        conn = get_connection()
        c = conn.cursor(cursor_factory=RealDictCursor)

        # ✅ Get org details BEFORE deletion
        c.execute("""
            SELECT org_name, admin_email
            FROM organizations
            WHERE id=%s
        """, (org_id,))
        org = c.fetchone()

        if not org:
            conn.close()
            return

        org_name = org["org_name"]
        admin_email = org["admin_email"]

        # ✅ Count users
        c.execute("""
            SELECT COUNT(*) AS total
            FROM users
            WHERE org_id=%s
        """, (org_id,))
        total_users = c.fetchone()["total"]

        # ✅ Count predictions
        c.execute("""
            SELECT COUNT(*) AS total
            FROM predictions
            WHERE org_id=%s
        """, (org_id,))
        total_predictions = c.fetchone()["total"]

        # ✅ Insert into log table
        c.execute("""
            INSERT INTO deactivated_organizations
            (org_name, admin_email, total_users, total_predictions)
            VALUES (%s, %s, %s, %s)
        """, (org_name, admin_email, total_users, total_predictions))

        # ✅ Delete organization (CASCADE works automatically)
        c.execute("""
            DELETE FROM organizations
            WHERE id=%s
        """, (org_id,))

        # ✅ Update request status
        c.execute("""
            UPDATE org_withdraw_requests
            SET status='approved'
            WHERE id=%s
        """, (request_id,))

        conn.commit()

    except Exception as e:
        print("Error in approve_withdraw_request:", e)

    finally:
        c.close()
        conn.close()

    # ✅ Send email (outside DB transaction)
    try:
        if admin_email:
            send_deactivation_email(admin_email, org_name)
    except Exception as e:
        print("Email failed:", e)

# Analytics functions
def get_platform_stats():
    conn = get_connection()
    c = conn.cursor(cursor_factory=RealDictCursor)

    c.execute("SELECT COUNT(*) AS count FROM organizations")
    total_orgs = c.fetchone()["count"]

    c.execute("SELECT COUNT(*) AS count FROM users")
    total_users = c.fetchone()["count"]

    c.execute("SELECT COUNT(*) AS count FROM predictions")
    total_predictions = c.fetchone()["count"]

    conn.close()

    return total_orgs, total_users, total_predictions

# Pass vs Fail Distribution

def get_prediction_distribution():
    conn = get_connection()
    c = conn.cursor(cursor_factory=RealDictCursor)
    c.execute("""
        SELECT result, COUNT(*) as count
        FROM predictions
        GROUP BY result
    """)
    rows = c.fetchall()

    conn.close()
    return rows

#Users by Role
def get_user_role_distribution():
    conn = get_connection()
    c = conn.cursor(cursor_factory=RealDictCursor)
    c.execute("""
        SELECT role, COUNT(*) as count
        FROM users
        GROUP BY role
    """)
    rows = c.fetchall()

    conn.close()
    return rows

def get_predictions_by_org_stats():
    conn = get_connection()
    # conn.row_factory = sqlite3.Row
    c = conn.cursor(cursor_factory=RealDictCursor)
    c.execute("""
        SELECT o.org_name AS org_name,
               COUNT(p.id) AS total_predictions
        FROM organizations o
        LEFT JOIN predictions p ON o.id = p.org_id
        GROUP BY o.id
    """)
    rows = c.fetchall()

    conn.close()
    return rows

