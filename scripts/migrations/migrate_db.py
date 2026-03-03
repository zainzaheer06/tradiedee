"""
Database migration script to add voice_name column to Agent table
"""
import sqlite3
import os
import sys

# Fix encoding for Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

def migrate_database():
    # Check both possible database locations
    possible_paths = ['voice_agent.db', 'instance/voice_agent.db', 'instance\\voice_agent.db']
    db_path = None

    for path in possible_paths:
        if os.path.exists(path):
            db_path = path
            break

    if not db_path:
        print(f"✓ Database not found in common locations.")
        print("✓ This is fine - when you run the app, it will create a new database with the updated schema.")
        print("✓ No migration needed.")
        return

    print(f"Found database at: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if voice_name column already exists
    cursor.execute("PRAGMA table_info(agent)")
    columns = [column[1] for column in cursor.fetchall()]

    if 'voice_name' in columns:
        print("✓ voice_name column already exists. No migration needed.")
        conn.close()
        return

    print("Adding voice_name column to agent table...")

    # Voice ID to Name mapping
    voice_mapping = {
        'G1L6zhS0TTaBvSr18eUY': 'Fatima',
        '6XO1vwWJxHDXGcEu6pMV': 'Ayesha',
        'kgxi5e6hsB6HuAGpjbQ5': 'Hiba',
        'KjDucWgG5NYuMBznv52L': 'Zainab',
        'YdWLuz4rVsaG3kWAECFE': 'Ali'
    }

    try:
        # Add the new column
        cursor.execute("ALTER TABLE agent ADD COLUMN voice_name VARCHAR(50) DEFAULT 'Fatima'")

        # Update existing records with appropriate voice names based on voice_id
        cursor.execute("SELECT id, voice_id FROM agent")
        agents = cursor.fetchall()

        for agent_id, voice_id in agents:
            voice_name = voice_mapping.get(voice_id, 'Fatima')
            cursor.execute("UPDATE agent SET voice_name = ? WHERE id = ?", (voice_name, agent_id))

        conn.commit()
        print(f"✓ Successfully migrated {len(agents)} agent records")
        print("✓ Migration completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"✗ Migration failed: {e}")
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    migrate_database()
