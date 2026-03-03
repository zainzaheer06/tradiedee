"""
Script to change 'initiated' status calls to 'failed' for a specific agent
These are calls that started but never completed properly.
"""
import sys
from app import app
from models import db, CallLog, Agent, User

def fix_initiated_calls_by_agent(agent_id, dry_run=True):
    """
    Update all calls with status='initiated' to status='failed' for a specific agent

    Args:
        agent_id: The agent ID to fix calls for
        dry_run: If True, only show what would be changed without actually changing it
    """
    with app.app_context():
        # Check if agent exists
        agent = Agent.query.get(agent_id)
        if not agent:
            print(f"ERROR: Agent with ID {agent_id} not found!")
            return

        user = User.query.get(agent.user_id)
        print(f"Agent: {agent.name} (ID: {agent_id})")
        print(f"Owner: {user.username if user else 'Unknown'}")
        print()

        # Find all initiated calls for this agent
        initiated_calls = CallLog.query.filter_by(
            agent_id=agent_id,
            status='initiated'
        ).all()

        if not initiated_calls:
            print(f"No 'initiated' calls found for agent '{agent.name}'. Nothing to fix!")
            return

        print("=" * 80)
        print(f"FOUND {len(initiated_calls)} CALLS WITH STATUS 'initiated'")
        print("=" * 80)
        print()

        # Show details of what will be changed
        print("Calls that will be changed to 'failed':")
        print("-" * 80)

        for call in initiated_calls:
            print(f"Call ID: {call.id}")
            print(f"  Room: {call.room_name}")
            print(f"  To: {call.to_number}")
            print(f"  Duration: {call.duration_seconds}s")
            print(f"  Minutes Used: {call.minutes_used}")
            print(f"  Created: {call.created_at}")
            print(f"  Status: {call.status} -> failed")
            print()

        print("=" * 80)

        if dry_run:
            print("DRY RUN MODE - No changes were made")
            print("To actually apply these changes, run:")
            print(f"  python fix_initiated_calls.py {agent_id} --apply")
        else:
            # Actually update the calls
            confirm = input(f"\nAre you sure you want to update {len(initiated_calls)} calls for agent '{agent.name}'? (yes/no): ")

            if confirm.lower() != 'yes':
                print("Cancelled. No changes made.")
                return

            for call in initiated_calls:
                call.status = 'failed'
                # Make sure minutes_used is 0 for failed calls
                if call.minutes_used > 0:
                    print(f"WARNING: Call {call.id} has minutes_used={call.minutes_used}, setting to 0")
                    call.minutes_used = 0

            try:
                db.session.commit()
                print(f"\nSUCCESS! Updated {len(initiated_calls)} calls to 'failed' status")
            except Exception as e:
                db.session.rollback()
                print(f"\nERROR: Failed to update calls: {e}")
                return

        print("=" * 80)


def list_agents():
    """List all agents and count of initiated calls"""
    with app.app_context():
        agents = Agent.query.all()
        print("=" * 80)
        print("AGENTS WITH 'INITIATED' CALLS")
        print("=" * 80)

        agents_with_issues = []

        for agent in agents:
            # Count initiated calls for each agent
            initiated_count = CallLog.query.filter_by(
                agent_id=agent.id,
                status='initiated'
            ).count()

            if initiated_count > 0:
                user = User.query.get(agent.user_id)
                agents_with_issues.append({
                    'id': agent.id,
                    'name': agent.name,
                    'owner': user.username if user else 'Unknown',
                    'count': initiated_count
                })

        if not agents_with_issues:
            print("No agents with 'initiated' calls found!")
        else:
            for agent_info in agents_with_issues:
                print(f"Agent ID: {agent_info['id']} | Name: {agent_info['name']} | Owner: {agent_info['owner']} | Initiated Calls: {agent_info['count']}")

        print("=" * 80)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python fix_initiated_calls.py <agent_id>           # Dry run (preview only)")
        print("  python fix_initiated_calls.py <agent_id> --apply   # Actually apply changes")
        print("  python fix_initiated_calls.py --list               # List agents with initiated calls")
        print()
        print("Example:")
        print("  python fix_initiated_calls.py 5                    # Preview changes for agent 5")
        print("  python fix_initiated_calls.py 5 --apply            # Apply changes for agent 5")
        print()
        list_agents()
        sys.exit(1)

    # Check if --list flag
    if sys.argv[1] == '--list':
        list_agents()
        sys.exit(0)

    # Get agent_id
    try:
        agent_id = int(sys.argv[1])
    except ValueError:
        print(f"ERROR: Invalid agent_id '{sys.argv[1]}'. Must be a number.")
        sys.exit(1)

    # Check if --apply flag is passed
    apply_changes = len(sys.argv) > 2 and sys.argv[2] == '--apply'

    if apply_changes:
        print("APPLYING CHANGES...")
        print()
        fix_initiated_calls_by_agent(agent_id, dry_run=False)
    else:
        print("DRY RUN MODE (no changes will be made)")
        print()
        fix_initiated_calls_by_agent(agent_id, dry_run=True)
