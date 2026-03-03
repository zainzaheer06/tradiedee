# 📅 Phase 1 Implementation Timeline

## Quick Overview

```
TODAY (Setup)           → DAY 1-2 (Build)         → DAY 3+ (Deploy)
├─ Install deps        ├─ Scheduling Feature     ├─ Test with businesses
├─ API keys            ├─ Emergency Feature      ├─ Monitor metrics
├─ DB migrations       ├─ Address Feature        ├─ Fix issues
└─ Verify setup        └─ Integration testing    └─ Full rollout
```

---

## 🎯 Detailed Timeline

### TODAY: Setup & Preparation (1-2 hours)

**Time: 30 minutes - API Key Configuration**
```
□ Google Maps API
  - Create project in Google Cloud Console
  - Enable Geocoding API
  - Create API key
  - Add to .env: GOOGLE_API_KEY=...

□ ServiceM8 API
  - Log into ServiceM8
  - Get API key from Settings
  - Add to .env: SERVICEM8_API_KEY=...
                  SERVICEM8_CUSTOMER_ID=...

□ Twilio (if not already set)
  - Get Account SID & Auth Token
  - Get phone number
  - Add to .env: TWILIO_ACCOUNT_SID=...
                 TWILIO_AUTH_TOKEN=...
                 TWILIO_PHONE_NUMBER=...
```

**Time: 15 minutes - Dependencies**
```
□ pip install -r requirements/phase1_additional.txt

Expected output:
✓ geopy==2.3.0
✓ aiohttp==3.8.0
✓ python-json-logger==2.0.7
```

**Time: 20 minutes - Database Setup**
```
□ python scripts/migrations/phase1_apply_schema.py

Expected output:
✓ All SQL migrations applied successfully
✓ MIGRATION COMPLETE
✓ All required tables present
✓ All required columns present
```

**Time: 20 minutes - Code Integration**
```
□ Verify integration files exist:
  ✓ integrations/serviceM8_api.py
  ✓ integrations/address_validator.py
  ✓ integrations/emergency_handler.py

□ Update models.py with new models:
  ✓ Business model
  ✓ Job model
  ✓ EmergencyEscalationLog model
```

**Checklist:** ✅ Setup Complete

---

### DAY 1: Implement Feature 1 - Scheduling (2-3 hours)

**Time: 45 minutes - Create Routes**
```
File: routes/booking.py
Create:
  /api/booking/check-availability [POST]
  /api/booking/book-job [POST]

Dependencies:
  - ServiceM8Integration class ✓
  - Database connection ✓
```

**Code Checklist:**
```python
□ Import ServiceM8Integration
□ Create booking_bp blueprint
□ Implement check-availability endpoint
□ Implement book-job endpoint
□ Add error handling
□ Register blueprint in app.py
```

**Time: 45 minutes - Update Agent Prompt**
```
Add to agent configuration:
  □ SCHEDULING_RULES
  □ AVAILABILITY_CHECK logic
  □ FALLBACK messages if API fails
  □ CONFIRMATION logic

Test with sample utterances:
  □ "When can you come?"
  □ "I'm free next Thursday"
  □ "Earliest appointment?"
```

**Time: 30 minutes - Testing**
```
□ Test ServiceM8 health check
  sm8.health_check() → Should return True

□ Test availability retrieval
  slots = sm8.get_available_slots()
  → Should return list of datetime objects

□ Test with real business
  - Create test business in database
  - Make call with test agent
  - Check if /api/booking/check-availability works
  - Verify slots returned correctly

□ Test fallback (simulate API failure)
  - Break API key temporarily
  - Verify fallback message shown
  - Agent doesn't crash
```

**Checklist:** ✅ Feature 1 Complete

---

### DAY 2: Implement Feature 2 - Emergency Escalation (2-3 hours)

**Time: 45 minutes - Configure Emergency Contacts**
```
Database setup for test business:
□ Create Business record with emergency_contacts JSON:
  {
    "emergency_contacts": [
      {"name": "John", "phone": "+61412345678", "priority": 1},
      {"name": "Sarah", "phone": "+61412345679", "priority": 2},
      {"name": "Owner", "phone": "+61412345680", "priority": 3}
    ]
  }

□ Enable emergency escalation:
  emergency_escalation_enabled = True
  emergency_transfer_timeout = 30
```

**Time: 45 minutes - Update Agent Prompt**
```
Add to agent configuration:
  □ EMERGENCY_KEYWORDS list
  □ EMERGENCY_DETECTION logic
  □ Fallback to escalation handler
  □ Response templates

Test keywords:
  □ "burst pipe"
  □ "gas leak"
  □ "power outage"
  □ "emergency"
  □ "urgent"
```

**Time: 30 minutes - Testing**
```
□ Test emergency keyword detection
  is_emergency, keywords = detect_emergency("I've got a burst pipe")
  → Should return True and ["burst pipe"]

□ Test escalation routing
  - Create test job with emergency flag
  - Trigger escalation
  - Check escalation log for attempts

□ Test SMS fallback
  - Simulate all techs unavailable
  - Verify SMS alert created
  - Check SMS log for status

□ Monitor logs for:
  - Emergency detection accuracy
  - Transfer attempts (should be in escalation log)
  - Fallback behavior
```

**Checklist:** ✅ Feature 2 Complete

---

### DAY 3: Implement Feature 3 - Address Validation (2-3 hours)

**Time: 45 minutes - Create Address Routes**
```
File: routes/address.py
Create:
  /api/address/validate [POST]
  /api/address/suggest [POST]

Dependencies:
  - AddressValidator class ✓
  - Google Maps API ✓
```

**Code Checklist:**
```python
□ Import AddressValidator
□ Create address_bp blueprint
□ Implement validate endpoint
□ Implement suggest endpoint
□ Add error handling
□ Register blueprint in app.py
```

**Time: 45 minutes - Update Agent Prompt**
```
Add to agent configuration:
  □ ADDRESS_CAPTURE logic
  □ Street address → Suburb → Postcode flow
  □ CONFIRMATION step before validation
  □ FALLBACK if validation fails
  □ SUGGESTION logic

Test flow:
  □ "42 Smith Street" → "Penrith" → "2750"
  □ Handle misspellings
  □ Handle missing postcode
  □ Suggest corrections
```

**Time: 30 minutes - Testing**
```
□ Test valid address validation
  result = validator.validate_address(
    "42 Smith Street", "Penrith", "2750"
  )
  → Should return {'valid': True, 'formatted_address': '...'}

□ Test invalid address handling
  → Should return suggestion or ask for correction

□ Test with real addresses
  □ Alexandria, NSW
  □ Parramatta, NSW
  □ Inner West suburbs
  → All should validate

□ Test edge cases
  □ Wrong postcode (should correct)
  □ Typo in suburb (should suggest)
  □ Street number only (should ask for name)

□ Monitor logs for:
  - Validation success rate (should be 98%+)
  - Time to validate (should be <2 seconds)
  - Failed validations (should be rare)
```

**Checklist:** ✅ Feature 3 Complete

---

### DAY 4: Integration Testing (2-3 hours)

**All 3 Features Together**

```
□ Test complete call flow:
  1. Customer calls
  2. AI detects emergency keyword (if applicable)
  3. AI captures address (street, suburb, postcode)
  4. AI validates address with Google Maps
  5. AI checks availability in ServiceM8
  6. AI offers available slots
  7. Customer confirms time
  8. Job created in ServiceM8
  9. Confirmation SMS sent
  → All steps should work end-to-end

□ Stress test:
  - Rapid API calls
  - Simultaneous address validations
  - Multiple emergency calls
  → No crashes or timeouts

□ Error scenarios:
  - ServiceM8 API down → Should gracefully degrade
  - Google API down → Should take address anyway
  - Both down → Should queue for manual followup

□ Database integrity:
  - No duplicate jobs created
  - All logs recorded properly
  - Address validations persisted
  - Emergency escalations tracked
```

**Checklist:** ✅ Integration Complete

---

### DAY 5: Monitoring & Optimization (1-2 hours)

**Metrics to Track**

```
□ Create dashboard or query for:
  SELECT
    COUNT(*) as total_calls,
    SUM(CASE WHEN address_validated = 1 THEN 1 ELSE 0 END) as addresses_validated,
    SUM(CASE WHEN serviceM8_job_id IS NOT NULL THEN 1 ELSE 0 END) as jobs_created,
    SUM(CASE WHEN is_emergency = 1 THEN 1 ELSE 0 END) as emergencies
  FROM job
  WHERE created_at > DATE('now', '-1 day');

□ Performance metrics:
  - Average time to validate address
  - Average time to check availability
  - API response times
  - Success rates for each step

□ Error tracking:
  - Failed validations
  - ServiceM8 errors
  - Emergency escalation failures
  - Incomplete bookings
```

**Optimization**

```
□ Cache frequently validated addresses
□ Batch ServiceM8 API calls if needed
□ Add request timeouts
□ Implement retry logic with exponential backoff
□ Add circuit breaker for external APIs
```

**Checklist:** ✅ Monitoring Complete

---

### DAY 6-7: Soft Launch (Rollout to 5-10 Customers)

**Friday Afternoon: Enable for Test Group**

```
□ Select 5-10 test businesses:
  - Mix of trade types
  - Different sizes (solo to 5 person team)
  - Different geographic areas

□ For each business:
  - Configure emergency contacts
  - Set service areas
  - Verify ServiceM8 integration
  - Brief them on changes

□ Enable features:
  - Feature flag or manual toggle:
    business.scheduling_enabled = True
    business.emergency_escalation_enabled = True
    business.address_validation_enabled = True

□ Communication:
  - "We've added new features to improve booking"
  - "Emergency calls are now prioritized"
  - "Addresses are validated for accuracy"
  - "Give feedback anytime"
```

**Monitoring (Friday Evening - Monday Morning)**

```
□ Watch logs for errors:
  - tail -f logs/*.log
  - Watch for: ERROR, EXCEPTION, FAILED

□ Check metrics hourly:
  - Booking success rate
  - Emergency detection accuracy
  - Address validation rate
  - API response times

□ Early warning signs to watch for:
  - API rate limit errors
  - Database connection issues
  - Silent failures (jobs not created)
  - Customers reporting issues
```

---

## 📊 Success Criteria by Day

| Day | Feature | Success Criteria |
|-----|---------|-----------------|
| 1 | Scheduling | ✅ 95%+ bookings created in ServiceM8 |
| 2 | Emergency | ✅ 90%+ emergencies transferred within 5s |
| 3 | Address | ✅ 99%+ addresses validate correctly |
| 4 | Integration | ✅ All 3 features work together |
| 5 | Monitoring | ✅ Dashboards show healthy metrics |
| 6-7 | Soft Launch | ✅ No critical errors in test group |

---

## 🚨 If Something Goes Wrong

### Day 1 - Scheduling Issues
```
Problem: ServiceM8 API returns empty slots
→ Solution: Check if business has jobs in ServiceM8
→ Workaround: Use manual availability list

Problem: Jobs not creating in ServiceM8
→ Solution: Verify API key and customer ID
→ Workaround: Log for manual creation

Problem: Availability check timing out
→ Solution: Increase timeout or add caching
→ Workaround: Skip availability check with warning
```

### Day 2 - Emergency Issues
```
Problem: Emergency calls not routing
→ Solution: Verify emergency_contacts configured
→ Workaround: Manual escalation (owner calls customer)

Problem: SMS not sending
→ Solution: Verify Twilio configured
→ Workaround: Rely on call transfer only
```

### Day 3 - Address Issues
```
Problem: Address validation always fails
→ Solution: Check Google API key and quota
→ Workaround: Accept address without validation

Problem: Address validation slow
→ Solution: Add caching or async validation
→ Workaround: Timeout after 10 seconds, proceed anyway
```

---

## 🎯 Full Timeline Summary

```
TODAY (2 hours)
├─ Setup: API keys, dependencies, DB migrations
└─ Status: ✅ Ready to build

DAY 1 (2-3 hours)
├─ Feature 1: Scheduling conflict prevention
└─ Status: ✅ Tested and working

DAY 2 (2-3 hours)
├─ Feature 2: Emergency escalation
└─ Status: ✅ Tested and working

DAY 3 (2-3 hours)
├─ Feature 3: Address validation
└─ Status: ✅ Tested and working

DAY 4 (2-3 hours)
├─ Integration testing all 3 features together
└─ Status: ✅ End-to-end flow works

DAY 5 (1-2 hours)
├─ Monitoring setup and optimization
└─ Status: ✅ Ready for customers

DAY 6-7 (Ongoing)
├─ Soft launch to 5-10 test businesses
├─ Monitor 24/7 for issues
└─ Status: ✅ Feedback collected

WEEK 2
├─ Address feedback and fixes
├─ Gradual rollout to remaining customers
├─ Full launch preparation
└─ Status: ✅ Live for all customers

WEEK 3+
├─ Monitor metrics (churn, booking rate, etc.)
├─ Collect customer feedback
├─ Plan Phase 2 features
└─ Status: ✅ Optimizing and learning
```

---

## 💡 Tips for Smooth Execution

### ✅ DO:
- [ ] Test each feature independently first
- [ ] Keep logs detailed for debugging
- [ ] Have fallback for every external API call
- [ ] Communicate changes to customers early
- [ ] Monitor metrics continuously
- [ ] Have quick rollback plan if needed
- [ ] Get customer feedback quickly

### ❌ DON'T:
- [ ] Don't skip integration testing
- [ ] Don't launch all features to all customers at once
- [ ] Don't ignore errors in logs
- [ ] Don't assume API keys are correct
- [ ] Don't forget to update documentation
- [ ] Don't deploy without monitoring in place
- [ ] Don't take down old features if you're adding new ones

---

## 📱 Daily Standup Template

Each day, track:

```
TODAY'S FOCUS: [Feature being built]

PROGRESS:
- ✅ [Completed task 1]
- ✅ [Completed task 2]
- ⏳ [In progress task]
- ❌ [Blocked on something?]

METRICS:
- API Success Rate: XX%
- Average Response Time: XXms
- Errors in last 24h: N
- Test Businesses: N

NEXT:
- [ ] [Tomorrow's tasks]

RISKS:
- [ ] Any blockers?
- [ ] Any concerns?
```

---

## 🏁 Ready? Let's Go!

You have everything you need:
- ✅ Complete code for all 3 features
- ✅ Database schema and migrations
- ✅ Integration files ready to use
- ✅ Detailed implementation guide
- ✅ Testing checklist
- ✅ Deployment strategy

**Start with TODAY's setup phase and you'll be live in a week! 🚀**

Good luck! Feel free to reach out if you get stuck on anything.
