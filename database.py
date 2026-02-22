import sqlite3
from datetime import datetime
import json

DB_NAME = "database.db"

def connect():
    return sqlite3.connect(DB_NAME)

def init_db():
    conn = connect()
    cursor = conn.cursor()
    try:
        # جدول المناطق
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS regions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE
        )
        """)

        # جدول المستشفيات
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS hospitals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            region_id INTEGER,
            name TEXT,
            FOREIGN KEY(region_id) REFERENCES regions(id)
        )
        """)

        # جدول الأقسام
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hospital_id INTEGER,
            name TEXT,
            FOREIGN KEY(hospital_id) REFERENCES hospitals(id)
        )
        """)

        # جدول الأطباء
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS doctors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            department_id INTEGER,
            name TEXT,
            title TEXT,
            pdf_male TEXT,
            pdf_female TEXT,
            FOREIGN KEY(department_id) REFERENCES departments(id)
        )
        """)

        # جدول المستخدمين
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

        # جدول المعاملات المالية
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            amount REAL,
            type TEXT,
            created_at TEXT
        )
        """)

        # جدول التقارير المنشأة
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

        # جدول القوالب الديناميكية
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS report_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doctor_id INTEGER UNIQUE,
            male_template_path TEXT,
            female_template_path TEXT,
            fields_json TEXT,
            user_required_fields TEXT,
            auto_fields TEXT,
            FOREIGN KEY(doctor_id) REFERENCES doctors(id) ON DELETE CASCADE
        )
        """)

        # إنشاء فهارس لتحسين الأداء
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_telegram_id ON transactions(telegram_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reports_doctor_id ON reports(doctor_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_doctors_department_id ON doctors(department_id)")

        conn.commit()
    finally:
        conn.close()

def seed_regions():
    conn = connect()
    cursor = conn.cursor()
    try:
        regions = [
            "الرياض", "مكة المكرمة", "المدينة المنورة", "القصيم",
            "الشرقية", "عسير", "تبوك", "حائل", "الحدود الشمالية",
            "جازان", "نجران", "الباحة", "الجوف"
        ]
        for r in regions:
            cursor.execute("INSERT OR IGNORE INTO regions (name) VALUES (?)", (r,))
        conn.commit()
    finally:
        conn.close()

# ========== دوال المناطق ==========
def get_regions():
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM regions ORDER BY name")
        rows = cursor.fetchall()
        return rows
    finally:
        conn.close()

def add_region(name):
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO regions (name) VALUES (?)", (name,))
        conn.commit()
    finally:
        conn.close()

def delete_region(region_id):
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM regions WHERE id=?", (region_id,))
        conn.commit()
    finally:
        conn.close()

def get_region_name(region_id):
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT name FROM regions WHERE id=?", (region_id,))
        row = cursor.fetchone()
        return row[0] if row else ""
    finally:
        conn.close()

# ========== دوال المستشفيات ==========
def get_hospitals(region_id=None):
    conn = connect()
    cursor = conn.cursor()
    try:
        if region_id:
            cursor.execute("SELECT * FROM hospitals WHERE region_id=? ORDER BY name", (region_id,))
        else:
            cursor.execute("SELECT * FROM hospitals ORDER BY name")
        rows = cursor.fetchall()
        return rows
    finally:
        conn.close()

def add_hospital(region_id, name):
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO hospitals (region_id, name) VALUES (?,?)", (region_id, name))
        conn.commit()
    finally:
        conn.close()

def delete_hospital(hospital_id):
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM hospitals WHERE id=?", (hospital_id,))
        conn.commit()
    finally:
        conn.close()

def get_hospital_name(hospital_id):
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT name FROM hospitals WHERE id=?", (hospital_id,))
        row = cursor.fetchone()
        return row[0] if row else ""
    finally:
        conn.close()

def get_hospital(hospital_id):
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM hospitals WHERE id=?", (hospital_id,))
        return cursor.fetchone()
    finally:
        conn.close()

# ========== دوال الأقسام ==========
def get_departments(hospital_id=None):
    conn = connect()
    cursor = conn.cursor()
    try:
        if hospital_id:
            cursor.execute("SELECT * FROM departments WHERE hospital_id=? ORDER BY name", (hospital_id,))
        else:
            cursor.execute("SELECT * FROM departments ORDER BY name")
        rows = cursor.fetchall()
        return rows
    finally:
        conn.close()

def add_department(hospital_id, name):
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO departments (hospital_id, name) VALUES (?,?)", (hospital_id, name))
        conn.commit()
    finally:
        conn.close()

def delete_department(department_id):
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM departments WHERE id=?", (department_id,))
        conn.commit()
    finally:
        conn.close()

def get_department_name(department_id):
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT name FROM departments WHERE id=?", (department_id,))
        row = cursor.fetchone()
        return row[0] if row else ""
    finally:
        conn.close()

def get_department(department_id):
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM departments WHERE id=?", (department_id,))
        return cursor.fetchone()
    finally:
        conn.close()

# ========== دوال الأطباء ==========
def get_doctors(department_id=None):
    conn = connect()
    cursor = conn.cursor()
    try:
        if department_id:
            cursor.execute("SELECT * FROM doctors WHERE department_id=? ORDER BY name", (department_id,))
        else:
            cursor.execute("SELECT * FROM doctors ORDER BY name")
        rows = cursor.fetchall()
        return rows
    finally:
        conn.close()

def get_doctor(doctor_id):
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM doctors WHERE id=?", (doctor_id,))
        row = cursor.fetchone()
        return row
    finally:
        conn.close()

def add_doctor(department_id, name, title, pdf_male, pdf_female):
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO doctors (department_id, name, title, pdf_male, pdf_female)
            VALUES (?,?,?,?,?)
        """, (department_id, name, title, pdf_male, pdf_female))
        doctor_id = cursor.lastrowid
        conn.commit()
        return doctor_id
    finally:
        conn.close()

def delete_doctor(doctor_id):
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM doctors WHERE id=?", (doctor_id,))
        conn.commit()
    finally:
        conn.close()

def get_doctor_name(doctor_id):
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT name FROM doctors WHERE id=?", (doctor_id,))
        row = cursor.fetchone()
        return row[0] if row else ""
    finally:
        conn.close()

# ========== دوال المستخدمين ==========
def add_user(telegram_id, username, is_admin=0):
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT OR IGNORE INTO users (telegram_id, username, is_admin, created_at)
        VALUES (?, ?, ?, ?)
        """, (telegram_id, username, is_admin, datetime.now()))
        conn.commit()
    finally:
        conn.close()

def get_user(telegram_id):
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,))
        user = cursor.fetchone()
        return user
    finally:
        conn.close()

def get_balance(telegram_id):
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT balance FROM users WHERE telegram_id=?", (telegram_id,))
        result = cursor.fetchone()
        return float(result[0]) if result else 0.0
    finally:
        conn.close()

def update_balance(telegram_id, amount, tx_type):
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE users SET balance = balance + ? WHERE telegram_id=?", (amount, telegram_id))
        cursor.execute("""
            INSERT INTO transactions (telegram_id, amount, type, created_at)
            VALUES (?, ?, ?, ?)
        """, (telegram_id, amount, tx_type, datetime.now()))
        conn.commit()
    finally:
        conn.close()

def ban_user(telegram_id, status):
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE users SET is_banned=? WHERE telegram_id=?", (status, telegram_id))
        conn.commit()
    finally:
        conn.close()

def get_all_active_users():
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT telegram_id FROM users WHERE is_banned=0")
        users = cursor.fetchall()
        return [u[0] for u in users]
    finally:
        conn.close()

def get_low_balance_users(limit=3):
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT telegram_id, balance
            FROM users
            WHERE balance < ? AND is_banned=0
        """, (limit,))
        users = cursor.fetchall()
        return users
    finally:
        conn.close()

def get_last_transaction(telegram_id):
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT amount, type, created_at
            FROM transactions
            WHERE telegram_id=?
            ORDER BY id DESC
            LIMIT 1
        """, (telegram_id,))
        tx = cursor.fetchone()
        return tx
    finally:
        conn.close()

def get_last_transaction_admin():
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT telegram_id, amount, type, created_at
            FROM transactions
            ORDER BY id DESC
            LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            return f"User {row[0]}: {row[1]} ({row[2]}) at {row[3]}"
        return None
    finally:
        conn.close()

def get_total_users_count():
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]
        return count
    finally:
        conn.close()

# ========== دوال التقارير ==========
def save_report(telegram_id, doctor_id, patient_name, patient_gender):
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO reports (telegram_id, doctor_id, patient_name, patient_gender, created_at)
            VALUES (?,?,?,?, datetime('now'))
        """, (telegram_id, doctor_id, patient_name, patient_gender))
        conn.commit()
    finally:
        conn.close()

def get_report_stats():
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM reports")
        total_reports = cursor.fetchone()[0]
        cursor.execute("SELECT SUM(amount) FROM transactions WHERE type='report'")
        total_income = cursor.fetchone()[0] or 0
        # أكثر مستشفى إصداراً
        cursor.execute("""
            SELECT h.name, COUNT(*) as cnt
            FROM reports r
            JOIN doctors d ON r.doctor_id = d.id
            JOIN departments de ON d.department_id = de.id
            JOIN hospitals h ON de.hospital_id = h.id
            GROUP BY h.id
            ORDER BY cnt DESC
            LIMIT 1
        """)
        top_hospital = cursor.fetchone()
        # أكثر طبيب إصداراً
        cursor.execute("""
            SELECT d.name, COUNT(*) as cnt
            FROM reports r
            JOIN doctors d ON r.doctor_id = d.id
            GROUP BY d.id
            ORDER BY cnt DESC
            LIMIT 1
        """)
        top_doctor = cursor.fetchone()
        return {
            "total_reports": total_reports,
            "total_income": total_income,
            "top_hospital": top_hospital,
            "top_doctor": top_doctor
        }
    finally:
        conn.close()

# ========== دوال القوالب الديناميكية ==========
def save_template(doctor_id, male_template_path, female_template_path, fields_json, user_required_fields, auto_fields):
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO report_templates
            (doctor_id, male_template_path, female_template_path, fields_json, user_required_fields, auto_fields)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (doctor_id, male_template_path, female_template_path, fields_json, user_required_fields, auto_fields))
        conn.commit()
    finally:
        conn.close()

def get_doctor_template(doctor_id):
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT male_template_path, female_template_path, fields_json, user_required_fields, auto_fields
            FROM report_templates WHERE doctor_id=?
        """, (doctor_id,))
        row = cursor.fetchone()
        if row:
            return {
                "male_template_path": row[0],
                "female_template_path": row[1],
                "fields_json": json.loads(row[2]) if row[2] else [],
                "user_required_fields": json.loads(row[3]) if row[3] else [],
                "auto_fields": json.loads(row[4]) if row[4] else []
            }
        return None
    finally:
        conn.close()

def get_all_templates():
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM report_templates")
        return cursor.fetchall()
    finally:
        conn.close()
