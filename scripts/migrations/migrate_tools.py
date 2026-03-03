"""
Migration script to add Tool and AgentTool tables to the database.

This adds support for user-defined tools that can be dynamically loaded into agents.
"""

import sqlite3
import os
from datetime import datetime, timezone

def migrate():
    """Add Tool and AgentTool tables"""
    db_path = os.path.join(os.path.dirname(__file__), 'instance', 'voice_agent.db')
    if not os.path.exists(db_path):
        db_path = os.path.join(os.path.dirname(__file__), 'voice_agent.db')

    if not os.path.exists(db_path):
        print(f"Database not found at: {db_path}")
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Create Tool table
        print("Creating Tool table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tool (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name VARCHAR(100) NOT NULL,
                description TEXT NOT NULL,
                tool_type VARCHAR(20) NOT NULL,
                config TEXT NOT NULL,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE
            )
        """)

        # Create AgentTool linking table
        print("Creating AgentTool table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_tool (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id INTEGER NOT NULL,
                tool_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (agent_id) REFERENCES agent(id) ON DELETE CASCADE,
                FOREIGN KEY (tool_id) REFERENCES tool(id) ON DELETE CASCADE,
                UNIQUE(agent_id, tool_id)
            )
        """)

        # Create indexes for better query performance
        print("Creating indexes...")
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tool_user_id ON tool(user_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tool_type ON tool(tool_type)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_agent_tool_agent ON agent_tool(agent_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_agent_tool_tool ON agent_tool(tool_id)
        """)

        conn.commit()
        print("Migration completed successfully!")

        # Verify tables were created
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('tool', 'agent_tool')")
        tables = cursor.fetchall()
        print(f"Tables created: {[t[0] for t in tables]}")

        return True

    except sqlite3.Error as e:
        print(f"Migration failed: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    print("Starting Tool tables migration...")
    success = migrate()
    if success:
        print("Migration completed!")
    else:
        print("Migration failed!")
