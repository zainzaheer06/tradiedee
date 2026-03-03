"""
WhatsApp Agent - Database Migration Script
==========================================
Run this script on the production server to create the whatsapp_agent table
and ensure all required columns exist.

Usage:
    cd /path/to/nevoxai-project
    python docs/scripts/migrate_whatsapp_agent.py

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

# ============================================================
# Step 1: Create table if it doesn't exist
# ============================================================
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS whatsapp_agent (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    agent_id INTEGER NOT NULL,
    name VARCHAR(100) NOT NULL,

    -- Provider
    whatsapp_provider VARCHAR(50) DEFAULT 'whapi',

    -- API Config
    whatsapp_api_url VARCHAR(500) NOT NULL,
    whatsapp_api_key VARCHAR(255) NOT NULL,
    whatsapp_phone_number VARCHAR(20),

    -- Custom endpoints
    send_text_endpoint VARCHAR(500),
    send_voice_endpoint VARCHAR(500),

    -- WhatsApp-specific prompt
    whatsapp_system_prompt TEXT,

    -- Feature toggles
    enable_voice_response BOOLEAN DEFAULT 0,
    enable_image_analysis BOOLEAN DEFAULT 1,
    enable_document_analysis BOOLEAN DEFAULT 1,
    memory_window INTEGER DEFAULT 10,

    -- n8n workflow tracking
    n8n_workflow_id VARCHAR(100),
    n8n_workflow_active BOOLEAN DEFAULT 0,
    webhook_path VARCHAR(200) UNIQUE,

    -- Status
    is_active BOOLEAN DEFAULT 0,
    status VARCHAR(20) DEFAULT 'draft',
    error_message TEXT,

    -- Stats
    total_messages INTEGER DEFAULT 0,
    total_conversations INTEGER DEFAULT 0,
    last_message_at DATETIME,

    -- Timestamps
    created_at DATETIME,
    updated_at DATETIME,

    FOREIGN KEY (user_id) REFERENCES user(id),
    FOREIGN KEY (agent_id) REFERENCES agent(id)
);
"""

cursor.execute(CREATE_TABLE_SQL)
print("✓ whatsapp_agent table exists (created if missing)")

# ============================================================
# Step 2: Add any missing columns (safe for existing tables)
# ============================================================
cursor.execute("PRAGMA table_info(whatsapp_agent)")
existing_columns = {row[1] for row in cursor.fetchall()}
print(f"  Existing columns: {len(existing_columns)}")

REQUIRED_COLUMNS = [
    ("whatsapp_provider",   "VARCHAR(50) DEFAULT 'whapi'"),
    ("send_text_endpoint",  "VARCHAR(500)"),
    ("send_voice_endpoint", "VARCHAR(500)"),
]

for col_name, col_type in REQUIRED_COLUMNS:
    if col_name not in existing_columns:
        cursor.execute(f"ALTER TABLE whatsapp_agent ADD COLUMN {col_name} {col_type}")
        print(f"  + Added column: {col_name}")
    else:
        print(f"  ✓ Column exists: {col_name}")

conn.commit()
conn.close()

print("\n✓ Migration complete!")
