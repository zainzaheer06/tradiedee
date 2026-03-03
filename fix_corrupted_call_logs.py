"""
Fix corrupted call_log records with invalid datetime values

This script fixes rows where:
- created_at contains 'testing' or agent names instead of timestamps
- Columns appear to be misaligned

Run this before using the delete agent function.
"""
import sqlite3
import os
from datetime import datetime

def get_db_path():
    """Get the database file path"""
    db_path = os.path.join('instance', 'voice_agent.db')
    if not os.path.exists(db_path):
        db_path = 'voice_agent.db'

    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found")

    return db_path

def fix_corrupted_records():
    """Fix or delete corrupted call_log records"""
    db_path = get_db_path()
    print(f"Database: {db_path}\n")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Find corrupted records (created_at contains text instead of datetime)
        cursor.execute("""
            SELECT id, agent_id, agent_name, created_at, status
            FROM call_log
            WHERE created_at LIKE '%testing%' OR created_at LIKE '%Agent%'
        """)
        corrupted_rows = cursor.fetchall()

        if not corrupted_rows:
            print("No corrupted records found!")
            return

        print(f"Found {len(corrupted_rows)} corrupted record(s):\n")
        for row in corrupted_rows:
            print(f"  ID {row[0]}: agent_id={row[1]}, agent_name={row[2]}, created_at={row[3]}, status={row[4]}")

        print("\nOptions:")
        print("1. Delete these corrupted records (RECOMMENDED)")
        print("2. Fix them with placeholder values")
        print("3. Cancel")

        choice = input("\nEnter choice (1-3): ").strip()

        if choice == '1':
            # Delete corrupted records
            ids_to_delete = [row[0] for row in corrupted_rows]
            placeholders = ','.join('?' * len(ids_to_delete))
            cursor.execute(f"DELETE FROM call_log WHERE id IN ({placeholders})", ids_to_delete)
            conn.commit()
            print(f"\nDeleted {len(ids_to_delete)} corrupted record(s)")

        elif choice == '2':
            # Fix with placeholder values
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            for row in corrupted_rows:
                call_id = row[0]
                agent_id = row[1]

                # Try to get agent name from agent table
                cursor.execute("SELECT name FROM agent WHERE id = ?", (agent_id,))
                agent_row = cursor.fetchone()
                agent_name = agent_row[0] if agent_row else 'Unknown Agent'

                # Fix the record
                cursor.execute("""
                    UPDATE call_log
                    SET agent_name = ?,
                        created_at = ?,
                        status = CASE WHEN status IS NULL THEN 'completed' ELSE status END
                    WHERE id = ?
                """, (agent_name, now, call_id))

            conn.commit()
            print(f"\nFixed {len(corrupted_rows)} record(s)")
        else:
            print("\nCancelled")
            return

        print("\nDone!")

    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    print("=" * 60)
    print("Fix Corrupted Call Log Records")
    print("=" * 60)
    fix_corrupted_records()
