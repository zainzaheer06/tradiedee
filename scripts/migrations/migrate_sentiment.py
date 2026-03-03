"""
Migration script to add sentiment_summary field to CallLog table
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
    """Add sentiment_summary column to CallLog table if it doesn't exist"""

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

        if 'sentiment_summary' in columns:
            print("✅ Column 'sentiment_summary' already exists")
        else:
            # Add the new column
            cursor.execute("""
                ALTER TABLE call_log
                ADD COLUMN sentiment_summary TEXT DEFAULT '{}'
            """)
            conn.commit()
            print("✅ Added 'sentiment_summary' column")

        conn.close()

        print(f"✅ Migration completed successfully for {db_path}")
        return True

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🔄 Database Migration: Add Sentiment Analysis Field")
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
        print("\nSentiment Analysis is now enabled!")
        print("\nFeatures:")
        print("  📊 Automatic sentiment analysis after each call")
        print("  🎯 5 levels: Very Positive, Positive, Neutral, Negative, Very Negative")
        print("  📈 Timeline view showing sentiment changes over time")
        print("  💯 Overall sentiment score and counts")

    print("\n" + "="*60 + "\n")
