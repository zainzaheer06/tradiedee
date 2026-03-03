# 🔧 Phase 1: Critical Features Implementation Guide

## Overview
Build 3 critical features to reduce churn and improve reliability:
1. **Scheduling Conflict Prevention** - Real-time availability checking with fallback
2. **Emergency Escalation Path** - Multiple contact routing when technician unavailable
3. **Address Validation** - Capture + validate addresses before booking

---

## Feature 1: Scheduling Conflict Prevention

### Problem
Customer calls, AI books job, but technician is already busy → Customer shows up to empty house → Angry call, negative review, potential churn.

### Solution
- Real-time check ServiceM8 before booking
- If unavailable: Tell customer truthfully ("no slots today, earliest is tomorrow 2pm")
- Have fallback list of nearby competitors to recommend
- Alert owner if overbooking happens anyway (safety net)

### Implementation

#### Database Changes
```python
# Add to Business model
class Business(db.Model):
    # ... existing fields ...

    # Fallback contacts for when fully booked
    backup_business_phone = db.Column(db.String(20), nullable=True)  # Alternative business
    backup_business_name = db.Column(db.String(100), nullable=True)  # Name of backup

    # Availability checking
    availability_check_enabled = db.Column(db.Boolean, default=True)
    availability_check_method = db.Column(db.String(50))  # "serviceM8", "calcom", "manual"
```

#### ServiceM8 Integration Module
```python
# integrations/serviceM8.py

import requests
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class ServiceM8Integration:
    def __init__(self, api_key, customer_id):
        self.api_key = api_key
        self.customer_id = customer_id
        self.base_url = "https://api.service-m8.com/api_1_0"

    def get_available_slots(self, days_ahead=7):
        """
        Get available appointment slots from ServiceM8
        Returns list of available datetime slots
        """
        try:
            # Get all jobs for the next 7 days
            endpoint = f"{self.base_url}/Job.json"
            params = {
                'auth': self.api_key,
                'filter': f'JobDate >= TODAY() AND JobDate <= TODAY(+{days_ahead})',
            }

            response = requests.get(endpoint, params=params, timeout=5)
            response.raise_for_status()
            jobs = response.json()

            # Determine occupied times
            occupied_slots = []
            for job in jobs:
                job_date = datetime.fromisoformat(job['JobDate'])
                # Assume 2-hour slots for simplicity (can be customized)
                occupied_slots.append({
                    'start': job_date,
                    'end': job_date + timedelta(hours=2)
                })

            # Generate available slots (e.g., 9am-5pm, 2-hour slots)
            available_slots = []
            current = datetime.now().replace(hour=9, minute=0, second=0)
            end_time = current + timedelta(days=days_ahead)

            while current < end_time:
                # Skip if slot is occupied
                is_occupied = any(
                    slot['start'] <= current < slot['end']
                    for slot in occupied_slots
                )

                # Skip if outside business hours (9am-5pm) or weekends
                if current.weekday() < 5 and 9 <= current.hour < 17 and not is_occupied:
                    available_slots.append(current)

                current += timedelta(hours=2)

            logger.info(f"Found {len(available_slots)} available slots")
            return available_slots

        except requests.RequestException as e:
            logger.error(f"ServiceM8 availability check failed: {str(e)}")
            return None  # Return None to indicate failure

    def create_job(self, customer_data, job_details):
        """
        Create a job in ServiceM8
        Returns job ID if successful, None if failed
        """
        try:
            endpoint = f"{self.base_url}/Job.json"

            payload = {
                'auth': self.api_key,
                'CompanyName': customer_data['name'],
                'CompanyPhone': customer_data['phone'],
                'CompanyEmail': customer_data.get('email', ''),
                'CompanyAddress': customer_data['address'],
                'CompanySuburb': customer_data['suburb'],
                'CompanyPostcode': customer_data['postcode'],
                'JobDescription': job_details['description'],
                'JobDate': job_details['scheduled_date'].isoformat(),
                'JobNotes': job_details.get('notes', ''),
            }

            response = requests.post(endpoint, json=payload, timeout=5)
            response.raise_for_status()

            job = response.json()
            logger.info(f"Job created in ServiceM8: {job.get('JobID')}")
            return job.get('JobID')

        except requests.RequestException as e:
            logger.error(f"ServiceM8 job creation failed: {str(e)}")
            return None

    def is_available(self, proposed_datetime):
        """
        Quick check if a specific datetime is available
        Returns True if available, False if booked, None if check failed
        """
        slots = self.get_available_slots(days_ahead=1)
        if slots is None:
            return None
        return proposed_datetime in slots

# integrations/__init__.py
from .serviceM8 import ServiceM8Integration
```

#### Agent Prompt Update
```python
# In agent.py or agent configuration

AGENT_SYSTEM_PROMPT = """
You are CallTradie, an AI receptionist for Australian tradies.

...existing prompt...

SCHEDULING RULES:
1. After capturing job details, check availability
2. If slots available: "Great! I have these times available: [list 3-5 slots]. What works for you?"
3. If fully booked today: "We're fully booked today, but I can book you [next available time]. Does that work?"
4. If customer insists on unavailable time: "Unfortunately, [time] is booked. Earliest I can do is [alternative]. Shall I book that?"
5. If you get an availability check error: "I'm having trouble accessing our calendar. Let me take your details and we'll call you back within 1 hour to confirm."

EMERGENCY OVERRIDE:
If customer says "EMERGENCY": Skip availability check, immediately offer to transfer call.
"""
```

#### Real-Time Checking in Flask App
```python
# routes/booking.py

from flask import Blueprint, request, jsonify
from integrations import ServiceM8Integration
import logging

logger = logging.getLogger(__name__)
booking_bp = Blueprint('booking', __name__, url_prefix='/api/booking')

@booking_bp.route('/check-availability', methods=['POST'])
def check_availability():
    """
    Called by agent during call to check availability
    """
    data = request.json
    business_id = data.get('business_id')
    days_ahead = data.get('days_ahead', 7)

    business = Business.query.get(business_id)
    if not business or not business.serviceM8_enabled:
        return jsonify({'error': 'ServiceM8 not configured'}), 400

    try:
        sm8 = ServiceM8Integration(business.serviceM8_api_key, business.serviceM8_customer_id)
        slots = sm8.get_available_slots(days_ahead=days_ahead)

        if slots is None:
            # Availability check failed - return fallback message
            return jsonify({
                'status': 'error',
                'message': 'Calendar check failed',
                'fallback': True,
                'backup_phone': business.backup_business_phone,
                'backup_name': business.backup_business_name
            })

        # Format slots for agent to read
        formatted_slots = [slot.strftime('%A %d/%m at %I:%M %p') for slot in slots[:5]]

        return jsonify({
            'status': 'success',
            'available_slots': formatted_slots,
            'raw_slots': [slot.isoformat() for slot in slots]
        })

    except Exception as e:
        logger.error(f"Availability check error: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e),
            'fallback': True
        }), 500

@booking_bp.route('/book-job', methods=['POST'])
def book_job():
    """
    After customer confirms time, create job in ServiceM8
    """
    data = request.json
    business_id = data['business_id']
    customer_data = data['customer']
    job_details = data['job']
    scheduled_time = data['scheduled_time']

    business = Business.query.get(business_id)
    sm8 = ServiceM8Integration(business.serviceM8_api_key, business.serviceM8_customer_id)

    # Create job
    job_id = sm8.create_job(customer_data, {
        **job_details,
        'scheduled_date': scheduled_time
    })

    if job_id:
        return jsonify({'status': 'success', 'job_id': job_id})
    else:
        return jsonify({'status': 'error', 'message': 'Failed to create job'}), 500
```

---

## Feature 2: Emergency Escalation Path

### Problem
Emergency detected → Call transferred to technician → Technician doesn't answer → Goes to voicemail → Customer calls competitor.

### Solution
Automatic escalation:
1. Try technician #1 (30-second timeout)
2. If no answer → Try technician #2
3. If no answer → Try business owner
4. If all fail → SMS alert to all three with job details

### Implementation

#### Database Changes
```python
# Add to Business model
class Business(db.Model):
    # ... existing fields ...

    emergency_contacts = db.Column(db.JSON, nullable=True)
    # Format: [
    #   {'name': 'John', 'phone': '+61412345678', 'priority': 1},
    #   {'name': 'Sarah', 'phone': '+61412345679', 'priority': 2},
    #   {'name': 'Owner', 'phone': '+61412345680', 'priority': 3}
    # ]

    emergency_escalation_enabled = db.Column(db.Boolean, default=True)
    emergency_transfer_timeout = db.Column(db.Integer, default=30)  # seconds

class EmergencyEscalationLog(db.Model):
    """Track all emergency escalations"""
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'), nullable=False)

    emergency_keywords = db.Column(db.JSON)  # ['burst pipe', 'flooding']

    # Escalation attempts
    contact_1_name = db.Column(db.String(100))
    contact_1_phone = db.Column(db.String(20))
    contact_1_status = db.Column(db.String(20))  # 'not_called', 'ringing', 'answered', 'no_answer'
    contact_1_answered_at = db.Column(db.DateTime, nullable=True)

    contact_2_name = db.Column(db.String(100))
    contact_2_phone = db.Column(db.String(20))
    contact_2_status = db.Column(db.String(20))
    contact_2_answered_at = db.Column(db.DateTime, nullable=True)

    contact_3_name = db.Column(db.String(100))
    contact_3_phone = db.Column(db.String(20))
    contact_3_status = db.Column(db.String(20))
    contact_3_answered_at = db.Column(db.DateTime, nullable=True)

    # SMS fallback
    sms_sent_to = db.Column(db.JSON)  # ['contact1', 'contact2', 'contact3']
    sms_sent_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(SYDNEY_TZ).replace(tzinfo=None))
```

#### Emergency Escalation Module
```python
# integrations/emergency_escalation.py

import asyncio
import logging
from datetime import datetime
from twilio.rest import Client

logger = logging.getLogger(__name__)

class EmergencyEscalation:
    def __init__(self, twilio_client, livekit_client):
        self.twilio = twilio_client
        self.livekit = livekit_client

    async def escalate(self, business, job, emergency_keywords):
        """
        Escalate emergency call through contact hierarchy
        """
        contacts = business.emergency_contacts or []
        if not contacts:
            logger.warning(f"No emergency contacts configured for business {business.id}")
            return None

        # Sort by priority
        contacts = sorted(contacts, key=lambda x: x.get('priority', 999))

        # Log escalation attempt
        log = EmergencyEscalationLog(
            business_id=business.id,
            job_id=job.id,
            emergency_keywords=emergency_keywords,
            contact_1_name=contacts[0].get('name'),
            contact_1_phone=contacts[0].get('phone'),
        )
        if len(contacts) > 1:
            log.contact_2_name = contacts[1].get('name')
            log.contact_2_phone = contacts[1].get('phone')
        if len(contacts) > 2:
            log.contact_3_name = contacts[2].get('name')
            log.contact_3_phone = contacts[2].get('phone')

        db.session.add(log)
        db.session.commit()

        # Try each contact in order
        for idx, contact in enumerate(contacts, 1):
            logger.info(f"Emergency escalation attempt {idx}: {contact['name']}")

            result = await self._try_transfer(
                contact['phone'],
                job,
                timeout=business.emergency_transfer_timeout
            )

            if result == 'answered':
                # Update log
                setattr(log, f'contact_{idx}_status', 'answered')
                setattr(log, f'contact_{idx}_answered_at', datetime.now(SYDNEY_TZ).replace(tzinfo=None))
                db.session.commit()
                logger.info(f"Emergency transferred to {contact['name']}")
                return contact['name']
            else:
                setattr(log, f'contact_{idx}_status', 'no_answer')
                db.session.commit()
                await asyncio.sleep(1)  # Small delay before next attempt

        # All contacts failed - send SMS alert
        await self._send_emergency_sms_alert(business, contacts, job, log)
        return None

    async def _try_transfer(self, phone_number, job, timeout=30):
        """
        Try to transfer call to contact
        Returns 'answered' or 'no_answer'
        """
        try:
            # Make call using Twilio
            call = self.twilio.calls.create(
                to=phone_number,
                from_=job.business.twilio_number,
                url='https://your-domain.com/twilio/emergency-transfer'
            )

            # Wait for answer with timeout
            start = datetime.now()
            while (datetime.now() - start).seconds < timeout:
                call = self.twilio.calls.get(call.sid)
                if call.status == 'in-progress':
                    return 'answered'
                await asyncio.sleep(1)

            return 'no_answer'

        except Exception as e:
            logger.error(f"Transfer attempt failed: {str(e)}")
            return 'no_answer'

    async def _send_emergency_sms_alert(self, business, contacts, job, log):
        """
        Send SMS alert to all contacts when transfer fails
        """
        message = f"""
🚨 EMERGENCY JOB ALERT 🚨

Issue: {job.job_type}
Details: {job.description}
Location: {job.customer_address}, {job.customer_suburb}
Customer: {job.customer_name} - {job.customer_phone}

PLEASE RESPOND ASAP
All technicians unavailable. Please advise.
"""

        for contact in contacts:
            try:
                self.twilio.messages.create(
                    body=message,
                    from_=business.twilio_number,
                    to=contact['phone']
                )
                logger.info(f"Emergency SMS sent to {contact['name']}")
            except Exception as e:
                logger.error(f"Failed to send emergency SMS to {contact['name']}: {str(e)}")

        log.sms_sent_to = [c['name'] for c in contacts]
        log.sms_sent_at = datetime.now(SYDNEY_TZ).replace(tzinfo=None)
        db.session.commit()

# integrations/__init__.py
from .emergency_escalation import EmergencyEscalation
```

#### Agent Prompt Update for Emergency Detection
```python
EMERGENCY_KEYWORDS = [
    'burst pipe', 'leak', 'flooding', 'water damage',
    'gas leak', 'power outage', 'no electricity', 'electrical fire',
    'no hot water', 'urgent', 'emergency', 'asap',
    'right now', 'immediately', 'can\'t wait', 'dangerous'
]

AGENT_SYSTEM_PROMPT += """
EMERGENCY DETECTION:
1. Listen carefully for emergency keywords: {EMERGENCY_KEYWORDS}
2. If detected, say: "I'm marking this as urgent. I'm connecting you directly to our team right now."
3. Trigger emergency escalation (will transfer to technician, owner, or send SMS alert)
4. Do NOT put emergency on hold or schedule for later
5. Even if customer hasn't used word "emergency", if situation sounds urgent (water damage, electrical hazard), treat as emergency
"""
```

---

## Feature 3: Address Validation

### Problem
Customer says address → AI books job → Address is invalid or incomplete → Technician shows up to wrong location.

### Solution
- Require complete address (street + suburb + postcode)
- Validate using Google Maps API
- If invalid, ask for correction before booking
- Auto-suggest corrections for misspellings

### Implementation

#### Database Changes
```python
# Add to Job model
class Job(db.Model):
    # ... existing fields ...

    # Address validation
    address_validated = db.Column(db.Boolean, default=False)
    address_validation_status = db.Column(db.String(20))  # 'pending', 'validated', 'invalid', 'corrected'
    address_components = db.Column(db.JSON)  # Google Maps parsed address
    address_coordinates = db.Column(db.JSON)  # {'lat': -33.xxx, 'lng': 151.xxx}
```

#### Address Validation Module
```python
# integrations/address_validation.py

import logging
from geopy.geocoders import GoogleV3
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable

logger = logging.getLogger(__name__)

class AddressValidator:
    def __init__(self, google_api_key):
        self.geocoder = GoogleV3(api_key=google_api_key, timeout=5)

    def validate_address(self, street, suburb, postcode, state='NSW'):
        """
        Validate address using Google Maps
        Returns:
        {
            'valid': True/False,
            'formatted_address': 'Full validated address',
            'components': {'street': '', 'suburb': '', 'postcode': '', 'state': ''},
            'coordinates': {'lat': -33.xxx, 'lng': 151.xxx},
            'suggestion': 'If invalid, did you mean...'
        }
        """
        try:
            # Build query
            query = f"{street}, {suburb} {postcode} {state}, Australia"

            # Geocode
            location = self.geocoder.geocode(query)

            if location:
                return {
                    'valid': True,
                    'formatted_address': location.address,
                    'coordinates': {
                        'lat': location.latitude,
                        'lng': location.longitude
                    },
                    'components': self._parse_address(location.address)
                }
            else:
                # Try without postcode (might be wrong)
                query_fallback = f"{street}, {suburb} {state}, Australia"
                location = self.geocoder.geocode(query_fallback)

                if location:
                    return {
                        'valid': False,
                        'message': 'Postcode might be wrong',
                        'suggestion': location.address,
                        'coordinates': {
                            'lat': location.latitude,
                            'lng': location.longitude
                        }
                    }
                else:
                    return {
                        'valid': False,
                        'message': 'Address not found. Please check spelling.',
                        'suggestion': None
                    }

        except GeocoderTimedOut:
            logger.error("Address validation timed out")
            return {
                'valid': None,  # Timeout - try again
                'message': 'Address check failed. Taking your details anyway.'
            }
        except Exception as e:
            logger.error(f"Address validation error: {str(e)}")
            return {
                'valid': None,
                'message': 'Address check failed. Taking your details anyway.'
            }

    def _parse_address(self, formatted_address):
        """Parse formatted address into components"""
        parts = formatted_address.split(',')
        return {
            'full': formatted_address,
            'parts_count': len(parts)
        }

# integrations/__init__.py
from .address_validation import AddressValidator
```

#### Agent Prompt Update for Address Capture
```python
AGENT_SYSTEM_PROMPT += """
ADDRESS CAPTURE RULES:
1. Ask: "What's the full street address where you need service?"
2. Wait for customer to provide street number, street name
3. Ask: "What suburb?" (confirm spelling if unclear)
4. Ask: "What's the postcode?" (customer usually knows it)
5. Say: "Let me confirm: [street address], [suburb] [postcode]. Is that correct?"
6. If customer says no: "What should I correct?"
7. Once confirmed, VALIDATE the address before booking
8. If invalid: "I'm getting a validation error. Let me check nearby locations... Did you mean [suggestion]?"
9. Once validated: Proceed to booking

EXAMPLE:
AI: "What's the full street address?"
Customer: "42 Smith Street"
AI: "Got it, 42 Smith Street. What suburb?"
Customer: "Penrith"
AI: "And the postcode?"
Customer: "2750"
AI: "So that's 42 Smith Street, Penrith 2750. Correct?"
Customer: "Yes"
AI: [Validates address] → Booking confirmed!
"""
```

#### Flask Routes for Address Validation
```python
# routes/address.py

from flask import Blueprint, request, jsonify
from integrations import AddressValidator
import logging

logger = logging.getLogger(__name__)
address_bp = Blueprint('address', __name__, url_prefix='/api/address')

@address_bp.route('/validate', methods=['POST'])
def validate_address():
    """
    Validate address during call
    """
    data = request.json

    validator = AddressValidator(os.environ.get('GOOGLE_API_KEY'))

    result = validator.validate_address(
        street=data['street'],
        suburb=data['suburb'],
        postcode=data['postcode'],
        state=data.get('state', 'NSW')
    )

    return jsonify(result)

@address_bp.route('/suggest', methods=['POST'])
def suggest_address():
    """
    If validation fails, suggest nearby addresses
    """
    data = request.json
    query = f"{data['suburb']} {data['postcode']}, NSW, Australia"

    validator = AddressValidator(os.environ.get('GOOGLE_API_KEY'))
    location = validator.geocoder.geocode(query)

    if location:
        return jsonify({
            'suggestion': location.address,
            'coordinates': {
                'lat': location.latitude,
                'lng': location.longitude
            }
        })

    return jsonify({'suggestion': None}), 400
```

---

## Integration Checklist

- [ ] Update `models.py` with new fields
- [ ] Create `integrations/serviceM8.py`
- [ ] Create `integrations/emergency_escalation.py`
- [ ] Create `integrations/address_validation.py`
- [ ] Create `routes/booking.py`
- [ ] Create `routes/address.py`
- [ ] Update agent system prompt with new rules
- [ ] Add environment variables to `.env`
- [ ] Run database migrations
- [ ] Test with live calls
- [ ] Monitor error logs for issues

---

## Environment Variables Needed

```env
# Google Maps API
GOOGLE_API_KEY=your-google-api-key

# ServiceM8 (if not already set)
SERVICEM8_API_KEY=your-serviceM8-key
SERVICEM8_CUSTOMER_ID=your-customer-id

# Twilio (if not already set)
TWILIO_ACCOUNT_SID=your-sid
TWILIO_AUTH_TOKEN=your-token
TWILIO_PHONE_NUMBER=+61...
```

---

## Testing Plan

1. **Scheduling Conflicts:**
   - Call with booked time → AI should say "fully booked"
   - Call with available time → AI books successfully
   - Simulate ServiceM8 downtime → AI should use fallback message

2. **Emergency Escalation:**
   - Say "emergency" → Should transfer to tech #1
   - Simulate tech #1 not answering → Try tech #2
   - Simulate all fail → Should send SMS alerts
   - Check logs to verify escalation path

3. **Address Validation:**
   - Valid address → Should validate and confirm
   - Typo in suburb → Should suggest correction
   - Invalid postcode → Should ask for correction
   - Valid address with wrong postcode → Should correct and proceed
