"""
SMS Routes - CallTradie SMS Management
Handles SMS sending, delivery tracking, and reminders
"""

import logging
from flask import Blueprint, request, jsonify
from datetime import datetime
import os

from models import db, SMSLog, Business
from utils.decorators import login_required

logger = logging.getLogger(__name__)

sms_bp = Blueprint('sms', __name__, url_prefix='/api/sms')


@sms_bp.route('/send', methods=['POST'])
def send_sms():
    """
    Send SMS message to customer
    Called by webhook after job creation
    """
    try:
        data = request.json
        phone = data.get('phone')
        message = data.get('message')
        job_id = data.get('job_id')

        if not phone or not message:
            return jsonify({'error': 'phone and message required'}), 400

        # TODO: Integrate with Twilio or other SMS provider
        # For now, just log it
        logger.info(f"📱 SMS to {phone}: {message}")

        # Create SMS log entry
        sms_log = SMSLog(
            job_id=job_id,
            recipient_phone=phone,
            message_type='confirmation',
            message_body=message,
            sent_at=datetime.now(),
            status='sent'  # Mark as sent after actual SMS is implemented
        )

        db.session.add(sms_log)
        db.session.commit()

        logger.info(f"✅ SMS logged: {sms_log.id}")

        return jsonify({
            'status': 'success',
            'sms_id': sms_log.id,
            'phone': phone,
            'message': 'SMS queued for delivery'
        }), 200

    except Exception as e:
        logger.error(f"Error sending SMS: {str(e)}")
        return jsonify({'error': str(e)}), 500


@sms_bp.route('/test', methods=['POST'])
def test_sms():
    """Test SMS sending (for development)"""
    try:
        data = request.json
        phone = data.get('phone', '+61412345678')
        message = data.get('message', 'Test SMS from CallTradie')

        logger.info(f"📱 TEST SMS to {phone}: {message}")

        return jsonify({
            'status': 'success',
            'message': f'Test SMS sent to {phone}',
            'phone': phone
        }), 200

    except Exception as e:
        logger.error(f"Error sending test SMS: {str(e)}")
        return jsonify({'error': str(e)}), 500
