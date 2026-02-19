import sqlite3
from datetime import datetime
import json

DB_NAME = "database.db"

def connect():
    return sqlite3.connect(DB_NAME)

def init_db():
    conn = connect()
    cursor = conn.cursor()

    # ---- الجداول الحالية (كما هي) ----
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER UNIQUE,
        username TEXT,
        balance REAL DEFAULT 0,
        is_admin INTEGER DEFAULT 0,
        is_banned INTEGER DEFAULT 0,
        created_at TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER,
        amount REAL,
        type TEXT,
        created_at TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS regions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS hospitals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        region_id INTEGER,
        name TEXT,
        FOREIGN KEY(region_id) REFERENCES regions(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS departments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hospital_id INTEGER,
        name TEXT,
        FOREIGN KEY(hospital_id) REFERENCES hospitals(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS doctors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        department_id INTEGER,
        name TEXT,
        title TEXT,
        FOREIGN KEY(department_id) REFERENCES departments(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER,
        doctor_id INTEGER,
        patient_name TEXT,
        patient_gender TEXT,
        created_at TEXT,
        FOREIGN KEY(doctor_id) REFERENCES doctors(id)
    )
    """)

    # ---- الجداول الجديدة لإدارة القوالب ----
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS report_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        doctor_id INTEGER UNIQUE,
        male_template_path TEXT,
        female_template_path TEXT,
        fields_to_fill TEXT,         -- JSON list of field names that will be filled by the bot
        user_required_fields TEXT,    -- JSON list of fields to ask the user (matching field names)
        FOREIGN KEY(doctor_id) REFERENCES doctors(id)
    )
    """)

    conn.commit()
    conn.close()

# ========== دوال إدارة القوالب الجديدة ==========
def save_template_config(doctor_id, male_path, female_path, fields_to_fill, user_fields):
    """حفظ تكوين القالب لطبيب معين"""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO report_templates
        (doctor_id, male_template_path, female_template_path, fields_to_fill, user_required_fields)
        VALUES (?, ?, ?, ?, ?)
    """, (doctor_id, male_path, female_path,
          json.dumps(fields_to_fill, ensure_ascii=False),
          json.dumps(user_fields, ensure_ascii=False)))
    conn.commit()
    conn.close()

def get_template_config(doctor_id):
    """استرجاع تكوين القالب لطبيب"""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM report_templates WHERE doctor_id=?", (doctor_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        # تحويل JSON إلى قائمة
        return {
            'id': row[0],
            'doctor_id': row[1],
            'male_path': row[2],
            'female_path': row[3],
            'fields_to_fill': json.loads(row[4]) if row[4] else [],
            'user_fields': json.loads(row[5]) if row[5] else []
        }
    return None

def delete_template_config(doctor_id):
    """حذف تكوين القالب عند حذف الطبيب"""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM report_templates WHERE doctor_id=?", (doctor_id,))
    conn.commit()
    conn.close()

# ========== باقي دوال المستخدمين والمستشفيات (كما هي) ==========
# (سيتم تضمينها كاملة في الملف النهائي، ولكن للاختصار نذكر التوقيعات فقط)
# ... (جميع الدوال السابقة من database.py تبقى كما هي) ...
