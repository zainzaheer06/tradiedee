"""
Migration script to add transcription_data field to CallLog table
Run this script to update your existing database
"""

import sqlite3
import os
import sys

# Fix Windows console encoding
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def migrate_database(db_path):
    """Add transcription_data column to CallLog table if it doesn't exist"""

    if not os.path.exists(db_path):
        print(f"❌ Database not found: {db_path}")
        return False

    print(f"📊 Migrating database: {db_path}")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if column already exists
        cursor.execute("PRAGMA table_info(call_log)")
        columns = [column[1] for column in cursor.fetchall()]

        if 'transcription_data' in columns:
            print("✅ Column 'transcription_data' already exists")
        else:
            # Add the new column
            cursor.execute("""
                ALTER TABLE call_log
                ADD COLUMN transcription_data TEXT DEFAULT '{}'
            """)
            conn.commit()
            print("✅ Added 'transcription_data' column")

        # Check if recording columns exist
        if 'recording_url' not in columns:
            cursor.execute("""
                ALTER TABLE call_log
                ADD COLUMN recording_url TEXT
            """)
            print("✅ Added 'recording_url' column")

        if 'recording_id' not in columns:
            cursor.execute("""
                ALTER TABLE call_log
                ADD COLUMN recording_id TEXT
            """)
            print("✅ Added 'recording_id' column")

        conn.commit()
        conn.close()

        print(f"✅ Migration completed successfully for {db_path}")
        return True

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🔄 Database Migration: Add Transcription Data Fields")
    print("="*60 + "\n")

    # Migrate both possible database locations
    databases = [
        'instance/voice_agent.db',
        'voice_agent.db',
        'nevox.db'
    ]

    migrated = False
    for db_path in databases:
        if os.path.exists(db_path):
            if migrate_database(db_path):
                migrated = True

    if not migrated:
        print("\n⚠️  No database files found to migrate")
        print("The migration will happen automatically when you run the app")
    else:
        print("\n✅ All migrations completed!")
        print("\nYou can now:")
        print("1. Run your Flask app")
        print("2. Make test calls with your agents")
        print("3. View the transcription data in the call logs")

    print("\n" + "="*60 + "\n")
