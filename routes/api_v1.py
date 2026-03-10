"""
API V1 Routes Blueprint
Public API for external integrations to trigger calls

Endpoints:
    POST /api/v1/calls/outbound - Initiate an outbound call
"""
import os
import json
import asyncio
import logging
from datetime import datetime
from functools import wraps
from flask import Blueprint, request, jsonify
from livekit import api

from models import db, Agent, User, CallLog, SAUDI_TZ
from services.api_key_service import api_key_service
from services.api_rate_limiter import api_rate_limiter

logger = logging.getLogger(__name__)

# Create blueprint
api_v1_bp = Blueprint('api_v1', __name__, url_prefix='/api/v1')


# ==================== AUTHENTICATION DECORATOR ====================

def require_api_key(f):
    """
    Decorator to require API key authentication + rate limiting

    Extracts API key from X-API-Key header and validates it.
    Enforces per-user rate limits via Redis.
    Sets g.current_user and rate limit info in g.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask import g

        api_key = request.headers.get('X-API-Key')

        if not api_key:
            logger.warning(f"API request without key from IP: {request.remote_addr}")
            return jsonify({
                'success': False,
                'error': 'API key required',
                'code': 'MISSING_API_KEY'
            }), 401

        user = api_key_service.validate_key(api_key)

        if not user:
            logger.warning(f"Invalid API key attempt from IP: {request.remote_addr}")
            return jsonify({
                'success': False,
                'error': 'Invalid API key',
                'code': 'INVALID_API_KEY'
            }), 401

        # Check if user is approved
        if not user.is_approved:
            return jsonify({
                'success': False,
                'error': 'Account not approved',
                'code': 'ACCOUNT_NOT_APPROVED'
            }), 403

        # ---- Rate Limiting (per-user, Redis-backed) ----
        allowed, remaining, limit, reset_seconds = api_rate_limiter.check_and_increment(user.id)

        # Store rate limit info for response headers
        g.rate_limit = limit
        g.rate_limit_remaining = remaining
        g.rate_limit_reset = reset_seconds

        if not allowed:
            logger.warning(f"Rate limit exceeded for user_id={user.id} from IP: {request.remote_addr}")
            resp = jsonify({
                'success': False,
                'error': 'Rate limit exceeded. Try again later.',
                'code': 'RATE_LIMIT_EXCEEDED',
                'retry_after_seconds': reset_seconds
            })
            resp.headers['Retry-After'] = str(reset_seconds)
            resp.headers['X-RateLimit-Limit'] = str(limit)
            resp.headers['X-RateLimit-Remaining'] = '0'
            resp.headers['X-RateLimit-Reset'] = str(reset_seconds)
            return resp, 429

        # Store user in flask g object for use in route
        g.current_user = user
        return f(*args, **kwargs)

    return decorated_function


@api_v1_bp.after_request
def add_rate_limit_headers(response):
    """Attach rate limit headers to every API v1 response"""
    from flask import g

    if hasattr(g, 'rate_limit'):
        response.headers['X-RateLimit-Limit'] = str(g.rate_limit)
        response.headers['X-RateLimit-Remaining'] = str(g.rate_limit_remaining)
        response.headers['X-RateLimit-Reset'] = str(g.rate_limit_reset)

    response.headers['X-API-Version'] = '1.0'
    return response


# ==================== HELPER FUNCTIONS ====================

def format_phone_number(phone_number: str) -> str:
    """
    Format phone numbers (without + prefix)

    Examples:
        +966501234567 -> 966501234567
        0501234567 -> 966501234567
        966501234567 -> 966501234567
    """
    # Remove all spaces, dashes, parentheses, and + sign
    cleaned = phone_number.strip().replace(' ', '').replace('-', '').replace('(', '').replace(')', '').replace('+', '')

    # Already has country code
    if cleaned.startswith('966') or cleaned.startswith('92') or cleaned.startswith('1'):
        return cleaned

    # Saudi local number starting with 0
    if cleaned.startswith('0'):
        return '966' + cleaned[1:]

    # Assume it's a Saudi local number without 0 prefix
    return '966' + cleaned


async def make_livekit_call(phone_number: str, room_name: str, agent_name: str,
                            outbound_trunk_id: str, agent_id: int = None,
                            webhook_context: dict = None):
    """
    Create a LiveKit room and initiate an outbound call

    Args:
        phone_number: E.164 formatted phone number
        room_name: Unique room name for the call
        agent_name: Name of the agent
        outbound_trunk_id: SIP trunk ID for outbound calls
        agent_id: Agent ID for metadata
        webhook_context: Optional context data to pass to agent
    """
    # Ensure E.164 format with + prefix (Twilio requires it)
    if not phone_number.startswith("+"):
        phone_number = f"+{phone_number}"
    lkapi = api.LiveKitAPI()

    # Create room metadata
    room_metadata = {
        "type": "outbound_api",
        "agent_id": agent_id,
        "phone_number": phone_number,
        "webhook_context": webhook_context  # Can be None or dict
    }

    logger.info(f"Creating SIP call to {phone_number} in room {room_name}")

    # Create SIP participant FIRST - this creates the room
    # Agent will auto-join when room is created (via agent dispatcher)
    sip_participant = await lkapi.sip.create_sip_participant(
        api.CreateSIPParticipantRequest(
            room_name=room_name,
            sip_trunk_id=outbound_trunk_id,
            sip_call_to=phone_number,
            participant_identity="phone_user",
            participant_metadata=json.dumps(room_metadata)
        )
    )

    await lkapi.aclose()


# ==================== API ENDPOINTS ====================

@api_v1_bp.route('/calls/outbound', methods=['POST'])
@require_api_key
def create_outbound_call():
    """
    Initiate an outbound call

    Request:
        Headers:
            X-API-Key: nvx_abc123...

        Body:
            {
                "agent_id": 12,
                "phone_number": "966501234567",
                "context": {                    // optional
                    "customer_name": "Ahmed",
                    "order_id": "ORD-456"
                }
            }

    Response:
        {
            "success": true,
            "call_id": 789,
            "room_name": "api-12-1706789456",
            "status": "initiated"
        }
    """
    from flask import g
    user = g.current_user

    # Parse request body
    data = request.get_json()

    if not data:
        return jsonify({
            'success': False,
            'error': 'Request body required',
            'code': 'MISSING_BODY'
        }), 400

    # Validate required fields
    agent_id = data.get('agent_id')
    phone_number = data.get('phone_number')

    if not agent_id:
        return jsonify({
            'success': False,
            'error': 'agent_id is required',
            'code': 'MISSING_AGENT_ID'
        }), 400

    if not phone_number:
        return jsonify({
            'success': False,
            'error': 'phone_number is required',
            'code': 'MISSING_PHONE_NUMBER'
        }), 400

    # Validate agent belongs to user
    agent = Agent.query.filter_by(id=agent_id, user_id=user.id).first()

    if not agent:
        return jsonify({
            'success': False,
            'error': 'Agent not found or access denied',
            'code': 'AGENT_NOT_FOUND'
        }), 404

    # Check user has minutes
    if user.minutes_balance <= 0:
        return jsonify({
            'success': False,
            'error': 'Insufficient minutes balance',
            'code': 'INSUFFICIENT_MINUTES'
        }), 402

    # Format phone number
    formatted_number = format_phone_number(phone_number)

    # Get outbound trunk
    outbound_trunk_id = user.outbound_trunk_id or os.environ.get('SIP_OUTBOUND_TRUNK_ID')

    if not outbound_trunk_id:
        logger.error(f"No outbound trunk configured for user {user.id}")
        return jsonify({
            'success': False,
            'error': 'Outbound calling not configured. Contact administrator.',
            'code': 'NO_TRUNK_CONFIGURED'
        }), 500

    # Get optional context
    context = data.get('context', {})

    try:
        # Generate room name
        timestamp = datetime.now(SAUDI_TZ).timestamp()
        room_name = f"call-{agent_id}-api-{user.username}-{int(timestamp)}"

        # Make the call
        logger.info(f"API call: user={user.id}, agent={agent.name}, phone={formatted_number}")

        asyncio.run(make_livekit_call(
            phone_number=formatted_number,
            room_name=room_name,
            agent_name=agent.name,
            outbound_trunk_id=outbound_trunk_id,
            agent_id=agent_id,
            webhook_context=context if context else None
        ))

        # Create call log
        call_log = CallLog(
            user_id=user.id,
            agent_id=agent_id,
            from_number=user.outbound_phone_number or os.environ.get('SAUDI_PHONE_NUMBER', 'API'),
            to_number=formatted_number,
            room_name=room_name,
            status='initiated',
            call_type='outbound'
        )

        db.session.add(call_log)
        db.session.commit()

        logger.info(f"API call initiated: call_id={call_log.id}, room={room_name}")

        return jsonify({
            'success': True,
            'call_id': call_log.id,
            'room_name': room_name,
            'status': 'initiated',
            'agent_id': agent_id,
            'phone_number': formatted_number
        }), 200

    except Exception as e:
        logger.error(f"Error initiating API call: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Failed to initiate call',
            'code': 'CALL_FAILED',
            'details': str(e)
        }), 500


@api_v1_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint (no auth required)"""
    return jsonify({
        'status': 'healthy',
        'service': 'NevoxAI API v1',
        'timestamp': datetime.now(SAUDI_TZ).isoformat()
    }), 200


@api_v1_bp.route('/agents', methods=['GET'])
@require_api_key
def list_agents():
    """
    List all agents available to the authenticated user

    Response:
        {
            "success": true,
            "agents": [
                {"id": 1, "name": "Sales Agent", "voice_name": "Fatima"},
                {"id": 2, "name": "Support Agent", "voice_name": "Ahmed"}
            ]
        }
    """
    from flask import g
    user = g.current_user

    agents = Agent.query.filter_by(user_id=user.id).order_by(Agent.name).all()

    return jsonify({
        'success': True,
        'agents': [
            {
                'id': a.id,
                'name': a.name,
                'voice_name': a.voice_name,
                'created_at': a.created_at.isoformat() if a.created_at else None
            }
            for a in agents
        ]
    }), 200


# ==================== UI ROUTES (Settings Page) ====================

from flask import render_template, redirect, url_for, flash, session
from utils.decorators import login_required, approved_required


@api_v1_bp.route('/settings/api-keys', methods=['GET'])
@login_required
@approved_required
def api_keys_page():
    """
    Display API keys management page
    """
    user_id = session['user_id']
    api_key_info = api_key_service.get_key_info(user_id)

    # Check for newly generated key in session
    new_key = session.pop('new_api_key', None)

    return render_template('settings/api_keys.html',
                         api_key_info=api_key_info,
                         new_key=new_key)


@api_v1_bp.route('/settings/api-keys/generate', methods=['POST'])
@login_required
@approved_required
def regenerate_api_key():
    """
    Generate or regenerate API key for current user
    """
    user_id = session['user_id']

    raw_key = api_key_service.create_key_for_user(user_id)

    if raw_key:
        # Store in session to display once
        session['new_api_key'] = raw_key
        flash('API key generated successfully!', 'success')
    else:
        flash('Failed to generate API key. Please try again.', 'error')

    return redirect(url_for('api_v1.api_keys_page'))


@api_v1_bp.route('/settings/api-keys/revoke', methods=['POST'])
@login_required
@approved_required
def revoke_api_key():
    """
    Revoke API key for current user
    """
    user_id = session['user_id']

    if api_key_service.revoke_key(user_id):
        flash('API key revoked successfully.', 'success')
    else:
        flash('No active API key found.', 'warning')

    return redirect(url_for('api_v1.api_keys_page'))
