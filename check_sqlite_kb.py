"""
Check knowledge_base table in SQLite database
"""
from sqlalchemy import create_engine, text

SQLITE_DB_URL = 'sqlite:///instance/voice_agent.db'

def main():
    print("=" * 70)
    print("  Checking knowledge_base in SQLite Database")
    print("=" * 70)

    engine = create_engine(SQLITE_DB_URL)

    with engine.connect() as conn:
        # Count total knowledge_base entries
        kb_count = conn.execute(text("SELECT COUNT(*) FROM knowledge_base")).scalar()
        print(f"\n📊 Total knowledge_base entries in SQLite: {kb_count}")

        if kb_count == 0:
            print("\n✅ SQLite knowledge_base is also empty - nothing to migrate!")
            return

        # Show all knowledge_base entries
        print("\n📋 Knowledge base entries:")
        result = conn.execute(text("""
            SELECT kb.id, kb.agent_id, kb.filename, kb.status, a.name as agent_name
            FROM knowledge_base kb
            LEFT JOIN agent a ON kb.agent_id = a.id
        """))

        for row in result:
            if row[4]:  # agent_name exists
                print(f"   ✅ ID {row[0]}: agent_id={row[1]} ({row[4]}) - {row[2]} [{row[3]}]")
            else:
                print(f"   ❌ ID {row[0]}: agent_id={row[1]} (ORPHANED - agent deleted) - {row[2]} [{row[3]}]")

        # Count orphaned entries
        orphaned = conn.execute(text("""
            SELECT COUNT(*) FROM knowledge_base
            WHERE agent_id NOT IN (SELECT id FROM agent)
        """)).scalar()

        print(f"\n⚠️  Orphaned entries (agent deleted): {orphaned}")
        print(f"✅ Valid entries (can be migrated): {kb_count - orphaned}")

        if orphaned > 0:
            print("\n💡 Orphaned entries cannot be migrated due to foreign key constraints.")
            print("   Options:")
            print("   1. Delete orphaned entries from SQLite")
            print("   2. Ignore them (they're for deleted agents anyway)")

if __name__ == '__main__':
    main()
