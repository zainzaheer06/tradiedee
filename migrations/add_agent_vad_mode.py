"""
Database Migration: Add vad_mode column to Agent table

This migration:
1. Adds vad_mode column to agent table
2. Sets default value to 'dynamic' for all existing agents

VAD Modes:
    - 'precise'  : No VAD, waits for complete input (best for collecting numbers/data)
    - 'natural'  : Semantic VAD, AI detects natural turn completion (balanced conversation)
    - 'dynamic'  : Server VAD, fast silence-based detection (quick responses) [DEFAULT]

Usage:
    python migrations/add_agent_vad_mode.py
"""
import os
import sys
import sqlite3
from datetime import datetime

# Add parent directory to path to import models
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_db_path():
    """Get the database file path"""
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance', 'voice_agent.db')
    if not os.path.exists(db_path):
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'voice_agent.db')

    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found at: {db_path}")

    return db_path


def migrate_database():
    """Run the migration"""
    db_path = get_db_path()
    print(f"📂 Database: {db_path}")

    # Create backup
    backup_path = f"{db_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    import shutil
    shutil.copy2(db_path, backup_path)
    print(f"💾 Backup created: {backup_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Step 1: Check if vad_mode column already exists
        cursor.execute("PRAGMA table_info(agent)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'vad_mode' in columns:
            print("✅ vad_mode column already exists, skipping creation")
        else:
            # Step 2: Add vad_mode column
            print("➕ Adding vad_mode column to agent table...")
            cursor.execute("""
                ALTER TABLE agent
                ADD COLUMN vad_mode VARCHAR(20) DEFAULT 'dynamic'
            """)
            print("✅ Column added successfully")

        # Step 3: Update existing agents to use default vad_mode
        print("📝 Setting vad_mode='dynamic' for existing agents...")
        cursor.execute("""
            UPDATE agent
            SET vad_mode = 'dynamic'
            WHERE vad_mode IS NULL
        """)
        updated_count = cursor.rowcount
        print(f"✅ Updated {updated_count} agent(s) with default vad_mode")

        # Commit changes
        conn.commit()
        print("✅ Migration completed successfully!")

        # Show summary
        cursor.execute("SELECT COUNT(*) FROM agent")
        total_agents = cursor.fetchone()[0]

        cursor.execute("SELECT vad_mode, COUNT(*) FROM agent GROUP BY vad_mode")
        vad_counts = cursor.fetchall()

        print("\n📊 Summary:")
        print(f"   - Total agents: {total_agents}")
        for vad_mode, count in vad_counts:
            print(f"   - {vad_mode}: {count} agent(s)")
        print(f"   - Backup location: {backup_path}")

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
        print(f"💾 You can restore from backup: {backup_path}")
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    print("=" * 60)
    print("Database Migration: Add vad_mode to Agent")
    print("=" * 60)
    print("\nVAD Mode Options:")
    print("   - precise  : No VAD (best for collecting numbers)")
    print("   - natural  : Semantic VAD (balanced conversation)")
    print("   - dynamic  : Server VAD (fast responses) [DEFAULT]")
    print("=" * 60)

    try:
        migrate_database()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

    print("\n✅ Migration complete!")
    print("   - All existing agents set to 'dynamic' mode")
    print("   - New agents will default to 'dynamic' mode")
