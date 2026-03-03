"""
Add recording_url and recording_id fields to CallLog table
"""

from app import app, db

with app.app_context():
    # Execute raw SQL to add columns
    try:
        db.session.execute(db.text("ALTER TABLE call_log ADD COLUMN recording_url VARCHAR(500)"))
        db.session.commit()
        print("[OK] Added recording_url column to call_log table")
    except Exception as e:
        db.session.rollback()
        if "duplicate column" in str(e).lower():
            print("[SKIP] recording_url column already exists")
        else:
            print(f"[ERROR] {e}")

    try:
        db.session.execute(db.text("ALTER TABLE call_log ADD COLUMN recording_id VARCHAR(100)"))
        db.session.commit()
        print("[OK] Added recording_id column to call_log table")
    except Exception as e:
        db.session.rollback()
        if "duplicate column" in str(e).lower():
            print("[SKIP] recording_id column already exists")
        else:
            print(f"[ERROR] {e}")

print("\n[SUCCESS] Migration completed!")
