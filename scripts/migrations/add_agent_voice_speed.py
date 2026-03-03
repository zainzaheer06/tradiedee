"""
Agent Voice Speed - Database Migration Script
==============================================
Run this script to add the voice_speed field to the agent table.

Usage:
    cd /path/to/nevoxai-project
    python scripts/migrations/add_agent_voice_speed.py

Safe to run multiple times — it checks before adding the column.
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
# Check if voice_speed column exists in agent table
# ============================================================
cursor.execute("PRAGMA table_info(agent)")
existing_columns = {row[1] for row in cursor.fetchall()}
print(f"[OK] Agent table has {len(existing_columns)} columns")

# ============================================================
# Add voice_speed column if it doesn't exist
# ============================================================
if 'voice_speed' not in existing_columns:
    print("  Adding column: voice_speed")
    cursor.execute("ALTER TABLE agent ADD COLUMN voice_speed REAL DEFAULT 0.90")
    print("  [OK] Column voice_speed added successfully")

    # Set voice_speed = 0.90 on existing rows where it might be NULL
    cursor.execute("UPDATE agent SET voice_speed = 0.90 WHERE voice_speed IS NULL")
    print(f"  [OK] Updated {cursor.rowcount} existing rows with default voice_speed = 0.90")
else:
    print("  [OK] Column voice_speed already exists")

conn.commit()
conn.close()

print("\n[OK] Migration complete!")
