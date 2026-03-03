import sqlite3
from pathlib import Path

# Resolve the project root so the script works regardless of the CWD
base_dir = Path(__file__).resolve().parents[2]
db_path = base_dir / 'instance' / 'voice_agent.db'

conn = sqlite3.connect(db_path)
conn.execute('ALTER TABLE agent ADD COLUMN temperature FLOAT DEFAULT 0.4')
conn.commit()
conn.close()
print("Done!")
