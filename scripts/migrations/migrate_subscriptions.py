"""
Migration script to add subscription features to the database
"""
import sqlite3
from datetime import datetime

def migrate():
    conn = sqlite3.connect('instance/voice_agent.db')
    cursor = conn.cursor()

    print("Starting subscription migration...")

    try:
        # Add subscription fields to User table
        print("Adding subscription_plan column...")
        cursor.execute("ALTER TABLE user ADD COLUMN subscription_plan VARCHAR(50) DEFAULT 'free'")

        print("Adding subscription_start_date column...")
        cursor.execute("ALTER TABLE user ADD COLUMN subscription_start_date DATETIME")

        print("Adding minutes_used column...")
        cursor.execute("ALTER TABLE user ADD COLUMN minutes_used INTEGER DEFAULT 0")

        # Update existing users with default values
        print("Updating existing users...")
        cursor.execute("""
            UPDATE user
            SET subscription_plan = 'free',
                subscription_start_date = created_at,
                minutes_used = 0
            WHERE subscription_plan IS NULL
        """)

        # Add last_used column to Agent table
        print("Adding last_used column to Agent table...")
        cursor.execute("ALTER TABLE agent ADD COLUMN last_used DATETIME")

        conn.commit()
        print("✅ Migration completed successfully!")

    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print(f"⚠️ Column already exists: {e}")
        else:
            print(f"❌ Error: {e}")
            conn.rollback()
            raise

    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
