"""
Database migration to add inbound call support

This script adds necessary columns to support inbound call agents:
- agent.call_type: 'outbound' or 'inbound'
- agent.dispatch_rule_id: LiveKit SIP dispatch rule ID
- agent.phone_number: Inbound phone number
- call_log.call_type: Track if call was inbound or outbound
"""

import sqlite3
import os

def migrate_database():
    # Find database
    db_paths = [
        'instance/voice_agent.db',
        'voice_agent.db',
        'nevox.db'
    ]

    db_path = None
    for path in db_paths:
        if os.path.exists(path):
            db_path = path
            break

    if not db_path:
        print("[ERROR] Database not found!")
        return False

    print(f"Using database: {db_path}")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if columns already exist
        cursor.execute("PRAGMA table_info(agent)")
        columns = [row[1] for row in cursor.fetchall()]

        migrations_applied = []

        # Add call_type column to agent table
        if 'call_type' not in columns:
            cursor.execute("""
                ALTER TABLE agent
                ADD COLUMN call_type VARCHAR(10) DEFAULT 'outbound'
            """)
            migrations_applied.append("Added agent.call_type column")

        # Add dispatch_rule_id column to agent table
        if 'dispatch_rule_id' not in columns:
            cursor.execute("""
                ALTER TABLE agent
                ADD COLUMN dispatch_rule_id VARCHAR(50) NULL
            """)
            migrations_applied.append("Added agent.dispatch_rule_id column")

        # Add phone_number column to agent table
        if 'phone_number' not in columns:
            cursor.execute("""
                ALTER TABLE agent
                ADD COLUMN phone_number VARCHAR(20) NULL
            """)
            migrations_applied.append("Added agent.phone_number column")

        # Check call_log table
        cursor.execute("PRAGMA table_info(call_log)")
        call_log_columns = [row[1] for row in cursor.fetchall()]

        # Add call_type column to call_log table
        if 'call_type' not in call_log_columns:
            cursor.execute("""
                ALTER TABLE call_log
                ADD COLUMN call_type VARCHAR(10) DEFAULT 'outbound'
            """)
            migrations_applied.append("Added call_log.call_type column")

        conn.commit()

        if migrations_applied:
            print("\nMigration completed successfully!")
            for msg in migrations_applied:
                print(f"   {msg}")
        else:
            print("\nDatabase already up to date - no migrations needed")

        conn.close()
        return True

    except sqlite3.Error as e:
        print(f"\n[ERROR] Migration failed: {e}")
        return False

if __name__ == "__main__":
    print("="*60)
    print("Inbound Call Migration")
    print("="*60)
    print()

    if migrate_database():
        print("\n[SUCCESS] You can now create inbound agents!")
    else:
        print("\n[ERROR] Migration failed - please check errors above")
