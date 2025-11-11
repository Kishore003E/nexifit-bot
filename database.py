import sqlite3
from datetime import datetime, date
from contextlib import contextmanager
import random

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
            
            # Auto-enable tips for new users
            cursor.execute('''
                INSERT INTO user_tip_preferences (phone_number, receive_tips)
                VALUES (?, 1)
            ''', (phone_number,))
            
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
        count = cursor.rowcount
        if count > 0:
            print(f"🧹 Cleaned {count} expired users")
        return count

# =====================
# MENTAL HEALTH TIPS FUNCTIONS
# =====================

def add_mental_health_tip(tip_text, category='general'):
    """Add a new mental health tip."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO mental_health_tips (tip_text, category)
                VALUES (?, ?)
            ''', (tip_text, category))
            return True, "Tip added successfully!", cursor.lastrowid
    except Exception as e:
        return False, f"Error: {str(e)}", None

def get_all_mental_health_tips(active_only=True):
    """Get all mental health tips."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if active_only:
            cursor.execute('''
                SELECT * FROM mental_health_tips 
                WHERE active = 1 
                ORDER BY category, id
            ''')
        else:
            cursor.execute('''
                SELECT * FROM mental_health_tips 
                ORDER BY category, id
            ''')
        return cursor.fetchall()

def get_tip_by_id(tip_id):
    """Get a specific tip by ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM mental_health_tips WHERE id = ?
        ''', (tip_id,))
        return cursor.fetchone()

def deactivate_tip(tip_id):
    """Deactivate a mental health tip."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE mental_health_tips 
            SET active = 0 
            WHERE id = ?
        ''', (tip_id,))
        
        if cursor.rowcount > 0:
            return True, "Tip deactivated successfully!"
        else:
            return False, "Tip not found"

def activate_tip(tip_id):
    """Reactivate a mental health tip."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE mental_health_tips 
            SET active = 1 
            WHERE id = ?
        ''', (tip_id,))
        
        if cursor.rowcount > 0:
            return True, "Tip reactivated successfully!"
        else:
            return False, "Tip not found"

def get_next_tip_for_user(phone_number):
    """
    Get the next tip for a user using smart rotation.
    Avoids tips sent in the last 15 days.
    If all tips exhausted, resets and starts over.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Get all active tips
        cursor.execute('SELECT id FROM mental_health_tips WHERE active = 1')
        all_tips = [row['id'] for row in cursor.fetchall()]
        
        if not all_tips:
            return None
        
        # Get tips sent to this user in the last 15 days
        cursor.execute('''
            SELECT DISTINCT tip_id 
            FROM user_tip_history 
            WHERE phone_number = ? 
            AND sent_date >= date('now', '-15 days')
        ''', (phone_number,))
        
        recent_tips = [row['tip_id'] for row in cursor.fetchall()]
        
        # Get available tips (not sent recently)
        available_tips = [tip_id for tip_id in all_tips if tip_id not in recent_tips]
        
        # If no available tips, reset and use all tips
        if not available_tips:
            available_tips = all_tips
        
        # Select random tip from available
        selected_tip_id = random.choice(available_tips)
        
        # Get the full tip
        cursor.execute('''
            SELECT * FROM mental_health_tips WHERE id = ?
        ''', (selected_tip_id,))
        
        return cursor.fetchone()

def log_tip_sent(phone_number, tip_id):
    """Log that a tip was sent to a user."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO user_tip_history (phone_number, tip_id, sent_date)
                VALUES (?, ?, date('now'))
            ''', (phone_number, tip_id))
            return True
    except Exception as e:
        print(f"Error logging tip: {e}")
        return False

# =====================
# USER TIP PREFERENCES
# =====================

def set_user_tip_preference(phone_number, receive_tips=True):
    """Set user's preference for receiving daily tips."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO user_tip_preferences (phone_number, receive_tips)
                VALUES (?, ?)
                ON CONFLICT(phone_number) DO UPDATE SET
                    receive_tips = ?,
                    last_modified = CURRENT_TIMESTAMP
            ''', (phone_number, 1 if receive_tips else 0, 1 if receive_tips else 0))
            return True
    except Exception as e:
        print(f"Error setting tip preference: {e}")
        return False

def get_user_tip_preference(phone_number):
    """Get user's tip preferences."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM user_tip_preferences WHERE phone_number = ?
        ''', (phone_number,))
        result = cursor.fetchone()
        
        # If no preference set, default to enabled
        if not result:
            set_user_tip_preference(phone_number, True)
            return {'receive_tips': 1, 'preferred_time': '07:00'}
        
        return result

def get_users_for_daily_tips():
    """Get all users who should receive daily tips."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT DISTINCT au.phone_number, au.name
            FROM authorized_users au
            LEFT JOIN user_tip_preferences utp ON au.phone_number = utp.phone_number
            WHERE au.authorized = 1
            AND (utp.receive_tips IS NULL OR utp.receive_tips = 1)
        ''')
        return cursor.fetchall()

# =====================
# TIP STATISTICS
# =====================

def get_user_tip_stats(phone_number):
    """Get statistics about tips sent to a user."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Total tips sent
        cursor.execute('''
            SELECT COUNT(*) as total FROM user_tip_history 
            WHERE phone_number = ?
        ''', (phone_number,))
        total = cursor.fetchone()['total']
        
        # Tips sent in last 30 days
        cursor.execute('''
            SELECT COUNT(*) as recent FROM user_tip_history 
            WHERE phone_number = ? 
            AND sent_date >= date('now', '-30 days')
        ''', (phone_number,))
        recent = cursor.fetchone()['recent']
        
        # Last tip sent date
        cursor.execute('''
            SELECT MAX(sent_date) as last_date FROM user_tip_history 
            WHERE phone_number = ?
        ''', (phone_number,))
        last_date = cursor.fetchone()['last_date']
        
        return {
            'total_tips_received': total,
            'tips_last_30_days': recent,
            'last_tip_date': last_date
        }

def get_global_tip_stats():
    """Get global statistics about tips."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Total active tips
        cursor.execute('SELECT COUNT(*) as count FROM mental_health_tips WHERE active = 1')
        total_tips = cursor.fetchone()['count']
        
        # Total tips sent today
        cursor.execute('''
            SELECT COUNT(*) as count FROM user_tip_history 
            WHERE sent_date = date('now')
        ''')
        tips_today = cursor.fetchone()['count']
        
        # Users with tips enabled
        cursor.execute('''
            SELECT COUNT(*) as count FROM user_tip_preferences 
            WHERE receive_tips = 1
        ''')
        users_enabled = cursor.fetchone()['count']
        
        # Category breakdown
        cursor.execute('''
            SELECT category, COUNT(*) as count 
            FROM mental_health_tips 
            WHERE active = 1 
            GROUP BY category
        ''')
        categories = cursor.fetchall()
        
        return {
            'total_active_tips': total_tips,
            'tips_sent_today': tips_today,
            'users_with_tips_enabled': users_enabled,
            'tips_by_category': dict(categories)
        }
# =====================
# WORKOUT TRACKING FUNCTIONS
# =====================

def log_workout_completion(phone_number, workout_minutes, calories_burned, progress_percent, goal):
    """Save workout data for progress tracking."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO workout_logs (phone_number, workout_minutes, calories_burned, progress_percent, goal)
                VALUES (?, ?, ?, ?, ?)
            ''', (phone_number, workout_minutes, calories_burned, progress_percent, goal))
            return True
    except Exception as e:
        print(f"Error logging workout: {e}")
        return False

def get_weekly_progress(phone_number):
    """Get user's workout stats for the last 7 days."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                COUNT(*) as workouts_completed,
                SUM(workout_minutes) as total_minutes,
                SUM(calories_burned) as total_calories,
                AVG(progress_percent) as avg_progress,
                goal
            FROM workout_logs
            WHERE phone_number = ? 
            AND date_completed >= datetime('now', '-7 days')
        ''', (phone_number,))
        
        result = cursor.fetchone()
        
        if result and result['workouts_completed'] > 0:
            return {
                'workouts_completed': result['workouts_completed'],
                'total_minutes': result['total_minutes'] or 0,
                'total_calories': result['total_calories'] or 0,
                'avg_progress': result['avg_progress'] or 0,
                'goal': result['goal']
            }
        return None

def get_users_for_weekly_report():
    """Get all active users for sending weekly reports."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT phone_number, name 
            FROM authorized_users 
            WHERE authorized = 1
        ''')
        return cursor.fetchall()
    

