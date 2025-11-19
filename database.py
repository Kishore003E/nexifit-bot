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
    """Check if a phone number is authorized AND not expired."""
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
        
        authorized = result['authorized']
        expiry_date_str = result['expiry_date']
        
        # If manually deactivated
        if not authorized:
            return False
        
        # If expiry date is set, check if expired
        if expiry_date_str:
            try:
                # Handle both formats: with and without microseconds
                if '.' in expiry_date_str:
                    expiry_date = datetime.strptime(expiry_date_str.split('.')[0], '%Y-%m-%d %H:%M:%S')
                else:
                    expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d %H:%M:%S')
                
                if datetime.now() > expiry_date:
                    return False  # Expired
            except ValueError as e:
                print(f"Warning: Invalid expiry_date format for {phone_number}: {expiry_date_str}")
                # Optionally treat invalid date as no expiry or expired
                pass
        
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
    
# =====================
# BONUS PERSONALIZED TIPS ENGINE
# =====================

def get_personalized_bonus_tips(user_data):
    """
    Returns 1-2 highly relevant bonus tips based on user's profile.
    user_data = session dict from main.py (name, gender, age, fitness_goal, injury, etc.)
    """
    tips = []
    gender = str(user_data.get("gender", "")).strip().lower()
    goal = str(user_data.get("fitness_goal", "")).strip().lower()
    injury = str(user_data.get("injury", "")).strip().lower()
    age = user_data.get("age")
    name = user_data.get("name", "there")

    # ── FEMALE-SPECIFIC TIPS ─────────────────────────────────────
    if gender in ["female", "woman", "f", "girl"]:
        tips.append("As a woman, your energy & strength fluctuate with your menstrual cycle. "
                    "Train heavy during follicular phase (Day 1–14), go lighter during luteal phase. "
                    "Listen to your body — it's smart!")

        if "pcod" in goal or "pcos" in goal or "pcod" in injury or "pcos" in injury:
            tips.append("For PCOS/PCOD: Cut dairy completely for 30 days — switch to almond/coconut milk. "
                        "Add spearmint tea 2x/day & inositol-rich foods (citrus, beans). "
                        "Many users see major hormone improvement!")

        if "period" in injury.lower() or "cramps" in injury.lower():
            tips.append("Heavy periods or cramps? Avoid intense lower abs & high-impact on Day 1–2. "
                        "Try yoga flows, walking, or light mobility. Your body is doing heavy work already!")

    # ── MALE-SPECIFIC TIPS ───────────────────────────────────────
    if gender in ["male", "man", "m", "boy"]:
        if "testosterone" in goal or "muscle" in goal or "strength" in goal:
            tips.append("Men build max muscle when sleep >7.5 hrs + train in evening (4–7 PM) "
                        "when testosterone peaks. Morning cardio = fat loss. Evening weights = muscle gain!")

    # ── INJURY-SPECIFIC TIPS ─────────────────────────────────────
    if injury and injury != "none":
        if any(word in injury for word in ["knee", "acl", "meniscus"]):
            tips.append("Knee injury? Replace squats/jumps with Spanish squats, reverse sled drags, "
                        "or step-ups. Build quads without stressing the joint!")

        if any(word in injury for word in ["back", "lower back", "disc", "herniated"]):
            tips.append("Lower back pain? Master the McGill Big 3 (curl-up, side plank, bird dog) daily. "
                        "Avoid crunches & sit-ups. Deadlifts only after 3 months pain-free!")

        if any(word in injury for word in ["shoulder", "rotator", "impingement"]):
            tips.append("Shoulder issues? Stop bench press for 4–6 weeks. Focus on face pulls, "
                        "band pull-aparts & Cuban presses. Fix posture = fix shoulder!")

    # ── GOAL-SPECIFIC TIPS ───────────────────────────────────────
    if "weight loss" in goal or "fat loss" in goal or "lose weight" in goal:
        tips.append("*Pro tip:* Walk 8–10k steps daily + strength training 3x/week "
                    "burns MORE fat than cardio alone. Muscle = 24/7 calorie burner!")

    if "muscle" in goal or "bulk" in goal or "gain" in goal:
        tips.append("Want to gain muscle fast? Eat in surplus + sleep 8+ hrs + "
                    "train each muscle 2x/week. Progressive overload is king!")

    if "flexibility" in goal or "yoga" in goal or "mobility" in goal:
        tips.append("Stretch daily for 10 mins (same time every day). Consistency > intensity. "
                    "Hold each stretch 30–60s. You'll be touching your toes in 30 days!")

    # ── AGE-SPECIFIC (Optional future use)
    # if age and int(age) > 45:
    #     tips.append("After 45, recovery is priority #1. Add 1 extra rest day, prioritize protein (1.6g/kg), and sleep!")

    # Return only top 2 most relevant tips
    return tips[:2]


# =====================
# STREAK TRACKING FUNCTIONS
# =====================
# Add this section at the END of your database.py file, after the BONUS PERSONALIZED TIPS ENGINE section

def initialize_streak_tracking():
    """Initialize streak tracking table. Call this once during app startup."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS workout_streaks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone_number TEXT UNIQUE NOT NULL,
                    current_streak INTEGER DEFAULT 0,
                    longest_streak INTEGER DEFAULT 0,
                    last_workout_date DATE,
                    FOREIGN KEY (phone_number) REFERENCES authorized_users(phone_number)
                )
            ''')
            
            print("✅ Streak tracking table initialized!")
            return True
    except Exception as e:
        print(f"❌ Error initializing streak tracking: {e}")
        return False


def update_workout_streak(phone_number):
    """
    Update user's workout streak when they complete a workout.
    
    Logic:
    - If workout on consecutive day → increment streak
    - If workout after gap → reset to 1 (streak broken)
    - If same day → no change (already counted)
    
    Returns:
        tuple: (current_streak, is_new_record, broke_streak)
        
    Example:
        (5, True, False) = 5 days streak, new personal record, didn't break
        (1, False, True) = reset to 1, not a record, streak was broken
    """
    from datetime import timedelta
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        today = date.today()
        
        # Get existing streak data
        cursor.execute('''
            SELECT current_streak, longest_streak, last_workout_date 
            FROM workout_streaks 
            WHERE phone_number = ?
        ''', (phone_number,))
        
        result = cursor.fetchone()
        
        # ── FIRST TIME USER ──────────────────────────
        if not result:
            cursor.execute('''
                INSERT INTO workout_streaks (phone_number, current_streak, longest_streak, last_workout_date)
                VALUES (?, 1, 1, ?)
            ''', (phone_number, today))
            print(f"🎉 First workout logged for {phone_number}")
            return (1, True, False)  # streak=1, new_record=True, broke_streak=False
        
        # ── EXISTING USER ────────────────────────────
        current_streak = result['current_streak']
        longest_streak = result['longest_streak']
        last_workout_date = result['last_workout_date']
        
        # Parse last workout date
        if last_workout_date:
            last_date = date.fromisoformat(last_workout_date)
        else:
            last_date = None
        
        # ── SAME DAY (Already worked out today) ──────
        if last_date == today:
            print(f"ℹ️ Workout already logged today for {phone_number}")
            return (current_streak, False, False)  # No change
        
        # ── CONSECUTIVE DAY (Yesterday) ──────────────
        if last_date == today - timedelta(days=1):
            current_streak += 1
            broke_streak = False
            print(f"🔥 Streak continues! {current_streak} days for {phone_number}")
        
        # ── STREAK BROKEN (Gap detected) ─────────────
        elif last_date and last_date < today - timedelta(days=1):
            current_streak = 1
            broke_streak = True
            print(f"🌱 Streak reset for {phone_number}. Starting fresh!")
        
        # ── EDGE CASE (First workout or unusual scenario) ──
        else:
            current_streak = 1
            broke_streak = False
        
        # ── CHECK IF NEW RECORD ──────────────────────
        is_new_record = current_streak > longest_streak
        if is_new_record:
            longest_streak = current_streak
            print(f"🏆 NEW RECORD! {current_streak} days for {phone_number}")
        
        # ── UPDATE DATABASE ──────────────────────────
        cursor.execute('''
            UPDATE workout_streaks 
            SET current_streak = ?, 
                longest_streak = ?, 
                last_workout_date = ?
            WHERE phone_number = ?
        ''', (current_streak, longest_streak, today, phone_number))
        
        return (current_streak, is_new_record, broke_streak)


def get_user_streak(phone_number):
    """
    Get user's current streak information.
    
    Returns:
        dict: {
            'current_streak': int,
            'longest_streak': int,
            'last_workout_date': str (YYYY-MM-DD) or None
        }
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT current_streak, longest_streak, last_workout_date
            FROM workout_streaks
            WHERE phone_number = ?
        ''', (phone_number,))
        
        result = cursor.fetchone()
        
        # If user hasn't started tracking yet
        if not result:
            return {
                'current_streak': 0,
                'longest_streak': 0,
                'last_workout_date': None
            }
        
        return {
            'current_streak': result['current_streak'],
            'longest_streak': result['longest_streak'],
            'last_workout_date': result['last_workout_date']
        }


def get_streak_leaderboard(limit=10):
    """
    Get top users by current streak (optional feature for gamification).
    
    Args:
        limit: Number of top users to return
        
    Returns:
        list: Top users sorted by current streak
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                ws.phone_number,
                au.name,
                ws.current_streak,
                ws.longest_streak
            FROM workout_streaks ws
            JOIN authorized_users au ON ws.phone_number = au.phone_number
            WHERE au.authorized = 1
            ORDER BY ws.current_streak DESC, ws.longest_streak DESC
            LIMIT ?
        ''', (limit,))
        
        return cursor.fetchall()


# =====================
# END OF STREAK TRACKING
# =====================