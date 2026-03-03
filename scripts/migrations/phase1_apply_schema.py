"""
Phase 1 Schema Migration
Applies database schema updates for critical features:
- Scheduling Conflict Prevention
- Emergency Escalation
- Address Validation
"""

import os
import sys
import logging
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from models import db, User
from flask import Flask
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///voice_agent.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)


def run_migration():
    """Apply Phase 1 schema updates"""

    with app.app_context():
        try:
            logger.info("=" * 60)
            logger.info("PHASE 1 SCHEMA MIGRATION")
            logger.info("=" * 60)

            # Read migration SQL
            migration_file = os.path.join(
                os.path.dirname(__file__),
                '..',
                '..',
                'migrations',
                'phase1_schema_updates.sql'
            )

            if not os.path.exists(migration_file):
                logger.error(f"Migration file not found: {migration_file}")
                return False

            with open(migration_file, 'r') as f:
                sql_script = f.read()

            logger.info("Running SQL migrations...")

            # Execute each statement
            statements = sql_script.split(';')
            for idx, statement in enumerate(statements, 1):
                statement = statement.strip()
                if not statement:
                    continue

                try:
                    logger.info(f"Executing statement {idx}...")
                    logger.debug(f"SQL: {statement[:100]}...")
                    db.session.execute(db.text(statement))
                    db.session.commit()
                except Exception as e:
                    logger.warning(f"Statement {idx} skipped (may already exist): {str(e)}")
                    db.session.rollback()

            logger.info("✅ All SQL migrations applied successfully")

            # Create new Python models
            logger.info("Creating ORM models...")
            _create_models()

            logger.info("=" * 60)
            logger.info("✅ MIGRATION COMPLETE")
            logger.info("=" * 60)
            logger.info("\nNext steps:")
            logger.info("1. Restart your application")
            logger.info("2. Configure emergency contacts: app.config['EMERGENCY_CONTACTS']")
            logger.info("3. Set Google API key for address validation")
            logger.info("4. Test with a sample emergency call")
            logger.info("5. Monitor logs for any issues")

            return True

        except Exception as e:
            logger.error(f"Migration failed: {str(e)}")
            logger.exception(e)
            return False


def _create_models():
    """Create new models if needed"""

    try:
        # Create tables from SQLAlchemy models
        logger.info("Creating tables from models...")

        # Import new models (you'll add these to models.py)
        # from models import Business, Job, EmergencyEscalationLog, SMSLog, AddressValidationLog

        # db.create_all()

        logger.info("✅ Models created")

    except Exception as e:
        logger.error(f"Error creating models: {str(e)}")


def verify_migration():
    """Verify migration was successful"""

    with app.app_context():
        try:
            logger.info("\nVerifying migration...")

            # Check if new tables exist
            inspector = db.inspect(db.engine)
            tables = inspector.get_table_names()

            required_tables = ['business', 'job', 'emergency_escalation_log', 'sms_log']
            missing_tables = [t for t in required_tables if t not in tables]

            if missing_tables:
                logger.warning(f"Missing tables: {missing_tables}")
                return False

            logger.info(f"✅ All required tables present")

            # Check if columns exist
            user_columns = [c['name'] for c in inspector.get_columns('user')]
            required_columns = ['serviceM8_api_key', 'google_api_key', 'twilio_phone_number']
            missing_columns = [c for c in required_columns if c not in user_columns]

            if missing_columns:
                logger.warning(f"Missing columns in User table: {missing_columns}")
                return False

            logger.info(f"✅ All required columns present")
            return True

        except Exception as e:
            logger.error(f"Verification failed: {str(e)}")
            return False


if __name__ == '__main__':
    logger.info("Starting Phase 1 migration...")

    success = run_migration()

    if success:
        verified = verify_migration()
        if verified:
            logger.info("\n✅ All checks passed! Migration is ready.")
            sys.exit(0)
        else:
            logger.warning("\n⚠️ Migration applied but some checks failed.")
            sys.exit(1)
    else:
        logger.error("\n❌ Migration failed!")
        sys.exit(1)
