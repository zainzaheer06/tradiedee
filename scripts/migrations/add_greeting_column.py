"""
Database migration script to add 'greeting' column to Agent table
Run this once to update your existing database
"""
import sqlite3
import os
import sys

# Set UTF-8 encoding for Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

def migrate_database():
    # Try both possible database locations
    db_paths = [
        os.path.join(os.path.dirname(__file__), 'instance', 'voice_agent.db'),
        os.path.join(os.path.dirname(__file__), 'voice_agent.db')
    ]

    default_greeting = 'السلام عليكم ورحمة الله وبركاته، أهلاً وسهلاً فيك. أنا مساعدك الذكي، كيف أقدر أساعدك اليوم؟'

    for db_path in db_paths:
        if os.path.exists(db_path):
            print(f"[INFO] Found database at: {db_path}")

            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()

                # Check if column already exists
                cursor.execute("PRAGMA table_info(agent)")
                columns = [col[1] for col in cursor.fetchall()]

                if 'greeting' in columns:
                    print(f"[OK] Column 'greeting' already exists in {db_path}")
                else:
                    # Add the greeting column with default value
                    cursor.execute(f"""
                        ALTER TABLE agent
                        ADD COLUMN greeting TEXT DEFAULT '{default_greeting}'
                    """)
                    conn.commit()
                    print(f"[SUCCESS] Added 'greeting' column to {db_path}")

                # Verify the change
                cursor.execute("PRAGMA table_info(agent)")
                columns = [col[1] for col in cursor.fetchall()]
                print(f"[INFO] Current columns in agent table: {', '.join(columns)}")

                conn.close()

            except sqlite3.Error as e:
                print(f"[ERROR] Error migrating {db_path}: {e}")
            except Exception as e:
                print(f"[ERROR] Unexpected error with {db_path}: {e}")
        else:
            print(f"[SKIP] Database not found at: {db_path}")

if __name__ == "__main__":
    print("[START] Database migration to add greeting column...")
    migrate_database()
    print("[DONE] Migration complete!")
