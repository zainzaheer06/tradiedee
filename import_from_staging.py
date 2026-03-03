"""
Import data from SQLite database to PostgreSQL database

This script connects to both databases and copies all data in the correct order
to respect foreign key constraints.

Usage:
    1. Ensure DATABASE_URL is set in .env (PostgreSQL target)
    2. Ensure SQLite database exists at instance/voice_agent.db
    3. Run: python import_from_staging.py
"""

import os
import sys
from sqlalchemy import create_engine, MetaData, Table, select, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

# Database URLs
SQLITE_DB_URL = 'sqlite:///instance/voice_agent.db'  # Source SQLite database
POSTGRES_DB_URL = os.environ.get('DATABASE_URL')     # Target PostgreSQL database

if not POSTGRES_DB_URL:
    print("❌ Error: DATABASE_URL environment variable not set!")
    sys.exit(1)

if not POSTGRES_DB_URL.startswith('postgresql'):
    print("❌ Error: DATABASE_URL must be a PostgreSQL connection string!")
    print(f"   Current: {POSTGRES_DB_URL}")
    sys.exit(1)

# Tables to import in correct order (respecting foreign keys)
IMPORT_ORDER = [
    'user',
    'workflow',
    'agent',
    'inbound_configuration',
    'call_log',
    'campaign',
    'campaign_contact',
    'knowledge_base',
    'tool',
    'agent_tool',
    'webhook_log',
    'api_key',
]


def copy_table_data(source_engine, target_engine, table_name):
    """Copy all data from source table to target table"""

    metadata = MetaData()
    metadata.reflect(bind=source_engine)

    if table_name not in metadata.tables:
        print(f"⚠️  Table '{table_name}' not found in staging database, skipping...")
        return 0

    table = metadata.tables[table_name]

    # Read data from source
    with source_engine.connect() as source_conn:
        result = source_conn.execute(select(table))
        rows = result.fetchall()
        columns = result.keys()

    if not rows:
        print(f"   ℹ️  No data in '{table_name}'")
        return 0

    # Write data to target
    with target_engine.connect() as target_conn:
        for row in rows:
            row_dict = dict(zip(columns, row))
            insert_stmt = table.insert().values(**row_dict)
            target_conn.execute(insert_stmt)
        target_conn.commit()

    print(f"   ✅ Copied {len(rows)} rows to '{table_name}'")
    return len(rows)


def main():
    print("=" * 70)
    print("  NEVOX AI - Migrate Data from SQLite to PostgreSQL")
    print("=" * 70)

    # Create database engines
    print("\n🔗 Connecting to databases...")
    try:
        source_engine = create_engine(SQLITE_DB_URL)
        target_engine = create_engine(POSTGRES_DB_URL)

        # Test connections
        with source_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("   ✅ Connected to SQLite database (source)")

        with target_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("   ✅ Connected to PostgreSQL database (target)")

    except Exception as e:
        print(f"   ❌ Connection failed: {e}")
        sys.exit(1)

    # Import data
    print("\n📦 Importing data...")
    total_rows = 0

    for table_name in IMPORT_ORDER:
        try:
            rows_copied = copy_table_data(source_engine, target_engine, table_name)
            total_rows += rows_copied
        except Exception as e:
            print(f"   ❌ Error copying '{table_name}': {e}")
            print(f"      Continuing with next table...")

    # Summary
    print("\n" + "=" * 70)
    print(f"✅ Import Complete! Total rows copied: {total_rows}")
    print("=" * 70)

    # List tables in PostgreSQL database
    print("\n📊 Tables in PostgreSQL database:")
    metadata = MetaData()
    metadata.reflect(bind=target_engine)
    for table_name in sorted(metadata.tables.keys()):
        with target_engine.connect() as conn:
            count = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
            print(f"   - {table_name}: {count} rows")

    print("\n✅ Done! Your PostgreSQL database now has all data from SQLite.")


if __name__ == '__main__':
    main()
