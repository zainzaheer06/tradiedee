"""
Address Validation Routes - Phase 1 Feature
Validates and corrects customer addresses using Google Maps
"""

import logging
import os
from flask import Blueprint, request, jsonify

from models import db, AddressValidationLog, Job, Business
from integrations.address_validator import AddressValidator

logger = logging.getLogger(__name__)

address_bp = Blueprint('address', __name__, url_prefix='/api/address')


# ============================================================================
# VALIDATE ADDRESS
# ============================================================================

@address_bp.route('/validate', methods=['POST'])
def validate_address():
    """
    Validate address using Google Maps
    Called during job creation to verify customer address
    """
    try:
        data = request.json

        street = data.get('street', '').strip()
        suburb = data.get('suburb', '').strip()
        postcode = data.get('postcode', '').strip()
        state = data.get('state', 'NSW').strip().upper()
        job_id = data.get('job_id')

        # Validate inputs
        if not street or not suburb:
            return jsonify({
                'valid': False,
                'message': 'Street address and suburb are required'
            }), 400

        # Initialize validator
        google_api_key = os.environ.get('GOOGLE_API_KEY')
        if not google_api_key:
            logger.warning("Google API key not configured, skipping validation")
            return jsonify({
                'valid': None,
                'message': 'Address validation unavailable',
                'fallback': True
            }), 200

        validator = AddressValidator(google_api_key)

        # Validate address
        result = validator.validate_address(street, suburb, postcode, state)

        # Log validation attempt if job_id provided
        if job_id:
            try:
                validation_log = AddressValidationLog(
                    job_id=job_id,
                    input_address=f"{street}, {suburb} {postcode}",
                    validated_address=result.get('formatted_address'),
                    validation_status='validated' if result.get('valid') else 'invalid',
                    coordinates=result.get('coordinates')
                )
                db.session.add(validation_log)
                db.session.commit()
            except Exception as log_error:
                logger.error(f"Error logging validation: {str(log_error)}")

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error validating address: {str(e)}")
        return jsonify({
            'valid': None,
            'error': str(e),
            'fallback': True
        }), 500


# ============================================================================
# SUGGEST ADDRESS CORRECTIONS
# ============================================================================

@address_bp.route('/suggest', methods=['POST'])
def suggest_address():
    """
    Suggest corrected address based on input
    Used when address validation fails
    """
    try:
        data = request.json
        partial_address = data.get('address', '').strip()

        if not partial_address:
            return jsonify({'error': 'Address required'}), 400

        google_api_key = os.environ.get('GOOGLE_API_KEY')
        if not google_api_key:
            return jsonify({
                'suggestion': None,
                'message': 'Address service unavailable'
            }), 200

        validator = AddressValidator(google_api_key)
        suggestion = validator.suggest_address(partial_address + ", Australia")

        return jsonify({
            'suggestion': suggestion,
            'found': suggestion is not None
        })

    except Exception as e:
        logger.error(f"Error suggesting address: {str(e)}")
        return jsonify({
            'suggestion': None,
            'error': str(e)
        }), 500


# ============================================================================
# VALIDATE SUBURB
# ============================================================================

@address_bp.route('/validate-suburb', methods=['POST'])
def validate_suburb():
    """
    Check if suburb exists in given state
    """
    try:
        data = request.json
        suburb = data.get('suburb', '').strip()
        state = data.get('state', 'NSW').strip().upper()

        if not suburb:
            return jsonify({'error': 'Suburb required'}), 400

        google_api_key = os.environ.get('GOOGLE_API_KEY')
        if not google_api_key:
            return jsonify({'valid': None, 'fallback': True}), 200

        validator = AddressValidator(google_api_key)
        result = validator.validate_suburb(suburb, state)

        return jsonify({
            'valid': result is not None,
            'suburb': suburb,
            'state': state,
            'coordinates': result.get('coordinates') if result else None
        })

    except Exception as e:
        logger.error(f"Error validating suburb: {str(e)}")
        return jsonify({'valid': None, 'error': str(e)}), 500


# ============================================================================
# VALIDATE POSTCODE
# ============================================================================

@address_bp.route('/validate-postcode', methods=['POST'])
def validate_postcode():
    """
    Check if postcode is valid for given state
    """
    try:
        data = request.json
        postcode = data.get('postcode', '').strip()
        state = data.get('state', 'NSW').strip().upper()

        google_api_key = os.environ.get('GOOGLE_API_KEY')
        if not google_api_key:
            return jsonify({'valid': None, 'fallback': True}), 200

        validator = AddressValidator(google_api_key)
        result = validator.validate_postcode(postcode, state)

        return jsonify({
            'valid': result is not None,
            'postcode': postcode,
            'state': state
        })

    except Exception as e:
        logger.error(f"Error validating postcode: {str(e)}")
        return jsonify({'valid': None, 'error': str(e)}), 500


# ============================================================================
# GET COORDINATES FOR ADDRESS
# ============================================================================

@address_bp.route('/coordinates', methods=['POST'])
def get_coordinates():
    """
    Get latitude/longitude for suburb for mapping
    """
    try:
        data = request.json
        suburb = data.get('suburb', '').strip()
        state = data.get('state', 'NSW').strip().upper()

        google_api_key = os.environ.get('GOOGLE_API_KEY')
        if not google_api_key:
            return jsonify({'coordinates': None, 'fallback': True}), 200

        validator = AddressValidator(google_api_key)
        coords = validator.get_coordinates(suburb, state)

        return jsonify({
            'coordinates': coords,
            'suburb': suburb,
            'state': state
        })

    except Exception as e:
        logger.error(f"Error getting coordinates: {str(e)}")
        return jsonify({'coordinates': None, 'error': str(e)}), 500


# ============================================================================
# UPDATE JOB ADDRESS VALIDATION
# ============================================================================

@address_bp.route('/update-job/<int:job_id>', methods=['PUT'])
def update_job_address(job_id):
    """
    Update job record with validated address
    """
    try:
        data = request.json
        job = Job.query.get(job_id)

        if not job:
            return jsonify({'error': 'Job not found'}), 404

        # Update address fields
        if data.get('validated_address'):
            job.customer_address = data.get('validated_address')

        if data.get('coordinates'):
            job.address_coordinates = data.get('coordinates')

        job.address_validated = data.get('address_validated', False)
        job.address_validation_status = data.get('validation_status', 'pending')

        db.session.commit()

        logger.info(f"Job #{job_id} address updated and validated")

        return jsonify({
            'status': 'success',
            'job_id': job_id,
            'message': 'Address updated successfully'
        })

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating job address: {str(e)}")
        return jsonify({'error': str(e)}), 500
