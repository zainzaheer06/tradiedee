"""
Create PostgreSQL database tables using server-code/model.py schema
This script creates the schema for the PostgreSQL database
"""
import sys
import os

# Add server-code to path so we can import model.py from there
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'server-code'))

from sqlalchemy import create_engine, inspect, text
from dotenv import load_dotenv

load_dotenv()

# Import the server models
from model import db

# Get DATABASE_URL
DATABASE_URL = os.environ.get('DATABASE_URL')

if not DATABASE_URL:
    print("❌ Error: DATABASE_URL environment variable not set!")
    sys.exit(1)

if not DATABASE_URL.startswith('postgresql'):
    print("❌ Error: DATABASE_URL must be a PostgreSQL connection string!")
    sys.exit(1)

if __name__ == '__main__':
    print("=" * 70)
    print("  Creating PostgreSQL Tables (server-code/model.py schema)")
    print("=" * 70)

    # Create engine
    print("\n🔗 Connecting to PostgreSQL...")
    try:
        engine = create_engine(DATABASE_URL)

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("   ✅ Connected to PostgreSQL database")

    except Exception as e:
        print(f"   ❌ Connection failed: {e}")
        sys.exit(1)

    # Create all tables
    print("\n📋 Creating database tables...")
    db.metadata.create_all(engine)
    print("   ✅ Tables created successfully!")

    # List created tables
    print("\n📊 Created tables:")
    inspector = inspect(engine)
    for table_name in sorted(inspector.get_table_names()):
        print(f"   - {table_name}")

    print("\n" + "=" * 70)
    print("✅ PostgreSQL database schema is ready!")
    print("=" * 70)
    print("\n💡 Next step: Run migrate_sqlite_to_postgres.py to import data")
