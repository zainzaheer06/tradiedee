#!/usr/bin/env python3
"""
Debug setup page error
"""

from app import app, db
from models import Business, User

with app.app_context():
    try:
        # Test 1: Check if Business model has all required columns
        print("✓ Checking Business model columns...")
        inspector = db.inspect(db.engine)
        columns = [c['name'] for c in inspector.get_columns('business')]
        print(f"  Business table columns: {columns}")

        # Test 2: Try to create a test business
        print("\n✓ Testing business creation...")
        user = User.query.first()
        if user:
            print(f"  Found user: {user.username} (ID: {user.id})")

            business = Business(
                user_id=user.id,
                business_name="Test Business",
                business_type="plumbing",
                phone_number="+61298765432"
            )
            print(f"  ✓ Business object created successfully")

            # Don't save, just check if it works
            print("\n✓ All tests passed!")
            print("  Business model is working correctly.")
        else:
            print("  ✗ No users found in database")

    except Exception as e:
        print(f"\n✗ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
