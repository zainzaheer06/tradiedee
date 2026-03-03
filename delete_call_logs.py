"""
Script to delete specific call logs by ID (no balance adjustments)
"""
import sys
from app import app
from models import db, CallLog, User

def delete_call_logs(call_ids, dry_run=True):
    """
    Delete call logs by IDs (no user balance changes)

    Args:
        call_ids: List of call log IDs to delete
        dry_run: If True, only show what would be deleted without actually deleting
    """
    with app.app_context():
        print("=" * 80)
        print(f"DELETE CALL LOGS: {', '.join(map(str, call_ids))}")
        print("=" * 80)
        print()

        calls_to_delete = []

        for call_id in call_ids:
            call = CallLog.query.get(call_id)
            if not call:
                print(f"ERROR: Call ID {call_id} not found!")
                print()
                continue

            user = User.query.get(call.user_id)
            user_name = user.username if user else 'Unknown'

            print(f"Call ID: {call_id}")
            print(f"  User: {user_name} (ID: {call.user_id})")
            print(f"  Room: {call.room_name}")
            print(f"  Status: {call.status}")
            print(f"  Duration: {call.duration_seconds}s")
            print(f"  Minutes: {call.minutes_used}")
            print(f"  Type: {call.call_type}")
            print(f"  Created: {call.created_at}")
            print()

            calls_to_delete.append(call)

        if not calls_to_delete:
            print("No calls found to delete!")
            return

        print("=" * 80)

        if dry_run:
            print("DRY RUN MODE - No changes were made")
            print("To actually delete these calls, run:")
            print(f"  python delete_call_logs.py {' '.join(map(str, call_ids))} --apply")
        else:
            # Confirm deletion
            confirm = input(f"\nAre you sure you want to DELETE {len(calls_to_delete)} call(s)? (yes/no): ")

            if confirm.lower() != 'yes':
                print("Cancelled. No changes made.")
                return

            # Delete calls
            for call in calls_to_delete:
                db.session.delete(call)

            try:
                db.session.commit()
                print(f"\nSUCCESS! Deleted {len(calls_to_delete)} call log(s)")
            except Exception as e:
                db.session.rollback()
                print(f"\nERROR: Failed to delete calls: {e}")
                return

        print("=" * 80)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python delete_call_logs.py <call_id> [call_id2] ...           # Dry run")
        print("  python delete_call_logs.py <call_id> [call_id2] ... --apply   # Actually delete")
        print()
        print("Examples:")
        print("  python delete_call_logs.py 735 738                # Preview deletion")
        print("  python delete_call_logs.py 735 738 --apply        # Actually delete")
        sys.exit(1)

    # Parse call IDs
    call_ids = []
    apply_changes = False

    for arg in sys.argv[1:]:
        if arg == '--apply':
            apply_changes = True
        else:
            try:
                call_ids.append(int(arg))
            except ValueError:
                print(f"ERROR: Invalid call_id '{arg}'. Must be a number.")
                sys.exit(1)

    if not call_ids:
        print("ERROR: No call IDs provided!")
        sys.exit(1)

    if apply_changes:
        print("APPLYING CHANGES...")
        print()
        delete_call_logs(call_ids, dry_run=False)
    else:
        print("DRY RUN MODE (no changes will be made)")
        print()
        delete_call_logs(call_ids, dry_run=True)
