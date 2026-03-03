"""
Business Setup Routes - Phase 1 Feature
Initial setup for businesses using Phase 1 features (scheduling, emergency, address)
"""

import logging
from flask import Blueprint, request, jsonify, render_template, session, redirect, url_for
from functools import wraps

from models import db, Business, User
from utils.decorators import login_required

logger = logging.getLogger(__name__)

business_setup_bp = Blueprint('business_setup', __name__, url_prefix='/setup')


def require_no_business(f):
    """Redirect if business already exists"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if user_id:
            business = Business.query.filter_by(user_id=user_id).first()
            if business:
                return redirect(url_for('jobs.job_dashboard'))
        return f(*args, **kwargs)

    return decorated_function


# ============================================================================
# SETUP WIZARD
# ============================================================================

@business_setup_bp.route('/', methods=['GET', 'POST'])
@login_required
@require_no_business
def setup():
    """Business setup wizard"""
    if request.method == 'POST':
        return setup_post()

    return render_template('setup/wizard.html')


def setup_post():
    """Handle setup form submission"""
    try:
        user_id = session.get('user_id')
        data = request.json or request.form

        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Check if business already exists
        existing = Business.query.filter_by(user_id=user_id).first()
        if existing:
            return jsonify({'error': 'Business already configured'}), 400

        # Create business
        business = Business(
            user_id=user_id,
            business_name=data.get('business_name', ''),
            business_type=data.get('business_type'),
            phone_number=data.get('phone_number'),
            greeting_message=data.get('greeting_message'),
            tone=data.get('tone', 'friendly'),
            working_hours_start=data.get('working_hours_start', '08:00'),
            working_hours_end=data.get('working_hours_end', '17:00'),
            timezone=data.get('timezone', 'Australia/Sydney'),
            availability_check_method=data.get('availability_check_method', 'serviceM8'),
        )

        # Configure ServiceM8 if provided
        if data.get('serviceM8_api_key'):
            business.serviceM8_enabled = True
            business.serviceM8_api_key = data.get('serviceM8_api_key')
            business.serviceM8_customer_id = data.get('serviceM8_customer_id')

        # Configure Google Maps if provided
        if data.get('google_api_key'):
            business.google_api_key = data.get('google_api_key')

        # Configure Twilio if provided
        if data.get('twilio_account_sid'):
            business.twilio_account_sid = data.get('twilio_account_sid')
            business.twilio_auth_token = data.get('twilio_auth_token')
            business.twilio_phone_number = data.get('twilio_phone_number')

        db.session.add(business)
        db.session.commit()

        logger.info(f"Business setup completed for user {user_id}: {business.business_name}")

        return jsonify({
            'status': 'success',
            'business_id': business.id,
            'message': 'Business configured successfully',
            'redirect': url_for('business_setup.configure_emergency')
        }), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error during setup: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# CONFIGURE EMERGENCY CONTACTS
# ============================================================================

@business_setup_bp.route('/emergency', methods=['GET', 'POST'])
@login_required
def configure_emergency():
    """Configure emergency contacts"""
    user_id = session.get('user_id')
    business = Business.query.filter_by(user_id=user_id).first()

    if not business:
        return redirect(url_for('business_setup.setup'))

    if request.method == 'POST':
        return configure_emergency_post(business)

    return render_template(
        'setup/emergency_contacts.html',
        business=business,
        current_contacts=business.emergency_contacts or []
    )


def configure_emergency_post(business):
    """Handle emergency contacts configuration"""
    try:
        data = request.json or request.form
        contacts = data.get('contacts', [])

        # Validate and clean contacts
        cleaned_contacts = []
        for i, contact in enumerate(contacts, 1):
            if contact.get('name') and contact.get('phone'):
                cleaned_contacts.append({
                    'name': contact.get('name'),
                    'phone': contact.get('phone'),
                    'priority': i
                })

        if not cleaned_contacts:
            return jsonify({'error': 'At least one emergency contact required'}), 400

        business.emergency_contacts = cleaned_contacts
        business.emergency_escalation_enabled = data.get('enabled', True)
        business.emergency_transfer_timeout = int(data.get('timeout', 30))

        db.session.commit()

        logger.info(f"Emergency contacts configured for business {business.id}: {len(cleaned_contacts)} contacts")

        return jsonify({
            'status': 'success',
            'message': 'Emergency contacts saved',
            'redirect': url_for('business_setup.configure_service_areas')
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error configuring emergency contacts: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# CONFIGURE SERVICE AREAS
# ============================================================================

@business_setup_bp.route('/service-areas', methods=['GET', 'POST'])
@login_required
def configure_service_areas():
    """Configure service areas"""
    user_id = session.get('user_id')
    business = Business.query.filter_by(user_id=user_id).first()

    if not business:
        return redirect(url_for('business_setup.setup'))

    if request.method == 'POST':
        return configure_service_areas_post(business)

    return render_template(
        'setup/service_areas.html',
        business=business,
        current_areas=business.service_areas or []
    )


def configure_service_areas_post(business):
    """Handle service areas configuration"""
    try:
        data = request.json or request.form
        areas = data.get('areas', [])

        # Filter out empty strings
        areas = [a.strip() for a in areas if a.strip()]

        business.service_areas = areas if areas else None

        db.session.commit()

        logger.info(f"Service areas configured for business {business.id}: {len(areas)} areas")

        return jsonify({
            'status': 'success',
            'message': 'Service areas saved',
            'redirect': url_for('jobs.job_dashboard')
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error configuring service areas: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# EDIT BUSINESS SETTINGS
# ============================================================================

@business_setup_bp.route('/edit', methods=['GET', 'POST'])
@login_required
def edit_business():
    """Edit business settings"""
    user_id = session.get('user_id')
    business = Business.query.filter_by(user_id=user_id).first()

    if not business:
        return redirect(url_for('business_setup.setup'))

    if request.method == 'POST':
        return edit_business_post(business)

    return render_template('setup/edit.html', business=business)


def edit_business_post(business):
    """Handle business settings update"""
    try:
        data = request.json or request.form

        # Update basic info
        business.business_name = data.get('business_name', business.business_name)
        business.business_type = data.get('business_type', business.business_type)
        business.phone_number = data.get('phone_number', business.phone_number)
        business.greeting_message = data.get('greeting_message', business.greeting_message)
        business.tone = data.get('tone', business.tone)
        business.working_hours_start = data.get('working_hours_start', business.working_hours_start)
        business.working_hours_end = data.get('working_hours_end', business.working_hours_end)

        # Update API keys if provided
        if data.get('serviceM8_api_key'):
            business.serviceM8_api_key = data.get('serviceM8_api_key')
        if data.get('serviceM8_customer_id'):
            business.serviceM8_customer_id = data.get('serviceM8_customer_id')
        if data.get('google_api_key'):
            business.google_api_key = data.get('google_api_key')

        # Update feature toggles
        business.serviceM8_enabled = data.get('serviceM8_enabled', False)
        business.availability_check_enabled = data.get('availability_check_enabled', True)
        business.emergency_escalation_enabled = data.get('emergency_escalation_enabled', True)

        db.session.commit()

        logger.info(f"Business settings updated for {business.id}")

        return jsonify({
            'status': 'success',
            'message': 'Settings saved successfully'
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating business settings: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# API: Get Business Details
# ============================================================================

@business_setup_bp.route('/api/business', methods=['GET'])
@login_required
def get_business():
    """Get current business details"""
    try:
        user_id = session.get('user_id')
        business = Business.query.filter_by(user_id=user_id).first()

        if not business:
            return jsonify({'error': 'Business not configured'}), 404

        return jsonify({
            'status': 'success',
            'business': {
                'id': business.id,
                'name': business.business_name,
                'type': business.business_type,
                'phone': business.phone_number,
                'tone': business.tone,
                'working_hours_start': business.working_hours_start,
                'working_hours_end': business.working_hours_end,
                'timezone': business.timezone,
                'serviceM8_enabled': business.serviceM8_enabled,
                'emergency_escalation_enabled': business.emergency_escalation_enabled,
                'availability_check_enabled': business.availability_check_enabled,
                'service_areas': business.service_areas or [],
                'emergency_contacts': business.emergency_contacts or [],
            }
        })

    except Exception as e:
        logger.error(f"Error getting business: {str(e)}")
        return jsonify({'error': str(e)}), 500
