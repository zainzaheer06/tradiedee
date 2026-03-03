"""Quick test to verify WhatsApp agent feature setup"""
from app import app
from models import db, WhatsAppAgent

print("App loaded OK")

with app.app_context():
    db.create_all()
    print("Tables created OK")
    
    # Verify the table exists
    count = WhatsAppAgent.query.count()
    print(f"WhatsAppAgent table exists, {count} records")

print("All checks passed!")
