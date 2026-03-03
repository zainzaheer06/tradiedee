"""
Diagnostic script to check for billing issues
"""
import sqlite3
import sys
from datetime import datetime, timedelta

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Connect to database
try:
    conn = sqlite3.connect('instance/voice_agent.db')
    cursor = conn.cursor()
except Exception as e:
    print(f"ERROR: Cannot connect to database: {e}")
    exit(1)

print("=" * 80)
print("BILLING DIAGNOSTIC REPORT")
print("=" * 80)
print()

# First, check what tables exist
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = cursor.fetchall()
print(f"Available tables: {[t[0] for t in tables]}")
print()

# Get all call logs from last 24 hours
cursor.execute("""
    SELECT id, user_id, room_name, duration_seconds, minutes_used, status, created_at
    FROM call_log
    WHERE datetime(created_at) >= datetime('now', '-1 day')
    ORDER BY created_at DESC
""")

calls = cursor.fetchall()

print(f"Total calls in last 24 hours: {len(calls)}")
print()

# Group by room_name to find duplicates
room_counts = {}
for call in calls:
    call_id, user_id, room_name, duration_seconds, minutes_used, status, created_at = call
    if room_name not in room_counts:
        room_counts[room_name] = []
    room_counts[room_name].append({
        'id': call_id,
        'user_id': user_id,
        'duration_seconds': duration_seconds,
        'minutes_used': minutes_used,
        'status': status,
        'created_at': created_at
    })

# Find duplicate room names (same call logged multiple times)
print("Checking for duplicate call logs...")
print()
duplicates_found = False
for room_name, entries in room_counts.items():
    if len(entries) > 1:
        duplicates_found = True
        print(f"WARNING - DUPLICATE FOUND: {room_name}")
        print(f"   This call was logged {len(entries)} times!")
        total_minutes = sum(e['minutes_used'] for e in entries)
        print(f"   Total minutes charged: {total_minutes} (should be only once)")
        for entry in entries:
            print(f"   - ID {entry['id']}: {entry['duration_seconds']}s -> {entry['minutes_used']} mins (Status: {entry['status']}, Created: {entry['created_at']})")
        print()

if not duplicates_found:
    print("No duplicate call logs found")
    print()

# Show call details
print("=" * 80)
print("RECENT CALL DETAILS")
print("=" * 80)
print()
for call in calls[:10]:  # Show last 10 calls
    call_id, user_id, room_name, duration_seconds, minutes_used, status, created_at = call
    expected_minutes = -(-duration_seconds // 60)  # Ceiling division
    match = "MATCH" if minutes_used == expected_minutes else "MISMATCH"
    print(f"Call ID: {call_id}")
    print(f"  User: {user_id}")
    print(f"  Room: {room_name}")
    print(f"  Duration: {duration_seconds}s")
    print(f"  Minutes charged: {minutes_used}")
    print(f"  Expected (ceil): {expected_minutes}")
    print(f"  {match}")
    print(f"  Status: {status}")
    print(f"  Created: {created_at}")
    print()

# Check user balances
print("=" * 80)
print("USER BALANCE SUMMARY")
print("=" * 80)
print()
cursor.execute("""
    SELECT id, username, minutes_balance, minutes_used
    FROM user
    WHERE minutes_used > 0 OR minutes_balance > 0
    ORDER BY id
""")

users = cursor.fetchall()
for user in users:
    user_id, username, minutes_balance, minutes_used = user
    print(f"User: {username} (ID: {user_id})")
    print(f"  Balance: {minutes_balance} minutes")
    print(f"  Total used: {minutes_used} minutes")

    # Get their call logs
    cursor.execute("""
        SELECT COUNT(*), SUM(minutes_used)
        FROM call_log
        WHERE user_id = ? AND status = 'completed'
    """, (user_id,))
    call_count, total_minutes = cursor.fetchone()
    total_minutes = total_minutes or 0

    print(f"  Completed calls: {call_count}")
    print(f"  Sum of call minutes: {total_minutes}")

    if total_minutes != minutes_used:
        print(f"  WARNING: User.minutes_used ({minutes_used}) != Sum of calls ({total_minutes})")
    else:
        print(f"  OK - Minutes match")
    print()

conn.close()

print("=" * 80)
print("DIAGNOSTIC COMPLETE")
print("=" * 80)
