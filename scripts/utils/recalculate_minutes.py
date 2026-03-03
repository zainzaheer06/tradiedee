"""
Recalculate minutes_used for all users based on their actual call logs.
This fixes users who had calls before the minutes_used tracking was added.
"""

from app import app, db, User, CallLog

with app.app_context():
    # Get all users
    users = User.query.all()

    print("Recalculating minutes_used for all users...")
    print("="*80 + "\n")

    for user in users:
        # Calculate total minutes from call logs
        total_minutes_from_logs = db.session.query(
            db.func.sum(CallLog.minutes_used)
        ).filter_by(user_id=user.id).scalar() or 0

        old_minutes_used = user.minutes_used or 0

        if total_minutes_from_logs != old_minutes_used:
            print(f"User #{user.id} - {user.username}")
            print(f"  Old minutes_used: {old_minutes_used}")
            print(f"  Calculated from logs: {total_minutes_from_logs}")
            print(f"  Difference: {total_minutes_from_logs - old_minutes_used}")

            # Update the user's minutes_used
            user.minutes_used = total_minutes_from_logs

            print(f"  [UPDATED] Set minutes_used to {total_minutes_from_logs}")
            print()

    # Commit changes
    db.session.commit()
    print("\n" + "="*80)
    print("[SUCCESS] Recalculation complete!")
    print("="*80 + "\n")

    # Show final state
    print("Final state of all users:")
    print("="*80 + "\n")

    for user in User.query.filter_by(is_approved=True).order_by(User.id).all():
        total_calls = len(user.call_logs)
        total_allocated = (user.minutes_used or 0) + user.minutes_balance

        print(f"User #{user.id} - {user.username}")
        print(f"  Total calls: {total_calls}")
        print(f"  Minutes used: {user.minutes_used or 0}")
        print(f"  Minutes balance: {user.minutes_balance}")
        print(f"  Total allocated: {total_allocated}")
        print()
