"""
Check call logs to see if they have duration and minutes tracked
"""

from app import app, db, User, CallLog

with app.app_context():
    # Get user #4 (example@gmail.com)
    user = User.query.get(4)

    if user:
        print(f"User: {user.username} ({user.email})")
        print(f"Total calls in database: {len(user.call_logs)}")
        print(f"Minutes balance: {user.minutes_balance}")
        print(f"Minutes used: {user.minutes_used or 0}")
        print("\n" + "="*80)
        print("Recent Call Logs:")
        print("="*80 + "\n")

        # Show last 10 calls
        recent_calls = CallLog.query.filter_by(user_id=user.id).order_by(CallLog.created_at.desc()).limit(10).all()

        for call in recent_calls:
            print(f"Call ID: {call.id}")
            print(f"  Created: {call.created_at}")
            print(f"  Room: {call.room_name}")
            print(f"  Duration: {call.duration_seconds} seconds")
            print(f"  Minutes used: {call.minutes_used}")
            print(f"  Status: {call.status}")
            print(f"  Agent ID: {call.agent_id}")
            print()

        # Calculate what minutes_used SHOULD be
        total_minutes_from_logs = db.session.query(db.func.sum(CallLog.minutes_used)).filter_by(user_id=user.id).scalar() or 0
        print(f"\n{'='*80}")
        print(f"Total minutes from call logs: {total_minutes_from_logs}")
        print(f"User.minutes_used field: {user.minutes_used or 0}")
        print(f"Difference: {total_minutes_from_logs - (user.minutes_used or 0)}")
