"""
API Key Table - Database Migration Script
==========================================
Run this script on the production server to create the api_key table
and ensure all required columns exist.

Usage:
    cd /path/to/nevoxai-project
    python scripts/migrations/migrate_apikey.py

Safe to run multiple times — it checks before creating/altering.
"""
import sqlite3
import os
import sys

# Resolve DB path relative to project root
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DB_PATH = os.path.join(PROJECT_ROOT, 'instance', 'voice_agent.db')

if not os.path.exists(DB_PATH):
    print(f"ERROR: Database not found at {DB_PATH}")
    sys.exit(1)

print(f"Database: {DB_PATH}")

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Enable foreign key support
cursor.execute("PRAGMA foreign_keys = ON")

# ============================================================
# Step 1: Create table if it doesn't exist
# ============================================================
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS api_key (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,

    -- Security: Store hashed key, never raw
    key_hash VARCHAR(64) NOT NULL UNIQUE,
    key_prefix VARCHAR(12) NOT NULL,

    name VARCHAR(100) DEFAULT 'Default API Key',
    is_active BOOLEAN DEFAULT 1,

    -- Usage tracking
    last_used_at DATETIME,
    total_calls INTEGER DEFAULT 0,

    -- Timestamps
    created_at DATETIME,
    revoked_at DATETIME,

    FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE
);
"""

cursor.execute(CREATE_TABLE_SQL)
print("✓ api_key table exists (created if missing)")

# ============================================================
# Step 2: Create indexes for performance
# ============================================================
INDEXES = [
    ("idx_api_key_user_id", "user_id"),
    ("idx_api_key_hash", "key_hash"),
    ("idx_api_key_active", "is_active"),
]

for index_name, column_name in INDEXES:
    cursor.execute(f"""
        CREATE INDEX IF NOT EXISTS {index_name} ON api_key({column_name})
    """)
    print(f"✓ Index exists: {index_name}")

# ============================================================
# Step 3: Verify table structure
# ============================================================
cursor.execute("PRAGMA table_info(api_key)")
existing_columns = {row[1] for row in cursor.fetchall()}
print(f"  Existing columns: {len(existing_columns)}")

REQUIRED_COLUMNS = [
    "id", "user_id", "key_hash", "key_prefix", "name",
    "is_active", "last_used_at", "total_calls", "created_at", "revoked_at"
]

all_exist = all(col in existing_columns for col in REQUIRED_COLUMNS)
if all_exist:
    print("  ✓ All required columns present")
else:
    missing = [col for col in REQUIRED_COLUMNS if col not in existing_columns]
    print(f"  ⚠ Missing columns: {missing}")

conn.commit()
conn.close()

print("\n✓ Migration complete!")
