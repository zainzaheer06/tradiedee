"""
Run database migration to add SIP trunk fields
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'voice_agent.db')

def run_migration():
    print(f"Connecting to database: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        print("Adding trunk fields to User table...")
        cursor.execute("ALTER TABLE user ADD COLUMN outbound_trunk_id VARCHAR(100)")
        cursor.execute("ALTER TABLE user ADD COLUMN sip_configured BOOLEAN DEFAULT FALSE")
        cursor.execute("ALTER TABLE user ADD COLUMN sip_configured_at DATETIME")
        cursor.execute("ALTER TABLE user ADD COLUMN sip_notes TEXT")
        print("[OK] User table updated")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("[SKIP] User table fields already exist")
        else:
            raise

    try:
        print("Adding trunk field to Agent table...")
        cursor.execute("ALTER TABLE agent ADD COLUMN inbound_trunk_id VARCHAR(100)")
        print("[OK] Agent table updated")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("[SKIP] Agent table field already exists")
        else:
            raise

    print("Setting default values...")
    cursor.execute("UPDATE user SET sip_configured = 0 WHERE sip_configured IS NULL")

    conn.commit()
    conn.close()

    print("\n[SUCCESS] Migration completed successfully!")
    print("\nNew fields added:")
    print("  User table:")
    print("    - outbound_trunk_id (VARCHAR 100)")
    print("    - sip_configured (BOOLEAN)")
    print("    - sip_configured_at (DATETIME)")
    print("    - sip_notes (TEXT)")
    print("  Agent table:")
    print("    - inbound_trunk_id (VARCHAR 100)")

if __name__ == "__main__":
    run_migration()
