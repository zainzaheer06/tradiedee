# 🎯 START TESTING NOW - 3 Steps

## Copy & Paste This Into Your Terminal

### Step 1: Update Environment (30 seconds)
```bash
# Add Google API key to .env (REQUIRED for address validation)
echo "GOOGLE_API_KEY=test" >> .env

# Optional - ServiceM8 integration
# echo "SERVICEM8_API_KEY=your-key" >> .env
# echo "SERVICEM8_CUSTOMER_ID=your-id" >> .env
```

### Step 2: Setup Database (1 minute)
```bash
python scripts/migrations/phase1_apply_schema.py
```

Watch for this output:
```
✓ All SQL migrations applied successfully
✓ MIGRATION COMPLETE
✓ All required tables present
✓ All required columns present
```

### Step 3: Start Application (10 seconds)
```bash
python app.py
```

Watch for:
```
 * Running on http://127.0.0.1:5000
 * Press CTRL+C to quit
```

---

## 🌐 Testing URLs

### Open in Your Browser

1. **Home Page**: http://localhost:5000/
2. **Setup Wizard**: http://localhost:5000/setup/
3. **Testing Dashboard**: http://localhost:5000/test
4. **Job Dashboard**: http://localhost:5000/jobs/

---

## ⚡ Quickest Test (No Setup Needed)

1. **Open**: http://localhost:5000/test
2. **Fill Address Fields**:
   - Street: "42 Smith Street"
   - Suburb: "Penrith"
   - Postcode: "2750"
   - State: "NSW"
3. **Click**: "Test Address Validation"
4. **See**: Address validation result in green

✅ **Success**: You see formatted address with coordinates!

---

## 📊 What's Ready to Test

### ✅ APIs (Test via /test Dashboard)
- POST `/api/address/validate` - Validate addresses
- POST `/api/booking/check-availability` - Check slots
- POST `/jobs/create` - Create jobs
- GET `/jobs/api/stats` - Get statistics
- PUT `/jobs/{id}/status` - Update status

### ✅ Frontend Pages
- `/` - Home page with feature overview
- `/setup/` - 4-step business setup wizard
- `/setup/emergency` - Emergency contact configuration
- `/setup/service-areas` - Service area setup
- `/jobs/` - Job management dashboard
- `/jobs/{id}` - Job detail view
- `/test` - API testing dashboard

### ✅ Database Models
- `Business` - Business configuration
- `Job` - Service appointments
- `EmergencyEscalationLog` - Emergency tracking
- `SMSLog` - SMS delivery
- `AddressValidationLog` - Address history

### ✅ Integration Files
- `serviceM8_api.py` - ServiceM8 API client
- `address_validator.py` - Google Maps validation
- `emergency_handler.py` - Emergency escalation

---

## 🧪 Test Scenarios

### Scenario 1: Address Validation (2 minutes)
```
1. Open: http://localhost:5000/test
2. Fill: 42 Smith Street, Penrith, 2750
3. Click: "Test Address Validation"
4. See: ✅ Valid address with coordinates
```

### Scenario 2: Create Job (3 minutes)
```
1. Open: http://localhost:5000/test
2. Fill all job fields
3. Click: "Create Job"
4. See: ✅ Job ID returned
5. Open: http://localhost:5000/jobs/
6. See: ✅ Job appears in dashboard
```

### Scenario 3: Full Setup Flow (5 minutes)
```
1. Open: http://localhost:5000/
2. Click: "Sign Up"
3. Create account: test@example.com / test123
4. Auto-redirects to: /setup/
5. Fill: Business details
6. Fill: Emergency contacts
7. Fill: Service areas
8. Done: See job dashboard
9. Open: /test
10. Create job via API
11. See: Job in dashboard
```

---

## ✅ Verification Checklist

### Database Check
```bash
# Open Python interpreter
python

# Check models imported correctly
>>> from models import Business, Job, EmergencyEscalationLog, SMSLog, AddressValidationLog
>>> print("✓ All models imported successfully")
```

### Routes Check
```bash
# In Flask app terminal, you should see something like:
* Route registered: GET / (phase1.home)
* Route registered: GET /setup/ (business_setup.setup)
* Route registered: GET /jobs/ (jobs.job_dashboard)
* Route registered: POST /api/address/validate (address.validate_address)
* Route registered: POST /api/booking/check-availability (booking.check_availability)
```

### Pages Check
```bash
# Test each URL in browser:
✅ http://localhost:5000/ - Returns HTML (home page)
✅ http://localhost:5000/test - Returns HTML (test dashboard)
✅ http://localhost:5000/setup/ - Requires auth or redirects
✅ http://localhost:5000/jobs/ - Requires auth or redirects
```

---

## 📝 Common Issues & Fixes

### Issue: "ModuleNotFoundError"
```bash
# Fix: Install dependencies
pip install flask flask-sqlalchemy
python app.py
```

### Issue: "Table doesn't exist"
```bash
# Fix: Run migrations
python scripts/migrations/phase1_apply_schema.py
```

### Issue: "Blueprint not registered"
```bash
# Fix: Check routes/__init__.py has all imports
# Restart Flask app
Ctrl+C, then python app.py
```

### Issue: "Address validation fails"
```bash
# Fix: Add GOOGLE_API_KEY to .env
echo "GOOGLE_API_KEY=test-key" >> .env
# Restart Flask app
```

### Issue: "404 on /jobs/"
```bash
# Fix: Make sure you're logged in
# Or check routes registration
python -c "from app import app; print(app.url_map)"
```

---

## 🎯 Next Steps After Successful Test

1. ✅ Verify home page loads
2. ✅ Test address validation in /test
3. ✅ Create test job
4. ✅ See job in dashboard
5. ✅ Update job status
6. ✅ Complete setup wizard
7. ✅ Integrate with AI agent
8. ✅ Deploy to customers

---

## 📊 Success = You See

### Address Validation
```json
{
  "valid": true,
  "formatted_address": "42 Smith Street, Penrith NSW 2750",
  "coordinates": {"lat": -33.738, "lng": 150.695}
}
```

### Job Creation
```json
{
  "status": "success",
  "job_id": 1,
  "message": "Job created successfully"
}
```

### Job Dashboard
- Lists all jobs
- Shows customer names
- Shows job types
- Shows status
- Can filter by date/status

---

## ⏱️ Total Time

- Setup: 2 minutes
- Testing: 5 minutes
- **Total: 7 minutes to live testing**

---

## 🚀 You're Ready!

Everything is complete and ready to test:

✅ **Code**: All written and integrated
✅ **Database**: Models ready
✅ **Frontend**: Templates ready
✅ **APIs**: Routes ready
✅ **Documentation**: Complete

**Just run the 3 commands above and start testing!**

👉 **Next: Follow LIVE_TESTING_GUIDE.md for detailed testing**

Good luck! 🎉
