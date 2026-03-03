"""
Migration: Add Pre-call and Post-call Webhook Columns to Workflow Table

This migration adds:
- post_call_enabled: Enable/disable post-call webhook (default: enabled)
- pre_call_enabled: Enable/disable pre-call webhook (default: disabled)
- pre_call_timeout: Timeout for pre-call webhook in seconds (default: 3)
- pre_call_webhook_url: Optional separate URL for pre-call webhook (default: NULL)

Run from project root:
    python migrations/add_workflow_webhook_columns.py
"""

import sqlite3
import os
import sys

def find_database():
    """Find the voice_agent.db database file"""
    possible_paths = [
        'instance/voice_agent.db',  # Standard Flask instance folder
        '../instance/voice_agent.db',  # If running from migrations folder
        'voice_agent.db',  # Root folder
    ]

    for path in possible_paths:
        if os.path.exists(path):
            return path

    return None

def migrate():
    """Add webhook control columns to workflow table"""
    print("=" * 60)
    print("Migration: Add Webhook Control Columns to Workflow Table")
    print("=" * 60)

    # Find database
    db_path = find_database()
    if not db_path:
        print("\n[ERROR] Database not found!")
        print("Please run this script from the project root directory.")
        print("\nTried these locations:")
        print("  - instance/voice_agent.db")
        print("  - ../instance/voice_agent.db")
        print("  - voice_agent.db")
        return False

    print(f"\n[OK] Found database: {db_path}")

    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check existing columns
        print("\n[INFO] Checking existing workflow table columns...")
        cursor.execute("PRAGMA table_info(workflow)")
        existing_columns = [row[1] for row in cursor.fetchall()]
        print(f"[OK] Found {len(existing_columns)} existing columns")

        # Columns to add
        columns_to_add = [
            ("post_call_enabled", "BOOLEAN DEFAULT 1", "Enable/disable post-call webhook"),
            ("pre_call_enabled", "BOOLEAN DEFAULT 0", "Enable/disable pre-call webhook"),
            ("pre_call_timeout", "INTEGER DEFAULT 3", "Pre-call webhook timeout in seconds"),
            ("pre_call_webhook_url", "VARCHAR(500)", "Optional separate URL for pre-call webhook"),
        ]

        added_count = 0
        skipped_count = 0

        for col_name, col_def, description in columns_to_add:
            if col_name in existing_columns:
                print(f"[SKIP] {col_name} already exists")
                skipped_count += 1
            else:
                print(f"[ADD] Adding column: {col_name}")
                print(f"      Description: {description}")
                cursor.execute(f"ALTER TABLE workflow ADD COLUMN {col_name} {col_def}")
                added_count += 1

        # Commit changes
        if added_count > 0:
            conn.commit()
            print(f"\n[SUCCESS] Added {added_count} new column(s)")
        else:
            print(f"\n[INFO] All columns already exist ({skipped_count} columns)")

        # Verify final state
        print("\n[INFO] Verifying final table structure...")
        cursor.execute("PRAGMA table_info(workflow)")
        final_columns = [row[1] for row in cursor.fetchall()]

        webhook_columns = [c for c in final_columns if 'call' in c or 'webhook' in c]
        print(f"[OK] Webhook-related columns: {', '.join(webhook_columns)}")

        conn.close()

        print("\n" + "=" * 60)
        print("[SUCCESS] Migration completed successfully!")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Restart your Flask application")
        print("2. The workflow UI will now show enable/disable checkboxes")
        print("3. Configure webhooks from the workflow management page")
        print("=" * 60)

        return True

    except sqlite3.Error as e:
        print(f"\n[ERROR] Database error: {e}")
        if conn:
            conn.rollback()
        return False

    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        if conn:
            conn.rollback()
        return False

    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    print("\nStarting migration...")
    print("Current directory:", os.getcwd())

    success = migrate()

    if not success:
        print("\n" + "=" * 60)
        print("[FAILED] Migration failed!")
        print("=" * 60)
        print("\nTroubleshooting:")
        print("1. Make sure you're running from the project root directory")
        print("2. Check that instance/voice_agent.db exists")
        print("3. Ensure the database is not locked by another process")
        print("4. Verify you have write permissions to the database")
        print("=" * 60)
        sys.exit(1)

    sys.exit(0)
