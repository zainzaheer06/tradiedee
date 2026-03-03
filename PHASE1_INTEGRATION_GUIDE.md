# 🔗 Phase 1: Complete Integration & Testing Guide

## What Was Added to Your Codebase

### ✅ Database Models (models.py)
- `Business` - Business configuration and settings
- `Job` - Service jobs/appointments
- `EmergencyEscalationLog` - Emergency routing audit trail
- `SMSLog` - SMS delivery tracking
- `AddressValidationLog` - Address validation history

### ✅ Routes/Blueprints
1. **`routes/jobs.py`** - Job management dashboard & CRUD
2. **`routes/booking.py`** - Appointment booking & availability
3. **`routes/address.py`** - Address validation API
4. **`routes/business_setup.py`** - Business onboarding wizard

All registered in `routes/__init__.py`

### ✅ Frontend Templates
1. **`templates/jobs/dashboard.html`** - Jobs dashboard with filtering
2. **`templates/jobs/detail.html`** - Job details & management
3. **`templates/setup/wizard.html`** - 4-step business setup wizard
4. **`templates/setup/emergency_contacts.html`** - Emergency configuration
5. **`templates/setup/service_areas.html`** - Service areas configuration

### ✅ Integration Files (Already Created Earlier)
- `integrations/serviceM8_api.py` - ServiceM8 API client
- `integrations/address_validator.py` - Google Maps address validation
- `integrations/emergency_handler.py` - Emergency escalation logic

---

## 🚀 Getting Started: 3 Simple Steps

### Step 1: Update Environment Variables

Add to your `.env` file:
```env
# Phase 1 Features - Google Maps
GOOGLE_API_KEY=your-google-maps-api-key

# ServiceM8 (if not already configured)
SERVICEM8_API_KEY=your-serviceM8-api-key
SERVICEM8_CUSTOMER_ID=your-customer-id

# Twilio (if not already configured)
TWILIO_ACCOUNT_SID=your-twilio-sid
TWILIO_AUTH_TOKEN=your-twilio-token
TWILIO_PHONE_NUMBER=+61...
```

### Step 2: Apply Database Migrations

Run the migration:
```bash
python scripts/migrations/phase1_apply_schema.py
```

Expected output:
```
✓ All SQL migrations applied successfully
✓ MIGRATION COMPLETE
✓ All required tables present
✓ All required columns present
```

### Step 3: Test the New Features

Start your Flask app:
```bash
python app.py
```

The application will automatically create the new tables.

---

## 🧪 Testing Each Feature

### Feature 1: Business Setup

**Access:** http://localhost:5000/setup/

**Test Flow:**
1. Click "Business Setup"
2. Fill in business details (name, type, phone)
3. Optionally add ServiceM8 API credentials
4. Add Google Maps API key (optional)
5. Configure emergency contacts
6. Set service areas
7. See jobs dashboard

**Expected:** New business created, no errors

**Database Check:**
```sql
SELECT * FROM business WHERE user_id = 1;
```

---

### Feature 2: Job Creation & Dashboard

**Access:** http://localhost:5000/jobs/

**Test via API:**
```bash
curl -X POST http://localhost:5000/api/booking/create-booking \
  -H "Content-Type: application/json" \
  -d '{
    "business_id": 1,
    "customer": {
      "name": "Test Customer",
      "phone": "+61412345678",
      "email": "test@example.com",
      "address": "42 Smith Street",
      "suburb": "Penrith",
      "postcode": "2750"
    },
    "job": {
      "type": "Burst Pipe",
      "description": "Water leak in kitchen",
      "is_emergency": true,
      "emergency_keywords": ["burst pipe", "water leak"]
    },
    "selected_datetime": "2026-03-05T14:00:00"
  }'
```

**Expected Response:**
```json
{
  "status": "success",
  "job_id": 1,
  "serviceM8_job_id": "SM8-123",
  "message": "Booking confirmed"
}
```

**Frontend Check:**
- Dashboard shows new job
- Job appears in correct status
- Customer info displayed correctly

---

### Feature 3: Address Validation

**Test via API:**
```bash
curl -X POST http://localhost:5000/api/address/validate \
  -H "Content-Type: application/json" \
  -d '{
    "street": "42 Smith Street",
    "suburb": "Penrith",
    "postcode": "2750",
    "state": "NSW"
  }'
```

**Expected Response (Valid):**
```json
{
  "valid": true,
  "formatted_address": "42 Smith Street, Penrith NSW 2750, Australia",
  "coordinates": {
    "lat": -33.7384,
    "lng": 150.6949
  },
  "components": {...}
}
```

**Expected Response (Invalid):**
```json
{
  "valid": false,
  "message": "Address not found",
  "suggestion": null
}
```

**Frontend Check:**
- Address displays correctly in job detail
- Coordinates stored in database
- Validation status shows in UI

---

### Feature 4: Availability Checking

**Test with ServiceM8:**
```bash
curl -X POST http://localhost:5000/api/booking/check-availability \
  -H "Content-Type: application/json" \
  -d '{
    "business_id": 1,
    "days_ahead": 7
  }'
```

**Expected Response:**
```json
{
  "status": "success",
  "available_slots": [
    {
      "datetime": "2026-03-05T10:00:00",
      "display": "Wednesday 05/03 at 10:00 AM",
      "day": "Wednesday",
      "time": "10:00 AM"
    }
  ],
  "total_slots": 15,
  "fallback": false
}
```

**If ServiceM8 Unavailable:**
```json
{
  "status": "error",
  "fallback": true,
  "message": "Calendar service temporarily unavailable"
}
```

---

### Feature 5: Emergency Escalation

**Test Emergency Detection:**
```python
from integrations.emergency_handler import EmergencyKeywordDetector

# Test
transcript = "Hi, I've got a burst pipe and water everywhere!"
is_emergency, keywords = EmergencyKeywordDetector.detect_emergency(transcript)

print(f"Emergency: {is_emergency}")  # True
print(f"Keywords: {keywords}")  # ['burst pipe', 'water']
```

**Database Check:**
```sql
SELECT * FROM emergency_escalation_log ORDER BY created_at DESC;
```

Should show escalation attempts and SMS alerts.

---

## 📋 Complete Testing Checklist

### Database
- [ ] Run migration without errors
- [ ] All new tables created
- [ ] All new columns added to User
- [ ] Foreign key relationships intact

### API Endpoints
- [ ] POST `/api/booking/check-availability` works
- [ ] POST `/api/booking/create-booking` works
- [ ] POST `/api/address/validate` works
- [ ] POST `/api/address/suggest` works
- [ ] GET `/jobs/` loads dashboard
- [ ] GET `/jobs/<id>` loads job detail
- [ ] PUT `/jobs/<id>/status` updates status

### Frontend Templates
- [ ] Job dashboard renders
- [ ] Job detail page renders
- [ ] Setup wizard completes
- [ ] Emergency contacts form works
- [ ] Service areas form works

### Business Logic
- [ ] Job created with all fields
- [ ] Address validation works
- [ ] ServiceM8 sync works (if configured)
- [ ] SMS logging works
- [ ] Status updates work
- [ ] Emergency detection works

### Integration
- [ ] Routes registered in blueprints
- [ ] Models accessible from routes
- [ ] Database transactions working
- [ ] Error handling working
- [ ] Logging functional

---

## 🔌 Integrating with Your AI Agent

### Update Agent Prompt

In your agent configuration (agent.py or similar), add:

```python
PHASE1_SYSTEM_PROMPT = """
You are CallTradie, an AI receptionist for Australian trades businesses.

[Your existing prompt...]

PHASE 1 FEATURES:

1. SCHEDULING
- After capturing customer details, check availability
- Ask: "When would be best for you?"
- Call API: POST /api/booking/check-availability
- Offer available times to customer
- Once confirmed, call: POST /api/booking/create-booking

2. EMERGENCY DETECTION
- Listen for: burst pipe, gas leak, power outage, flooding, emergency, urgent
- If detected: "I'm marking this as urgent. Connecting you to our team."
- Create job with is_emergency=true
- Trigger emergency escalation

3. ADDRESS CAPTURE & VALIDATION
- Ask: "What's the full address?"
- Capture: street, suburb, postcode
- Validate via API: POST /api/address/validate
- If invalid: "Let me confirm that address... Did you mean [suggestion]?"
- Once validated: Proceed to booking

FULL CALL FLOW:
1. Answer call
2. Detect if emergency
3. Capture customer details (name, phone, address)
4. Validate address
5. Understand job type & description
6. Check availability
7. Offer times
8. Confirm booking
9. Create job in system + ServiceM8
10. Send SMS confirmation
"""
```

### Send Job Data to Backend

After call completion, send job data:

```python
import requests

job_data = {
    'business_id': business_id,
    'customer_name': transcript_data['customer_name'],
    'customer_phone': transcript_data['customer_phone'],
    'customer_email': transcript_data.get('customer_email'),
    'customer_address': transcript_data['customer_address'],
    'customer_suburb': transcript_data['customer_suburb'],
    'customer_postcode': transcript_data['customer_postcode'],
    'job_type': transcript_data['job_type'],
    'description': transcript_data['description'],
    'is_emergency': 'emergency' in transcript_data.get('keywords', []),
    'emergency_keywords': transcript_data.get('keywords', []),
    'scheduled_datetime': transcript_data['booking_time'].isoformat(),
    'call_transcript': full_transcript,
    'call_summary': ai_generated_summary,
    'recording_url': recording_url,
    'address_validated': address_validation_result['valid']
}

response = requests.post(
    'http://localhost:5000/jobs/create',
    json=job_data
)
```

---

## 🐛 Troubleshooting

### "Database table doesn't exist"
**Solution:** Run migration again
```bash
python scripts/migrations/phase1_apply_schema.py
```

### "Blueprint not registered"
**Solution:** Check `routes/__init__.py` has all imports and `app.register_blueprint()` calls

### "Google Maps API error"
**Solution:**
1. Check API key in .env
2. Verify Geocoding API is enabled in Google Cloud Console
3. Test with curl:
```bash
curl -X POST http://localhost:5000/api/address/validate \
  -H "Content-Type: application/json" \
  -d '{"street": "42 Smith", "suburb": "Penrith", "postcode": "2750"}'
```

### "ServiceM8 sync fails"
**Solution:**
1. Verify API key and customer ID
2. Test with:
```python
from integrations.serviceM8_api import ServiceM8Integration
sm8 = ServiceM8Integration(api_key, customer_id)
print(sm8.health_check())  # Should be True
```

### "Job not appearing in dashboard"
**Solution:**
1. Check database: `SELECT * FROM job;`
2. Verify business_id is correct
3. Check browser console for JavaScript errors
4. Verify blueprint is registered: `flask routes` command

---

## 📊 Database Verification

After setup, verify everything is in place:

```sql
-- Check tables exist
SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%job%';
-- Should show: job, job_log, emergency_escalation_log, sms_log, address_validation_log

-- Check business created
SELECT * FROM business WHERE user_id = 1;

-- Check jobs created
SELECT * FROM job WHERE business_id = 1;

-- Check emergency logs
SELECT * FROM emergency_escalation_log;

-- Check SMS logs
SELECT * FROM sms_log;
```

---

## 🎯 Next Steps

1. **Test all features independently** with curl/Postman
2. **Test frontend** by visiting each page
3. **Test end-to-end** from setup wizard to job dashboard
4. **Integrate with AI agent** prompt
5. **Test with real calls** using your voice agent
6. **Monitor logs** for any errors or issues
7. **Deploy** to production with confidence

---

## 📞 Common Integration Points

### AI Agent → Backend
- Call `/jobs/create` to create job
- Call `/api/booking/check-availability` to get slots
- Call `/api/booking/create-booking` to confirm
- Call `/api/address/validate` to validate address

### Backend → Database
- All operations use SQLAlchemy ORM
- Transactions auto-commit
- Cascading deletes on foreign keys

### Frontend → Backend
- All AJAX calls to `/api/*` endpoints
- HTML forms use standard POST
- Real-time updates via JavaScript

### Feature Flags
```python
# In routes, check if feature enabled
if business.serviceM8_enabled:
    # Use ServiceM8
else:
    # Use fallback
```

---

## ✅ Deployment Checklist

Before going to production:

- [ ] All environment variables set
- [ ] Database migrations applied
- [ ] Integration files present
- [ ] Routes registered
- [ ] Templates in place
- [ ] All features tested
- [ ] AI agent prompt updated
- [ ] Error handling in place
- [ ] Logging configured
- [ ] API keys are secure
- [ ] Database backed up

---

## 🎉 You're Ready!

All Phase 1 features are now integrated into your Nevox application:

✅ Models
✅ Routes
✅ APIs
✅ Frontend
✅ Integration files
✅ Testing guides

Follow the testing checklist, deploy with confidence, and start capturing those emergency jobs! 🚀
