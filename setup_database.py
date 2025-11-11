import sqlite3
from datetime import datetime, timedelta

def setup_database():
    """Create the database and tables for user authentication and mental health tips."""
    
    conn = sqlite3.connect('nexifit_users.db')
    cursor = conn.cursor()
    
    # Create authorized users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS authorized_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT UNIQUE NOT NULL,
            name TEXT,
            authorized INTEGER DEFAULT 1,
            date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expiry_date TIMESTAMP,
            notes TEXT
        )
    ''')
    
    # Create admin users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT UNIQUE NOT NULL,
            name TEXT,
            date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create audit log table (tracks all authentication attempts)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS auth_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT NOT NULL,
            action TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            success INTEGER DEFAULT 0
        )
    ''')
    
    # =====================
    # WORKOUT TRACKING TABLE
    # =====================

    # Track completed workouts for progress reports
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS workout_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT NOT NULL,
            workout_minutes INTEGER,
            calories_burned INTEGER,
            progress_percent REAL,
            goal TEXT,
            date_completed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (phone_number) REFERENCES authorized_users(phone_number)
        )
    ''')

    # Create index for faster queries
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_workout_logs_phone_date 
        ON workout_logs(phone_number, date_completed)
    ''')


    # =====================
    # MENTAL HEALTH TIPS TABLES
    # =====================
    
    # Mental health tips storage
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mental_health_tips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tip_text TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            active INTEGER DEFAULT 1
        )
    ''')
    
    # User preferences for daily tips
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_tip_preferences (
            phone_number TEXT PRIMARY KEY,
            receive_tips INTEGER DEFAULT 1,
            preferred_time TEXT DEFAULT '07:00',
            last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (phone_number) REFERENCES authorized_users(phone_number)
        )
    ''')
    
    # Track which tips were sent to which users
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_tip_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT NOT NULL,
            tip_id INTEGER NOT NULL,
            sent_date DATE NOT NULL,
            sent_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tip_id) REFERENCES mental_health_tips(id),
            FOREIGN KEY (phone_number) REFERENCES authorized_users(phone_number)
        )
    ''')
    
    # Create indexes for better performance
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_user_tip_history_phone 
        ON user_tip_history(phone_number)
    ''')
    
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_user_tip_history_date 
        ON user_tip_history(sent_date)
    ''')
    
    conn.commit()
    print("✅ Database tables created successfully!")
    
    # Add a default admin (REPLACE WITH YOUR ACTUAL WHATSAPP NUMBER)
    default_admin = "whatsapp:+918667643749"  # ⚠️ CHANGE THIS!
    
    try:
        cursor.execute('''
            INSERT INTO admin_users (phone_number, name) 
            VALUES (?, ?)
        ''', (default_admin, "System Admin"))
        
        # Also add admin as authorized user
        cursor.execute('''
            INSERT INTO authorized_users (phone_number, name, authorized) 
            VALUES (?, ?, 1)
        ''', (default_admin, "System Admin"))
        
        conn.commit()
        print(f"✅ Default admin added: {default_admin}")
    except sqlite3.IntegrityError:
        print("ℹ️ Admin already exists in database")
    
    # =====================
    # SEED MENTAL HEALTH TIPS
    # =====================
    seed_mental_health_tips(cursor)
    conn.commit()
    
    conn.close()
    print("\n🎉 Database setup complete!")
    print("📝 Database file: nexifit_users.db")
    print(f"💭 Mental health tips loaded: Check with ADMIN LIST_TIPS")


def seed_mental_health_tips(cursor):
    """Populate initial mental health tips."""
    
    tips = [
        # Motivation (10 tips)
        ("Start your day with gratitude. Name three things you're thankful for today. Small moments of appreciation can shift your entire mindset.", "motivation"),
        ("Remember: Progress, not perfection. Every small step forward counts, even on days when you feel you're barely moving.", "motivation"),
        ("You are stronger than you think. The fact that you're here, trying, is proof of your resilience and courage.", "motivation"),
        ("Celebrate small wins today. Did you drink water? Take a walk? That's progress worth acknowledging.", "motivation"),
        ("Your mental health journey is just as important as your physical fitness. Both deserve equal attention and care.", "motivation"),
        ("Be patient with yourself. Growth takes time, and setbacks are part of the process, not signs of failure.", "motivation"),
        ("You don't have to be positive all the time. It's okay to have difficult days. What matters is that you keep going.", "motivation"),
        ("Your worth is not determined by your productivity. Rest is not laziness; it's essential for growth.", "motivation"),
        ("Every expert was once a beginner. Trust the process and keep showing up for yourself.", "motivation"),
        ("You are doing better than you think. Sometimes we can't see our own progress while we're in the middle of it.", "motivation"),
        
        # Stress Management (10 tips)
        ("Take 5 deep breaths right now. Inhale for 4 counts, hold for 4, exhale for 6. Notice how your body feels after.", "stress"),
        ("When overwhelmed, try the 5-4-3-2-1 technique: Name 5 things you see, 4 you can touch, 3 you hear, 2 you smell, 1 you taste.", "stress"),
        ("Stress is normal, but chronic stress isn't. If you're feeling overwhelmed, it's okay to ask for help or take a break.", "stress"),
        ("Physical exercise is a powerful stress reliever. Even a 10-minute walk can significantly reduce stress hormones.", "stress"),
        ("Write down what's stressing you. Sometimes seeing worries on paper helps you realize they're more manageable than they feel.", "stress"),
        ("Practice saying 'no' to protect your energy. You can't pour from an empty cup.", "stress"),
        ("Schedule 'worry time' - allow yourself 15 minutes to worry, then consciously move on. Don't let stress consume your whole day.", "stress"),
        ("Connect with someone you trust. Talking about stress often makes it feel lighter and more manageable.", "stress"),
        ("Limit caffeine when stressed. While it might feel helpful, it can actually increase anxiety and stress levels.", "stress"),
        ("Remember: You can only control your actions, not outcomes. Focus your energy on what's within your control.", "stress"),
        
        # Mindfulness (10 tips)
        ("Take a mindful minute. Close your eyes and focus only on your breath. Let thoughts pass like clouds in the sky.", "mindfulness"),
        ("Eat one meal today without distractions. Notice the flavors, textures, and how your body feels as you eat.", "mindfulness"),
        ("Practice body scanning: Starting from your toes, slowly bring awareness to each part of your body, releasing tension.", "mindfulness"),
        ("Be present in simple moments. Feel the water when you wash your hands, notice the warmth of the sun, hear the birds.", "mindfulness"),
        ("Mindfulness isn't about stopping thoughts. It's about observing them without judgment and gently returning to the present.", "mindfulness"),
        ("Try a walking meditation today. Focus on each step, the movement of your body, the feeling of your feet touching the ground.", "mindfulness"),
        ("When emotions feel intense, pause and name them. 'I'm feeling anxious' creates distance and helps you respond vs. react.", "mindfulness"),
        ("Practice loving-kindness meditation: Wish yourself well, then extend those wishes to others. Start with 'May I be happy and healthy.'", "mindfulness"),
        ("Notice one beautiful thing today. A flower, a smile, a sunset. Let yourself fully experience that moment of beauty.", "mindfulness"),
        ("Your breath is always with you as an anchor to the present moment. When lost in thoughts, return to your breathing.", "mindfulness"),
        
        # Sleep & Recovery (10 tips)
        ("Aim for 7-9 hours of sleep tonight. Quality sleep is when your body repairs muscles and your mind processes emotions.", "sleep"),
        ("Create a wind-down routine 30 minutes before bed. Dim lights, avoid screens, and signal your body it's time to rest.", "sleep"),
        ("Your bedroom should be cool, dark, and quiet. These conditions promote deeper, more restorative sleep.", "sleep"),
        ("Avoid screens 1 hour before bed. Blue light suppresses melatonin and can delay sleep by up to 3 hours.", "sleep"),
        ("If you can't sleep, don't fight it. Get up, do something calming, and return to bed when you feel sleepy.", "sleep"),
        ("Consistency matters: Try to wake up and go to bed at the same time every day, even on weekends.", "sleep"),
        ("Naps can be helpful, but keep them under 30 minutes and before 3 PM to avoid disrupting night sleep.", "sleep"),
        ("Physical activity helps sleep quality, but avoid intense workouts 3 hours before bed as they can be energizing.", "sleep"),
        ("Write down tomorrow's tasks before bed. This 'brain dump' can prevent late-night worrying and improve sleep.", "sleep"),
        ("Recovery isn't lazy. Rest days allow your body and mind to rebuild stronger. Honor your need for recovery.", "sleep"),
        
        # Positivity & Self-Compassion (10 tips)
        ("Speak to yourself like you would to a good friend. Would you be this harsh to someone you care about?", "positivity"),
        ("Negative thoughts are not facts. Challenge them: What evidence supports this? What evidence contradicts it?", "positivity"),
        ("Start a gratitude journal. Write 3 good things that happened today, no matter how small.", "positivity"),
        ("Practice self-compassion: Acknowledge your pain, remember you're not alone, and treat yourself with kindness.", "positivity"),
        ("Your feelings are valid, but they don't define your reality. It's okay to feel bad and still be okay.", "positivity"),
        ("Compare yourself only to who you were yesterday. Everyone's journey is different and uniquely their own.", "positivity"),
        ("Perfectionism is a cage. Embrace 'good enough' and free yourself from impossible standards.", "positivity"),
        ("Surround yourself with positivity. The energy you consume matters - choose content and people that uplift you.", "positivity"),
        ("It's okay to not be okay. Mental health struggles don't make you weak; seeking help makes you strong.", "positivity"),
        ("Celebrate your uniqueness. What makes you different is what makes you valuable. You are enough, exactly as you are.", "positivity"),
    ]
    
    # Check if tips already exist
    cursor.execute('SELECT COUNT(*) as count FROM mental_health_tips')
    existing_count = cursor.fetchone()[0]
    
    if existing_count == 0:
        cursor.executemany('''
            INSERT INTO mental_health_tips (tip_text, category)
            VALUES (?, ?)
        ''', tips)
        print(f"✅ Seeded {len(tips)} mental health tips")
    else:
        print(f"ℹ️ Mental health tips already exist ({existing_count} tips)")


if __name__ == "__main__":
    setup_database()