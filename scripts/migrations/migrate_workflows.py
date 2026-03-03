"""
Migration script to add Workflow and WebhookLog tables for n8n integration.

This adds support for:
- User-defined workflows with API key authentication
- Webhook logging for debugging and monitoring
- Agent-to-workflow linking
"""

import sqlite3
import os
from datetime import datetime

def migrate():
    """Add Workflow and WebhookLog tables, and workflow_id to Agent table"""
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
        print(f"Database not found. Tried: {db_paths}")
        return False

    print(f"Using database at: {db_path}")
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

        # Check if workflow_id column already exists in agent table
        print("Checking if workflow_id column exists in agent table...")
        cursor.execute("PRAGMA table_info(agent)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'workflow_id' not in columns:
            print("Adding workflow_id column to agent table...")
            cursor.execute("""
                ALTER TABLE agent ADD COLUMN workflow_id INTEGER REFERENCES workflow(id) ON DELETE SET NULL
            """)
        else:
            print("workflow_id column already exists in agent table")

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

        conn.commit()
        print("Migration completed successfully!")

        # Verify tables were created
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('workflow', 'webhook_log')")
        tables = cursor.fetchall()
        print(f"Tables created: {[t[0] for t in tables]}")

        # Verify workflow_id column was added
        cursor.execute("PRAGMA table_info(agent)")
        agent_columns = [row[1] for row in cursor.fetchall()]
        if 'workflow_id' in agent_columns:
            print("workflow_id column added to agent table")

        return True

    except sqlite3.Error as e:
        print(f"Migration failed: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    print("=" * 60)
    print("Starting Workflow tables migration...")
    print("=" * 60)
    success = migrate()
    print("=" * 60)
    if success:
        print("✅ Migration completed successfully!")
    else:
        print("❌ Migration failed!")
    print("=" * 60)
