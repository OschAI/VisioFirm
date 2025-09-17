import sqlite3
from passlib.context import CryptContext
from visiofirm.config import get_cache_folder
import os

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_db_path():
    return os.path.join(get_cache_folder(), 'users.db')

def init_db():
    db_path = get_db_path()
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                company TEXT
            )
        ''')
        conn.commit()

def create_user(first_name, last_name, username, email, password, company):
    db_path = get_db_path()
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        password_hash = pwd_context.hash(password)
        try:
            cursor.execute('''
                INSERT INTO users (first_name, last_name, username, email, password_hash, company)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (first_name, last_name, username, email, password_hash, company))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

def update_user(user_id, updates):
    db_path = get_db_path()
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        try:
            # Handle password_hash specially if provided as plain text
            if 'password_hash' in updates and 'password' in updates:
                updates['password_hash'] = pwd_context.hash(updates.pop('password'))
            set_clause = ', '.join(f"{key} = ?" for key in updates)
            values = list(updates.values()) + [user_id]
            cursor.execute(f'''
                UPDATE users
                SET {set_clause}
                WHERE id = ?
            ''', values)
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.IntegrityError:
            return False

def get_user_by_username(username):
    db_path = get_db_path()
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, username, password_hash, first_name, last_name, email, company
            FROM users WHERE username = ?
        ''', (username,))
        return cursor.fetchone()

def get_user_by_email(email):
    db_path = get_db_path()
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, username, password_hash, first_name, last_name, email, company
            FROM users WHERE email = ?
        ''', (email,))
        return cursor.fetchone()

def get_user_by_id(user_id):
    db_path = get_db_path()
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, username, password_hash, first_name, last_name, email, company
            FROM users WHERE id = ?
        ''', (user_id,))
        return cursor.fetchone()

class User:
    def __init__(self, user_id, username, first_name, last_name, email, company):
        self.id = user_id
        self.username = username
        self.first_name = first_name
        self.last_name = last_name
        self.email = email
        self.company = company

    @property
    def avatar(self):
        return f"{self.first_name[0]}.{self.last_name[0]}" if self.first_name and self.last_name else ""