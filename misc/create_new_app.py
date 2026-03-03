"""Script to create new streamlined app.py"""

new_app_content = '''"""
NevoxAI Voice Agent Platform - Main Application
Modular Flask application with blueprint-based routing
"""
import os
import logging
from flask import Flask
from flask_mail import Mail
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

# Import database and models
from models import db, User

# Import utilities
from utils.helpers import from_json_filter
from utils.email import init_email_utils

# Import blueprint registration
from routes import register_blueprints

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///voice_agent.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Email Configuration
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True') == 'True'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER')

# Initialize extensions
db.init_app(app)
mail = Mail(app)

# Initialize email utilities
init_email_utils(app, mail)

# Register Jinja2 filters
app.template_filter('from_json')(from_json_filter)

# Register all blueprints
register_blueprints(app)

logger.info("All blueprints registered successfully")


def init_db():
    """Initialize database and create default admin user"""
    with app.app_context():
        db.create_all()
        logger.info("Database tables created")
        
        # Create default admin if not exists
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(
                username='admin',
                email='admin@example.com',
                password=generate_password_hash('admin123'),
                is_admin=True,
                is_approved=True,
                is_email_verified=True,
                minutes_balance=999999
            )
            db.session.add(admin)
            db.session.commit()
            logger.info("Default admin created: username='admin', password='admin123'")
        else:
            logger.info("Admin user already exists")


if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5002, host='0.0.0.0')
'''

# Write the new app.py
with open('app.py', 'w', encoding='utf-8') as f:
    f.write(new_app_content)

print("New app.py created successfully!")
print("File size:", len(new_app_content), "bytes")
