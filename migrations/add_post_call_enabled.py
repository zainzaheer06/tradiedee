"""
Migration Script: Add post_call_enabled to Workflow Table
Adds the post_call_enabled column to enable/disable post-call webhooks
"""
import sqlite3
import os
import sys

def find_database():
    """Find the correct database file"""
    # Possible paths to check
    possible_paths = [
        'instance/voice_agent.db',
        os.path.join(os.path.dirname(__file__), '..', '..', 'instance', 'voice_agent.db'),
    ]

    for db_path in possible_paths:
        if os.path.exists(db_path):
            # Verify it has the workflow table
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='workflow'")
                if cursor.fetchone():
                    conn.close()
                    return db_path
                conn.close()
            except Exception as e:
                print(f"Error checking {db_path}: {e}")
                continue

    return None

def migrate():
    """Add post_call_enabled column to workflow table"""

    db_path = find_database()

    if not db_path:
        print("[ERROR] Could not find database with 'workflow' table!")
        print("\nTried the following locations:")
        print("  - instance/voice_agent.db")
        print("  - scripts/migrations/../../instance/voice_agent.db")
        return False

    print(f"[OK] Found database at: {db_path}")
    print()

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if post_call_enabled column already exists
        print("Checking if post_call_enabled column exists in workflow table...")
        cursor.execute("PRAGMA table_info(workflow)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'post_call_enabled' not in columns:
            print("Adding post_call_enabled column to workflow table...")
            cursor.execute("""
                ALTER TABLE workflow ADD COLUMN post_call_enabled BOOLEAN DEFAULT 1
            """)
            print("[OK] post_call_enabled column added to workflow table")

            # Update existing workflows to have post_call_enabled = True (maintain current behavior)
            cursor.execute("UPDATE workflow SET post_call_enabled = 1 WHERE post_call_enabled IS NULL")
            print("[OK] Updated existing workflows to enable post-call webhooks by default")
        else:
            print("[WARN] post_call_enabled column already exists in workflow table")

        conn.commit()

        # Verify changes
        print("\nVerifying migration...")
        cursor.execute("PRAGMA table_info(workflow)")
        workflow_columns = [row[1] for row in cursor.fetchall()]
        if 'post_call_enabled' in workflow_columns:
            print("[OK] post_call_enabled column confirmed in workflow table")

        # Show current workflow status
        cursor.execute("SELECT id, name, pre_call_enabled, post_call_enabled FROM workflow")
        workflows = cursor.fetchall()
        if workflows:
            print(f"\nCurrent workflows ({len(workflows)}):")
            for wf in workflows:
                print(f"  - ID {wf[0]}: {wf[1]} | Pre-call: {bool(wf[2])} | Post-call: {bool(wf[3])}")

        return True

    except sqlite3.Error as e:
        print(f"\n❌ Migration failed: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    print("=" * 60)
    print("Adding post_call_enabled to Workflow Table")
    print("=" * 60)
    print()

    success = migrate()

    print()
    print("=" * 60)
    if success:
        print("[SUCCESS] Migration completed successfully!")
        print()
        print("What changed:")
        print("  - Added post_call_enabled column to workflow table")
        print("  - All existing workflows now have post_call_enabled = True")
        print()
        print("Next steps:")
        print("  1. Restart your application server")
        print("  2. Navigate to /workflows in your web UI")
        print("  3. You can now enable/disable post-call webhooks per workflow")
    else:
        print("[FAILED] Migration failed!")
        print()
        print("Please check:")
        print("  1. Database file exists in instance/ folder")
        print("  2. You have write permissions to the database")
        print("  3. The database is not locked by another process")
    print("=" * 60)