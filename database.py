import sqlite3
from datetime import datetime

def connect():
    return sqlite3.connect("database.db")

def init_db():
    conn = connect()
    cursor = conn.cursor()

    # المستخدمين
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER UNIQUE,
        username TEXT,
        balance REAL DEFAULT 0,
        is_banned INTEGER DEFAULT 0
    )
    """)

    # العمليات
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        type TEXT,
        created_at TEXT
    )
    """)

    # المستشفيات
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS hospitals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT
    )
    """)

    # الأقسام
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS departments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hospital_id INTEGER,
        name TEXT
    )
    """)

    # الأطباء
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

    conn.commit()
    conn.close()


# ================= Hospitals =================

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


# ================= Departments =================

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
        "SELECT * FROM departments WHERE hospital_id=?",
        (hospital_id,)
    )
    data = cursor.fetchall()
    conn.close()
    return data


# ================= Doctors =================

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
        SELECT * FROM doctors
        WHERE hospital_id=? AND department_id=?
    """, (hospital_id, department_id))
    data = cursor.fetchall()
    conn.close()
    return data
