"""
Verify PostgreSQL migration - check row counts
"""
import os
from sqlalchemy import create_engine, text, inspect
from dotenv import load_dotenv

load_dotenv()

POSTGRES_DB_URL = os.environ.get('DATABASE_URL')

def main():
    print("=" * 70)
    print("  PostgreSQL Migration Verification")
    print("=" * 70)

    engine = create_engine(POSTGRES_DB_URL)

    print("\n📊 Row counts in PostgreSQL:")

    inspector = inspect(engine)
    tables = sorted(inspector.get_table_names())

    total_rows = 0
    for table_name in tables:
        with engine.connect() as conn:
            # Quote table name to handle reserved keywords like 'user'
            count = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()
            total_rows += count
            icon = "✅" if count > 0 else "⚠️ "
            print(f"   {icon} {table_name:30s}: {count:5d} rows")

    print("\n" + "=" * 70)
    print(f"Total rows: {total_rows}")
    print("=" * 70)

    # Sample a few users to verify
    print("\n👥 Sample users (first 5):")
    with engine.connect() as conn:
        result = conn.execute(text("SELECT id, username, email FROM \"user\" LIMIT 5"))
        for row in result:
            print(f"   - ID {row[0]}: {row[1]} ({row[2]})")

if __name__ == '__main__':
    main()
