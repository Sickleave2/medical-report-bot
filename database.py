import sqlite3
from datetime import datetime

DB_NAME = "database.db"

def connect():
    return sqlite3.connect(DB_NAME)

def init_db():
    conn = connect()
    cursor = conn.cursor()

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

    # جدول العمليات
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        type TEXT,
        created_at TEXT
    )
    """)

    # جدول التقارير
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        doctor TEXT,
        hospital TEXT,
        created_at TEXT
    )
    """)

    conn.commit()
    conn.close()


# -------------------------
# إدارة المستخدمين
# -------------------------

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


def update_balance(telegram_id, amount, tx_type):
    conn = connect()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE users SET balance = balance + ? WHERE telegram_id=?",
        (amount, telegram_id)
    )

    cursor.execute(
        "INSERT INTO transactions (user_id, amount, type, created_at) VALUES (?, ?, ?, ?)",
        (telegram_id, amount, tx_type, datetime.now())
    )

    conn.commit()
    conn.close()


def get_balance(telegram_id):
    conn = connect()
    cursor = conn.cursor()

    cursor.execute("SELECT balance FROM users WHERE telegram_id=?", (telegram_id,))
    result = cursor.fetchone()

    conn.close()
    return result[0] if result else 0


def ban_user(telegram_id, status):
    conn = connect()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE users SET is_banned=? WHERE telegram_id=?",
        (status, telegram_id)
    )

    conn.commit()
    conn.close()
