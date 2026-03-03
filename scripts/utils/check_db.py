import sqlite3

# Connect to database
conn = sqlite3.connect('instance/voice_agent.db')
cursor = conn.cursor()

# Check database schema
print("📋 Call log table schema:")
cursor.execute('PRAGMA table_info(call_log)')
columns = cursor.fetchall()
for i, col in enumerate(columns):
    print(f"  {i}: {col[1]} ({col[2]})")

print("\n" + "="*50)

# Check for the specific call log
room_name = 'call-13-1762181375.949719'
cursor.execute('SELECT * FROM call_log WHERE room_name = ?', (room_name,))
result = cursor.fetchone()

if result:
    print(f"✅ Call log found: ID={result[0]}")
    print(f"   Room: {result[10] if len(result) > 10 else 'N/A'}")
    print(f"   Status: {result[9] if len(result) > 9 else 'N/A'}")
    print(f"   Full record: {result}")
else:
    print(f"❌ Call log NOT found for room: {room_name}")
    
    # Check what call logs exist
    cursor.execute('SELECT id, room_name FROM call_log ORDER BY id DESC LIMIT 5')
    recent = cursor.fetchall()
    print("\nRecent call logs:")
    for log in recent:
        print(f"  ID={log[0]}, Room={log[1]}")

conn.close()