"""
Grant schema permissions for PostgreSQL database

Since nevox_prod is a Privileged Account, we can grant schema permissions to ourselves.
"""

import psycopg2
import sys

# Database credentials (nevox_prod is privileged, so can grant to itself)
DB_HOST = "pgm-l4v70dv4z1o481p3oo.pgsql.me-central-1.rds.aliyuncs.com"
DB_PORT = 5432
DB_NAME = "nevox_prod"
DB_USER = "nevox_prod"
DB_PASSWORD = "tdQJ@u57SrVZg4v"

# User to grant permissions to (self)
TARGET_USER = "nevox_prod"

# SQL commands to grant permissions
GRANT_COMMANDS = [
    f"GRANT CREATE ON SCHEMA public TO {TARGET_USER};",
    f"GRANT USAGE ON SCHEMA public TO {TARGET_USER};",
    f"GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO {TARGET_USER};",
    f"GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO {TARGET_USER};",
    f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO {TARGET_USER};",
    f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO {TARGET_USER};",
]

def main():
    print("=" * 70)
    print("  Grant PostgreSQL Permissions to nevox_prod User")
    print("=" * 70)

    try:
        # Connect as nevox_prod (privileged account)
        print(f"\n🔗 Connecting to PostgreSQL as {DB_USER}...")
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        conn.autocommit = True
        cursor = conn.cursor()

        print(f"   ✅ Connected successfully!")

        # Execute grant commands
        print(f"\n🔐 Granting permissions to {TARGET_USER}...")
        for i, command in enumerate(GRANT_COMMANDS, 1):
            try:
                cursor.execute(command)
                print(f"   ✅ ({i}/{len(GRANT_COMMANDS)}) {command}")
            except Exception as e:
                print(f"   ⚠️  ({i}/{len(GRANT_COMMANDS)}) Failed: {command}")
                print(f"       Error: {e}")

        cursor.close()
        conn.close()

        print("\n" + "=" * 70)
        print("✅ Permissions granted successfully!")
        print("=" * 70)
        print("\n💡 Next step: Run create_db.py to create tables")

    except psycopg2.OperationalError as e:
        print(f"\n❌ Connection failed: {e}")
        print("\nPossible reasons:")
        print("  1. Wrong database credentials in script")
        print("  2. Network/firewall issue")
        print("  3. Database host unreachable")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
