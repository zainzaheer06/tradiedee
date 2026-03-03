"""
Migrate only valid knowledge_base entries (skip orphaned ones)
"""
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

SQLITE_DB_URL = 'sqlite:///instance/voice_agent.db'
POSTGRES_DB_URL = os.environ.get('DATABASE_URL')

def main():
    print("=" * 70)
    print("  Migrate Valid Knowledge Base Entries")
    print("=" * 70)

    sqlite_engine = create_engine(SQLITE_DB_URL)
    postgres_engine = create_engine(POSTGRES_DB_URL)

    # Get valid knowledge_base entries (only those with existing agents)
    with sqlite_engine.connect() as sqlite_conn:
        result = sqlite_conn.execute(text("""
            SELECT kb.*
            FROM knowledge_base kb
            INNER JOIN agent a ON kb.agent_id = a.id
        """))

        rows = result.fetchall()
        columns = result.keys()

    print(f"\n📊 Found {len(rows)} valid knowledge_base entries to migrate")

    if len(rows) == 0:
        print("\n✅ No valid entries to migrate!")
        return

    # Migrate to PostgreSQL
    migrated = 0
    skipped = 0

    with postgres_engine.connect() as postgres_conn:
        for row in rows:
            row_dict = dict(zip(columns, row))

            try:
                # Check if agent exists in PostgreSQL
                agent_exists = postgres_conn.execute(
                    text(f'SELECT COUNT(*) FROM agent WHERE id = {row_dict["agent_id"]}')
                ).scalar()

                if not agent_exists:
                    print(f"   ⚠️  Skipping ID {row_dict['id']}: agent_id={row_dict['agent_id']} not in PostgreSQL")
                    skipped += 1
                    continue

                # Insert into PostgreSQL
                postgres_conn.execute(text("""
                    INSERT INTO knowledge_base
                    (id, agent_id, filename, file_path, file_type, file_size, status, created_at, updated_at)
                    VALUES
                    (:id, :agent_id, :filename, :file_path, :file_type, :file_size, :status, :created_at, :updated_at)
                """), row_dict)

                print(f"   ✅ Migrated ID {row_dict['id']}: {row_dict['filename']} (agent_id={row_dict['agent_id']})")
                migrated += 1

            except Exception as e:
                print(f"   ❌ Error migrating ID {row_dict['id']}: {e}")
                skipped += 1

        postgres_conn.commit()

    print("\n" + "=" * 70)
    print(f"✅ Migration Complete!")
    print(f"   Migrated: {migrated}")
    print(f"   Skipped: {skipped}")
    print("=" * 70)

    # Verify
    with postgres_engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM knowledge_base")).scalar()
        print(f"\n📊 PostgreSQL knowledge_base now has: {count} rows")

if __name__ == '__main__':
    main()
