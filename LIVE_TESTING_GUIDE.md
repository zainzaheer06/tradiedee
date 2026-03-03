# 🚀 LIVE TESTING GUIDE - Phase 1 Complete

## ⚡ Quick Start (5 Minutes to Live Testing)

### Step 1: Setup Environment Variables
```bash
# Open .env and add these (if not already there):
GOOGLE_API_KEY=test-key-or-your-real-key
SERVICEM8_API_KEY=optional
SERVICEM8_CUSTOMER_ID=optional
```

### Step 2: Apply Database Migrations
```bash
python scripts/migrations/phase1_apply_schema.py
```

Expected output:
```
✓ All SQL migrations applied successfully
✓ MIGRATION COMPLETE
✓ All required tables present
```

### Step 3: Start Your Application
```bash
python app.py
```

Expected output:
```
 * Running on http://127.0.0.1:5000
 * Press CTRL+C to quit
```

### Step 4: Open Your Browser

Navigate to: **http://localhost:5000/**

You should see the **CallTradie Phase 1 home page** with:
- Feature overview
- Setup wizard link
- Testing options

---

## 🧪 Live Testing (No External Tools Needed)

### Option A: Use Built-in Testing Dashboard

1. **Login or Sign Up** at http://localhost:5000/login
2. **Go to Testing Dashboard**: http://localhost:5000/test
3. **You can test all APIs directly in the browser**:
   - ✅ Address Validation
   - ✅ Check Availability
   - ✅ Create Job
   - ✅ Get Jobs
   - ✅ Update Job Status
   - ✅ Database Status

### Option B: Manual Setup + Testing

1. **Go to Setup Wizard**: http://localhost:5000/setup/
2. **Fill in Business Details**:
   - Business Name: "Test Plumbing"
   - Business Type: "Plumbing"
   - Phone: "+61412345678"
3. **Click Continue** → Configure Emergency Contacts
4. **Add 3 Emergency Contacts**:
   - Contact 1: John, +61412345678
   - Contact 2: Sarah, +61412345679
   - Contact 3: Owner, +61412345680
5. **Click Continue** → Set Service Areas
6. **Add Service Areas**: Alexandria, Penrith, Parramatta
7. **Click Finish** → See Job Dashboard

---

## 📡 Testing Individual APIs with curl

### Test 1: Address Validation
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

**Expected Response** (Success):
```json
{
  "valid": true,
  "formatted_address": "42 Smith Street, Penrith NSW 2750, Australia",
  "coordinates": {
    "lat": -33.7384,
    "lng": 150.6949
  }
}
```

### Test 2: Check Availability
```bash
curl -X POST http://localhost:5000/api/booking/check-availability \
  -H "Content-Type: application/json" \
  -d '{
    "business_id": 1,
    "days_ahead": 7
  }'
```

**Expected Response**:
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
  "fallback": false
}
```

### Test 3: Create Job
```bash
curl -X POST http://localhost:5000/jobs/create \
  -H "Content-Type: application/json" \
  -d '{
    "business_id": 1,
    "customer_name": "John Smith",
    "customer_phone": "+61412345678",
    "customer_email": "john@example.com",
    "customer_address": "42 Smith Street",
    "customer_suburb": "Penrith",
    "customer_postcode": "2750",
    "job_type": "Burst Pipe",
    "description": "Water is everywhere",
    "scheduled_datetime": "2026-03-05T14:00:00",
    "is_emergency": true,
    "emergency_keywords": ["burst pipe", "water"]
  }'
```

**Expected Response**:
```json
{
  "status": "success",
  "job_id": 1,
  "message": "Job created successfully"
}
```

### Test 4: Get Job Stats
```bash
curl http://localhost:5000/jobs/api/stats
```

**Expected Response**:
```json
{
  "status": "success",
  "total_jobs": 1,
  "today_jobs": 1,
  "completed": 0,
  "emergencies": 1,
  "pending": 1
}
```

### Test 5: Update Job Status
```bash
curl -X PUT http://localhost:5000/jobs/1/status \
  -H "Content-Type: application/json" \
  -d '{
    "status": "in_progress",
    "notes": "Started work"
  }'
```

**Expected Response**:
```json
{
  "status": "success",
  "job_id": 1,
  "new_status": "in_progress"
}
```

---

## 🌐 Browser Testing (Easiest)

### Complete User Journey Test

1. **Start**: http://localhost:5000/
2. **Sign Up**: Click "Sign Up" button
3. **Complete Signup**: Fill email, password
4. **Setup**: Redirects to /setup/
5. **Business Details**: Fill form, click Continue
6. **Emergency Contacts**: Add 3 contacts, click Continue
7. **Service Areas**: Add suburbs, click Done
8. **Dashboard**: See job dashboard at /jobs/
9. **Testing**: Go to /test for API testing

### Each Page Functionality

| Page | URL | What to Test |
|------|-----|--------------|
| Home | `/` | Business status loads |
| Setup Wizard | `/setup/` | 4-step wizard completes |
| Emergency Config | `/setup/emergency` | Emergency contacts save |
| Service Areas | `/setup/service-areas` | Areas save correctly |
| Job Dashboard | `/jobs/` | Shows jobs, filters work |
| Job Detail | `/jobs/1` | Shows job info, can update status |
| Test Dashboard | `/test` | All API tests work |

---

## ✅ Complete Testing Checklist

### Database
- [ ] Run migration without errors
- [ ] Check tables created: `SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%job%';`
- [ ] Check models: `SELECT * FROM business;` (should be empty initially)

### APIs
- [ ] POST `/api/address/validate` returns valid address
- [ ] POST `/api/booking/check-availability` returns slots or fallback
- [ ] POST `/jobs/create` creates job
- [ ] GET `/jobs/api/stats` returns stats
- [ ] PUT `/jobs/{id}/status` updates status

### Frontend
- [ ] Home page loads: http://localhost:5000/
- [ ] Setup wizard completes: http://localhost:5000/setup/
- [ ] Job dashboard loads: http://localhost:5000/jobs/
- [ ] Job detail loads: http://localhost:5000/jobs/1
- [ ] Test dashboard works: http://localhost:5000/test

### End-to-End
- [ ] User signup works
- [ ] Business setup wizard completes
- [ ] Job can be created via API
- [ ] Job appears in dashboard
- [ ] Job status can be updated
- [ ] Stats show correct counts

---

## 🐛 Troubleshooting Live Testing

### Error: "Table doesn't exist"
```
Solution: Run migration again
python scripts/migrations/phase1_apply_schema.py
```

### Error: "Blueprint not found"
```
Solution: Check routes/__init__.py has:
- from .phase1 import phase1_bp
- app.register_blueprint(phase1_bp)
```

### Error: "Template not found"
```
Solution: Check file exists
ls templates/phase1_home.html
ls templates/phase1_test.html
```

### Error: "AttributeError: module has no attribute"
```
Solution: Restart Flask app
Ctrl+C to stop, then python app.py to start again
```

### Error: "Address validation fails"
```
Solution: Check GOOGLE_API_KEY in .env
If not set, address validation will fail gracefully with fallback
```

### Error: "Business not configured"
```
Solution: Complete setup wizard first
Go to http://localhost:5000/setup/ and complete all steps
```

---

## 📊 Database Verification Commands

Use these SQL queries to verify everything is working:

```sql
-- Check Phase 1 tables exist
SELECT name FROM sqlite_master
WHERE type='table'
AND name IN ('business', 'job', 'emergency_escalation_log', 'sms_log', 'address_validation_log');

-- See all businesses
SELECT id, business_name, business_type FROM business;

-- See all jobs
SELECT id, customer_name, job_type, status, is_emergency FROM job;

-- See emergency logs
SELECT * FROM emergency_escalation_log ORDER BY created_at DESC LIMIT 5;

-- See SMS logs
SELECT * FROM sms_log ORDER BY sent_at DESC LIMIT 5;

-- Count jobs by status
SELECT status, COUNT(*) as count FROM job GROUP BY status;

-- Count jobs by emergency
SELECT is_emergency, COUNT(*) as count FROM job GROUP BY is_emergency;
```

---

## 🎯 What to Look For When Testing

### Address Validation Success Indicators
- ✅ Valid address returns `"valid": true`
- ✅ Coordinates returned for mapping
- ✅ Invalid address returns suggestion
- ✅ Google Maps integration working

### Booking Success Indicators
- ✅ Available slots returned
- ✅ Multiple time options shown
- ✅ Slots are in the future
- ✅ Fallback works if API fails

### Job Creation Success Indicators
- ✅ Job appears in database
- ✅ All fields populated correctly
- ✅ Status shows in dashboard
- ✅ Emergency flag set correctly

### Emergency Escalation Success Indicators
- ✅ Keywords detected in description
- ✅ Emergency flag set to true
- ✅ Job marked as high priority
- ✅ Escalation log created

---

## 📈 Performance Metrics to Monitor

While testing, watch these:

```
Address Validation:
- Response time: <2 seconds
- Success rate: 95%+
- Fallback when needed: Yes

Availability Check:
- Response time: <3 seconds
- Slots returned: 5+
- Fallback: Working

Job Creation:
- Response time: <1 second
- Database insert: Immediate
- Fields saved correctly: 100%

Dashboard Load:
- Page load time: <2 seconds
- Stats update: Real-time
- Filtering: Instant
```

---

## 🎬 Live Demo Script

Follow this for a complete live demo:

```
1. Open http://localhost:5000/ (30 sec)
   → Show home page
   → Explain Phase 1 features

2. Signup new user (1 min)
   → Email: test@example.com
   → Password: test123

3. Complete setup (3 min)
   → Business name: "Demo Plumbing"
   → Emergency contacts: 3
   → Service areas: 3 suburbs

4. Create test job (2 min)
   → Go to /test
   → Fill job form
   → Click "Create Job"
   → Show it appears in dashboard

5. Test address validation (1 min)
   → Test valid address
   → Test invalid address
   → Show auto-correction

6. View dashboard (1 min)
   → Show jobs list
   → Filter by status
   → Show stats

Total: ~8 minutes for full demo
```

---

## ✨ Success Indicators

Your Phase 1 is fully working when:

✅ Home page loads without errors
✅ Setup wizard completes successfully
✅ Jobs appear in dashboard
✅ Address validation works
✅ Availability checking works (with fallback)
✅ All APIs respond correctly
✅ Database has all tables
✅ Emergency flags set correctly
✅ Stats show accurate counts
✅ Status updates work

---

## 🚀 Next Steps After Live Testing

1. **Verify**: Everything works in your browser
2. **Create**: Test data via API (jobs, addresses, etc)
3. **Monitor**: Check logs for errors
4. **Integrate**: Connect with AI agent
5. **Deploy**: Roll out to customers
6. **Monitor**: Track metrics daily

---

## 📞 Quick Help

| Problem | Solution |
|---------|----------|
| App won't start | Check Python version, reinstall requirements |
| 404 on /jobs/ | Check routes/__init__.py blueprint registration |
| No Google Maps | Add GOOGLE_API_KEY to .env |
| Database locked | Restart Flask app |
| Tests fail | Check all tables exist via SQL |
| Templates missing | Verify file paths in templates/ |

---

## ✅ Ready to Test!

Everything is ready for live testing:
- ✅ Database models complete
- ✅ Routes complete
- ✅ Frontend complete
- ✅ APIs tested
- ✅ Documentation complete

**Start with Step 1: Setup Environment, then follow the testing checklist!**

Good luck! 🎉
