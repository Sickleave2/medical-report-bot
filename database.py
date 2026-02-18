import sqlite3
from datetime import datetime

DB_NAME = "database.db"

def connect():
    return sqlite3.connect(DB_NAME)

def init_db():
    conn = connect()
    cursor = conn.cursor()

    # الجداول الأساسية
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

    # جداول المستشفيات والأقسام والأطباء والتقارير (جديد)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS hospitals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS departments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hospital_id INTEGER,
        name TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS doctors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hospital_id INTEGER,
        department_id INTEGER,
        name TEXT,
        specialization TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER,
        hospital_name TEXT,
        doctor_name TEXT,
        patient_name TEXT,
        created_at TEXT
    )
    """)

    conn.commit()
    conn.close()

# ---------------- Users ----------------

def add_user(telegram_id, username, is_admin=0):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR IGNORE INTO users
    (telegram_id, username, is_admin, created_at)
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
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE telegram_id=?", (telegram_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def update_balance(telegram_id, amount, tx_type):
    conn = connect()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE users SET balance = balance + ? WHERE telegram_id=?",
        (amount, telegram_id)
    )

    cursor.execute(
        "INSERT INTO transactions (telegram_id, amount, type, created_at) VALUES (?, ?, ?, ?)",
        (telegram_id, amount, tx_type, datetime.now())
    )

    conn.commit()
    conn.close()

def ban_user(telegram_id, status):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET is_banned=? WHERE telegram_id=?",
        (status, telegram_id)
    )
    conn.commit()
    conn.close()

# ---------------- Queries ----------------

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

# ================= مستشفيات / أقسام / أطباء =================

def add_hospital(name):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO hospitals (name) VALUES (?)", (name,))
    conn.commit()
    conn.close()

def get_hospitals():
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hospitals")
    data = cursor.fetchall()
    conn.close()
    return data

def add_department(hospital_id, name):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO departments (hospital_id, name) VALUES (?,?)",
                   (hospital_id, name))
    conn.commit()
    conn.close()

def get_departments(hospital_id):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM departments WHERE hospital_id=?",
                   (hospital_id,))
    data = cursor.fetchall()
    conn.close()
    return data

def add_doctor(hospital_id, department_id, name, specialization):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO doctors (hospital_id, department_id, name, specialization)
        VALUES (?,?,?,?)
    """, (hospital_id, department_id, name, specialization))
    conn.commit()
    conn.close()

def get_doctors(department_id):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM doctors WHERE department_id=?",
                   (department_id,))
    data = cursor.fetchall()
    conn.close()
    return data

def save_report(telegram_id, hospital_name, doctor_name, patient_name):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO reports (telegram_id, hospital_name, doctor_name, patient_name, created_at)
        VALUES (?,?,?,?, datetime('now'))
    """, (telegram_id, hospital_name, doctor_name, patient_name))
    conn.commit()
    conn.close()
