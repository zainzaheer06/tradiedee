"""
Migration script: Add Meta WhatsApp Business API fields to whatsapp_agent table.

New columns:
  - meta_phone_number_id (VARCHAR 100)
  - meta_business_account_id (VARCHAR 100)
  - meta_access_token (VARCHAR 500)
  - meta_app_secret (VARCHAR 255)
  - meta_verify_token (VARCHAR 100)
  - meta_webhook_verified (BOOLEAN, default FALSE)

Also makes whatsapp_api_url and whatsapp_api_key nullable (they're not needed for Meta provider).

Run: python migrate_meta_whatsapp.py
"""
import os
import sys
from sqlalchemy import create_engine, text, inspect
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get('DATABASE_URL', '')

def get_engine():
    if DATABASE_URL and DATABASE_URL.startswith('postgresql'):
        return create_engine(DATABASE_URL)
    else:
        # Fall back to SQLite — match Flask's sqlite:///voice_agent.db (instance folder)
        db_path = os.path.join(os.path.dirname(__file__), 'instance', 'voice_agent.db')
        if not os.path.exists(db_path):
            # Try root folder
            db_path = os.path.join(os.path.dirname(__file__), 'voice_agent.db')
        if not os.path.exists(db_path):
            db_path = os.path.join(os.path.dirname(__file__), 'instance', 'database.db')
        return create_engine(f'sqlite:///{db_path}')

def run_migration():
    engine = get_engine()
    db_type = 'postgresql' if str(engine.url).startswith('postgresql') else 'sqlite'
    
    print(f"🔗 Connected to {db_type} database")
    print("=" * 60)
    print("  Migration: Add Meta WhatsApp Business API fields")
    print("=" * 60)
    
    inspector = inspect(engine)
    
    # Check if table exists
    if 'whatsapp_agent' not in inspector.get_table_names():
        print("❌ Table 'whatsapp_agent' does not exist. Run db.create_all() first.")
        sys.exit(1)
    
    # Get existing columns
    existing_columns = {col['name'] for col in inspector.get_columns('whatsapp_agent')}
    print(f"\n📋 Existing columns: {len(existing_columns)}")
    
    # New columns to add
    new_columns = [
        ('meta_phone_number_id', 'VARCHAR(100)'),
        ('meta_business_account_id', 'VARCHAR(100)'),
        ('meta_access_token', 'VARCHAR(500)'),
        ('meta_app_secret', 'VARCHAR(255)'),
        ('meta_verify_token', 'VARCHAR(100)'),
        ('meta_webhook_verified', 'BOOLEAN DEFAULT FALSE'),
    ]
    
    with engine.begin() as conn:
        added = 0
        for col_name, col_type in new_columns:
            if col_name in existing_columns:
                print(f"   ⏭️  Column '{col_name}' already exists — skipping")
            else:
                sql = f"ALTER TABLE whatsapp_agent ADD COLUMN {col_name} {col_type}"
                try:
                    conn.execute(text(sql))
                    print(f"   ✅ Added column: {col_name} ({col_type})")
                    added += 1
                except Exception as e:
                    print(f"   ❌ Failed to add column '{col_name}': {e}")
        
        # Make whatsapp_api_url and whatsapp_api_key nullable if PostgreSQL
        if db_type == 'postgresql':
            try:
                conn.execute(text("ALTER TABLE whatsapp_agent ALTER COLUMN whatsapp_api_url DROP NOT NULL"))
                print("   ✅ Made whatsapp_api_url nullable")
            except Exception as e:
                print(f"   ⏭️  whatsapp_api_url already nullable or error: {e}")
            try:
                conn.execute(text("ALTER TABLE whatsapp_agent ALTER COLUMN whatsapp_api_key DROP NOT NULL"))
                print("   ✅ Made whatsapp_api_key nullable")
            except Exception as e:
                print(f"   ⏭️  whatsapp_api_key already nullable or error: {e}")
    
    print(f"\n✅ Migration complete! Added {added} new column(s).")
    print("=" * 60)

if __name__ == '__main__':
    run_migration()
