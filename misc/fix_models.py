import codecs

# Read from backup and write to models.py
with codecs.open('app_backup.py', 'r', encoding='utf-8') as f:
    backup_lines = f.readlines()

# Extract the models section (lines 76-229)
models_header = '''"""
Database Models for NevoxAI Voice Agent Platform
"""
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


'''

# Get models from backup
models_section = ''.join(backup_lines[76:230])

# Write to models.py
with codecs.open('models.py', 'w', encoding='utf-8') as f:
    f.write(models_header)
    f.write(models_section)

print("models.py fixed successfully!")
