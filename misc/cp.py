import sqlite3
conn = sqlite3.connect('instance/voice_agent.db')
cursor = conn.cursor()

# Update call window to current time range (e.g., 21:00 - 23:59)
cursor.execute("""
    UPDATE campaign 
    SET call_window_start = '21:00', call_window_end = '23:59'
    WHERE id = 5
""")

conn.commit()
conn.close()
print("✅ Call window updated to 21:00-23:59")