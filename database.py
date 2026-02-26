# database.py (مع إضافة دوال pdf_configs)
import sqlite3
from datetime import datetime

DB_NAME = "database.db"

def connect():
    return sqlite3.connect(DB_NAME, timeout=10)

def init_db():
    conn = connect()
    cursor = conn.cursor()

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
        price REAL DEFAULT 3.0,
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

    # جدول إعدادات قوالب PDF (يحفظ الحقول التي اخترت تعبئتها ✅)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pdf_configs (
        doctor_id INTEGER,
        gender TEXT,
        field_name TEXT,
        PRIMARY KEY(doctor_id, gender, field_name)
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

    conn.commit()
    conn.close()

def seed_regions():
    conn = connect()
    cursor = conn.cursor()
    regions = [
        "الرياض", "مكة المكرمة", "المدينة المنورة", "القصيم",
        "الشرقية", "عسير", "تبوك", "حائل", "الحدود الشمالية",
        "جازان", "نجران", "الباحة", "الجوف"
    ]
    for r in regions:
        cursor.execute("INSERT OR IGNORE INTO regions (name) VALUES (?)", (r,))
    conn.commit()
    conn.close()

# ========== دوال المناطق ==========
def get_regions():
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM regions ORDER BY name")
    rows = cursor.fetchall()
    conn.close()
    return rows

def add_region(name):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO regions (name) VALUES (?)", (name,))
    conn.commit()
    conn.close()

def delete_region(region_id):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM regions WHERE id=?", (region_id,))
    conn.commit()
    conn.close()

def get_region(region_id):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM regions WHERE id=?", (region_id,))
    row = cursor.fetchone()
    conn.close()
    return row

# ========== دوال المستشفيات والأسعار ==========
def get_hospitals(region_id=None):
    conn = connect()
    cursor = conn.cursor()
    if region_id:
        cursor.execute("SELECT * FROM hospitals WHERE region_id=? ORDER BY name", (region_id,))
    else:
        cursor.execute("SELECT * FROM hospitals ORDER BY name")
    rows = cursor.fetchall()
    conn.close()
    return rows

def add_hospital(region_id, name):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO hospitals (region_id, name) VALUES (?,?)", (region_id, name))
    conn.commit()
    conn.close()

def delete_hospital(hospital_id):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM hospitals WHERE id=?", (hospital_id,))
    conn.commit()
    conn.close()

def get_hospital(hosp_id):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hospitals WHERE id=?", (hosp_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def update_hospital_price(hospital_id, new_price):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("UPDATE hospitals SET price=? WHERE id=?", (new_price, hospital_id))
    conn.commit()
    conn.close()

def get_hospital_price(hospital_id):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT price FROM hospitals WHERE id=?", (hospital_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 3.0

# ========== دوال الأقسام ==========
def get_departments(hospital_id=None):
    conn = connect()
    cursor = conn.cursor()
    if hospital_id:
        cursor.execute("SELECT * FROM departments WHERE hospital_id=? ORDER BY name", (hospital_id,))
    else:
        cursor.execute("SELECT * FROM departments ORDER BY name")
    rows = cursor.fetchall()
    conn.close()
    return rows

def add_department(hospital_id, name):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO departments (hospital_id, name) VALUES (?,?)", (hospital_id, name))
    conn.commit()
    conn.close()

def delete_department(department_id):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM departments WHERE id=?", (department_id,))
    conn.commit()
    conn.close()

def get_department(dept_id):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM departments WHERE id=?", (dept_id,))
    row = cursor.fetchone()
    conn.close()
    return row

# ========== دوال الأطباء ==========
def get_doctors(department_id=None):
    conn = connect()
    cursor = conn.cursor()
    if department_id:
        cursor.execute("SELECT * FROM doctors WHERE department_id=? ORDER BY name", (department_id,))
    else:
        cursor.execute("SELECT * FROM doctors ORDER BY name")
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_doctor(doctor_id):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM doctors WHERE id=?", (doctor_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def add_doctor(department_id, name, title, pdf_male, pdf_female):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO doctors (department_id, name, title, pdf_male, pdf_female)
        VALUES (?,?,?,?,?)
    """, (department_id, name, title, pdf_male, pdf_female))
    doctor_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return doctor_id

def delete_doctor(doctor_id):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM doctors WHERE id=?", (doctor_id,))
    conn.commit()
    conn.close()

# ========== دوال قوالب PDF الديناميكية ==========
def save_pdf_config(doctor_id, gender, fields_list):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pdf_configs WHERE doctor_id=? AND gender=?", (doctor_id, gender))
    for field in fields_list:
        cursor.execute("INSERT INTO pdf_configs (doctor_id, gender, field_name) VALUES (?,?,?)", (doctor_id, gender, field))
    conn.commit()
    conn.close()

def get_pdf_config(doctor_id, gender):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT field_name FROM pdf_configs WHERE doctor_id=? AND gender=?", (doctor_id, gender))
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

# ========== دوال المستخدمين ==========
def add_user(telegram_id, username, is_admin=0):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR IGNORE INTO users (telegram_id, username, is_admin, created_at)
    VALUES (?, ?, ?, ?)
    """, (telegram_id, username, is_admin, datetime.now()))
    conn.commit()
    conn.close()

def get_user(telegram_id):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def get_balance(telegram_id):
    user = get_user(telegram_id)
    return float(user[3]) if user else 0.0

def update_balance(telegram_id, amount, tx_type):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance + ? WHERE telegram_id = ?", (amount, telegram_id))
    cursor.execute("""
        INSERT INTO transactions (telegram_id, amount, type, created_at)
        VALUES (?, ?, ?, ?)
    """, (telegram_id, amount, tx_type, datetime.now()))
    conn.commit()
    conn.close()

def ban_user(telegram_id, status):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_banned=? WHERE telegram_id=?", (status, telegram_id))
    conn.commit()
    conn.close()

def get_all_active_users():
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT telegram_id FROM users WHERE is_banned=0")
    users = cursor.fetchall()
    conn.close()
    return [u[0] for u in users]

def get_low_balance_users(limit=3):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT telegram_id, balance
        FROM users
        WHERE balance < ? AND is_banned=0
    """, (limit,))
    users = cursor.fetchall()
    conn.close()
    return users

def get_last_transaction(telegram_id):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT amount, type, created_at
        FROM transactions
        WHERE telegram_id=?
        ORDER BY id DESC
        LIMIT 1
    """, (telegram_id,))
    tx = cursor.fetchone()
    conn.close()
    return tx

# ========== دوال التقارير ==========
def save_report(telegram_id, doctor_id, patient_name, patient_gender):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO reports (telegram_id, doctor_id, patient_name, patient_gender, created_at)
        VALUES (?,?,?,?, datetime('now'))
    """, (telegram_id, doctor_id, patient_name, patient_gender))
    conn.commit()
    conn.close()

def get_report_stats():
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM reports")
    total_reports = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(amount) FROM transactions WHERE type='report'")
    total_income = cursor.fetchone()[0] or 0
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
    cursor.execute("""
        SELECT d.name, COUNT(*) as cnt
        FROM reports r
        JOIN doctors d ON r.doctor_id = d.id
        GROUP BY d.id
        ORDER BY cnt DESC
        LIMIT 1
    """)
    top_doctor = cursor.fetchone()
    conn.close()
    return {
        "total_reports": total_reports,
        "total_income": total_income,
        "top_hospital": top_hospital,
        "top_doctor": top_doctor
    }
