"""
Database migration for outbound campaign system
"""
import sqlite3
import os
from datetime import datetime, timezone

def migrate():
    """Add campaign tables to database"""
    db_path = os.path.join(os.path.dirname(__file__), 'instance', 'voice_agent.db')

    if not os.path.exists(db_path):
        print("[ERROR] Database not found at:", db_path)
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("=" * 60)
    print("Outbound Campaign Migration")
    print("=" * 60)
    print(f"\nUsing database: {db_path}\n")

    try:
        # Check if campaign table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='campaign'")
        if cursor.fetchone():
            print("[INFO] Campaign table already exists")
        else:
            # Create campaign table
            cursor.execute("""
                CREATE TABLE campaign (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    agent_id INTEGER NOT NULL,
                    name VARCHAR(100) NOT NULL,
                    description TEXT,
                    status VARCHAR(20) DEFAULT 'draft',
                    start_time DATETIME,
                    end_time DATETIME,
                    call_window_start VARCHAR(5),
                    call_window_end VARCHAR(5),
                    concurrent_calls INTEGER DEFAULT 5,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES user(id),
                    FOREIGN KEY (agent_id) REFERENCES agent(id)
                )
            """)
            print("[SUCCESS] Created 'campaign' table")

        # Check if campaign_contact table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='campaign_contact'")
        if cursor.fetchone():
            print("[INFO] CampaignContact table already exists")
        else:
            # Create campaign_contact table
            cursor.execute("""
                CREATE TABLE campaign_contact (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id INTEGER NOT NULL,
                    phone_number VARCHAR(20) NOT NULL,
                    name VARCHAR(100),
                    status VARCHAR(20) DEFAULT 'pending',
                    interest_level VARCHAR(20),
                    duration INTEGER DEFAULT 0,
                    attempts INTEGER DEFAULT 0,
                    transcription TEXT,
                    room_name VARCHAR(100),
                    last_attempt DATETIME,
                    completed_at DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (campaign_id) REFERENCES campaign(id)
                )
            """)
            print("[SUCCESS] Created 'campaign_contact' table")

        conn.commit()
        print("\n[SUCCESS] Outbound campaign migration completed!")
        print("=" * 60)
        return True

    except sqlite3.Error as e:
        print(f"\n[ERROR] Migration failed: {e}")
        conn.rollback()
        return False

    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
