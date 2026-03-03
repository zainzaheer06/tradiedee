"""
Database Migration: Add agent_name column to CallLog table

This migration:
1. Adds agent_name column to call_log table
2. Populates existing call logs with agent names from the agent relationship
3. Updates foreign key constraint to SET NULL on delete

Run this script once to migrate existing data.

Usage:
    python migrations/add_agent_name_to_call_logs.py
"""
import os
import sys
import sqlite3
from datetime import datetime

# Add parent directory to path to import models
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def get_db_path():
    """Get the database file path"""
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance', 'voice_agent.db')
    if not os.path.exists(db_path):
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'voice_agent.db')

    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found at: {db_path}")

    return db_path


def migrate_database():
    """Run the migration"""
    db_path = get_db_path()
    print(f"📂 Database: {db_path}")

    # Create backup
    backup_path = f"{db_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    import shutil
    shutil.copy2(db_path, backup_path)
    print(f"💾 Backup created: {backup_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Step 1: Check if agent_name column already exists
        cursor.execute("PRAGMA table_info(call_log)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'agent_name' in columns:
            print("✅ agent_name column already exists, skipping creation")
        else:
            # Step 2: Add agent_name column
            print("➕ Adding agent_name column to call_log table...")
            cursor.execute("""
                ALTER TABLE call_log
                ADD COLUMN agent_name VARCHAR(100)
            """)
            print("✅ Column added successfully")

        # Step 3: Populate agent_name for existing call logs
        print("📝 Populating agent names for existing call logs...")
        cursor.execute("""
            UPDATE call_log
            SET agent_name = (
                SELECT name
                FROM agent
                WHERE agent.id = call_log.agent_id
            )
            WHERE agent_id IS NOT NULL AND agent_name IS NULL
        """)
        updated_count = cursor.rowcount
        print(f"✅ Updated {updated_count} call log(s) with agent names")

        # Step 4: Recreate the table with proper foreign key constraint
        # SQLite doesn't support modifying foreign keys, so we need to recreate the table
        print("🔄 Recreating table with SET NULL foreign key constraint...")

        # Create new table with correct constraints
        cursor.execute("""
            CREATE TABLE call_log_new (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                agent_id INTEGER,
                agent_name VARCHAR(100),
                from_number VARCHAR(20) NOT NULL,
                to_number VARCHAR(20) NOT NULL,
                duration_seconds INTEGER DEFAULT 0,
                minutes_used INTEGER DEFAULT 0,
                transcription TEXT DEFAULT '',
                transcription_data TEXT DEFAULT '{}',
                sentiment_summary TEXT DEFAULT '{}',
                room_name VARCHAR(100),
                status VARCHAR(20) DEFAULT 'completed',
                recording_url VARCHAR(500),
                recording_id VARCHAR(100),
                call_type VARCHAR(10) DEFAULT 'outbound',
                created_at DATETIME,
                FOREIGN KEY (user_id) REFERENCES user(id),
                FOREIGN KEY (agent_id) REFERENCES agent(id) ON DELETE SET NULL
            )
        """)

        # Copy data from old table to new table
        cursor.execute("""
            INSERT INTO call_log_new
            SELECT * FROM call_log
        """)

        # Drop old table
        cursor.execute("DROP TABLE call_log")

        # Rename new table
        cursor.execute("ALTER TABLE call_log_new RENAME TO call_log")

        print("✅ Table recreated with proper foreign key constraints")

        # Commit changes
        conn.commit()
        print("✅ Migration completed successfully!")

        # Show summary
        cursor.execute("SELECT COUNT(*) FROM call_log WHERE agent_name IS NOT NULL")
        count_with_names = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM call_log WHERE agent_id IS NULL")
        count_orphaned = cursor.fetchone()[0]

        print("\n📊 Summary:")
        print(f"   - Call logs with agent names: {count_with_names}")
        print(f"   - Call logs with null agent_id: {count_orphaned}")
        print(f"   - Backup location: {backup_path}")

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
        print(f"💾 Database restored from backup: {backup_path}")
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    print("=" * 60)
    print("Database Migration: Add agent_name to CallLog")
    print("=" * 60)

    try:
        migrate_database()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

    print("\n✅ Migration complete! You can now safely delete agents.")
    print("   - Call history will be preserved")
    print("   - Agent names will show even after deletion")
