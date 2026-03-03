# 🚀 CallTradie Strategic Direction & Feature Roadmap

## Current State: You're Already Winning 🎯

**What's Working:**
- ✅ 200+ active tradies
- ✅ $100-200/month ARPU (healthy for pay-per-minute model)
- ✅ Natural Australian voice (customers can't tell it's AI)
- ✅ Emergency detection & call transfer
- ✅ ServiceM8 integration working
- ✅ SMS transcripts & spam filtering
- ✅ 98.7% accuracy rate
- ✅ 47 seconds average call-to-booking time

**Why add Cal.com?**
- Some tradies don't use ServiceM8 (Simpro, AroFlo, Google Calendar)
- Cal.com is simpler for solo tradies
- Multiple booking platform = bigger TAM (total addressable market)
- Reduces dependency on single integration

---

## 📊 PAIN POINTS TO SOLVE (Priority Order)

### 🔴 Critical Issues (Affecting Churn)

**1. Scheduling Conflicts**
- **Problem:** Customer calls, AI books a job, but technician is already on a job
- **Current Solution:** ServiceM8 integration checks availability
- **Gap:** What if ServiceM8 is down? No fallback.
- **Solution:**
  - Add real-time calendar sync failure detection
  - Show "no availability" gracefully instead of booking conflicts
  - Alert business owner of overbooking immediately

**2. Emergency Call Transfers Fail Sometimes**
- **Problem:** Emergency detected, call transferred to technician, but technician doesn't answer
- **Current Solution:** Goes to voicemail
- **Gap:** No escalation path
- **Solution:**
  - Escalation queue: Try tech 1 → try tech 2 → try business owner → SMS alert
  - Option to add multiple on-call contacts
  - Auto-SMS to team when emergency detected

**3. Customer Details Lost in Translation**
- **Problem:** ServiceM8 job gets created but missing customer address/suburb
- **Current Solution:** Relies on call transcript search
- **Gap:** Technician has to call customer back for address
- **Solution:**
  - Require address capture BEFORE booking confirmation
  - Validate address in real-time (Google Maps API)
  - Auto-populate if returning customer

---

### 🟡 High-Impact Improvements

**4. After-Hours Smart Handling**
- **Current:** All after-hours calls answered, booked for "tomorrow"
- **Gap:** No prioritization of emergencies vs. routine
- **Solution:**
  - Emergency calls: SMS owner immediately + mark urgent
  - Routine calls: Queue for next business day, send SMS confirmation
  - Owner can override (answer emergency live)

**5. Multiple Service Areas (Suburbs/Postcodes)**
- **Current:** Single location only
- **Gap:** Regional tradies can't use CallTradie
- **Solution:**
  - "Service Area" config: Add 5-10 suburbs tradie covers
  - If caller outside area: "We service [suburbs]. You're in [caller's suburb]. Can't help but here's a local recommendation"
  - Reduces out-of-area bookings

**6. Customer History & Context**
- **Current:** No memory of past calls
- **Gap:** Every customer is "new," missed upsell opportunities
- **Solution:**
  - Look up customer by phone number
  - Show: "Hi Jake! You called 3 weeks ago about a burst pipe. Do you have another issue?"
  - Show past issues: "Last time: leaking tap. This time: power outage?"
  - Technician sees: "Returning customer, give 10% loyalty discount?"

---

### 🟢 Nice-to-Have Features (But Profitable)

**7. Technician Dispatch Intelligence**
- Assign jobs based on: location proximity, skill, availability, ratings
- SMS technician: "New job assigned: Kitchen tap, 5km away, 2 hours"
- Technician accepts/rejects in app

**8. Post-Job Automation**
- After job marked "complete" in ServiceM8:
  - Auto-SMS customer: "Thanks! Please rate your experience"
  - Auto-SMS owner: "Job complete. Ready to invoice?"
  - Request Google review link

**9. Business Analytics Dashboard**
- Calls received today
- Jobs booked (and no-show rate)
- Revenue impact (calls × avg job value)
- Technician performance (response time, completion rate, rating)
- Busiest times/days

---

## 🎯 HOW CAL.COM ADDS VALUE

### Current Booking Flow (ServiceM8)
```
Call → Capture Details → Check ServiceM8 Availability →
Book in ServiceM8 → ServiceM8 API creates job → SMS sent
```

### New Flow (Multi-Platform)
```
Sign Up → Choose: "ServiceM8" OR "Cal.com" OR "Google Calendar"
     ↓
Call → Capture Details → Check chosen platform availability →
Book in chosen platform → SMS sent
```

### Cal.com Benefits
- **Simpler** for solo/2-person teams (no complex job management)
- **Integrated calendar** (personal + team calendar in one place)
- **Automation ready** (use Cal.com workflows, Zapier integration)
- **White-label** option (hide Cal.com branding)
- **Smaller learning curve** vs ServiceM8

### Cal.com Pricing
- Free tier: 1 user, limited features
- Pro: $15/month per user
- If CallTradie adds Cal.com integration, could offer white-labeled Cal.com:
  - $49/month tier for solo tradies
  - Built-in scheduling + CallTradie answering
  - Margin: $34/month per subscription customer

---

## 💡 FEATURE PRIORITIES: 3 PHASES

### 🔵 PHASE 1: Stability & Integration (4-6 weeks)
**Goal:** Fix pain points, reduce churn, improve core experience

**Must-Do:**
1. ✅ Add Cal.com as booking option (customer choice at signup)
2. ✅ Address capture validation (Google Maps API)
3. ✅ Customer history lookup (by phone number)
4. ✅ Emergency escalation path (multiple contact numbers)
5. ✅ Service area filtering (suburbs/postcodes)
6. ✅ Real-time ServiceM8 availability check (with fallback)

**Effort:** Medium | **Impact:** High | **Revenue:** Reduce churn, keep customers

**Database Changes:**
```python
# Add to Business model
- service_areas: JSON (list of suburbs)
- emergency_contacts: JSON (list of names + phones)
- calcom_api_key: String (if using Cal.com)
- booking_platform: Enum (ServiceM8 | Cal.com | GoogleCalendar)
- customer_history_enabled: Boolean

# Add new CustomerHistory model
- customer_phone
- previous_job_types
- previous_technician
- customer_notes
```

---

### 🟢 PHASE 2: Intelligence & Automation (6-8 weeks)
**Goal:** Make CallTradie smarter, reduce manual work for tradies

**Should-Do:**
1. ✅ Smart technician assignment (by location, skill, availability)
2. ✅ Post-job SMS automation (review requests, invoicing prompts)
3. ✅ Returning customer recognition (greet by name)
4. ✅ After-hours emergency vs routine splitting
5. ✅ Voicemail-to-SMS for missed transfers
6. ✅ Job no-show detection & SMS reminder (24h before)

**Effort:** Medium-High | **Impact:** High | **Revenue:** Increase usage, retention

**New Integrations Needed:**
- Twilio for SMS automation (already have this!)
- Google Maps API for address validation
- ServiceM8 webhooks for job status updates

---

### 🟣 PHASE 3: Revenue Expansion (8-12 weeks)
**Goal:** New revenue streams, premium tier, bigger market

**Could-Do:**
1. ✅ Technician mobile app (view jobs, update status)
2. ✅ Business dashboard (KPIs, analytics, insights)
3. ✅ Review aggregation (Google, Facebook, local ratings)
4. ✅ Invoice integration (Xero, Wave)
5. ✅ Premium pricing tier ($99/month with advanced features)
6. ✅ White-label licensing (resell to competitors)

**Effort:** High | **Impact:** Very High | **Revenue:** New customer segments, higher ARPU

---

## 📈 REVENUE STRATEGY: "Hooks & Ladders"

### Current Model: Transactional
- $0.50/minute
- Average: 200-400 min/month = $100-200/month
- Problem: Linear scaling, payment friction, churn risk

### Proposed Model: Hybrid
```
Entry Level (Solo Tradies):
├─ Pay-per-minute: $0.50/min
├─ OR monthly subscription: $49/month (100 min included)
└─ Good for: Testing, low volume

Professional (Small Teams):
├─ Monthly: $99/month
├─ Includes: 500 min + advanced features
├─ + Technician app
├─ + Customer history
└─ Good for: 3-5 person teams

Enterprise (Growing Businesses):
├─ Monthly: $199/month
├─ Unlimited calls + all features
├─ Dedicated Slack support
├─ Custom integrations
└─ Good for: 10+ technicians, complex operations
```

### Add-On Revenue
- ServiceM8 white-label setup: +$25/month
- Cal.com white-label setup: +$25/month
- Premium voice options (celebrity voices): +$10/month
- SMS overage: $0.10/SMS after included quota
- Custom greeting recording: $99 one-time

---

## 🛠️ TECHNICAL DECISIONS

### Database
**Current:** SQLite (works for 200 tradies)
**Proposal:** Migrate to PostgreSQL when hitting 1,000+ customers
- Better concurrency
- Better for analytics queries
- JSON support for flexible data

### Scaling Bottlenecks to Address Now
1. **ServiceM8 API rate limits** - Need caching/queue system
2. **Call spike handling** - Queue systems for booking creation
3. **SMS delivery** - Twilio has built-in retry, but monitor costs
4. **Real-time availability checks** - Cache calendar data with 30-60s TTL

### Architecture Improvements
```
Current:
Voice Agent → Create Job → ServiceM8 API → SMS

Proposed:
Voice Agent → Create Job (local) → Queue System →
  ├─ ServiceM8 sync (background)
  ├─ SMS send (background)
  ├─ Customer history lookup (async)
  └─ Notification to technician (real-time)

Benefits:
- Call drops from API failures
- SMS sent even if ServiceM8 fails
- Faster response to customer
```

---

## 📊 SUCCESS METRICS TO TRACK

### Health Metrics
- **Call answer rate:** Target 99.5%+ (99% = 7+ missed per month)
- **Booking success rate:** Target 95%+ (5% failures = customer lost)
- **Emergency detection accuracy:** Target 98%+
- **Average time to booking:** Target <60 seconds
- **SMS delivery rate:** Target 99%+

### Business Metrics
- **Monthly Recurring Revenue (MRR):** Track growth
- **Customer Acquisition Cost (CAC):** How much to get one paying customer
- **Lifetime Value (LTV):** How much one customer worth over 12 months
- **Churn rate:** % of customers leaving each month (target <5%)
- **NPS (Net Promoter Score):** Target 50+

### Usage Metrics
- **Calls per customer per month:** Track usage growth
- **Jobs booked per call:** Conversion rate
- **No-show rate:** Jobs scheduled but not completed
- **Emergency calls %:** Should be 5-10% of total

---

## 🎯 NEXT STEPS: Pick One Path

### Path A: Quick Wins (4 weeks)
Focus: Stability + Cal.com integration
- Add Cal.com as booking option
- Improve emergency escalation
- Better error handling
- Target: Reduce churn by 20%, add 50 new customers

### Path B: Smart Expansion (8 weeks)
Focus: Intelligence + customer retention
- Everything in Path A
- Smart technician assignment
- Customer history lookup
- Post-job automation
- Target: Increase ARPU by 30%, reduce churn by 50%

### Path C: Full Platform (12 weeks)
Focus: Premium tier, mobile app, market dominance
- Everything in Path A + B
- Technician mobile app
- Business analytics dashboard
- Multiple revenue tiers
- Target: 10x revenue growth, TAM expansion

---

## 💬 DISCUSSION POINTS

**1. Pain Points**
- What are your top 3 customer complaints right now?
- Which issue is causing the most cancellations?

**2. Cal.com Strategy**
- Should it be the default for certain customer types? (solo tradies?)
- Or always let customer choose?
- Premium tier upsell with included Cal.com white-label?

**3. Technician Dispatch**
- Do you have live technician data (location, status)?
- Or do tradies manage own schedules?

**4. Revenue**
- Happy with $100-200 ARPU or want to increase?
- Would customers pay $99/month for premium features?
- Monthly subscriptions vs pay-per-minute?

**5. Roadmap**
- Which phase resonates most (A, B, or C)?
- Timeline: aggressive growth or sustainable?
- Staffing: can you build this or need partnership?

---

## 🏁 Recommendation

**Start with Phase 1** (Stability + Cal.com):
- Low risk, high impact
- Fixes real customer pain points
- Adds Cal.com for new customer segment
- 4-6 weeks execution
- Expected: 20% churn reduction + 50 new customers

**Then assess Phase 2** based on customer feedback and revenue impact.

**Path to $10k/month MRR:**
```
Current: 200 customers × $150 avg = $30k/month revenue ✅
        (But $0.50/min transactional model)

Proposed: 400 customers × $100 avg = $40k/month
        (50% subscription + 50% pay-per-minute)
        = $60k/month with upsells

With Phase 2: 600 customers × $120 avg = $72k/month
            (Smart automation increases usage + retention)
```

---

## 📌 Questions for You

1. **What's the current churn rate?** (How many tradies cancel per month?)
2. **Who are your biggest competitors?** (Other AI receptionists, human reception services)
3. **What's your customer acquisition cost?** (How much do you spend to get one customer?)
4. **Are you at capacity?** (Can you support more customers with current infrastructure?)
5. **What's holding you back from $10k+ MRR?** (Product? Marketing? Sales?)
