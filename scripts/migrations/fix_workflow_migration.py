"""
Fixed Migration Script for Workflow Integration
Targets the correct instance/voice_agent.db database
"""
import sqlite3
import os
import sys

def find_database():
    """Find the correct database file"""
    # Possible paths to check
    possible_paths = [
        '/root/nevoxai-project-2/instance/voice_agent.db',
        'instance/voice_agent.db',
        os.path.join(os.path.dirname(__file__), '..', '..', 'instance', 'voice_agent.db'),
    ]

    for db_path in possible_paths:
        if os.path.exists(db_path):
            # Verify it has the agent table
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='agent'")
                if cursor.fetchone():
                    conn.close()
                    return db_path
                conn.close()
            except Exception as e:
                print(f"Error checking {db_path}: {e}")
                continue

    return None

def migrate():
    """Add Workflow and WebhookLog tables, and workflow_id to Agent table"""

    db_path = find_database()

    if not db_path:
        print("❌ Could not find database with 'agent' table!")
        print("\nTried the following locations:")
        print("  - /root/nevoxai-project-2/instance/voice_agent.db")
        print("  - instance/voice_agent.db")
        print("  - scripts/migrations/../../instance/voice_agent.db")
        return False

    print(f"✅ Found database at: {db_path}")
    print()

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Create Workflow table
        print("Creating Workflow table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workflow (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name VARCHAR(100) NOT NULL,
                description TEXT,
                webhook_url VARCHAR(500) NOT NULL,
                api_key VARCHAR(64) NOT NULL UNIQUE,
                is_active BOOLEAN DEFAULT 1,
                total_calls INTEGER DEFAULT 0,
                successful_calls INTEGER DEFAULT 0,
                failed_calls INTEGER DEFAULT 0,
                last_triggered_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE
            )
        """)
        print("✅ Workflow table created")

        # Create WebhookLog table
        print("Creating WebhookLog table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS webhook_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_id INTEGER NOT NULL,
                call_log_id INTEGER,
                status VARCHAR(20),
                http_status INTEGER,
                request_payload TEXT,
                response_body TEXT,
                error_message TEXT,
                retry_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (workflow_id) REFERENCES workflow(id) ON DELETE CASCADE,
                FOREIGN KEY (call_log_id) REFERENCES call_log(id) ON DELETE SET NULL
            )
        """)
        print("✅ WebhookLog table created")

        # Check if workflow_id column already exists in agent table
        print("Checking if workflow_id column exists in agent table...")
        cursor.execute("PRAGMA table_info(agent)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'workflow_id' not in columns:
            print("Adding workflow_id column to agent table...")
            cursor.execute("""
                ALTER TABLE agent ADD COLUMN workflow_id INTEGER REFERENCES workflow(id) ON DELETE SET NULL
            """)
            print("✅ workflow_id column added to agent table")
        else:
            print("⚠️  workflow_id column already exists in agent table")

        # Create indexes for better query performance
        print("Creating indexes...")
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_workflow_user_id ON workflow(user_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_workflow_api_key ON workflow(api_key)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_workflow_is_active ON workflow(is_active)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_webhook_log_workflow_id ON webhook_log(workflow_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_webhook_log_call_log_id ON webhook_log(call_log_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_webhook_log_status ON webhook_log(status)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_webhook_log_created_at ON webhook_log(created_at)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_agent_workflow_id ON agent(workflow_id)
        """)
        print("✅ Indexes created")

        conn.commit()

        # Verify changes
        print("\nVerifying migration...")
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('workflow', 'webhook_log')")
        tables = cursor.fetchall()
        print(f"✅ Tables created: {[t[0] for t in tables]}")

        cursor.execute("PRAGMA table_info(agent)")
        agent_columns = [row[1] for row in cursor.fetchall()]
        if 'workflow_id' in agent_columns:
            print("✅ workflow_id column confirmed in agent table")

        return True

    except sqlite3.Error as e:
        print(f"\n❌ Migration failed: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    print("=" * 60)
    print("Starting Workflow Tables Migration (Fixed)")
    print("=" * 60)
    print()

    success = migrate()

    print()
    print("=" * 60)
    if success:
        print("✅ Migration completed successfully!")
        print()
        print("Next steps:")
        print("1. Restart your application service")
        print("2. Check that the dashboard loads without errors")
    else:
        print("❌ Migration failed!")
        print()
        print("Please check:")
        print("1. Database file exists in instance/ folder")
        print("2. You have write permissions to the database")
        print("3. The database is not locked by another process")
    print("=" * 60)
