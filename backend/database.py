import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resolve_ai.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for thread-safe database concurrency
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except Exception:
        pass
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Users Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('ACTIVE', 'LOCKED')),
        loyalty_points INTEGER DEFAULT 0
    )
    """)
    
    # 2. Orders Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        order_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        item_name TEXT NOT NULL,
        price REAL NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('DELIVERED', 'REFUNDED', 'PENDING')),
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    )
    """)
    
    # 3. Tickets Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tickets (
        ticket_id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('OPEN', 'PENDING_APPROVAL', 'RESOLVED', 'REJECTED')),
        created_at TEXT NOT NULL,
        logs TEXT -- Will hold JSON serialized steps/traces
    )
    """)
    
    # 4. Emails Sent Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS emails_sent (
        email_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        recipient TEXT NOT NULL,
        subject TEXT NOT NULL,
        body TEXT NOT NULL,
        sent_at TEXT NOT NULL
    )
    """)
    
    conn.commit()
    seed_data(conn)
    conn.close()

def seed_data(conn):
    cursor = conn.cursor()
    
    # Clear existing data to make seeding idempotent
    cursor.execute("DELETE FROM users")
    cursor.execute("DELETE FROM orders")
    cursor.execute("DELETE FROM tickets")
    cursor.execute("DELETE FROM emails_sent")
    
    # Insert Demo Users
    users = [
        ("USR-1001", "Alice Smith", "alice.smith@example.com", "LOCKED", 350),
        ("USR-1002", "Bob Johnson", "bob.johnson@example.com", "ACTIVE", 80),
        ("USR-1003", "Charlie Brown", "charlie.brown@example.com", "ACTIVE", 15),
        ("USR-1004", "Diana Prince", "diana.prince@example.com", "ACTIVE", 1200)
    ]
    cursor.executemany("INSERT INTO users VALUES (?, ?, ?, ?, ?)", users)
    
    # Insert Demo Orders
    orders = [
        (201, "USR-1001", "Ultra Wireless Headphones", 120.00, "DELIVERED"),
        (202, "USR-1002", "Ergonomic Office Chair", 85.00, "DELIVERED"),
        (203, "USR-1002", "Mini Desk Fan", 18.50, "DELIVERED"),
        (204, "USR-1003", "Leather Cable Organizer", 12.00, "DELIVERED"),
        (205, "USR-1004", "Mechanical Keyboard", 150.00, "DELIVERED")
    ]
    cursor.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?)", orders)
    
    conn.commit()

def reset_db():
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
        except Exception:
            pass
    init_db()

# DB Access Helper functions
def query_db(query, args=(), one=False):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(query, args)
    rv = cursor.fetchall()
    conn.commit()
    conn.close()
    return (rv[0] if rv else None) if one else rv

def execute_db(query, args=()):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(query, args)
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully at:", DB_PATH)
