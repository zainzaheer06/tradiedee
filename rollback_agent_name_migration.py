"""
ROLLBACK Migration: Remove agent_name column from CallLog table

This script reverts the agent_name changes and restores the original database schema.

Usage:
    python rollback_agent_name_migration.py
"""
import os
import sys
import sqlite3
from datetime import datetime
import shutil

def get_db_path():
    """Get the database file path"""
    db_path = os.path.join('instance', 'voice_agent.db')
    if not os.path.exists(db_path):
        db_path = 'voice_agent.db'

    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found at: {db_path}")

    return db_path


def rollback_migration():
    """Rollback the migration - remove agent_name column"""
    db_path = get_db_path()
    print(f"Database: {db_path}")

    # Create backup
    backup_path = f"{db_path}.rollback_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(db_path, backup_path)
    print(f"Backup created: {backup_path}\n")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Step 1: Create new table WITHOUT agent_name column (original schema)
        print("Creating new table with original schema...")
        cursor.execute("""
            CREATE TABLE call_log_original (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                agent_id INTEGER,
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
                FOREIGN KEY (agent_id) REFERENCES agent(id)
            )
        """)

        # Step 2: Copy only VALID data (skip corrupted records)
        print("Copying valid records (skipping corrupted data)...")
        cursor.execute("""
            INSERT INTO call_log_original
                (id, user_id, agent_id, from_number, to_number, duration_seconds,
                 minutes_used, transcription, transcription_data, sentiment_summary,
                 room_name, status, recording_url, recording_id, call_type, created_at)
            SELECT
                id, user_id, agent_id, from_number, to_number, duration_seconds,
                minutes_used, transcription, transcription_data, sentiment_summary,
                room_name, status, recording_url, recording_id, call_type, created_at
            FROM call_log
            WHERE created_at LIKE '____-__-__ __:__:%'
        """)

        valid_count = cursor.rowcount
        print(f"Copied {valid_count} valid records")

        # Step 3: Count how many corrupted records were skipped
        cursor.execute("SELECT COUNT(*) FROM call_log")
        total_before = cursor.fetchone()[0]
        skipped = total_before - valid_count
        if skipped > 0:
            print(f"Skipped {skipped} corrupted records")

        # Step 4: Drop old table
        print("Dropping old table...")
        cursor.execute("DROP TABLE call_log")

        # Step 5: Rename new table
        print("Renaming new table...")
        cursor.execute("ALTER TABLE call_log_original RENAME TO call_log")

        # Commit changes
        conn.commit()
        print("\nRollback completed successfully!")
        print(f"- Valid records preserved: {valid_count}")
        print(f"- Corrupted records removed: {skipped}")
        print(f"- Backup location: {backup_path}")

    except Exception as e:
        print(f"\nRollback failed: {e}")
        conn.rollback()
        print(f"Database restored from backup: {backup_path}")
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    print("=" * 60)
    print("ROLLBACK: Remove agent_name Column from CallLog")
    print("=" * 60)

    try:
        rollback_migration()
        print("\nNext step: Revert the models.py changes to original schema")
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)
