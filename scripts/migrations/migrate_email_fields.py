"""
Database migration script to add email verification fields to User table
"""
import sqlite3
import os
import sys

# Fix encoding for Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

def migrate_database():
    # Check both possible database locations
    possible_paths = ['voice_agent.db', 'instance/voice_agent.db', 'instance\\voice_agent.db']
    db_path = None

    for path in possible_paths:
        if os.path.exists(path):
            db_path = path
            break

    if not db_path:
        print(f"✓ Database not found in common locations.")
        print("✓ This is fine - when you run the app, it will create a new database with the updated schema.")
        print("✓ No migration needed.")
        return

    print(f"Found database at: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if email verification columns already exist
    cursor.execute("PRAGMA table_info(user)")
    columns = [column[1] for column in cursor.fetchall()]

    migration_needed = False

    if 'is_email_verified' not in columns:
        migration_needed = True
        print("Adding is_email_verified column...")
        cursor.execute("ALTER TABLE user ADD COLUMN is_email_verified BOOLEAN DEFAULT 0")

    if 'email_verified_at' not in columns:
        migration_needed = True
        print("Adding email_verified_at column...")
        cursor.execute("ALTER TABLE user ADD COLUMN email_verified_at DATETIME")

    if not migration_needed:
        print("✓ Email verification columns already exist. No migration needed.")
        conn.close()
        return

    try:
        # Update existing users to have email verified (for backward compatibility)
        cursor.execute("UPDATE user SET is_email_verified = 1 WHERE is_admin = 1 OR is_approved = 1")

        conn.commit()
        print("✓ Successfully added email verification fields!")
        print("✓ Existing approved users have been marked as email verified.")
        print("✓ Migration completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"✗ Migration failed: {e}")
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    migrate_database()
