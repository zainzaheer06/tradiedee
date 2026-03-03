# Clinic Platform — Phase 2 Implementation Guide

This guide shows how to implement the backend for the clinic platform templates you just built.

## Architecture Overview

```
User fills out clinic config form
    ↓
POST /clinic/[feature-name]
    ↓
Clinic service creates/updates Workflow record
    ↓
n8n URLs saved in Workflow.pre_call_webhook_url & Workflow.webhook_url
    ↓
AI Agent triggered → calls n8n webhooks → updates HMS
```

---

## Phase 2 Tasks (In Order)

### **Task 1: Extend Workflow Model**

**File:** `models.py`

Add these fields to the `Workflow` class:

```python
class Workflow(db.Model):
    # ... existing fields ...

    # NEW: Clinic-specific fields
    clinic_feature_type = db.Column(db.String(50), nullable=True)
    # Values: 'appointment_booking', 'noshow_recovery', 'patient_reminders',
    #         'vaccination_campaign', 'new_patient_intake'

    clinic_config = db.Column(db.JSON, nullable=True)
    # Stores feature-specific config as JSON, e.g.:
    # {
    #   "booking_hours": {"start": "08:00", "end": "18:00"},
    #   "operating_days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
    #   "agent_id": 123,
    #   "min_advance_hours": 2,
    #   "max_advance_days": 30
    # }
```

**Migration command:**
```bash
flask db migrate -m "Add clinic feature fields to Workflow"
flask db upgrade
```

---

### **Task 2: Create Clinic Service**

**File:** `services/clinic_service.py` (NEW)

```python
"""
Clinic service — handles clinic feature configuration and workflow creation
"""
import json
from datetime import datetime
from models import db, Workflow, Agent, SAUDI_TZ
from services.webhook_service import webhook_service

class ClinicService:
    """Manages clinic feature workflows"""

    @staticmethod
    def create_clinic_workflow(user_id, feature_type, config_data):
        """
        Create or update a clinic feature workflow

        Args:
            user_id: User creating the workflow
            feature_type: 'appointment_booking', 'noshow_recovery', etc.
            config_data: Dict with clinic-specific config + webhook URLs

        Returns:
            Workflow object
        """
        # Validate agent exists
        agent_id = config_data.get('agent_id')
        agent = Agent.query.filter_by(id=agent_id, user_id=user_id).first()
        if not agent:
            raise ValueError('Agent not found')

        # Check if workflow already exists for this feature
        workflow = Workflow.query.filter_by(
            user_id=user_id,
            clinic_feature_type=feature_type
        ).first()

        # Extract webhook URLs from config
        pre_call_url = config_data.pop('pre_call_webhook_url', None)
        post_call_url = config_data.pop('post_call_webhook_url', None)

        # If no URLs provided, generate placeholder (Phase 2 enhancement)
        if not post_call_url:
            post_call_url = f"https://n8n.yourdomain.com/webhook/{feature_type}/post"

        if not workflow:
            # Create new workflow
            workflow = Workflow(
                user_id=user_id,
                name=f"{feature_type.replace('_', ' ').title()} Workflow",
                clinic_feature_type=feature_type,
                webhook_url=post_call_url,
                pre_call_webhook_url=pre_call_url,
                pre_call_enabled=bool(pre_call_url),
                post_call_enabled=True,
                api_key=webhook_service.generate_api_key(),
                clinic_config=json.dumps(config_data),
                is_active=True
            )
            db.session.add(workflow)
        else:
            # Update existing workflow
            workflow.webhook_url = post_call_url
            workflow.pre_call_webhook_url = pre_call_url
            workflow.pre_call_enabled = bool(pre_call_url)
            workflow.clinic_config = json.dumps(config_data)
            workflow.updated_at = datetime.now(SAUDI_TZ).replace(tzinfo=None)

        db.session.commit()
        return workflow

    @staticmethod
    def get_clinic_workflow(user_id, feature_type):
        """Get clinic feature workflow"""
        return Workflow.query.filter_by(
            user_id=user_id,
            clinic_feature_type=feature_type
        ).first()

    @staticmethod
    def get_clinic_config(workflow):
        """Parse clinic_config JSON from workflow"""
        if workflow.clinic_config:
            return json.loads(workflow.clinic_config)
        return {}

    @staticmethod
    def delete_clinic_workflow(user_id, feature_type):
        """Delete clinic feature workflow"""
        workflow = Workflow.query.filter_by(
            user_id=user_id,
            clinic_feature_type=feature_type
        ).first()

        if workflow:
            db.session.delete(workflow)
            db.session.commit()
            return True
        return False

# Singleton instance
clinic_service = ClinicService()
```

---

### **Task 3: Update Clinic Routes to Handle Form Submissions**

**File:** `routes/clinic.py` (REPLACE existing file)

```python
"""
Clinic Platform Routes Blueprint — Phase 2 (with backend wiring)
"""

from flask import Blueprint, request, jsonify, render_template, session
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
    """Clinic platform hub"""
    return render_template('clinic/clinic_hub.html')


@clinic_bp.route('/appointment-booking')
@login_required
@approved_required
def appointment_booking():
    """Appointment booking configuration"""
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
    """No-show recovery configuration"""
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
    """Patient reminders configuration"""
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
    """Vaccination campaign management"""
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
    """New patient intake configuration"""
    workflow = clinic_service.get_clinic_workflow(session['user_id'], 'new_patient_intake')
    config = clinic_service.get_clinic_config(workflow) if workflow else {}
    agents = Agent.query.filter_by(user_id=session['user_id']).all()

    return render_template(
        'clinic/new_patient_intake.html',
        workflow=workflow,
        config=config,
        agents=agents
    )


# ==================== API ROUTES (Handle Form Submissions) ====================

@clinic_bp.route('/api/appointment-booking', methods=['POST'])
@login_required
@approved_required
def save_appointment_booking():
    """Save appointment booking configuration"""
    try:
        data = request.json

        # Validate required fields
        if not data.get('agent_id'):
            return jsonify({'error': 'Agent is required'}), 400

        # Prepare config
        config = {
            'agent_id': int(data['agent_id']),
            'opening_time': data.get('opening_time', '08:00'),
            'closing_time': data.get('closing_time', '18:00'),
            'operating_days': data.get('operating_days', []),
            'after_hours_voicemail': data.get('after_hours_voicemail', False),
            'send_confirmation_call': data.get('send_confirmation_call', False),
            'confirmation_delay': data.get('confirmation_delay', 0),
            'send_sms_confirmation': data.get('send_sms_confirmation', False),
            'min_advance_hours': data.get('min_advance_hours', 2),
            'max_advance_days': data.get('max_advance_days', 30),
            'default_duration': data.get('default_duration', 30),
            'pre_call_webhook_url': data.get('pre_call_webhook_url'),
            'post_call_webhook_url': data.get('post_call_webhook_url'),
        }

        # Create/update workflow
        workflow = clinic_service.create_clinic_workflow(
            user_id=session['user_id'],
            feature_type='appointment_booking',
            config_data=config
        )

        logger.info(f"Saved appointment booking config (user: {session['user_id']}, workflow: {workflow.id})")

        return jsonify({
            'success': True,
            'message': 'Appointment booking configured successfully',
            'workflow_id': workflow.id
        }), 200

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error saving appointment booking: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@clinic_bp.route('/api/noshow-recovery', methods=['POST'])
@login_required
@approved_required
def save_noshow_recovery():
    """Save no-show recovery configuration"""
    try:
        data = request.json

        if not data.get('agent_id'):
            return jsonify({'error': 'Agent is required'}), 400

        config = {
            'agent_id': int(data['agent_id']),
            'trigger_delay': data.get('trigger_delay', 30),
            'max_attempts': data.get('max_attempts', 2),
            'attempt_interval': data.get('attempt_interval', 6),
            'recovery_script': data.get('recovery_script', ''),
            'offer_reschedule': data.get('offer_reschedule', False),
            'capture_reason': data.get('capture_reason', False),
            'escalate_to_staff': data.get('escalate_to_staff', False),
            'escalation_email': data.get('escalation_email'),
            'pre_call_webhook_url': data.get('pre_call_webhook_url'),
            'post_call_webhook_url': data.get('post_call_webhook_url'),
        }

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

    except Exception as e:
        logger.error(f"Error saving no-show recovery: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@clinic_bp.route('/api/patient-reminders', methods=['POST'])
@login_required
@approved_required
def save_patient_reminders():
    """Save patient reminders configuration"""
    try:
        data = request.json

        if not data.get('agent_id'):
            return jsonify({'error': 'Agent is required'}), 400

        config = {
            'agent_id': int(data['agent_id']),
            'reminder_times': data.get('reminder_times', []),  # e.g., [48, 24, 2] hours
            'reminder_script': data.get('reminder_script', ''),
            'language': data.get('language', 'en'),
            'confirm_action': data.get('confirm_action'),
            'reschedule_action': data.get('reschedule_action'),
            'cancel_action': data.get('cancel_action'),
            'pre_call_webhook_url': data.get('pre_call_webhook_url'),
            'post_call_webhook_url': data.get('post_call_webhook_url'),
        }

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

    except Exception as e:
        logger.error(f"Error saving patient reminders: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@clinic_bp.route('/api/vaccination-campaign', methods=['POST'])
@login_required
@approved_required
def save_vaccination_campaign():
    """Create/update vaccination campaign"""
    try:
        data = request.json

        if not data.get('agent_id'):
            return jsonify({'error': 'Agent is required'}), 400
        if not data.get('campaign_name'):
            return jsonify({'error': 'Campaign name is required'}), 400

        config = {
            'agent_id': int(data['agent_id']),
            'campaign_name': data.get('campaign_name'),
            'campaign_type': data.get('campaign_type'),
            'campaign_script': data.get('campaign_script'),
            'start_date': data.get('start_date'),
            'end_date': data.get('end_date'),
            'target_group': data.get('target_group'),
            'daily_limit': data.get('daily_limit', 50),
            'post_call_webhook_url': data.get('post_call_webhook_url'),
        }

        # For campaigns, create a unique workflow per campaign
        feature_type = f"vaccination_campaign_{data.get('campaign_name', '').replace(' ', '_')}"

        workflow = clinic_service.create_clinic_workflow(
            user_id=session['user_id'],
            feature_type=feature_type,
            config_data=config
        )

        return jsonify({
            'success': True,
            'message': f"Campaign '{data.get('campaign_name')}' created successfully",
            'workflow_id': workflow.id
        }), 201

    except Exception as e:
        logger.error(f"Error creating vaccination campaign: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@clinic_bp.route('/api/new-patient-intake', methods=['POST'])
@login_required
@approved_required
def save_new_patient_intake():
    """Save new patient intake configuration"""
    try:
        data = request.json

        if not data.get('agent_id'):
            return jsonify({'error': 'Agent is required'}), 400

        config = {
            'agent_id': int(data['agent_id']),
            'intake_mode': data.get('intake_mode', 'inbound'),
            'fields_to_collect': data.get('fields_to_collect', []),
            'intake_script': data.get('intake_script', ''),
            'hold_music': data.get('hold_music', False),
            'language': data.get('language', 'en'),
            'book_appointment': data.get('book_appointment', False),
            'send_sms_summary': data.get('send_sms_summary', False),
            'notify_doctor': data.get('notify_doctor', False),
            'doctor_email': data.get('doctor_email'),
            'pre_call_webhook_url': data.get('pre_call_webhook_url'),
            'post_call_webhook_url': data.get('post_call_webhook_url'),
        }

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

    except Exception as e:
        logger.error(f"Error saving patient intake: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
```

---

### **Task 4: Update Templates to Submit Forms**

**File:** `templates/clinic/appointment_booking.html` (Update the save function)

Replace the placeholder JavaScript `saveConfiguration()` function with:

```javascript
async function saveConfiguration() {
    const agent = document.getElementById('agentSelect').value;
    if (!agent) {
        showToast('Please select an agent', 'error');
        return;
    }

    const openingTime = document.querySelector('input[type="time"]').value;
    const closingTime = document.querySelectorAll('input[type="time"]')[1].value;

    const data = {
        agent_id: parseInt(agent),
        opening_time: openingTime,
        closing_time: closingTime,
        operating_days: Array.from(document.querySelectorAll('.day-selected'))
            .map(btn => btn.textContent.trim()),
        after_hours_voicemail: document.getElementById('afterHoursVoicemail').checked,
        send_confirmation_call: document.getElementById('confirmationCall').checked,
        confirmation_delay: document.getElementById('confirmDelay').value,
        send_sms_confirmation: document.getElementById('smsConfirmation').checked,
        min_advance_hours: parseInt(document.getElementById('minAdvance').value),
        max_advance_days: parseInt(document.getElementById('maxAdvance').value),
        default_duration: document.getElementById('duration').value,
        pre_call_webhook_url: document.getElementById('preCallUrl').value,
        post_call_webhook_url: document.getElementById('postCallUrl').value,
    };

    try {
        const response = await fetch('/clinic/api/appointment-booking', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (!response.ok) {
            showToast(result.error || 'Failed to save', 'error');
            return;
        }

        showToast('Configuration saved successfully!', 'success');
        setTimeout(() => {
            window.location.href = '{{ url_for('clinic.clinic_hub') }}';
        }, 1500);
    } catch (error) {
        console.error('Error:', error);
        showToast('Failed to save configuration', 'error');
    }
}
```

**Do the same for the other 4 templates** (noshow_recovery, patient_reminders, vaccination_campaign, new_patient_intake)

---

### **Task 5: Update Clinic Hub to Show Configuration Status**

**File:** `templates/clinic/clinic_hub.html` (Update with Jinja2 logic)

Replace the feature cards with conditional rendering:

```html
<!-- Example: Appointment Booking Card -->
<div class="bg-white rounded-lg border border-gray-200 hover:border-gray-300 transition-all" style="padding:16px 18px; display:flex; flex-direction:column; gap:10px; cursor:pointer;" onclick="window.location='{{ url_for('clinic.appointment_booking') }}'">
    <div style="display:flex; align-items:flex-start; gap:12px;">
        <div style="width:40px; height:40px; border-radius:10px; background:#EEF2FF; display:flex; align-items:center; justify-content:center; flex-shrink:0;">
            <i class="bi bi-calendar2-check" style="font-size:18px; color:#4F46E5;"></i>
        </div>
        <div style="flex:1; min-width:0;">
            <div style="display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:2px;">
                <p style="font-size:13px; font-weight:600; color:var(--t1);">Appointment Booking</p>
                {% if appointment_booking_workflow %}
                    <span class="badge badge-green">Active</span>
                {% else %}
                    <span class="badge badge-gray">Not Configured</span>
                {% endif %}
            </div>
            <p style="font-size:12px; color:var(--t3); line-height:1.4;">Let patients book appointments via AI phone calls 24/7.</p>
        </div>
    </div>
    <a href="{{ url_for('clinic.appointment_booking') }}" class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-700 bg-gray-50 rounded-md hover:bg-gray-100 transition-colors w-fit" style="text-decoration:none;">
        <i class="bi bi-gear" style="font-size:11px;"></i> {% if appointment_booking_workflow %}Edit{% else %}Configure{% endif %}
    </a>
</div>
```

Pass workflow data from the route:

```python
@clinic_bp.route('/')
@login_required
@approved_required
def clinic_hub():
    """Clinic platform hub"""
    appointment_booking_workflow = clinic_service.get_clinic_workflow(
        session['user_id'], 'appointment_booking'
    )
    noshow_recovery_workflow = clinic_service.get_clinic_workflow(
        session['user_id'], 'noshow_recovery'
    )
    # ... get other workflows ...

    return render_template(
        'clinic/clinic_hub.html',
        appointment_booking_workflow=appointment_booking_workflow,
        noshow_recovery_workflow=noshow_recovery_workflow,
        # ... pass other workflows ...
    )
```

---

## Testing Checklist

- [ ] Create an agent (Setup > Agents)
- [ ] Navigate to `/clinic/`
- [ ] Click "Configure" on Appointment Booking
- [ ] Select an agent, fill in the form, paste n8n webhook URLs
- [ ] Click "Save Configuration"
- [ ] Check database: `SELECT * FROM workflow WHERE clinic_feature_type='appointment_booking'`
- [ ] Verify workflow was created with clinic_config JSON
- [ ] Go back to hub, verify it now shows "Active" badge

---

## Key Points

✅ **Clinic features map to Workflow records** — One workflow per feature type
✅ **Config stored in JSON** — Flexible for different feature types
✅ **Pre/post webhooks** — Separate URLs for patient lookup and HMS updates
✅ **Easy to delete** — Clinic code is fully isolated
✅ **Scalable** — Add new features by adding new routes + form templates

---

## Next Steps (Phase 3)

1. **Auto-generate n8n workflows** — Instead of user pasting URLs
2. **Campaign CRUD** — List, edit, delete campaigns from DB
3. **Test buttons** — Send test webhooks to n8n
4. **Analytics** — Show call counts, success rates per feature
5. **Multi-branch support** — Route to different n8n endpoints per branch

---

## Questions?

Message me if you need help with:
- SQLAlchemy JSON field handling
- n8n webhook signature verification
- Campaign multi-record management
- Error handling for HMS API failures
