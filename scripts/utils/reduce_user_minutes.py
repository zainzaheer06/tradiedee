"""
Reduce minutes from a client account by username.
Usage: python reduce_user_minutes.py
"""

import sys
import os

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app import app, db, User


def reduce_minutes(username: str, minutes_to_reduce: int):
    """
    Reduce minutes from a user's account.

    Args:
        username: Username of the client
        minutes_to_reduce: Number of minutes to deduct

    Returns:
        bool: True if successful, False otherwise
    """
    with app.app_context():
        # Find user by username
        user = User.query.filter_by(username=username).first()

        if not user:
            print(f"❌ Error: User '{username}' not found!")
            return False

        # Check if user has enough balance
        if user.minutes_balance < minutes_to_reduce:
            print(f"⚠️  Warning: User only has {user.minutes_balance} minutes available")
            print(f"   Requested to reduce: {minutes_to_reduce} minutes")

            response = input("   Continue anyway? (yes/no): ").strip().lower()
            if response not in ['yes', 'y']:
                print("❌ Operation cancelled")
                return False

        # Store old values
        old_balance = user.minutes_balance

        # Reduce minutes
        user.minutes_balance -= minutes_to_reduce

        # Ensure balance doesn't go negative (optional - can be removed if negative is allowed)
        if user.minutes_balance < 0:
            user.minutes_balance = 0
            actual_reduced = old_balance
        else:
            actual_reduced = minutes_to_reduce

        # Commit changes
        db.session.commit()

        # Display result
        print("\n" + "="*80)
        print("✅ Minutes successfully reduced!")
        print("="*80)
        print(f"User: {user.username} (ID: {user.id})")
        print(f"Email: {user.email}")
        print(f"Previous Balance: {old_balance} minutes")
        print(f"Minutes Reduced: {actual_reduced} minutes")
        print(f"New Balance: {user.minutes_balance} minutes")
        print("="*80 + "\n")

        return True


def main():
    """Main function to run the script interactively"""
    print("="*80)
    print("REDUCE USER MINUTES")
    print("="*80 + "\n")

    # Get username
    username = input("Enter username: ").strip()

    if not username:
        print("❌ Error: Username cannot be empty")
        return

    # Get minutes to reduce
    try:
        minutes = int(input("Enter minutes to reduce: ").strip())

        if minutes <= 0:
            print("❌ Error: Minutes must be a positive number")
            return

    except ValueError:
        print("❌ Error: Please enter a valid number")
        return

    # Confirm action
    print(f"\n⚠️  You are about to reduce {minutes} minutes from user '{username}'")
    confirm = input("Are you sure? (yes/no): ").strip().lower()

    if confirm not in ['yes', 'y']:
        print("❌ Operation cancelled")
        return

    # Execute reduction
    reduce_minutes(username, minutes)


if __name__ == "__main__":
    main()