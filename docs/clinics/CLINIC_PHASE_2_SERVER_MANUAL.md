# Clinic Platform Phase 2 — Server-Side Implementation Manual

Complete step-by-step guide to manually implement all backend changes for the clinic platform.

---

## Table of Contents
1. [Database Model Changes](#1-database-model-changes)
2. [Create Migration File](#2-create-migration-file)
3. [Create Clinic Service](#3-create-clinic-service)
4. [Update Routes](#4-update-routes)
5. [Run Migration](#5-run-migration)
6. [Testing Checklist](#6-testing-checklist)

---

## 1. Database Model Changes

### File: `models.py`

**Location:** Find the `Workflow` class (around line 180)

**Current code (before):**
```python
class Workflow(db.Model):
    """User-defined workflows for n8n integration with API key authentication"""
    __tablename__ = 'workflow'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    webhook_url = db.Column(db.String(500), nullable=False)
    api_key = db.Column(db.String(64), nullable=False, unique=True)
    is_active = db.Column(db.Boolean, default=True)

    post_call_enabled = db.Column(db.Boolean, default=True)

    # PRE-call webhook (optional - triggered before call starts to fetch customer data)
    pre_call_enabled = db.Column(db.Boolean, default=False)
    pre_call_webhook_url = db.Column(db.String(500), nullable=True)
    pre_call_timeout = db.Column(db.Integer, default=3)

    # Stats for monitoring
    total_calls = db.Column(db.Integer, default=0)
    successful_calls = db.Column(db.Integer, default=0)
    failed_calls = db.Column(db.Integer, default=0)
    last_triggered_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None), onupdate=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))

    # Relationships
    user = db.relationship('User', backref='workflows')
    agents = db.relationship('Agent', back_populates='workflow')

    def __repr__(self):
        return f'<Workflow {self.name}>'
```

**Change:** Add these 4 lines after `last_triggered_at` field (before `created_at`):

```python
    # Clinic Platform Phase 2 fields
    clinic_feature_type = db.Column(db.String(50), nullable=True)
    # Values: 'appointment_booking', 'noshow_recovery', 'patient_reminders', 'vaccination_campaign', 'new_patient_intake'
    clinic_config = db.Column(db.JSON, nullable=True)
    # Stores feature-specific config as JSON
```

**Final code (after):**
```python
    # Stats for monitoring
    total_calls = db.Column(db.Integer, default=0)
    successful_calls = db.Column(db.Integer, default=0)
    failed_calls = db.Column(db.Integer, default=0)
    last_triggered_at = db.Column(db.DateTime, nullable=True)

    # Clinic Platform Phase 2 fields
    clinic_feature_type = db.Column(db.String(50), nullable=True)
    # Values: 'appointment_booking', 'noshow_recovery', 'patient_reminders', 'vaccination_campaign', 'new_patient_intake'
    clinic_config = db.Column(db.JSON, nullable=True)
    # Stores feature-specific config as JSON

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None), onupdate=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))
```

---

## 2. Create Migration File

### File: `migrations/add_clinic_feature_fields.py` (NEW FILE)

**Create this new file in the migrations folder:**

```python
"""
Add clinic-specific fields to Workflow model for Phase 2 implementation
- clinic_feature_type: categorize workflow by clinic feature (appointment_booking, etc.)
- clinic_config: JSON field to store feature-specific configuration

This migration is part of the Clinic Platform Phase 2 implementation.
It can be safely removed if the clinic feature is deleted.
"""

from alembic import op
import sqlalchemy as sa


def upgrade():
    """Add clinic fields to workflow table"""
    op.add_column('workflow', sa.Column('clinic_feature_type', sa.String(50), nullable=True))
    op.add_column('workflow', sa.Column('clinic_config', sa.JSON, nullable=True))

    # Create index on clinic_feature_type for faster queries
    op.create_index('ix_workflow_clinic_feature_type', 'workflow', ['clinic_feature_type'])


def downgrade():
    """Remove clinic fields from workflow table"""
    op.drop_index('ix_workflow_clinic_feature_type', table_name='workflow')
    op.drop_column('workflow', 'clinic_config')
    op.drop_column('workflow', 'clinic_feature_type')
```

---

## 3. Create Clinic Service

### File: `services/clinic_service.py` (NEW FILE)

**Create this new file in the services folder:**

```python
"""
Clinic Service — Phase 2 Backend

Handles clinic feature configuration and workflow creation.
This service is completely isolated and can be deleted with:
  - Delete this file
  - Remove clinic_feature_type and clinic_config from Workflow model
  - Delete the clinic migration

Dependencies: models.Workflow, models.Agent, webhook_service
"""

import json
import logging
from datetime import datetime
from models import db, Workflow, Agent, SAUDI_TZ
from services.webhook_service import webhook_service

logger = logging.getLogger(__name__)


class ClinicService:
    """Manages clinic feature workflows and configurations"""

    @staticmethod
    def create_clinic_workflow(user_id, feature_type, config_data):
        """
        Create or update a clinic feature workflow.

        Args:
            user_id (int): User ID creating the workflow
            feature_type (str): Clinic feature type
                - 'appointment_booking'
                - 'noshow_recovery'
                - 'patient_reminders'
                - 'vaccination_campaign'
                - 'new_patient_intake'
            config_data (dict): Configuration with:
                - agent_id: required
                - pre_call_webhook_url: optional
                - post_call_webhook_url: optional
                - ... feature-specific fields ...

        Returns:
            Workflow: Created or updated workflow object

        Raises:
            ValueError: If agent not found or required fields missing
        """
        # Validate agent exists
        agent_id = config_data.get('agent_id')
        if not agent_id:
            raise ValueError('Agent ID is required')

        agent = Agent.query.filter_by(id=agent_id, user_id=user_id).first()
        if not agent:
            raise ValueError('Agent not found or does not belong to this user')

        # Extract webhook URLs from config (don't store them in clinic_config)
        pre_call_url = config_data.pop('pre_call_webhook_url', None)
        post_call_url = config_data.pop('post_call_webhook_url', None)

        # Check if workflow already exists for this feature
        workflow = Workflow.query.filter_by(
            user_id=user_id,
            clinic_feature_type=feature_type
        ).first()

        if workflow:
            # Update existing workflow
            workflow.webhook_url = post_call_url or workflow.webhook_url
            workflow.pre_call_webhook_url = pre_call_url
            workflow.pre_call_enabled = bool(pre_call_url)
            workflow.post_call_enabled = True
            workflow.clinic_config = json.dumps(config_data)
            workflow.updated_at = datetime.now(SAUDI_TZ).replace(tzinfo=None)

            logger.info(f"Updated clinic workflow: {feature_type} (workflow_id: {workflow.id}, user: {user_id})")
        else:
            # Create new workflow
            workflow_name = feature_type.replace('_', ' ').title()
            workflow = Workflow(
                user_id=user_id,
                name=workflow_name,
                clinic_feature_type=feature_type,
                webhook_url=post_call_url or f"https://n8n.yourdomain.com/webhook/{feature_type}/post",
                pre_call_webhook_url=pre_call_url,
                pre_call_enabled=bool(pre_call_url),
                post_call_enabled=True,
                api_key=webhook_service.generate_api_key(),
                clinic_config=json.dumps(config_data),
                is_active=True
            )
            db.session.add(workflow)

            logger.info(f"Created clinic workflow: {feature_type} (user: {user_id})")

        db.session.commit()
        return workflow

    @staticmethod
    def get_clinic_workflow(user_id, feature_type):
        """
        Get a clinic feature workflow.

        Args:
            user_id (int): User ID
            feature_type (str): Clinic feature type

        Returns:
            Workflow or None: Workflow if exists, None otherwise
        """
        return Workflow.query.filter_by(
            user_id=user_id,
            clinic_feature_type=feature_type
        ).first()

    @staticmethod
    def get_clinic_config(workflow):
        """
        Parse clinic configuration from workflow.

        Args:
            workflow (Workflow): Workflow object

        Returns:
            dict: Parsed configuration, or empty dict if none
        """
        if not workflow or not workflow.clinic_config:
            return {}

        try:
            return json.loads(workflow.clinic_config)
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"Failed to parse clinic_config for workflow {workflow.id}")
            return {}

    @staticmethod
    def list_clinic_workflows(user_id):
        """
        List all clinic feature workflows for a user.

        Args:
            user_id (int): User ID

        Returns:
            list: List of Workflow objects with clinic features
        """
        return Workflow.query.filter_by(
            user_id=user_id
        ).filter(
            Workflow.clinic_feature_type.isnot(None)
        ).all()

    @staticmethod
    def delete_clinic_workflow(user_id, feature_type):
        """
        Delete a clinic feature workflow.

        Args:
            user_id (int): User ID
            feature_type (str): Clinic feature type

        Returns:
            bool: True if deleted, False if not found
        """
        workflow = Workflow.query.filter_by(
            user_id=user_id,
            clinic_feature_type=feature_type
        ).first()

        if workflow:
            db.session.delete(workflow)
            db.session.commit()
            logger.info(f"Deleted clinic workflow: {feature_type} (workflow_id: {workflow.id}, user: {user_id})")
            return True

        return False

    @staticmethod
    def get_clinic_feature_status(user_id, feature_type):
        """
        Get configuration status for a clinic feature.

        Args:
            user_id (int): User ID
            feature_type (str): Clinic feature type

        Returns:
            dict: Status info with keys:
                - configured (bool): Whether feature is configured
                - workflow_id (int or None): Workflow ID if configured
                - agent_id (int or None): Assigned agent ID
                - last_updated (str or None): ISO format datetime
        """
        workflow = ClinicService.get_clinic_workflow(user_id, feature_type)

        if not workflow:
            return {
                'configured': False,
                'workflow_id': None,
                'agent_id': None,
                'last_updated': None
            }

        config = ClinicService.get_clinic_config(workflow)

        return {
            'configured': True,
            'workflow_id': workflow.id,
            'agent_id': config.get('agent_id'),
            'last_updated': workflow.updated_at.isoformat() if workflow.updated_at else None
        }

    @staticmethod
    def validate_clinic_config(feature_type, config_data):
        """
        Validate clinic configuration data.

        Args:
            feature_type (str): Clinic feature type
            config_data (dict): Configuration to validate

        Returns:
            tuple: (is_valid, error_message)
        """
        # Common validations
        if not config_data.get('agent_id'):
            return False, 'Agent is required'

        try:
            int(config_data['agent_id'])
        except (ValueError, TypeError):
            return False, 'Agent ID must be a number'

        # Feature-specific validations
        if feature_type == 'appointment_booking':
            if config_data.get('min_advance_hours') and config_data.get('max_advance_days'):
                if int(config_data['min_advance_hours']) < 0:
                    return False, 'Minimum advance hours cannot be negative'
                if int(config_data['max_advance_days']) < 1:
                    return False, 'Maximum advance days must be at least 1'

        elif feature_type == 'vaccination_campaign':
            if not config_data.get('campaign_name'):
                return False, 'Campaign name is required'
            if not config_data.get('campaign_type'):
                return False, 'Campaign type is required'

        return True, None


# Singleton instance
clinic_service = ClinicService()
```

---

## 4. Update Routes

### File: `routes/clinic.py`

**Replace the entire file with this content:**

```python
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
    workflow = clinic_service.get_clinic_workflow(session['user_id'], 'vaccination_campaign')
    config = clinic_service.get_clinic_config(workflow) if workflow else {}
    agents = Agent.query.filter_by(user_id=session['user_id']).all()

    return render_template(
        'clinic/vaccination_campaign.html',
        workflow=workflow,
        config=config,
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
    """Create/update vaccination campaign"""
    try:
        data = request.json

        config = {
            'agent_id': int(data.get('agent_id', 0)),
            'campaign_name': data.get('campaign_name', ''),
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

        workflow = clinic_service.create_clinic_workflow(
            user_id=session['user_id'],
            feature_type='vaccination_campaign',
            config_data=config
        )

        return jsonify({
            'success': True,
            'message': f"Campaign '{config['campaign_name']}' created successfully",
            'workflow_id': workflow.id
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
```

---

## 5. Run Migration

After making all the above changes, run the migration:

```bash
# Navigate to project directory
cd /c/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project

# Create migration (if not already done)
flask db migrate -m "Add clinic feature fields to Workflow"

# Apply migration to database
flask db upgrade

# Verify migration worked
flask db current
# Should show: Add clinic feature fields to Workflow
```

---

## 6. Testing Checklist

After implementing all changes:

### ✅ Step 1: Verify Files Exist
- [ ] `migrations/add_clinic_feature_fields.py` — exists
- [ ] `services/clinic_service.py` — exists
- [ ] `routes/clinic.py` — updated with Phase 2 code
- [ ] `models.py` — has clinic fields in Workflow class
- [ ] `templates/clinic/*.html` — all templates have form submission code

### ✅ Step 2: Restart Flask App
```bash
# Stop current Flask server (Ctrl+C)
# Restart it
python app.py
# or
flask run
```

### ✅ Step 3: Test Configuration Flow

1. **Navigate to clinic hub**
   - Go to `http://localhost:5004/clinic/`
   - Should see all 17 clinic features
   - All should show "Not Configured" badge

2. **Create an agent** (if none exists)
   - Setup > Agents > Create Agent
   - Name: "Test Agent"
   - Save and note the agent ID

3. **Configure Appointment Booking**
   - Click "Configure" on Appointment Booking
   - Select the agent you just created
   - Fill in some values:
     - Opening Time: 09:00
     - Closing Time: 17:00
     - Select Mon-Fri
   - Click "Save Configuration"
   - Should see success toast: "Appointment booking configured successfully!"
   - Should redirect to clinic hub

4. **Verify in Database**
   - Open database client (DB Browser or similar)
   - Query: `SELECT * FROM workflow WHERE clinic_feature_type='appointment_booking' AND user_id=<YOUR_USER_ID>;`
   - Should see a row with:
     - clinic_feature_type: `appointment_booking`
     - clinic_config: JSON object with your settings
     - api_key: generated value
     - is_active: 1

5. **Check Hub Status**
   - Return to clinic hub
   - Appointment Booking should now show "Active" badge
   - Button should show "Edit" instead of "Configure"

6. **Test Edit**
   - Click "Edit" on Appointment Booking
   - Form should be pre-filled with saved values
   - Make a change (e.g., change time)
   - Click "Save Configuration"
   - Changes should persist

### ✅ Step 4: Debug If Issues

**404 Error on /clinic/**
- Flask app not restarted? Restart it.
- Blueprint not imported? Check `routes/__init__.py` has clinic import.

**Migration Error**
```bash
# If migration fails, rollback:
flask db downgrade

# Then try again:
flask db upgrade
```

**Form Doesn't Submit**
- Check browser console (F12) for JavaScript errors
- Check network tab to see what response the API returns
- Check Flask logs for server-side errors

**Database Error**
- Ensure migration ran successfully
- Check Workflow table has clinic_feature_type and clinic_config columns:
  ```sql
  PRAGMA table_info(workflow);
  ```

---

## Summary of All Changes

### Files Created:
1. `migrations/add_clinic_feature_fields.py` — DB migration
2. `services/clinic_service.py` — Clinic business logic

### Files Modified:
1. `models.py` — Added clinic fields to Workflow
2. `routes/clinic.py` — Added Phase 2 API endpoints
3. `templates/clinic/*.html` — All 6 templates updated with form submission

### Files Already Updated (Phase 1):
- `routes/__init__.py` — imports clinic_bp
- `templates/base.html` — sidebar includes clinic section

---

## Quick Reference: API Endpoints

```
POST /clinic/api/appointment-booking
POST /clinic/api/noshow-recovery
POST /clinic/api/patient-reminders
POST /clinic/api/vaccination-campaign
POST /clinic/api/new-patient-intake
GET  /clinic/api/status/<feature_type>

GET  /clinic/
GET  /clinic/appointment-booking
GET  /clinic/noshow-recovery
GET  /clinic/patient-reminders
GET  /clinic/vaccination-campaign
GET  /clinic/new-patient-intake
```

---

## Removing Clinic (If Needed)

```bash
# 1. Downgrade database
flask db downgrade

# 2. Delete these files
rm services/clinic_service.py
rm migrations/add_clinic_feature_fields.py
rm -rf templates/clinic/

# 3. Revert models.py (remove clinic fields from Workflow)

# 4. Revert routes/clinic.py (or delete if created fresh)

# 5. Update routes/__init__.py (remove clinic import/registration)

# 6. Update templates/base.html (remove clinic sidebar section)
```
