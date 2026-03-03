python -c "
import sqlite3
conn = sqlite3.connect('instance/voice_agent.db')
cursor = conn.cursor()
cursor.execute('ALTER TABLE agent ADD COLUMN temperature FLOAT DEFAULT 0.4 NOT NULL')
cursor.execute('UPDATE agent SET temperature = 0.4 WHERE temperature IS NULL')
conn.commit()
conn.close()
print('Migration completed!')
"