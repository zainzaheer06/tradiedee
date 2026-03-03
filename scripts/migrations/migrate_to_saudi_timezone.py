#!/usr/bin/env python3
"""
Migration Script: Convert Pakistan Timezone (UTC+5) to Saudi Arabia Timezone (UTC+3)

This script adjusts all existing datetime fields in the database by subtracting 2 hours
to convert from Pakistan Standard Time to Saudi Arabia Standard Time.

Tables affected:
- user: created_at, email_verified_at, sip_configured_at, subscription_start_date
- agent: created_at, last_used
- inbound_configuration: created_at
- call_log: created_at
- campaign: created_at, updated_at, start_time, end_time
- campaign_contact: last_attempt, completed_at, created_at
- knowledge_base: created_at, updated_at
- tool: created_at, updated_at
- agent_tool: created_at

Usage:
    python scripts/migrations/migrate_to_saudi_timezone.py
"""

import sqlite3
from datetime import datetime
import os
import sys

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

def migrate_timestamps():
    """Convert all timestamps from Pakistan time (UTC+5) to Saudi time (UTC+3)"""
    
    # Database file path
    db_path = 'instance/voice_agent.db'
    
    if not os.path.exists(db_path):
        print(f"❌ Database file not found: {db_path}")
        return False
    
    # Create backup
    backup_path = f"{db_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"📦 Creating backup: {backup_path}")
    
    try:
        import shutil
        shutil.copy2(db_path, backup_path)
        print(f"✅ Backup created successfully")
    except Exception as e:
        print(f"❌ Failed to create backup: {e}")
        return False
    
    # Connect to database
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("🔄 Starting timezone migration (Pakistan UTC+5 → Saudi UTC+3)...")
        
        # Define all datetime columns to update
        migrations = [
            # Table: user
            ("user", "created_at"),
            ("user", "email_verified_at"),
            ("user", "sip_configured_at"),
            ("user", "subscription_start_date"),
            
            # Table: agent
            ("agent", "created_at"),
            ("agent", "last_used"),
            
            # Table: inbound_configuration
            ("inbound_configuration", "created_at"),
            
            # Table: call_log
            ("call_log", "created_at"),
            
            # Table: campaign
            ("campaign", "created_at"),
            ("campaign", "updated_at"),
            ("campaign", "start_time"),
            ("campaign", "end_time"),
            
            # Table: campaign_contact
            ("campaign_contact", "last_attempt"),
            ("campaign_contact", "completed_at"),
            ("campaign_contact", "created_at"),
            
            # Table: knowledge_base
            ("knowledge_base", "created_at"),
            ("knowledge_base", "updated_at"),
            
            # Table: tool
            ("tool", "created_at"),
            ("tool", "updated_at"),
            
            # Table: agent_tool
            ("agent_tool", "created_at"),
        ]
        
        total_updates = 0
        
        for table, column in migrations:
            try:
                # Check if table exists
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
                if not cursor.fetchone():
                    print(f"⚠️  Table '{table}' not found, skipping...")
                    continue
                
                # Check if column exists
                cursor.execute(f"PRAGMA table_info({table})")
                columns = [col[1] for col in cursor.fetchall()]
                if column not in columns:
                    print(f"⚠️  Column '{table}.{column}' not found, skipping...")
                    continue
                
                # Count non-null records before update
                cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE {column} IS NOT NULL")
                count_before = cursor.fetchone()[0]
                
                if count_before == 0:
                    print(f"📝 {table}.{column}: No records to update")
                    continue
                
                # Update timestamps: subtract 2 hours (Pakistan UTC+5 → Saudi UTC+3)
                update_sql = f"""
                UPDATE {table} 
                SET {column} = datetime({column}, '-2 hours')
                WHERE {column} IS NOT NULL
                """
                
                cursor.execute(update_sql)
                updated_count = cursor.rowcount
                total_updates += updated_count
                
                print(f"✅ {table}.{column}: Updated {updated_count} records")
                
            except Exception as e:
                print(f"❌ Error updating {table}.{column}: {e}")
                conn.rollback()
                return False
        
        # Commit all changes
        conn.commit()
        print(f"\n🎉 Migration completed successfully!")
        print(f"📊 Total records updated: {total_updates}")
        print(f"⏰ All timestamps converted from Pakistan (UTC+5) to Saudi (UTC+3)")
        print(f"💾 Backup saved as: {backup_path}")
        
        return True
        
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return False
    
    finally:
        if 'conn' in locals():
            conn.close()

def verify_migration():
    """Verify the migration by showing before/after samples"""
    print("\n🔍 Verifying migration results...")
    
    try:
        conn = sqlite3.connect('instance/voice_agent.db')
        cursor = conn.cursor()
        
        # Show sample of recent records
        cursor.execute("SELECT created_at FROM call_log ORDER BY id DESC LIMIT 3")
        recent_logs = cursor.fetchall()
        
        if recent_logs:
            print("📋 Sample call log timestamps (should now be in Saudi time):")
            for i, (timestamp,) in enumerate(recent_logs, 1):
                print(f"   {i}. {timestamp}")
        
        cursor.execute("SELECT created_at FROM user ORDER BY id DESC LIMIT 2")
        recent_users = cursor.fetchall()
        
        if recent_users:
            print("👥 Sample user timestamps (should now be in Saudi time):")
            for i, (timestamp,) in enumerate(recent_users, 1):
                print(f"   {i}. {timestamp}")
        
        conn.close()
        
    except Exception as e:
        print(f"⚠️ Verification error: {e}")

if __name__ == "__main__":
    print("=" * 60)
    print("🇸🇦 SAUDI ARABIA TIMEZONE MIGRATION")
    print("=" * 60)
    print("Converting timestamps: Pakistan (UTC+5) → Saudi Arabia (UTC+3)")
    print("This will subtract 2 hours from all existing datetime fields.")
    print()
    
    # Confirm before proceeding
    response = input("Continue with migration? (y/N): ").strip().lower()
    if response not in ['y', 'yes']:
        print("❌ Migration cancelled")
        sys.exit(0)
    
    # Run migration
    success = migrate_timestamps()
    
    if success:
        verify_migration()
        print("\n✅ Migration completed successfully!")
        print("🚀 You can now start the application with Saudi Arabia timezone.")
    else:
        print("\n❌ Migration failed. Please check the errors above.")
        sys.exit(1)