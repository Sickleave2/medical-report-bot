import sqlite3
from datetime import datetime

DB_NAME = "database.db"

def connect():
    return sqlite3.connect(DB_NAME)

def init_db():
    conn = connect()
    cursor = conn.cursor()

    # users
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER UNIQUE,
        username TEXT,
        balance REAL DEFAULT 0,
        is_banned INTEGER DEFAULT 0,
        created_at TEXT
    )
    """)

    # transactions
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        type TEXT,
        created_at TEXT
    )
    """)

    # hospitals
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS hospitals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT
    )
    """)

    # departments
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS departments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hospital_id INTEGER,
        name TEXT
    )
    """)

    # doctors
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS doctors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hospital_id INTEGER,
        department_id INTEGER,
        name TEXT,
        specialty TEXT,
        license_number TEXT
    )
    """)

    # reports
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        hospital_id INTEGER,
        department_id INTEGER,
        doctor_id INTEGER,
        patient_name TEXT,
        diagnosis TEXT,
        created_at TEXT
    )
    """)

    conn.commit()
    conn.close()


# ---------------- Users ----------------

def add_user(telegram_id, username):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR IGNORE INTO users
    (telegram_id, username, created_at)
    VALUES (?, ?, ?)
    """, (telegram_id, username, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_balance(telegram_id):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE telegram_id=?", (telegram_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0


# ---------------- Hospitals ----------------

def add_hospital(name):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO hospitals (name) VALUES (?)", (name,))
    conn.commit()
    conn.close()

def get_hospitals():
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM hospitals")
    data = cursor.fetchall()
    conn.close()
    return data


# ---------------- Departments ----------------

def add_department(hospital_id, name):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO departments (hospital_id, name) VALUES (?, ?)",
        (hospital_id, name)
    )
    conn.commit()
    conn.close()

def get_departments(hospital_id):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, name FROM departments WHERE hospital_id=?",
        (hospital_id,)
    )
    data = cursor.fetchall()
    conn.close()
    return data


# ---------------- Doctors ----------------

def add_doctor(hospital_id, department_id, name, specialty, license_number):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO doctors
        (hospital_id, department_id, name, specialty, license_number)
        VALUES (?, ?, ?, ?, ?)
    """, (hospital_id, department_id, name, specialty, license_number))
    conn.commit()
    conn.close()

def get_doctors(hospital_id, department_id):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, specialty FROM doctors
        WHERE hospital_id=? AND department_id=?
    """, (hospital_id, department_id))
    data = cursor.fetchall()
    conn.close()
    return data
