"""
Booking Routes - Phase 1 Feature
Handles appointment booking and availability checking
"""

import logging
from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
import os

from models import db, Job, Business
from integrations.serviceM8_api import ServiceM8Integration

logger = logging.getLogger(__name__)

booking_bp = Blueprint('booking', __name__, url_prefix='/api/booking')


# ============================================================================
# CHECK AVAILABILITY
# ============================================================================

@booking_bp.route('/check-availability', methods=['POST'])
def check_availability():
    """
    Check available time slots from ServiceM8
    Called by AI agent during call
    """
    try:
        data = request.json
        business_id = data.get('business_id')
        days_ahead = data.get('days_ahead', 7)

        # Get business
        business = Business.query.get(business_id)
        if not business:
            return jsonify({'error': 'Business not found'}), 404

        if not business.serviceM8_enabled:
            return jsonify({
                'error': 'ServiceM8 not configured',
                'fallback': True,
                'message': 'Availability check unavailable, booking with confirmation'
            }), 400

        # Check ServiceM8
        try:
            sm8 = ServiceM8Integration(
                business.serviceM8_api_key,
                business.serviceM8_customer_id,
                timeout=10
            )

            # Get available slots
            slots = sm8.get_available_slots(days_ahead=days_ahead)

            if slots is None:
                # API error - return fallback
                return jsonify({
                    'status': 'error',
                    'fallback': True,
                    'message': 'Calendar service temporarily unavailable',
                    'backup_phone': business.backup_business_phone,
                    'backup_name': business.backup_business_name
                }), 200  # Return 200 with fallback info

            # Format slots for display
            formatted_slots = [
                {
                    'datetime': slot.isoformat(),
                    'display': slot.strftime('%A %d/%m at %I:%M %p'),
                    'day': slot.strftime('%A'),
                    'time': slot.strftime('%I:%M %p'),
                }
                for slot in slots[:5]  # Return first 5 slots
            ]

            logger.info(f"Found {len(formatted_slots)} available slots for business {business_id}")

            return jsonify({
                'status': 'success',
                'available_slots': formatted_slots,
                'total_slots': len(slots),
                'fallback': False
            })

        except Exception as sm8_error:
            logger.error(f"ServiceM8 API error: {str(sm8_error)}")
            # Return fallback response
            return jsonify({
                'status': 'error',
                'fallback': True,
                'message': 'Unable to check calendar, proceeding with confirmation',
                'backup_phone': business.backup_business_phone,
                'backup_name': business.backup_business_name
            }), 200

    except Exception as e:
        logger.error(f"Error checking availability: {str(e)}")
        return jsonify({
            'status': 'error',
            'error': str(e),
            'fallback': True
        }), 500


# ============================================================================
# CREATE BOOKING
# ============================================================================

@booking_bp.route('/create-booking', methods=['POST'])
def create_booking():
    """
    Create booking in ServiceM8 and create Job record
    """
    try:
        data = request.json
        business_id = data.get('business_id')

        # Get business
        business = Business.query.get(business_id)
        if not business:
            return jsonify({'error': 'Business not found'}), 404

        customer_data = data.get('customer', {})
        job_details = data.get('job', {})
        selected_datetime = data.get('selected_datetime')

        if not selected_datetime:
            return jsonify({'error': 'Datetime required'}), 400

        # Convert to datetime
        scheduled_dt = datetime.fromisoformat(selected_datetime)

        # Try to sync with ServiceM8
        serviceM8_job_id = None
        serviceM8_sync_status = 'pending'

        if business.serviceM8_enabled:
            try:
                sm8 = ServiceM8Integration(
                    business.serviceM8_api_key,
                    business.serviceM8_customer_id
                )

                serviceM8_job_id = sm8.create_job(customer_data, {
                    **job_details,
                    'scheduled_datetime': scheduled_dt
                })

                serviceM8_sync_status = 'synced' if serviceM8_job_id else 'failed'

            except Exception as sm8_error:
                logger.error(f"ServiceM8 sync failed: {str(sm8_error)}")
                serviceM8_sync_status = 'failed'

        # Create Job record
        job = Job(
            business_id=business_id,
            customer_name=customer_data.get('name', ''),
            customer_phone=customer_data.get('phone', ''),
            customer_email=customer_data.get('email'),
            customer_address=customer_data.get('address', ''),
            customer_suburb=customer_data.get('suburb', ''),
            customer_postcode=customer_data.get('postcode', ''),
            job_type=job_details.get('type', ''),
            description=job_details.get('description', ''),
            scheduled_datetime=scheduled_dt,
            status='scheduled',
            is_emergency=job_details.get('is_emergency', False),
            emergency_keywords_detected=job_details.get('emergency_keywords'),
            address_validated=job_details.get('address_validated', False),
            address_coordinates=job_details.get('address_coordinates'),
            serviceM8_job_id=serviceM8_job_id,
            serviceM8_sync_status=serviceM8_sync_status,
            booking_confirmed_at=datetime.now()
        )

        db.session.add(job)
        db.session.commit()

        logger.info(f"Booking created: Job #{job.id}, ServiceM8 ID: {serviceM8_job_id}")

        return jsonify({
            'status': 'success',
            'job_id': job.id,
            'serviceM8_job_id': serviceM8_job_id,
            'scheduled_datetime': scheduled_dt.isoformat(),
            'message': 'Booking confirmed'
        }), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating booking: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# CHECK SPECIFIC TIME AVAILABILITY
# ============================================================================

@booking_bp.route('/check-time', methods=['POST'])
def check_time_availability():
    """Check if a specific time is available"""
    try:
        data = request.json
        business_id = data.get('business_id')
        proposed_datetime = datetime.fromisoformat(data.get('datetime'))

        business = Business.query.get(business_id)
        if not business or not business.serviceM8_enabled:
            return jsonify({
                'available': True,  # Assume available if can't check
                'fallback': True
            })

        sm8 = ServiceM8Integration(
            business.serviceM8_api_key,
            business.serviceM8_customer_id
        )

        is_available = sm8.is_available(proposed_datetime)

        return jsonify({
            'available': is_available if is_available is not None else True,
            'fallback': is_available is None
        })

    except Exception as e:
        logger.error(f"Error checking time: {str(e)}")
        return jsonify({'available': True, 'fallback': True}), 200


# ============================================================================
# GET BOOKING DETAILS
# ============================================================================

@booking_bp.route('/job/<int:job_id>', methods=['GET'])
def get_booking(job_id):
    """Get booking/job details"""
    try:
        job = Job.query.get(job_id)
        if not job:
            return jsonify({'error': 'Job not found'}), 404

        return jsonify({
            'status': 'success',
            'job': {
                'id': job.id,
                'customer_name': job.customer_name,
                'customer_phone': job.customer_phone,
                'customer_address': job.customer_address,
                'job_type': job.job_type,
                'description': job.description,
                'scheduled_datetime': job.scheduled_datetime.isoformat() if job.scheduled_datetime else None,
                'status': job.status,
                'is_emergency': job.is_emergency,
                'serviceM8_job_id': job.serviceM8_job_id,
            }
        })

    except Exception as e:
        logger.error(f"Error getting booking: {str(e)}")
        return jsonify({'error': str(e)}), 500
