# -*- coding: utf-8 -*-
"""
Migration script to add pre-call webhook fields to Workflow table.

This adds support for:
- Optional pre-call webhook to fetch customer data before call starts
- Configurable timeout for pre-call webhook
- Separate webhook URL for pre-call (optional, can use same URL as post-call)
"""

import sqlite3
import os
import sys
from datetime import datetime

# Fix encoding for Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def migrate():
    """Add pre-call webhook fields to Workflow table"""
    # Try multiple possible database paths
    db_paths = [
        os.path.join(os.path.dirname(__file__), '..', '..', 'voice_agent.db'),
        os.path.join(os.path.dirname(__file__), '..', '..', 'instance', 'voice_agent.db'),
        'voice_agent.db',
        'instance/voice_agent.db'
    ]

    db_path = None
    for path in db_paths:
        if os.path.exists(path):
            db_path = path
            break

    if not db_path:
        print("[ERROR] Database not found. Tried: " + str(db_paths))
        return False

    print("[OK] Using database at: " + db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if columns already exist
        print("[INFO] Checking existing workflow table structure...")
        cursor.execute("PRAGMA table_info(workflow)")
        columns = [row[1] for row in cursor.fetchall()]

        # Add pre_call_enabled column
        if 'pre_call_enabled' not in columns:
            print("[+] Adding pre_call_enabled column...")
            cursor.execute("""
                ALTER TABLE workflow ADD COLUMN pre_call_enabled BOOLEAN DEFAULT 0
            """)
            print("[OK] Added pre_call_enabled column")
        else:
            print("[INFO] pre_call_enabled column already exists")

        # Add pre_call_webhook_url column
        if 'pre_call_webhook_url' not in columns:
            print("[+] Adding pre_call_webhook_url column...")
            cursor.execute("""
                ALTER TABLE workflow ADD COLUMN pre_call_webhook_url VARCHAR(500)
            """)
            print("[OK] Added pre_call_webhook_url column")
        else:
            print("[INFO] pre_call_webhook_url column already exists")

        # Add pre_call_timeout column
        if 'pre_call_timeout' not in columns:
            print("[+] Adding pre_call_timeout column...")
            cursor.execute("""
                ALTER TABLE workflow ADD COLUMN pre_call_timeout INTEGER DEFAULT 3
            """)
            print("[OK] Added pre_call_timeout column")
        else:
            print("[INFO] pre_call_timeout column already exists")

        conn.commit()
        print("[OK] Migration completed successfully!")

        # Verify columns were added
        cursor.execute("PRAGMA table_info(workflow)")
        workflow_columns = [row[1] for row in cursor.fetchall()]

        new_columns = ['pre_call_enabled', 'pre_call_webhook_url', 'pre_call_timeout']
        for col in new_columns:
            if col in workflow_columns:
                print("[OK] Verified: " + col + " column exists")
            else:
                print("[ERROR] Warning: " + col + " column missing!")

        return True

    except sqlite3.Error as e:
        print("[ERROR] Migration failed: " + str(e))
        conn.rollback()
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    print("=" * 60)
    print("Starting Pre-Webhook Fields Migration...")
    print("=" * 60)
    success = migrate()
    print("=" * 60)
    if success:
        print("[SUCCESS] Migration completed successfully!")
        print("[INFO] You can now enable pre-call webhooks in Workflow settings")
    else:
        print("[FAILED] Migration failed!")
    print("=" * 60)