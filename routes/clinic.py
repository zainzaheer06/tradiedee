"""
Clinic Platform Routes Blueprint — Phase 2 Complete Implementation

Handles:
- GET routes for rendering clinic feature configuration pages
- POST/API routes for saving clinic configurations
- Workflow creation and management

Fully isolated and can be removed by:
1. Delete this file
2. Remove clinic section from base.html sidebar
3. Remove import/registration from routes/__init__.py
4. Run: flask db downgrade (to remove clinic_feature_type, clinic_config fields)
5. Delete services/clinic_service.py
"""

from flask import Blueprint, request, jsonify, render_template, session, flash
from models import db, Agent
from utils.decorators import login_required, approved_required
from services.clinic_service import clinic_service
import logging

logger = logging.getLogger(__name__)

clinic_bp = Blueprint('clinic', __name__, url_prefix='/clinic')


# ==================== GET ROUTES (Render Templates) ====================

@clinic_bp.route('/')
@login_required
@approved_required
def clinic_hub():
    """Clinic platform hub — dashboard with all features"""
    workflows = clinic_service.list_clinic_workflows(session['user_id'])

    # Build status dict for each feature type
    feature_statuses = {}
    for workflow in workflows:
        feature_statuses[workflow.clinic_feature_type] = {
            'configured': True,
            'workflow_id': workflow.id,
            'is_active': workflow.is_active
        }

    return render_template(
        'clinic/clinic_hub.html',
        feature_statuses=feature_statuses
    )


@clinic_bp.route('/appointment-booking')
@login_required
@approved_required
def appointment_booking():
    """Appointment booking configuration page"""
    workflow = clinic_service.get_clinic_workflow(session['user_id'], 'appointment_booking')
    config = clinic_service.get_clinic_config(workflow) if workflow else {}
    agents = Agent.query.filter_by(user_id=session['user_id']).all()

    return render_template(
        'clinic/appointment_booking.html',
        workflow=workflow,
        config=config,
        agents=agents
    )


@clinic_bp.route('/noshow-recovery')
@login_required
@approved_required
def noshow_recovery():
    """No-show recovery configuration page"""
    workflow = clinic_service.get_clinic_workflow(session['user_id'], 'noshow_recovery')
    config = clinic_service.get_clinic_config(workflow) if workflow else {}
    agents = Agent.query.filter_by(user_id=session['user_id']).all()

    return render_template(
        'clinic/noshow_recovery.html',
        workflow=workflow,
        config=config,
        agents=agents
    )


@clinic_bp.route('/patient-reminders')
@login_required
@approved_required
def patient_reminders():
    """Patient reminders configuration page"""
    workflow = clinic_service.get_clinic_workflow(session['user_id'], 'patient_reminders')
    config = clinic_service.get_clinic_config(workflow) if workflow else {}
    agents = Agent.query.filter_by(user_id=session['user_id']).all()

    return render_template(
        'clinic/patient_reminders.html',
        workflow=workflow,
        config=config,
        agents=agents
    )


@clinic_bp.route('/vaccination-campaign')
@login_required
@approved_required
def vaccination_campaign():
    """Vaccination campaign management page"""
    import json

    # Fetch all vaccination campaigns for this user
    campaigns = Workflow.query.filter_by(
        user_id=session['user_id'],
        clinic_feature_type='vaccination_campaign'
    ).all()

    # Parse configs for display
    campaign_data = []
    for campaign in campaigns:
        config = json.loads(campaign.clinic_config) if campaign.clinic_config else {}
        campaign_data.append({
            'id': campaign.id,
            'name': campaign.name,
            'config': config,
            'is_active': campaign.is_active,
            'created_at': campaign.created_at
        })

    agents = Agent.query.filter_by(user_id=session['user_id']).all()

    return render_template(
        'clinic/vaccination_campaign.html',
        campaigns=campaign_data,
        agents=agents
    )


@clinic_bp.route('/new-patient-intake')
@login_required
@approved_required
def new_patient_intake():
    """New patient intake configuration page"""
    workflow = clinic_service.get_clinic_workflow(session['user_id'], 'new_patient_intake')
    config = clinic_service.get_clinic_config(workflow) if workflow else {}
    agents = Agent.query.filter_by(user_id=session['user_id']).all()

    return render_template(
        'clinic/new_patient_intake.html',
        workflow=workflow,
        config=config,
        agents=agents
    )


# ==================== API ROUTES (Form Submissions) ====================

@clinic_bp.route('/api/appointment-booking', methods=['POST'])
@login_required
@approved_required
def save_appointment_booking():
    """Save appointment booking configuration"""
    try:
        data = request.json

        # Build config dict
        config = {
            'agent_id': int(data.get('agent_id', 0)),
            'opening_time': data.get('opening_time', '08:00'),
            'closing_time': data.get('closing_time', '18:00'),
            'operating_days': data.get('operating_days', []),
            'after_hours_voicemail': data.get('after_hours_voicemail', False),
            'send_confirmation_call': data.get('send_confirmation_call', False),
            'confirmation_delay': data.get('confirmation_delay', 0),
            'send_sms_confirmation': data.get('send_sms_confirmation', False),
            'min_advance_hours': int(data.get('min_advance_hours', 2)),
            'max_advance_days': int(data.get('max_advance_days', 30)),
            'default_duration': data.get('default_duration', '30'),
            'pre_call_webhook_url': data.get('pre_call_webhook_url', '').strip() or None,
            'post_call_webhook_url': data.get('post_call_webhook_url', '').strip() or None,
        }

        # Validate
        is_valid, error = clinic_service.validate_clinic_config('appointment_booking', config)
        if not is_valid:
            return jsonify({'error': error}), 400

        # Create/update workflow
        workflow = clinic_service.create_clinic_workflow(
            user_id=session['user_id'],
            feature_type='appointment_booking',
            config_data=config
        )

        return jsonify({
            'success': True,
            'message': 'Appointment booking configured successfully',
            'workflow_id': workflow.id
        }), 200

    except ValueError as e:
        logger.warning(f"Validation error: {e}")
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error saving appointment booking: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'error': 'Failed to save configuration'}), 500


@clinic_bp.route('/api/noshow-recovery', methods=['POST'])
@login_required
@approved_required
def save_noshow_recovery():
    """Save no-show recovery configuration"""
    try:
        data = request.json

        config = {
            'agent_id': int(data.get('agent_id', 0)),
            'trigger_delay': data.get('trigger_delay', 30),
            'max_attempts': int(data.get('max_attempts', 2)),
            'attempt_interval': int(data.get('attempt_interval', 6)),
            'recovery_script': data.get('recovery_script', ''),
            'offer_reschedule': data.get('offer_reschedule', False),
            'capture_reason': data.get('capture_reason', False),
            'escalate_to_staff': data.get('escalate_to_staff', False),
            'escalation_email': data.get('escalation_email', '').strip() or None,
            'pre_call_webhook_url': data.get('pre_call_webhook_url', '').strip() or None,
            'post_call_webhook_url': data.get('post_call_webhook_url', '').strip() or None,
        }

        is_valid, error = clinic_service.validate_clinic_config('noshow_recovery', config)
        if not is_valid:
            return jsonify({'error': error}), 400

        workflow = clinic_service.create_clinic_workflow(
            user_id=session['user_id'],
            feature_type='noshow_recovery',
            config_data=config
        )

        return jsonify({
            'success': True,
            'message': 'No-show recovery configured successfully',
            'workflow_id': workflow.id
        }), 200

    except ValueError as e:
        logger.warning(f"Validation error: {e}")
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error saving no-show recovery: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'error': 'Failed to save configuration'}), 500


@clinic_bp.route('/api/patient-reminders', methods=['POST'])
@login_required
@approved_required
def save_patient_reminders():
    """Save patient reminders configuration"""
    try:
        data = request.json

        config = {
            'agent_id': int(data.get('agent_id', 0)),
            'reminder_times': data.get('reminder_times', []),
            'reminder_script': data.get('reminder_script', ''),
            'language': data.get('language', 'en'),
            'confirm_action': data.get('confirm_action'),
            'reschedule_action': data.get('reschedule_action'),
            'cancel_action': data.get('cancel_action'),
            'pre_call_webhook_url': data.get('pre_call_webhook_url', '').strip() or None,
            'post_call_webhook_url': data.get('post_call_webhook_url', '').strip() or None,
        }

        is_valid, error = clinic_service.validate_clinic_config('patient_reminders', config)
        if not is_valid:
            return jsonify({'error': error}), 400

        workflow = clinic_service.create_clinic_workflow(
            user_id=session['user_id'],
            feature_type='patient_reminders',
            config_data=config
        )

        return jsonify({
            'success': True,
            'message': 'Patient reminders configured successfully',
            'workflow_id': workflow.id
        }), 200

    except ValueError as e:
        logger.warning(f"Validation error: {e}")
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error saving patient reminders: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'error': 'Failed to save configuration'}), 500


@clinic_bp.route('/api/vaccination-campaign', methods=['POST'])
@login_required
@approved_required
def save_vaccination_campaign():
    """Create a new vaccination campaign"""
    try:
        data = request.json
        campaign_name = data.get('campaign_name', '')

        config = {
            'agent_id': int(data.get('agent_id', 0)),
            'campaign_name': campaign_name,
            'campaign_type': data.get('campaign_type', ''),
            'campaign_script': data.get('campaign_script', ''),
            'start_date': data.get('start_date'),
            'end_date': data.get('end_date'),
            'target_group': data.get('target_group'),
            'daily_limit': int(data.get('daily_limit', 50)),
            'post_call_webhook_url': data.get('post_call_webhook_url', '').strip() or None,
        }

        is_valid, error = clinic_service.validate_clinic_config('vaccination_campaign', config)
        if not is_valid:
            return jsonify({'error': error}), 400

        # Use create_campaign method to always create a new campaign
        campaign = clinic_service.create_campaign(
            user_id=session['user_id'],
            campaign_name=campaign_name,
            config_data=config
        )

        return jsonify({
            'success': True,
            'message': f"Campaign '{campaign_name}' created successfully",
            'campaign_id': campaign.id
        }), 201

    except ValueError as e:
        logger.warning(f"Validation error: {e}")
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error creating vaccination campaign: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'error': 'Failed to save campaign'}), 500


@clinic_bp.route('/api/new-patient-intake', methods=['POST'])
@login_required
@approved_required
def save_new_patient_intake():
    """Save new patient intake configuration"""
    try:
        data = request.json

        config = {
            'agent_id': int(data.get('agent_id', 0)),
            'intake_mode': data.get('intake_mode', 'inbound'),
            'fields_to_collect': data.get('fields_to_collect', []),
            'intake_script': data.get('intake_script', ''),
            'hold_music': data.get('hold_music', False),
            'language': data.get('language', 'en'),
            'book_appointment': data.get('book_appointment', False),
            'send_sms_summary': data.get('send_sms_summary', False),
            'notify_doctor': data.get('notify_doctor', False),
            'doctor_email': data.get('doctor_email', '').strip() or None,
            'pre_call_webhook_url': data.get('pre_call_webhook_url', '').strip() or None,
            'post_call_webhook_url': data.get('post_call_webhook_url', '').strip() or None,
        }

        is_valid, error = clinic_service.validate_clinic_config('new_patient_intake', config)
        if not is_valid:
            return jsonify({'error': error}), 400

        workflow = clinic_service.create_clinic_workflow(
            user_id=session['user_id'],
            feature_type='new_patient_intake',
            config_data=config
        )

        return jsonify({
            'success': True,
            'message': 'Patient intake configured successfully',
            'workflow_id': workflow.id
        }), 200

    except ValueError as e:
        logger.warning(f"Validation error: {e}")
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error saving patient intake: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'error': 'Failed to save configuration'}), 500


# ==================== Helper Routes ====================

@clinic_bp.route('/api/status/<feature_type>', methods=['GET'])
@login_required
@approved_required
def get_feature_status(feature_type):
    """Get configuration status for a clinic feature"""
    status = clinic_service.get_clinic_feature_status(session['user_id'], feature_type)
    return jsonify(status), 200
