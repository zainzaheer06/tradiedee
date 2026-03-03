"""
Fix existing users who don't have subscription_start_date set.
Uses Flask app context to access the database properly.
"""

from app import app, db, User
from datetime import datetime

with app.app_context():
    # Get all approved users without subscription_start_date
    users = User.query.filter_by(is_approved=True).filter(
        User.subscription_start_date == None
    ).all()

    print(f"Found {len(users)} users without subscription_start_date\n")

    for user in users:
        # Set subscription_start_date to created_at (when they registered)
        user.subscription_start_date = user.created_at
        if not user.subscription_plan:
            user.subscription_plan = 'free'

        print(f"[OK] Updated user #{user.id} - {user.username} ({user.email})")
        print(f"  - Set subscription_start_date to: {user.created_at}")
        print(f"  - Minutes balance: {user.minutes_balance}")
        print(f"  - Minutes used: {user.minutes_used or 0}")
        print(f"  - Total assigned: {(user.minutes_used or 0) + user.minutes_balance}")
        print()

    # Commit all changes
    db.session.commit()
    print(f"\n[SUCCESS] Successfully updated {len(users)} users")

    # Show all approved users current state
    print("\n=== All Approved Users ===")
    all_users = User.query.filter_by(is_approved=True).order_by(User.id).all()

    for user in all_users:
        total = (user.minutes_used or 0) + user.minutes_balance
        days_ago = (datetime.utcnow() - user.subscription_start_date).days if user.subscription_start_date else 0
        print(f"User #{user.id} ({user.username}):")
        print(f"  - Balance: {user.minutes_balance} min")
        print(f"  - Used: {user.minutes_used or 0} min")
        print(f"  - Total: {total} min")
        print(f"  - Started: {user.subscription_start_date.strftime('%b %d, %Y') if user.subscription_start_date else 'N/A'} ({days_ago} days ago)")
        print()
