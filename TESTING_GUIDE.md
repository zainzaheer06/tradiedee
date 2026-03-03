# CallTradie Testing Guide

## Overview
This guide explains how to test the complete CallTradie system including job creation, dashboard, and SMS logging.

---

## Method 1: Python Test Script (Recommended)

### Setup
```bash
cd c:\Users\mzain\Python-projects\Commercial\sophie\nevoxai-project
python test_calltradie.py
```

### What it tests:
1. ✅ **Login** - Authenticates with test credentials
2. ✅ **Business Setup** - Creates a test business profile
3. ✅ **Create Job (Webhook)** - Simulates a completed call
4. ✅ **Job Dashboard** - Verifies job appears on dashboard
5. ✅ **Job Detail Page** - Checks all customer info displays
6. ✅ **Emergency Job** - Tests emergency detection (burst pipe keywords)
7. ✅ **SMS Endpoint** - Tests SMS logging
8. ✅ **Database Verification** - Checks data in database

### Expected Output:
```
============================================================
  CALLTRADIE COMPLETE TEST SUITE
============================================================

✓ Login successful
✓ Business profile created
✓ Job created: ID=123
✓ Job appears on dashboard
✓ Job detail page loaded (Job #123)
✓ Emergency job created: ID=124
✓ SMS endpoint working
✓ Business found in DB: CallTradie Test - Plumbing Services

============================================================
TEST SUMMARY
============================================================
Login: ✓ PASS
Business Setup: ✓ PASS
Create Job (Webhook): ✓ PASS
Job Dashboard: ✓ PASS
Job Detail Page: ✓ PASS
Emergency Job: ✓ PASS
SMS Endpoint: ✓ PASS
Database Queries: ✓ PASS

Results: 8/8 tests passed
✓ All tests passed! CallTradie is working correctly.
```

---

## Method 2: Bash/Curl Script (Quick Test)

### Setup
```bash
cd c:\Users\mzain\Python-projects\Commercial\sophie\nevoxai-project
bash test_calltradie.sh
```

### What it tests:
1. ✅ App is running
2. ✅ Create normal job via webhook
3. ✅ Job appears on dashboard
4. ✅ Job detail page loads
5. ✅ Emergency detection works
6. ✅ SMS endpoint works

### Pros/Cons:
- **Pros**: Quick, no Python dependencies, no login required
- **Cons**: Less detailed, doesn't verify database

---

## Method 3: Manual Browser Testing

### Step 1: Login
Navigate to: `http://localhost:5015/login`
```
Username: example@gmail.com
Password: example@gmail.com
```

### Step 2: Create Business (Setup)
Navigate to: `http://localhost:5015/setup`
- Fill in business name: "Test Plumbing"
- Business type: "plumbing"
- Add emergency contacts
- Click Save

### Step 3: Send Webhook (Create Job)
```bash
curl -X POST http://localhost:5015/webhook/call-ended \
  -H "Content-Type: application/json" \
  -d '{
    "room_name": "test-call-001",
    "duration": 300,
    "transcription": "AGENT: Hello. CUSTOMER: Hi, my name is John Smith. I have a leaking tap at 42 Smith Street, Sydney.",
    "metadata": {
      "messages": [
        {"role": "agent", "text": "Hello"},
        {"role": "user", "text": "Hi, my name is John Smith. I have a leaking tap at 42 Smith Street, Sydney."}
      ],
      "sip_info": {
        "phone_number": "+61412345678",
        "trunk_phone_number": "+61298765432",
        "call_status": "active"
      }
    }
  }'
```

### Step 4: View Job Dashboard
Navigate to: `http://localhost:5015/jobs/`

**Expected to see:**
- Job card with customer name "John Smith"
- Phone number: +61412345678
- Address: 42 Smith Street, Sydney
- Service type: Plumbing
- Status badge: "NEW" (yellow)
- SMS status indicator

### Step 5: View Job Details
Click "View Details" on the job card

**Expected to see:**
- Customer Information section
- Phone (clickable link)
- Full address
- Job Details (leaking tap)
- Scheduling section
- SMS Confirmations section
- Status selector dropdown

---

## Method 4: Emergency Job Test

Send a webhook with emergency keywords:

```bash
curl -X POST http://localhost:5015/webhook/call-ended \
  -H "Content-Type: application/json" \
  -d '{
    "room_name": "emergency-001",
    "duration": 180,
    "transcription": "CUSTOMER: HELP! BURST PIPE at 88 Main Street, Melbourne! Water everywhere!",
    "metadata": {
      "messages": [
        {"role": "user", "text": "HELP! BURST PIPE at 88 Main Street, Melbourne!"}
      ],
      "sip_info": {
        "phone_number": "+61487654321",
        "trunk_phone_number": "+61298765432",
        "call_status": "active"
      }
    }
  }'
```

**Expected to see:**
- Red left border on job card
- 🚨 EMERGENCY badge
- Status shows "NEW" with alert
- On detail page: "Emergency Information" section

---

## Method 5: SMS Test

Test the SMS endpoint directly:

```bash
curl -X POST http://localhost:5015/api/sms/send \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "+61412345678",
    "message": "Hi John! Your service appointment confirmed for Thursday 10am at 42 Smith Street.",
    "job_id": 1
  }'
```

**Expected response:**
```json
{
  "status": "success",
  "sms_id": 1,
  "phone": "+61412345678",
  "message": "SMS queued for delivery"
}
```

---

## Checklist: What Should Work

### Setup Page (`/setup/`)
- [ ] Form displays correctly with Bootstrap styling
- [ ] Can enter business details
- [ ] Can add emergency contacts
- [ ] Can define service areas
- [ ] Save button works

### Jobs Dashboard (`/jobs/`)
- [ ] Page loads without CSS errors
- [ ] Job cards display in 2-column grid (desktop) / 1-column (mobile)
- [ ] Customer name shows
- [ ] Phone number is clickable
- [ ] Address shows completely
- [ ] Status badge displays with correct color
- [ ] Service type badge shows
- [ ] Emergency jobs have red left border
- [ ] 🚨 EMERGENCY badge shows for emergencies
- [ ] SMS status indicator appears
- [ ] "View Details" button works
- [ ] "Call Customer" button is clickable

### Job Detail Page (`/jobs/{id}`)
- [ ] Page loads correctly
- [ ] Customer information section shows all details
- [ ] Phone number is clickable (tel: link)
- [ ] Full address displays
- [ ] Job type shows (plumbing, electrical, etc.)
- [ ] Description shows issue summary
- [ ] Scheduling section shows appointment time
- [ ] Address validation status displays
- [ ] Emergency section shows (if emergency)
- [ ] SMS Confirmations section displays
- [ ] Status dropdown works (can change status)
- [ ] Back to Dashboard button works

### SMS System
- [ ] SMS endpoint accepts POST requests
- [ ] SMS logs are created in database
- [ ] SMS shows in job detail page
- [ ] Message type icon displays (✅ Confirmation, 🔔 Reminder)
- [ ] Status badge shows (Sent, Delivered, Queued, Failed)
- [ ] Timestamp shows when SMS was sent
- [ ] Full message text displays

---

## Debugging

### App not running?
```bash
cd c:\Users\mzain\Python-projects\Commercial\sophie\nevoxai-project
python app.py
# Should start on http://localhost:5015
```

### Login fails?
- Username: `example@gmail.com`
- Password: `example@gmail.com`
- Check browser console for errors (F12)

### Jobs not appearing?
1. Check webhook response - should return `{"job_id": X, "status": "success"}`
2. Check Flask logs for errors
3. Check database: `sqlite3 nevox_ai.db "SELECT * FROM job;"`

### CSS still broken?
- Clear browser cache (Ctrl+Shift+Delete)
- Force refresh (Ctrl+F5)
- Check that Bootstrap CSS loaded: Open DevTools → Network tab → Search for "bootstrap"

### Database issues?
```bash
# Check if tables exist
sqlite3 nevox_ai.db ".tables"

# Check job records
sqlite3 nevox_ai.db "SELECT id, customer_name, customer_phone, status FROM job;"

# Check SMS logs
sqlite3 nevox_ai.db "SELECT id, job_id, message_type, delivery_status FROM sms_log;"
```

---

## Success Criteria

✅ **All tests pass if:**
1. Business can be created in setup
2. Jobs appear on dashboard after webhook
3. Emergency jobs show red border and 🚨 badge
4. Job detail page loads with all customer info
5. SMS endpoint logs messages
6. No CSS styling issues
7. All Bootstrap classes apply correctly

---

## Next Steps

Once testing is complete:
1. ✅ Configure real SMS service (Twilio, AWS SNS)
2. ✅ Add Google Maps API key for address validation
3. ✅ Connect to ServiceM8 for real availability
4. ✅ Set up SMS reminders (24 hours before appointment)
5. ✅ Add technician assignment workflow
6. ✅ Create invoice generation system

---

**Status:** Ready for complete testing! 🚀
