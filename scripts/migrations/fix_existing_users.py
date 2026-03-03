"""
Fix existing users who don't have subscription_start_date set.
Set it to their account creation date.
"""

import sqlite3
from datetime import datetime

# Connect to database
conn = sqlite3.connect('nevox.db')
cursor = conn.cursor()

# Get all approved users without subscription_start_date
cursor.execute("""
    SELECT id, username, email, created_at, minutes_balance, minutes_used
    FROM User
    WHERE is_approved = 1 AND subscription_start_date IS NULL
""")

users = cursor.fetchall()

print(f"Found {len(users)} users without subscription_start_date")

for user in users:
    user_id, username, email, created_at, minutes_balance, minutes_used = user

    # Set subscription_start_date to created_at
    cursor.execute("""
        UPDATE User
        SET subscription_start_date = created_at,
            subscription_plan = 'free'
        WHERE id = ?
    """, (user_id,))

    print(f"✓ Updated user {username} ({email})")
    print(f"  - Set subscription_start_date to: {created_at}")
    print(f"  - Minutes balance: {minutes_balance}")
    print(f"  - Minutes used: {minutes_used or 0}")
    print()

# Commit changes
conn.commit()
print(f"\n✓ Successfully updated {len(users)} users")

# Show current state
print("\n=== Current User States ===")
cursor.execute("""
    SELECT id, username, email, subscription_start_date, minutes_balance, minutes_used
    FROM User
    WHERE is_approved = 1
    ORDER BY id
""")

for row in cursor.fetchall():
    user_id, username, email, sub_start, balance, used = row
    total = (used or 0) + balance
    print(f"User #{user_id} ({username}): {balance} min balance, {used or 0} min used, {total} total, started: {sub_start}")

conn.close()
