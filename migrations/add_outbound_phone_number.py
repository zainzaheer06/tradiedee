"""
Migration: Add outbound_phone_number field to User model
Date: 2026-02-03
Description: Store phone number alongside trunk ID for accurate call log "From Number" display
"""

import sqlite3
import os
import glob

def find_database():
    """Find the database file with tables"""
    base_dir = os.path.dirname(os.path.dirname(__file__))

    # Search for all .db files
    db_files = glob.glob(os.path.join(base_dir, '**', '*.db'), recursive=True)

    print(f"Found {len(db_files)} database files:")
    for db_file in db_files:
        try:
            conn = sqlite3.connect(db_file)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [t[0] for t in cursor.fetchall()]
            conn.close()

            has_user = any(t.lower() == 'user' for t in tables)
            print(f"  - {db_file}: {len(tables)} tables, has_user={has_user}")

            if has_user:
                return db_file
        except Exception as e:
            print(f"  - {db_file}: Error - {e}")

    return None

def run_migration():
    db_path = find_database()

    if not db_path:
        print("Error: Could not find database file.")
        print("Please specify the database path manually.")
        return False

    print(f"Connecting to database: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # List all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [t[0] for t in cursor.fetchall()]
        print(f"Tables found: {tables}")

        # Find the user table (might be 'user' or 'User')
        user_table = None
        for t in tables:
            if t.lower() == 'user':
                user_table = t
                break

        if not user_table:
            print("Error: Could not find user table")
            return False

        print(f"Using table: {user_table}")

        # Check if column already exists
        cursor.execute(f"PRAGMA table_info({user_table})")
        columns = [col[1] for col in cursor.fetchall()]
        print(f"Existing columns: {columns}")

        if 'outbound_phone_number' in columns:
            print("Column 'outbound_phone_number' already exists. Skipping migration.")
            return True

        # Add the new column
        print(f"Adding 'outbound_phone_number' column to {user_table} table...")
        cursor.execute(f"ALTER TABLE {user_table} ADD COLUMN outbound_phone_number VARCHAR(20)")

        conn.commit()
        print("Migration completed successfully!")
        return True

    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()
        return False

    finally:
        conn.close()

if __name__ == '__main__':
    run_migration()
