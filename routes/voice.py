"""
CallTradie Voice System - Inbound Call Handling
Handles the complete conversation flow for job booking
"""

import logging
from datetime import datetime
from flask import Blueprint, request, jsonify, session
from models import db, Business, Job, CallLog, User
from utils.decorators import login_required
from integrations.address_validator import AddressValidator
from integrations.emergency_handler import EmergencyEscalationHandler, EmergencyKeywordDetector
import os

logger = logging.getLogger(__name__)

voice_bp = Blueprint('voice', __name__, url_prefix='/voice')


# ============================================================================
# CONVERSATION STATES
# ============================================================================

CONVERSATION_STATES = {
    'greeting': 'Greeting caller',
    'ask_help': 'Asking what service is needed',
    'understand_service': 'Understanding service type',
    'check_emergency': 'Checking for emergency',
    'collect_details': 'Collecting caller details',
    'offer_times': 'Offering available times',
    'confirm_booking': 'Confirming booking',
    'send_confirmation': 'Sending SMS confirmation',
    'completed': 'Call completed'
}


# ============================================================================
# INBOUND CALL WEBHOOK - Receives calls from phone system
# ============================================================================

@voice_bp.route('/inbound', methods=['POST'])
def inbound_call():
    """
    Webhook endpoint for receiving inbound calls
    Called by phone system (Twilio, etc.) when call comes in
    """
    try:
        # Get call data from phone system
        call_data = request.get_json()
        business_id = call_data.get('business_id')
        phone_number = call_data.get('from_number')

        # Get business config
        business = Business.query.get(business_id)
        if not business:
            return jsonify({'error': 'Business not found'}), 404

        # Create call log
        call_log = CallLog(
            user_id=business.user_id,
            from_number=phone_number,
            to_number=call_data.get('to_number'),
            call_type='inbound',
            status='active',
            created_at=datetime.now()
        )
        db.session.add(call_log)
        db.session.commit()

        # Start conversation
        return start_conversation(business, call_log, phone_number)

    except Exception as e:
        logger.error(f"Error in inbound call: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# CONVERSATION FLOW
# ============================================================================

@voice_bp.route('/start', methods=['POST'])
def start_conversation_route():
    """Start a new conversation with caller"""
    try:
        data = request.get_json()
        business_id = data.get('business_id')
        phone_number = data.get('from_number')

        business = Business.query.get(business_id)
        if not business:
            return jsonify({'error': 'Business not found'}), 404

        # Create call log
        call_log = CallLog(
            user_id=business.user_id,
            from_number=phone_number,
            to_number=data.get('to_number'),
            call_type='inbound',
            status='active'
        )
        db.session.add(call_log)
        db.session.commit()

        return start_conversation(business, call_log, phone_number)

    except Exception as e:
        logger.error(f"Error starting conversation: {str(e)}")
        return jsonify({'error': str(e)}), 500


def start_conversation(business, call_log, phone_number):
    """Start the conversation flow"""
    # Step 1: Greeting
    greeting_text = f"Hello! You've reached {business.business_name}. How can I help you today?"

    return jsonify({
        'status': 'success',
        'call_id': call_log.id,
        'state': 'greeting',
        'message': greeting_text,
        'action': 'listen',
        'business_name': business.business_name
    })


# ============================================================================
# STEP 1: GREETING
# ============================================================================

@voice_bp.route('/greeting', methods=['POST'])
def greeting():
    """Handle greeting response"""
    try:
        data = request.get_json()
        call_id = data.get('call_id')
        caller_response = data.get('transcript', '').lower()

        call_log = CallLog.query.get(call_id)
        if not call_log:
            return jsonify({'error': 'Call not found'}), 404

        # Move to next step
        return ask_service_needed(call_log)

    except Exception as e:
        logger.error(f"Error in greeting: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# STEP 2: ASK SERVICE NEEDED
# ============================================================================

@voice_bp.route('/ask-service', methods=['POST'])
def ask_service_needed(call_log=None):
    """Ask what service the caller needs"""
    try:
        if not call_log:
            data = request.get_json()
            call_log = CallLog.query.get(data.get('call_id'))

        message = "What service do you need today? For example, plumbing repair, electrical work, or emergency?"

        return jsonify({
            'status': 'success',
            'call_id': call_log.id,
            'state': 'ask_help',
            'message': message,
            'action': 'listen'
        })

    except Exception as e:
        logger.error(f"Error asking service: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# STEP 3: UNDERSTAND SERVICE & CHECK EMERGENCY
# ============================================================================

@voice_bp.route('/understand-service', methods=['POST'])
def understand_service():
    """Process service request and check for emergency"""
    try:
        data = request.get_json()
        call_id = data.get('call_id')
        transcript = data.get('transcript', '').lower()

        call_log = CallLog.query.get(call_id)
        if not call_log:
            return jsonify({'error': 'Call not found'}), 404

        business = Business.query.get_by(user_id=call_log.user_id).first()

        # Check for emergency keywords
        emergency_handler = EmergencyHandler()
        is_emergency = emergency_handler.detect_emergency(transcript)

        # Extract service type
        service_type = extract_service_type(transcript)

        if is_emergency:
            return handle_emergency_call(call_log, transcript, service_type)
        else:
            return collect_caller_details(call_log, service_type)

    except Exception as e:
        logger.error(f"Error understanding service: {str(e)}")
        return jsonify({'error': str(e)}), 500


def extract_service_type(transcript):
    """Extract service type from transcript"""
    services = {
        'plumbing': ['plumb', 'pipe', 'water', 'leak', 'drain', 'burst'],
        'electrical': ['electric', 'power', 'wire', 'light', 'switch'],
        'hvac': ['hvac', 'heat', 'cool', 'air', 'conditioning'],
        'gas': ['gas', 'heating'],
        'general': ['repair', 'fix', 'maintenance']
    }

    transcript_lower = transcript.lower()
    for service, keywords in services.items():
        if any(keyword in transcript_lower for keyword in keywords):
            return service

    return 'general'


# ============================================================================
# STEP 4: HANDLE EMERGENCY
# ============================================================================

def handle_emergency_call(call_log, description, service_type):
    """Handle emergency call - immediate escalation"""
    try:
        business = Business.query.filter_by(user_id=call_log.user_id).first()

        # Alert emergency contacts immediately
        emergency_handler = EmergencyHandler()
        escalation = emergency_handler.escalate_emergency(
            business_id=business.id,
            description=description,
            caller_phone=call_log.from_number
        )

        message = "I've detected this is an emergency. Transferring you to the team immediately. Stay on the line."

        return jsonify({
            'status': 'success',
            'call_id': call_log.id,
            'state': 'emergency_escalation',
            'is_emergency': True,
            'message': message,
            'action': 'transfer',
            'transfer_to': business.phone_number,
            'escalation_id': escalation.get('id')
        })

    except Exception as e:
        logger.error(f"Error handling emergency: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# STEP 5: COLLECT CALLER DETAILS
# ============================================================================

@voice_bp.route('/collect-details', methods=['POST'])
def collect_caller_details(call_log=None, service_type=None):
    """Collect caller name, address, phone"""
    try:
        if not call_log:
            data = request.get_json()
            call_log = CallLog.query.get(data.get('call_id'))
            service_type = data.get('service_type', 'general')

        # Start with name
        message = "Let me get some details. What's your name?"

        return jsonify({
            'status': 'success',
            'call_id': call_log.id,
            'state': 'collect_name',
            'message': message,
            'action': 'listen',
            'service_type': service_type
        })

    except Exception as e:
        logger.error(f"Error collecting details: {str(e)}")
        return jsonify({'error': str(e)}), 500


@voice_bp.route('/collect-address', methods=['POST'])
def collect_address():
    """Collect address from caller"""
    try:
        data = request.get_json()
        call_id = data.get('call_id')
        caller_name = data.get('caller_name')
        service_type = data.get('service_type', 'general')

        call_log = CallLog.query.get(call_id)

        message = "What's your address? Just give me the street and suburb."

        return jsonify({
            'status': 'success',
            'call_id': call_id,
            'state': 'collect_address',
            'message': message,
            'action': 'listen',
            'caller_name': caller_name,
            'service_type': service_type
        })

    except Exception as e:
        logger.error(f"Error collecting address: {str(e)}")
        return jsonify({'error': str(e)}), 500


@voice_bp.route('/collect-phone', methods=['POST'])
def collect_phone():
    """Collect phone number"""
    try:
        data = request.get_json()
        call_id = data.get('call_id')
        caller_name = data.get('caller_name')
        address = data.get('address')
        service_type = data.get('service_type', 'general')

        # Validate address
        address_validator = AddressValidator(os.getenv('GOOGLE_API_KEY', 'test'))
        validation_result = address_validator.validate_address(
            street=address,
            suburb='',
            postcode='',
            state='NSW'
        )

        message = f"Thanks! Just to confirm, is your address {validation_result.get('formatted_address', address)}? What's your phone number?"

        return jsonify({
            'status': 'success',
            'call_id': call_id,
            'state': 'collect_phone',
            'message': message,
            'action': 'listen',
            'caller_name': caller_name,
            'address': validation_result.get('formatted_address', address),
            'service_type': service_type
        })

    except Exception as e:
        logger.error(f"Error collecting phone: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# STEP 6: OFFER BOOKING TIMES
# ============================================================================

@voice_bp.route('/offer-times', methods=['POST'])
def offer_booking_times():
    """Offer available booking times"""
    try:
        data = request.get_json()
        call_id = data.get('call_id')
        business_id = data.get('business_id')

        # Get available slots (from ServiceM8 or calendar)
        available_slots = get_available_slots(business_id)

        # Format for voice
        slots_text = format_slots_for_voice(available_slots)

        message = f"We have availability on {slots_text}. Which time works best for you?"

        return jsonify({
            'status': 'success',
            'call_id': call_id,
            'state': 'offer_times',
            'message': message,
            'action': 'listen',
            'available_slots': available_slots
        })

    except Exception as e:
        logger.error(f"Error offering times: {str(e)}")
        return jsonify({'error': str(e)}), 500


def get_available_slots(business_id):
    """Get available time slots for business"""
    # TODO: Integrate with ServiceM8 or calendar
    # For now, return mock data
    return [
        {'datetime': '2026-03-05T10:00:00', 'display': 'Wednesday 10:00 AM'},
        {'datetime': '2026-03-05T14:00:00', 'display': 'Wednesday 2:00 PM'},
        {'datetime': '2026-03-06T09:00:00', 'display': 'Thursday 9:00 AM'},
    ]


def format_slots_for_voice(slots):
    """Format booking slots for voice presentation"""
    if not slots:
        return "tomorrow morning"

    displays = [slot['display'] for slot in slots[:3]]
    if len(displays) == 1:
        return displays[0]
    elif len(displays) == 2:
        return f"{displays[0]} or {displays[1]}"
    else:
        return f"{displays[0]}, {displays[1]}, or {displays[2]}"


# ============================================================================
# STEP 7: CONFIRM BOOKING
# ============================================================================

@voice_bp.route('/confirm-booking', methods=['POST'])
def confirm_booking():
    """Confirm the booking with caller"""
    try:
        data = request.get_json()
        call_id = data.get('call_id')
        business_id = data.get('business_id')
        caller_name = data.get('caller_name')
        address = data.get('address')
        phone_number = data.get('phone_number')
        selected_time = data.get('selected_time')
        service_type = data.get('service_type')

        call_log = CallLog.query.get(call_id)
        business = Business.query.get(business_id)

        # Create job in database
        job = Job(
            business_id=business_id,
            customer_name=caller_name,
            customer_phone=phone_number,
            customer_address=address,
            customer_suburb='',
            customer_postcode='',
            job_type=service_type,
            description=f"Booked via voice call",
            scheduled_datetime=selected_time,
            status='scheduled',
            original_call_id=call_id
        )
        db.session.add(job)
        db.session.commit()

        message = f"Perfect! I've booked {caller_name} for {service_type} on {selected_time}. You'll receive an SMS confirmation shortly. Thank you!"

        return jsonify({
            'status': 'success',
            'call_id': call_id,
            'job_id': job.id,
            'state': 'booking_confirmed',
            'message': message,
            'action': 'proceed'
        })

    except Exception as e:
        logger.error(f"Error confirming booking: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# STEP 8: SEND SMS CONFIRMATION
# ============================================================================

@voice_bp.route('/send-sms', methods=['POST'])
def send_sms_confirmation():
    """Send SMS confirmation to customer"""
    try:
        data = request.get_json()
        job_id = data.get('job_id')
        phone_number = data.get('phone_number')

        job = Job.query.get(job_id)

        sms_text = f"Hi {job.customer_name}! Your {job.job_type} appointment is confirmed for {job.scheduled_datetime}. " \
                   f"Contact us if you need to reschedule."

        # TODO: Send via Twilio
        # send_sms(phone_number, sms_text)

        return jsonify({
            'status': 'success',
            'job_id': job_id,
            'state': 'sms_sent',
            'message': 'SMS confirmation sent',
            'action': 'end_call'
        })

    except Exception as e:
        logger.error(f"Error sending SMS: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# END CALL
# ============================================================================

@voice_bp.route('/end-call', methods=['POST'])
def end_call():
    """End the call and save transcript"""
    try:
        data = request.get_json()
        call_id = data.get('call_id')
        transcript = data.get('transcript', '')
        duration = data.get('duration_seconds', 0)

        call_log = CallLog.query.get(call_id)
        if call_log:
            call_log.transcription = transcript
            call_log.duration_seconds = duration
            call_log.status = 'completed'
            db.session.commit()

        return jsonify({
            'status': 'success',
            'call_id': call_id,
            'message': 'Call ended and saved'
        })

    except Exception as e:
        logger.error(f"Error ending call: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# GET ACTIVE CALLS
# ============================================================================

@voice_bp.route('/active-calls', methods=['GET'])
@login_required
def get_active_calls():
    """Get all active calls for logged-in user's business"""
    try:
        user_id = session.get('user_id')

        # Get user's business
        business = Business.query.filter_by(user_id=user_id).first()
        if not business:
            return jsonify({'calls': []})

        # Get active calls
        active_calls = CallLog.query.filter(
            CallLog.user_id == user_id,
            CallLog.status == 'active'
        ).all()

        calls_data = [{
            'id': call.id,
            'from_number': call.from_number,
            'state': 'in_progress',
            'is_emergency': 'burst' in (call.transcription or '').lower(),
            'duration': 0,
            'created_at': call.created_at
        } for call in active_calls]

        return jsonify({'calls': calls_data})

    except Exception as e:
        logger.error(f"Error getting active calls: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# GET RECENT CALLS
# ============================================================================

@voice_bp.route('/recent-calls', methods=['GET'])
@login_required
def get_recent_calls():
    """Get recent calls for logged-in user's business"""
    try:
        user_id = session.get('user_id')

        # Get calls from last 24 hours
        from datetime import timedelta
        yesterday = datetime.now() - timedelta(hours=24)

        recent_calls = CallLog.query.filter(
            CallLog.user_id == user_id,
            CallLog.created_at >= yesterday
        ).order_by(CallLog.created_at.desc()).limit(20).all()

        calls_data = [{
            'id': call.id,
            'from_number': call.from_number,
            'created_at': call.created_at,
            'duration_seconds': call.duration_seconds or 0,
            'status': call.status,
            'transcription': call.transcription
        } for call in recent_calls]

        return jsonify({'calls': calls_data})

    except Exception as e:
        logger.error(f"Error getting recent calls: {str(e)}")
        return jsonify({'error': str(e)}), 500
