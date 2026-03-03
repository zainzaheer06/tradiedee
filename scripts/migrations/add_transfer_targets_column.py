"""
Database migration script to add 'transfer_targets' column to Agent table.
Used by the agent-to-agent call transfer (handoff) feature.

Column type: JSON (stored as TEXT in SQLite, native JSON in MySQL/PostgreSQL)
Default: NULL (transfers disabled unless configured)

Run once on server:
    python scripts/migrations/add_transfer_targets_column.py
"""
import os
import sys

# Set UTF-8 encoding for Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')


def migrate_sqlite(db_path):
    """Run migration on a SQLite database file."""
    import sqlite3

    print(f"[INFO] Found SQLite database at: {db_path}")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if column already exists
        cursor.execute("PRAGMA table_info(agent)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'transfer_targets' in columns:
            print(f"[OK] Column 'transfer_targets' already exists — nothing to do.")
        else:
            cursor.execute("ALTER TABLE agent ADD COLUMN transfer_targets TEXT DEFAULT NULL")
            conn.commit()
            print(f"[SUCCESS] Added 'transfer_targets' column to agent table.")

        # Verify
        cursor.execute("PRAGMA table_info(agent)")
        columns = [col[1] for col in cursor.fetchall()]
        print(f"[INFO] Current columns: {', '.join(columns)}")

        conn.close()

    except Exception as e:
        print(f"[ERROR] SQLite migration failed: {e}")
        import traceback
        traceback.print_exc()


def migrate_mysql(host, port, user, password, database):
    """Run migration on a MySQL/MariaDB database."""
    try:
        import pymysql
    except ImportError:
        print("[ERROR] pymysql not installed. Run: pip install pymysql")
        return

    print(f"[INFO] Connecting to MySQL: {user}@{host}:{port}/{database}")
    try:
        conn = pymysql.connect(
            host=host, port=int(port), user=user,
            password=password, database=database,
            charset='utf8mb4'
        )
        cursor = conn.cursor()

        # Check if column already exists
        cursor.execute("""
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s
              AND TABLE_NAME   = 'agent'
              AND COLUMN_NAME  = 'transfer_targets'
        """, (database,))
        exists = cursor.fetchone()[0]

        if exists:
            print(f"[OK] Column 'transfer_targets' already exists — nothing to do.")
        else:
            cursor.execute("ALTER TABLE agent ADD COLUMN transfer_targets JSON DEFAULT NULL")
            conn.commit()
            print(f"[SUCCESS] Added 'transfer_targets' JSON column to agent table.")

        # Verify
        cursor.execute("SHOW COLUMNS FROM agent")
        columns = [row[0] for row in cursor.fetchall()]
        print(f"[INFO] Current columns: {', '.join(columns)}")

        conn.close()

    except Exception as e:
        print(f"[ERROR] MySQL migration failed: {e}")
        import traceback
        traceback.print_exc()


def run_migration():
    """Auto-detect DB type from environment, fall back to SQLite file search."""

    # --- Try MySQL/MariaDB via DATABASE_URL or individual env vars ---
    database_url = os.environ.get('DATABASE_URL', '')
    if database_url.startswith('mysql'):
        # Parse DATABASE_URL: mysql+pymysql://user:pass@host:port/dbname
        try:
            from urllib.parse import urlparse
            parsed = urlparse(database_url.replace('mysql+pymysql://', 'mysql://'))
            migrate_mysql(
                host=parsed.hostname,
                port=parsed.port or 3306,
                user=parsed.username,
                password=parsed.password,
                database=parsed.path.lstrip('/')
            )
            return
        except Exception as e:
            print(f"[WARN] Could not parse DATABASE_URL: {e}")

    # Try individual MySQL env vars
    mysql_host = os.environ.get('MYSQL_HOST') or os.environ.get('DB_HOST')
    if mysql_host:
        migrate_mysql(
            host=mysql_host,
            port=os.environ.get('MYSQL_PORT') or os.environ.get('DB_PORT') or 3306,
            user=os.environ.get('MYSQL_USER') or os.environ.get('DB_USER', 'root'),
            password=os.environ.get('MYSQL_PASSWORD') or os.environ.get('DB_PASSWORD', ''),
            database=os.environ.get('MYSQL_DATABASE') or os.environ.get('DB_NAME', 'nevoxai')
        )
        return

    # --- Fall back to SQLite ---
    # Search common locations relative to this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, '..', '..'))

    sqlite_candidates = [
        os.path.join(project_root, 'instance', 'voice_agent.db'),
        os.path.join(project_root, 'voice_agent.db'),
        os.path.join(script_dir, 'instance', 'voice_agent.db'),
        os.path.join(script_dir, 'voice_agent.db'),
    ]

    found = False
    for db_path in sqlite_candidates:
        if os.path.exists(db_path):
            migrate_sqlite(db_path)
            found = True

    if not found:
        print("[ERROR] No database found. Checked:")
        for p in sqlite_candidates:
            print(f"         {p}")
        print()
        print("Provide the path manually:")
        print("  python add_transfer_targets_column.py /path/to/voice_agent.db")
        print()
        print("Or set environment variables for MySQL:")
        print("  MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE")


if __name__ == "__main__":
    # Allow passing a db path directly as argument
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg.endswith('.db'):
            if os.path.exists(arg):
                migrate_sqlite(arg)
            else:
                print(f"[ERROR] File not found: {arg}")
        else:
            print(f"[ERROR] Unrecognized argument: {arg}")
            print("Usage: python add_transfer_targets_column.py [path/to/db.db]")
        sys.exit(0)

    print("=" * 55)
    print("  Migration: add transfer_targets column to agent")
    print("=" * 55)

    # Load .env if present
    try:
        from dotenv import load_dotenv
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '.env')
        if os.path.exists(env_path):
            load_dotenv(env_path)
            print(f"[INFO] Loaded .env from {os.path.abspath(env_path)}")
    except ImportError:
        pass

    run_migration()

    print("=" * 55)
    print("  Done!")
    print("=" * 55)
