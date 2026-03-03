"""
Create database tables (schema only, no data)
Run this script to initialize the PostgreSQL database with empty tables
"""
from database import init_db, check_connection, get_table_names

if __name__ == '__main__':
    print("Checking database connection...")
    if not check_connection():
        print("❌ Database connection failed!")
        exit(1)

    print("✅ Database connection successful!")
    print("\nCreating database tables...")

    init_db()

    print("✅ Tables created successfully!")
    print("\nCreated tables:")
    for table in get_table_names():
        print(f"  - {table}")

    print("\n✅ Database schema is ready! You can now import data from staging.")
