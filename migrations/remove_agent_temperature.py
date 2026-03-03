"""
Remove temperature column from agent table
Run this script to completely remove the temperature column from the database
"""
import sqlite3
import os

def remove_temperature_column():
    # Connect to database
    db_path = os.path.join(os.path.dirname(__file__), '..', 'instance', 'voice_agent.db')
    if not os.path.exists(db_path):
        db_path = os.path.join(os.path.dirname(__file__), '..', 'voice_agent.db')

    print(f"Connecting to: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check SQLite version
        cursor.execute("SELECT sqlite_version()")
        version = cursor.fetchone()[0]
        print(f"SQLite version: {version}")

        # Get current table structure
        cursor.execute("PRAGMA table_info(agent)")
        columns = cursor.fetchall()
        print(f"\nCurrent columns: {[col[1] for col in columns]}")

        # Create new table without temperature column
        print("\nCreating new agent table without temperature...")
        cursor.execute("""
            CREATE TABLE agent_new (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                user_agent_number INTEGER,
                name VARCHAR(100) NOT NULL,
                prompt TEXT NOT NULL,
                greeting TEXT DEFAULT 'السلام عليكم ورحمة الله وبركاته، أهلاً وسهلاً فيك. أنا مساعدك الذكي، كيف أقدر أساعدك اليوم؟',
                voice_id VARCHAR(100) DEFAULT 'G1L6zhS0TTaBvSr18eUY',
                voice_name VARCHAR(50) DEFAULT 'Fatima',
                created_at DATETIME,
                last_used DATETIME,
                call_type VARCHAR(10) DEFAULT 'outbound',
                dispatch_rule_id VARCHAR(50),
                phone_number VARCHAR(20),
                inbound_trunk_id VARCHAR(100),
                FOREIGN KEY (user_id) REFERENCES user(id)
            )
        """)

        # Copy data from old table (excluding temperature)
        print("Copying data from old table...")
        cursor.execute("""
            INSERT INTO agent_new (
                id, user_id, user_agent_number, name, prompt, greeting,
                voice_id, voice_name, created_at, last_used,
                call_type, dispatch_rule_id, phone_number, inbound_trunk_id
            )
            SELECT
                id, user_id, user_agent_number, name, prompt, greeting,
                voice_id, voice_name, created_at, last_used,
                call_type, dispatch_rule_id, phone_number, inbound_trunk_id
            FROM agent
        """)

        # Drop old table
        print("Dropping old table...")
        cursor.execute("DROP TABLE agent")

        # Rename new table
        print("Renaming new table...")
        cursor.execute("ALTER TABLE agent_new RENAME TO agent")

        # Commit changes
        conn.commit()

        # Verify
        cursor.execute("PRAGMA table_info(agent)")
        new_columns = cursor.fetchall()
        print(f"\nNew columns: {[col[1] for col in new_columns]}")

        print("\n✅ SUCCESS! Temperature column removed from agent table")

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        conn.rollback()

    finally:
        conn.close()

if __name__ == "__main__":
    remove_temperature_column()
