"""
Public API Routes Blueprint
Handles public-facing API endpoints for external website integration
"""
import os
import asyncio
import logging
from datetime import datetime
from functools import wraps
from flask import Blueprint, request, jsonify
from livekit import api
import phonenumbers

from models import db, Agent, User, CallLog, SAUDI_TZ
from utils.rate_limiter import website_rate_limiter

logger = logging.getLogger(__name__)

# Create blueprint
public_api_bp = Blueprint('public_api', __name__, url_prefix='/api/public')


# ==================== AUTHENTICATION DECORATOR ====================

def require_api_key(f):
    """Decorator to require API key authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        expected_key = os.environ.get('API_KEY_WEBSITE')

        if not expected_key:
            logger.error("API_KEY_WEBSITE not configured in environment")
            return jsonify({'success': False, 'error': 'API configuration error'}), 500

        if not api_key or api_key != expected_key:
            logger.warning(f"Invalid API key attempt from IP: {request.remote_addr}")
            return jsonify({'success': False, 'error': 'Invalid API key'}), 401

        return f(*args, **kwargs)
    return decorated_function


# ==================== HELPER FUNCTIONS ====================

def validate_phone_number(phone_number):
    """
    Validate and format phone number to E.164 format

    Args:
        phone_number: Phone number string

    Returns:
        str: Formatted phone number or None if invalid
    """
    try:
        # Try parsing as Saudi number
        parsed = phonenumbers.parse(phone_number, "SA")

        # Validate the number
        if not phonenumbers.is_valid_number(parsed):
            return None

        # Format to E.164 (+966xxxxxxxxx)
        formatted = phonenumbers.format_number(
            parsed,
            phonenumbers.PhoneNumberFormat.E164
        )

        return formatted

    except phonenumbers.NumberParseException as e:
        logger.warning(f"Phone number parsing failed: {phone_number} - {e}")
        return None


async def make_livekit_call(phone_number, room_name, agent_name, outbound_trunk_id):
    """
    Create a dispatch and add a SIP participant to call the phone number
    Reused from agents.py

    Args:
        phone_number: E.164 formatted phone number
        room_name: LiveKit room name
        agent_name: Agent name for dispatch
        outbound_trunk_id: SIP trunk ID for outbound calls
    """
    lkapi = api.LiveKitAPI()

    # Create agent dispatch
    dispatch = await lkapi.agent_dispatch.create_dispatch(
        api.CreateAgentDispatchRequest(
            agent_name="agent",
            room=room_name,
            metadata=phone_number
        )
    )

    # Wait for agent to connect before adding SIP participant (prevents race condition)
    await asyncio.sleep(2)

    logger.info(f"Creating SIP call to {phone_number} in room {room_name}")

    # Create SIP participant to make the call
    sip_participant = await lkapi.sip.create_sip_participant(
        api.CreateSIPParticipantRequest(
            room_name=room_name,
            sip_trunk_id=outbound_trunk_id,
            sip_call_to=phone_number,
            participant_identity="phone_user",
        )
    )

    await lkapi.aclose()


# ==================== PUBLIC ENDPOINTS ====================

@public_api_bp.route('/website-call', methods=['POST'])
@require_api_key
def website_call():
    """
    Public endpoint for initiating calls from external website

    Request body:
        {
            "phone_number": "+966501234567"
        }

    Response:
        {
            "success": true,
            "call_id": 12345,
            "message": "Call initiated successfully",
            "agent_id": 54
        }
    """
    # Get client IP for rate limiting
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ',' in client_ip:
        client_ip = client_ip.split(',')[0].strip()

    # Check rate limit
    allowed, remaining, reset_time = website_rate_limiter.is_allowed(client_ip)

    if not allowed:
        logger.warning(f"Rate limit exceeded for IP: {client_ip}")
        return jsonify({
            'success': False,
            'error': 'Rate limit exceeded. Maximum 5 calls per hour.',
            'reset_time': reset_time.isoformat()
        }), 429

    # Get phone number from request
    data = request.get_json()
    if not data or 'phone_number' not in data:
        return jsonify({
            'success': False,
            'error': 'Phone number is required'
        }), 400

    phone_number = data['phone_number'].strip()

    # Validate phone number
    formatted_number = validate_phone_number(phone_number)
    if not formatted_number:
        return jsonify({
            'success': False,
            'error': 'Invalid phone number format. Please use Saudi format (e.g., 0501234567 or +966501234567)'
        }), 400

    # Get agent ID 54 (website call agent)
    agent = db.session.get(Agent, 54)
    if not agent:
        logger.error("Agent ID 54 (website call agent) not found in database")
        return jsonify({
            'success': False,
            'error': 'Service configuration error. Please contact administrator.'
        }), 500

    # Get user with email example@gmail.com
    user = User.query.filter_by(email='example@gmail.com').first()
    if not user:
        logger.error("User with email example@gmail.com not found")
        return jsonify({
            'success': False,
            'error': 'Service configuration error. Please contact administrator.'
        }), 500

    # Check if user has minutes
    if user.minutes_balance <= 0:
        logger.warning(f"User {user.email} has insufficient minutes: {user.minutes_balance}")
        return jsonify({
            'success': False,
            'error': 'Service temporarily unavailable. Please try again later.'
        }), 503

    try:
        # Get outbound trunk ID
        outbound_trunk_id = user.outbound_trunk_id if user.outbound_trunk_id else os.environ.get('SIP_OUTBOUND_TRUNK_ID')

        if not outbound_trunk_id:
            logger.error("No outbound trunk ID configured")
            return jsonify({
                'success': False,
                'error': 'Service configuration error. Please contact administrator.'
            }), 500

        # Create room name
        room_name = f"website-{datetime.now(SAUDI_TZ).timestamp()}"

        # Initiate the call via LiveKit
        asyncio.run(make_livekit_call(formatted_number, room_name, agent.name, outbound_trunk_id))

        # Create call log (identical to normal outbound calls)
        call_log = CallLog(
            user_id=user.id,
            agent_id=54,
            from_number=user.outbound_phone_number or os.environ.get('SAUDI_PHONE_NUMBER', '966115108724'),
            to_number=formatted_number,
            room_name=room_name,
            status='initiated',
            call_type='outbound'
        )

        db.session.add(call_log)
        db.session.commit()

        # Record this call in rate limiter
        website_rate_limiter.record_call(client_ip)

        logger.info(f"Website call initiated: {formatted_number} -> Room: {room_name} -> Call ID: {call_log.id}")

        return jsonify({
            'success': True,
            'call_id': call_log.id,
            'message': 'Call initiated successfully',
            'agent_id': 54
        }), 200

    except Exception as e:
        logger.error(f"Error initiating website call: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Failed to initiate call. Please try again later.'
        }), 500


@public_api_bp.route('/health', methods=['GET'])
def health_check():
    """Simple health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'NevoxAI Public API',
        'timestamp': datetime.now(SAUDI_TZ).isoformat()
    }), 200
