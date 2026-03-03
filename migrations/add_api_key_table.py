"""
Database Migration: Create api_key table

This migration:
1. Creates the api_key table for storing user API keys
2. Adds unique constraints on user_id and key_hash

Table Structure:
    - id: Primary key
    - user_id: Foreign key to user (unique - one key per user)
    - key_hash: SHA-256 hash of the API key (unique)
    - key_prefix: Display prefix like "nvx_a1b2..."
    - name: Optional name for the key
    - is_active: Whether the key is active
    - last_used_at: Last time the key was used
    - total_calls: Total API calls made with this key
    - created_at: When the key was created
    - revoked_at: When the key was revoked (if applicable)

Usage:
    python migrations/add_api_key_table.py
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
        # Step 1: Check if api_key table already exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='api_key'
        """)
        table_exists = cursor.fetchone() is not None

        if table_exists:
            print("✅ api_key table already exists, skipping creation")
        else:
            # Step 2: Create api_key table
            print("➕ Creating api_key table...")
            cursor.execute("""
                CREATE TABLE api_key (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL UNIQUE,
                    key_hash VARCHAR(64) NOT NULL UNIQUE,
                    key_prefix VARCHAR(12) NOT NULL,
                    name VARCHAR(100) DEFAULT 'Default API Key',
                    is_active BOOLEAN DEFAULT 1,
                    last_used_at DATETIME,
                    total_calls INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    revoked_at DATETIME,
                    FOREIGN KEY (user_id) REFERENCES user (id)
                )
            """)
            print("✅ Table created successfully")

            # Step 3: Create indexes for performance
            print("➕ Creating indexes...")

            # Index on key_hash for fast lookups during authentication
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS ix_api_key_hash
                ON api_key (key_hash)
            """)
            print("   - Created index on key_hash")

            # Index on user_id for fast user lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS ix_api_key_user_id
                ON api_key (user_id)
            """)
            print("   - Created index on user_id")

            # Index on is_active for filtering active keys
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS ix_api_key_active
                ON api_key (is_active)
            """)
            print("   - Created index on is_active")

        # Commit changes
        conn.commit()
        print("✅ Migration completed successfully!")

        # Show summary
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='api_key'
        """)
        table_exists = cursor.fetchone() is not None

        cursor.execute("SELECT COUNT(*) FROM api_key")
        key_count = cursor.fetchone()[0]

        print("\n📊 Summary:")
        print(f"   - Table exists: {table_exists}")
        print(f"   - Existing keys: {key_count}")
        print(f"   - Backup location: {backup_path}")

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
        print(f"💾 You can restore from backup: {backup_path}")
        raise
    finally:
        conn.close()


def rollback_migration():
    """Rollback the migration (drop the table)"""
    db_path = get_db_path()
    print(f"📂 Database: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        print("🗑️  Dropping api_key table...")
        cursor.execute("DROP TABLE IF EXISTS api_key")
        conn.commit()
        print("✅ Table dropped successfully")
    except Exception as e:
        print(f"❌ Rollback failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    print("=" * 60)
    print("Database Migration: Create api_key Table")
    print("=" * 60)
    print("\nAPI Key Features:")
    print("   - One key per user (unique constraint)")
    print("   - SHA-256 hashed storage (secure)")
    print("   - Usage tracking (total_calls, last_used_at)")
    print("   - Revokable (is_active, revoked_at)")
    print("=" * 60)

    # Check for rollback flag
    if len(sys.argv) > 1 and sys.argv[1] == '--rollback':
        print("\n⚠️  ROLLBACK MODE - This will DROP the api_key table!")
        confirm = input("Are you sure? (yes/no): ")
        if confirm.lower() == 'yes':
            rollback_migration()
            print("\n✅ Rollback complete!")
        else:
            print("Rollback cancelled.")
        sys.exit(0)

    try:
        migrate_database()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

    print("\n✅ Migration complete!")
    print("   - api_key table is ready")
    print("   - Users can now generate API keys from Settings > API Keys")
