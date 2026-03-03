"""
Migrate data from SQLite to PostgreSQL

This script:
1. Reads all data from your local SQLite database (instance/voice_agent.db)
2. Writes it to PostgreSQL database (configured in DATABASE_URL)
3. Handles schema differences between SQLite and PostgreSQL
4. Skips fields that don't exist in target PostgreSQL schema

Usage:
    python migrate_sqlite_to_postgres.py
"""

import os
import sys
from sqlalchemy import create_engine, MetaData, select, text, inspect
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
    # Note: 'api_key' is NOT in server-code/model.py, so skip it
]


def get_common_columns(source_table, target_table):
    """Get column names that exist in both source and target tables"""
    source_cols = {col.name for col in source_table.columns}
    target_cols = {col.name for col in target_table.columns}
    common = source_cols & target_cols
    return sorted(common)


def copy_table_data(source_engine, target_engine, table_name):
    """Copy all data from source table to target table"""

    # Reflect both databases
    source_metadata = MetaData()
    source_metadata.reflect(bind=source_engine)

    target_metadata = MetaData()
    target_metadata.reflect(bind=target_engine)

    # Check if table exists in both databases
    if table_name not in source_metadata.tables:
        print(f"⚠️  Table '{table_name}' not found in SQLite database, skipping...")
        return 0

    if table_name not in target_metadata.tables:
        print(f"⚠️  Table '{table_name}' not found in PostgreSQL database, skipping...")
        return 0

    source_table = source_metadata.tables[table_name]
    target_table = target_metadata.tables[table_name]

    # Get columns that exist in both schemas
    common_columns = get_common_columns(source_table, target_table)

    if not common_columns:
        print(f"⚠️  No common columns between source and target for '{table_name}', skipping...")
        return 0

    # Read data from SQLite (only common columns)
    with source_engine.connect() as source_conn:
        # Select only common columns
        stmt = select(*[source_table.c[col] for col in common_columns])
        result = source_conn.execute(stmt)
        rows = result.fetchall()

    if not rows:
        print(f"   ℹ️  No data in '{table_name}'")
        return 0

    # Write data to PostgreSQL
    with target_engine.connect() as target_conn:
        for row in rows:
            row_dict = dict(zip(common_columns, row))
            insert_stmt = target_table.insert().values(**row_dict)
            target_conn.execute(insert_stmt)
        target_conn.commit()

    print(f"   ✅ Copied {len(rows)} rows to '{table_name}' ({len(common_columns)} columns)")
    return len(rows)


def main():
    print("=" * 70)
    print("  NEVOX AI - Migrate Data from SQLite to PostgreSQL")
    print("=" * 70)

    # Check if SQLite database exists
    sqlite_path = 'instance/voice_agent.db'
    if not os.path.exists(sqlite_path):
        print(f"❌ Error: SQLite database not found at {sqlite_path}")
        sys.exit(1)

    # Create database engines
    print("\n🔗 Connecting to databases...")
    try:
        source_engine = create_engine(SQLITE_DB_URL)
        target_engine = create_engine(POSTGRES_DB_URL)

        # Test connections
        with source_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print(f"   ✅ Connected to SQLite database (source): {sqlite_path}")

        with target_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("   ✅ Connected to PostgreSQL database (target)")

    except Exception as e:
        print(f"   ❌ Connection failed: {e}")
        sys.exit(1)

    # Show schema info
    print("\n📋 Schema compatibility check...")
    source_inspector = inspect(source_engine)
    target_inspector = inspect(target_engine)

    source_tables = set(source_inspector.get_table_names())
    target_tables = set(target_inspector.get_table_names())

    print(f"   SQLite tables: {len(source_tables)}")
    print(f"   PostgreSQL tables: {len(target_tables)}")
    print(f"   Tables to migrate: {len([t for t in IMPORT_ORDER if t in source_tables and t in target_tables])}")

    # Import data
    print("\n📦 Migrating data...")
    total_rows = 0

    for table_name in IMPORT_ORDER:
        try:
            rows_copied = copy_table_data(source_engine, target_engine, table_name)
            total_rows += rows_copied
        except Exception as e:
            print(f"   ❌ Error copying '{table_name}': {e}")
            import traceback
            traceback.print_exc()
            print(f"      Continuing with next table...")

    # Summary
    print("\n" + "=" * 70)
    print(f"✅ Migration Complete! Total rows copied: {total_rows}")
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
    print("\n💡 Next steps:")
    print("   1. Verify the data in PostgreSQL")
    print("   2. Test your application with PostgreSQL")
    print("   3. Keep SQLite backup until confident PostgreSQL is working")


if __name__ == '__main__':
    main()
