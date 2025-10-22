import sqlite3
from datetime import datetime
from contextlib import contextmanager

DB_NAME = 'nexifit_users.db'

@contextmanager
def get_db_connection():
    """Context manager for database connections."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row  # Access columns by name
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

# =====================
# AUTHENTICATION FUNCTIONS
# =====================

def is_user_authorized(phone_number):
    """Check if a phone number is authorized to use the bot."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT authorized, expiry_date 
            FROM authorized_users 
            WHERE phone_number = ?
        ''', (phone_number,))
        
        result = cursor.fetchone()
        
        if not result:
            return False
        
        # Check if authorized
        if result['authorized'] != 1:
            return False
        
        # Check expiry date if set
        if result['expiry_date']:
            expiry = datetime.fromisoformat(result['expiry_date'])
            if datetime.now() > expiry:
                return False
        
        return True

def is_admin(phone_number):
    """Check if a phone number is an admin."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id FROM admin_users WHERE phone_number = ?
        ''', (phone_number,))
        return cursor.fetchone() is not None

def log_auth_attempt(phone_number, action, success=False):
    """Log authentication attempts for security."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO auth_logs (phone_number, action, success)
            VALUES (?, ?, ?)
        ''', (phone_number, action, 1 if success else 0))

# =====================
# ADMIN FUNCTIONS
# =====================

def add_user(phone_number, name=None, expiry_days=None):
    """Add a new authorized user."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            expiry_date = None
            if expiry_days:
                from datetime import timedelta
                expiry_date = (datetime.now() + timedelta(days=expiry_days)).isoformat()
            
            cursor.execute('''
                INSERT INTO authorized_users (phone_number, name, expiry_date)
                VALUES (?, ?, ?)
            ''', (phone_number, name, expiry_date))
            
            return True, "User added successfully!"
    except sqlite3.IntegrityError:
        return False, "User already exists in database"
    except Exception as e:
        return False, f"Error: {str(e)}"

def remove_user(phone_number):
    """Remove/deactivate a user."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE authorized_users 
            SET authorized = 0 
            WHERE phone_number = ?
        ''', (phone_number,))
        
        if cursor.rowcount > 0:
            return True, "User deactivated successfully!"
        else:
            return False, "User not found"

def reactivate_user(phone_number):
    """Reactivate a previously deactivated user."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE authorized_users 
            SET authorized = 1 
            WHERE phone_number = ?
        ''', (phone_number,))
        
        if cursor.rowcount > 0:
            return True, "User reactivated successfully!"
        else:
            return False, "User not found"

def list_all_users():
    """Get list of all users."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT phone_number, name, authorized, date_added, expiry_date
            FROM authorized_users
            ORDER BY date_added DESC
        ''')
        return cursor.fetchall()

def get_user_info(phone_number):
    """Get detailed info about a specific user."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM authorized_users WHERE phone_number = ?
        ''', (phone_number,))
        return cursor.fetchone()

# =====================
# UTILITY FUNCTIONS
# =====================

def get_total_users():
    """Get total number of authorized users."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) as count FROM authorized_users WHERE authorized = 1')
        return cursor.fetchone()['count']

def clean_expired_users():
    """Deactivate users whose subscription has expired."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE authorized_users 
            SET authorized = 0 
            WHERE expiry_date IS NOT NULL 
            AND datetime(expiry_date) < datetime('now')
            AND authorized = 1
        ''')
        return cursor.rowcount