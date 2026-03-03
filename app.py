"""
NevoxAI Voice Agent Platform - Main Application
Modular Flask application with blueprint-based routing
"""
import os
import logging
import uuid
from datetime import datetime, timezone
from flask import Flask, render_template, request
from flask_mail import Mail
from flask_cors import CORS
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

# Import database and models
from models import db, User, SAUDI_TZ

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

# =============================================================================
# SESSION SECURITY CONFIGURATION
# =============================================================================
# SESSION_COOKIE_SECURE: Only send cookies over HTTPS connections
# WHY: Prevents session hijacking via man-in-the-middle attacks on HTTP
# NOTE: Set to False for development (HTTP), True for production (HTTPS)
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('USE_HTTPS', 'false').lower() in ('true', '1', 'yes')

# SESSION_COOKIE_HTTPONLY: JavaScript cannot access the session cookie
# WHY: Prevents XSS attacks from stealing session cookies via document.cookie
app.config['SESSION_COOKIE_HTTPONLY'] = True

# SESSION_COOKIE_SAMESITE: Cookie only sent with same-site requests
# WHY: Prevents CSRF attacks - browser won't send cookie with cross-origin requests
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# PERMANENT_SESSION_LIFETIME: Sessions expire after 2 hours of inactivity
# WHY: Limits exposure window if session is compromised
from datetime import timedelta
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)


# Disable template caching for development

app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

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

# Configure CORS for API endpoints
CORS(app, resources={
    r"/api/public/*": {
        "origins": os.environ.get('ALLOWED_WEBSITE_DOMAIN', '*').split(','),
        "methods": ["POST", "GET", "OPTIONS"],
        "allow_headers": ["Content-Type", "X-API-Key"],
        "supports_credentials": False
    },
    r"/api/v1/*": {
        "origins": "*",  # API v1 is accessed via API key, not session
        "methods": ["POST", "GET", "OPTIONS"],
        "allow_headers": ["Content-Type", "X-API-Key"],
        "supports_credentials": False
    }
})

# Initialize email utilities
init_email_utils(app, mail)

# Register Jinja2 filters
app.template_filter('from_json')(from_json_filter)

# Register all blueprints
register_blueprints(app)

logger.info("All blueprints registered successfully")


# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors with custom page"""
    logger.warning(f"404 Error: {request.url} - IP: {request.remote_addr}")
    return render_template('errors/404.html', current_year=datetime.now(SAUDI_TZ).year), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors with generic page"""
    error_id = str(uuid.uuid4())[:8]
    logger.error(f"500 Error [{error_id}]: {error} - URL: {request.url} - IP: {request.remote_addr}")
    db.session.rollback()
    return render_template('errors/generic.html',
                         error_code=500,
                         error_name="Internal Server Error",
                         error_description="Something went wrong on our end. Please try again later.",
                         error_id=error_id,
                         current_year=datetime.now(SAUDI_TZ).year), 500

@app.errorhandler(403)
def forbidden_error(error):
    """Handle 403 errors with generic page"""
    logger.warning(f"403 Error: {request.url} - IP: {request.remote_addr}")
    return render_template('errors/generic.html',
                         error_code=403,
                         error_name="Access Forbidden",
                         error_description="You don't have permission to access this resource.",
                         current_year=datetime.now(SAUDI_TZ).year), 403


# =============================================================================
# SECURITY HEADERS MIDDLEWARE
# =============================================================================
# These headers are added to EVERY response to protect against common attacks
@app.after_request
def add_security_headers(response):
    """Add security headers to all responses"""

    # X-Content-Type-Options: nosniff
    # WHY: Prevents browser from MIME-sniffing (guessing content type)
    # ATTACK PREVENTED: Attackers can't trick browser into executing malicious
    # files by disguising them as safe content types
    response.headers['X-Content-Type-Options'] = 'nosniff'

    # X-Frame-Options: DENY
    # WHY: Prevents your pages from being embedded in iframes on other sites
    # ATTACK PREVENTED: Clickjacking - where attacker overlays invisible iframe
    # to trick users into clicking hidden buttons
    response.headers['X-Frame-Options'] = 'DENY'

    # X-XSS-Protection: 1; mode=block
    # WHY: Enables browser's built-in XSS filter and blocks page if attack detected
    # ATTACK PREVENTED: Reflected XSS attacks in older browsers
    response.headers['X-XSS-Protection'] = '1; mode=block'

    # Referrer-Policy: strict-origin-when-cross-origin
    # WHY: Controls how much referrer info is sent with requests
    # BENEFIT: Prevents leaking sensitive URLs to external sites
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'

    # Content-Security-Policy (basic)
    # WHY: Controls which resources can be loaded
    # ATTACK PREVENTED: XSS, data injection, clickjacking
    # NOTE: Adjust 'unsafe-inline' based on your needs - stricter is better
    response.headers['Content-Security-Policy'] = "frame-ancestors 'none';"

    return response


# ==================== DATABASE INITIALIZATION ====================

def migrate_job_table():
    """Migrate job table to allow nullable fields for AI extraction"""
    try:
        # Check if job table needs migration (SQLite can't ALTER nullable)
        result = db.session.execute(db.text("PRAGMA table_info(job)")).fetchall()
        if not result:
            return  # Table doesn't exist yet, will be created by create_all

        # Check if business_id is NOT NULL (old schema)
        for col in result:
            # col format: (cid, name, type, notnull, default, pk)
            if col[1] == 'business_id' and col[3] == 1:  # notnull=1 means NOT NULL
                logger.info("Migrating job table: making fields nullable for AI extraction...")

                # Recreate table with nullable fields
                db.session.execute(db.text("ALTER TABLE job RENAME TO job_old"))
                db.session.commit()

                # Create new table with updated schema
                db.create_all()

                # Copy data from old table
                db.session.execute(db.text("""
                    INSERT INTO job SELECT * FROM job_old
                """))
                db.session.execute(db.text("DROP TABLE job_old"))
                db.session.commit()
                logger.info("Job table migrated successfully!")
                return

        logger.info("Job table schema is up to date")
    except Exception as e:
        db.session.rollback()
        logger.warning(f"Job table migration skipped: {e}")


def migrate_customer_table():
    """Add customer_id column to job table if missing, and create customer table"""
    try:
        result = db.session.execute(db.text("PRAGMA table_info(job)")).fetchall()
        columns = [col[1] for col in result]
        if 'customer_id' not in columns:
            logger.info("Adding customer_id column to job table...")
            db.session.execute(db.text("ALTER TABLE job ADD COLUMN customer_id INTEGER REFERENCES customer(id)"))
            db.session.commit()
            logger.info("customer_id column added to job table")
    except Exception as e:
        db.session.rollback()
        logger.warning(f"Customer migration skipped: {e}")


def init_db():
    """Initialize database and create default admin user"""
    with app.app_context():
        db.create_all()
        migrate_job_table()
        migrate_customer_table()
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
    debug_mode = os.environ.get('FLASK_DEBUG', 'false').lower() in ('true', '1', 'yes')
    port = int(os.environ.get('FLASK_PORT', '5016'))
    app.run(debug=debug_mode, port=port, host='0.0.0.0')
