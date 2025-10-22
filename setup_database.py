import sqlite3
from datetime import datetime, timedelta

def setup_database():
    """Create the database and tables for user authentication."""
    
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
    
    conn.close()
    print("\n🎉 Database setup complete!")
    print("📝 Database file: nexifit_users.db")

if __name__ == "__main__":
    setup_database()