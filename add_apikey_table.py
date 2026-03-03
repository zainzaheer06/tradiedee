"""
Add ApiKey table to production database
Run once to create the api_key table
"""
import psycopg2
from psycopg2 import sql

# Production database connection
# Note: @ in password is URL-encoded as %40
DB_URL = "postgresql://nevox_prod:tdQJ%40u57SrVZg4v@pgm-l4v70dv4z1o481p3oo.pgsql.me-central-1.rds.aliyuncs.com:5432/nevox_prod"

def create_apikey_table():
    """Create the api_key table with all constraints and indexes"""

    conn = None
    cursor = None

    create_table_sql = """
    -- Create api_key table
    CREATE TABLE IF NOT EXISTS api_key (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL UNIQUE,
        key_hash VARCHAR(64) NOT NULL UNIQUE,
        key_prefix VARCHAR(12) NOT NULL,
        name VARCHAR(100) DEFAULT 'Default API Key',
        is_active BOOLEAN DEFAULT TRUE,
        last_used_at TIMESTAMP NULL,
        total_calls INTEGER DEFAULT 0,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        revoked_at TIMESTAMP NULL,

        -- Foreign key constraint
        CONSTRAINT fk_api_key_user FOREIGN KEY (user_id) REFERENCES "user"(id) ON DELETE CASCADE
    );
    """

    create_indexes_sql = """
    -- Create indexes for better performance
    CREATE INDEX IF NOT EXISTS idx_api_key_user_id ON api_key(user_id);
    CREATE INDEX IF NOT EXISTS idx_api_key_hash ON api_key(key_hash);
    CREATE INDEX IF NOT EXISTS idx_api_key_active ON api_key(is_active);
    """

    verify_sql = """
    SELECT column_name, data_type, character_maximum_length, is_nullable
    FROM information_schema.columns
    WHERE table_name = 'api_key'
    ORDER BY ordinal_position;
    """

    try:
        # Connect to database
        print("🔌 Connecting to production database...")
        conn = psycopg2.connect(DB_URL)
        cursor = conn.cursor()

        # Create table
        print("📝 Creating api_key table...")
        cursor.execute(create_table_sql)
        conn.commit()
        print("✅ Table created successfully!")

        # Create indexes
        print("🔍 Creating indexes...")
        cursor.execute(create_indexes_sql)
        conn.commit()
        print("✅ Indexes created successfully!")

        # Verify table structure
        print("\n📋 Verifying table structure:")
        cursor.execute(verify_sql)
        columns = cursor.fetchall()

        print("\n" + "="*80)
        print(f"{'Column Name':<20} {'Data Type':<20} {'Max Length':<15} {'Nullable':<10}")
        print("="*80)
        for col in columns:
            col_name, data_type, max_length, nullable = col
            max_len_str = str(max_length) if max_length else 'N/A'
            print(f"{col_name:<20} {data_type:<20} {max_len_str:<15} {nullable:<10}")
        print("="*80)

        # Check foreign key constraints
        print("\n🔗 Checking foreign key constraints:")
        cursor.execute("""
            SELECT constraint_name, constraint_type
            FROM information_schema.table_constraints
            WHERE table_name = 'api_key';
        """)
        constraints = cursor.fetchall()
        for constraint in constraints:
            print(f"  - {constraint[0]}: {constraint[1]}")

        print("\n✅ API Key table setup complete!")
        print("🎉 You can now use the ApiKey model in your application!")

        cursor.close()
        conn.close()

    except psycopg2.Error as e:
        print(f"❌ Database error: {e}")
        if conn is not None:
            conn.rollback()
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()

if __name__ == "__main__":
    print("="*80)
    print("🚀 Adding ApiKey Table to Production Database")
    print("="*80)
    create_apikey_table()
