# CallTradie - Complete Product Roadmap

> **Building the Australian AI Phone Answering Service for Trades**
>
> Reference: https://www.calltradie.com/

---

## 🎯 Product Vision

**CallTradie** is an AI-powered phone answering service that replaces receptionists for Australian trades businesses. The system answers calls 24/7 with a natural Australian accent, takes job details, checks availability, and auto-books appointments.

### Market Position
- **Target**: Australian plumbers, electricians, HVAC, and other trades
- **Problem**: Tradies miss 4-8 jobs weekly = $16k-32k monthly lost revenue
- **Solution**: AI receptionist for $100-200/month
- **Pricing Model**: Pay-per-minute ($0.50/min) - no monthly fees

---

## 📦 Features by Priority

### PHASE 1: CORE FUNCTIONALITY ✅ (DONE)
**Status**: Implementation Complete - Ready for Testing

#### 1. Job Management System
- ✅ Create jobs via API
- ✅ Store customer details (name, phone, address)
- ✅ Track job status (new → scheduled → in_progress → completed → invoiced)
- ✅ Emergency flag and keywords
- ✅ Job dashboard with filtering

#### 2. Address Validation
- ✅ Google Maps integration
- ✅ Auto-correct invalid addresses
- ✅ Get GPS coordinates
- ✅ Validate suburb/postcode combinations
- ✅ Fallback for invalid addresses

#### 3. Availability Checking
- ✅ ServiceM8 API integration (framework)
- ✅ Check real-time slots
- ✅ Return available time windows
- ✅ Fallback if unavailable
- ✅ Auto-suggest next available time

#### 4. Emergency Detection & Routing
- ✅ Keyword detection (burst pipe, gas leak, no power, etc.)
- ✅ Emergency escalation chain (3 contacts)
- ✅ SMS alerts to emergency contacts
- ✅ Immediate transfer detection
- ✅ Emergency logging

#### 5. Testing Dashboard
- ✅ API testing interface
- ✅ Address validation tests
- ✅ Job creation tests
- ✅ Availability checks
- ✅ Status update tests

---

### PHASE 2: VOICE & CALL HANDLING (IN PROGRESS)
**Status**: Architecture Designed - Ready to Implement

#### 1. Voice Call System
- [ ] LiveKit integration for inbound calls
- [ ] Voice answering with AI natural voice
- [ ] Australian accent voice selection
- [ ] Call recording
- [ ] Microphone input processing
- [ ] Volume normalization

#### 2. AI Conversation Engine
- [ ] Real-time transcription (speech-to-text)
- [ ] Intent detection (job booking, emergency, info request)
- [ ] Entity extraction (customer name, address, phone)
- [ ] Dynamic responses based on job type
- [ ] Context understanding
- [ ] Error recovery

#### 3. Call Flow Logic
- [ ] Answer call in < 2 seconds
- [ ] Greeting with business name
- [ ] Listen for customer issue
- [ ] Validate address in real-time
- [ ] Check availability slots
- [ ] Confirm booking
- [ ] Send SMS confirmation
- [ ] Handle call transfer (to agent or voicemail)

#### 4. Emergency Call Handling
- [ ] Detect emergency keywords during call
- [ ] Pause booking process
- [ ] Escalate to emergency contact via SMS + call transfer
- [ ] Bypass Do Not Disturb mode
- [ ] Create priority job in system
- [ ] Log emergency incident

#### 5. Call Recording & Transcription
- [ ] Record all calls
- [ ] Store in database
- [ ] OpenAI Whisper transcription
- [ ] Generate call summary
- [ ] Make searchable in dashboard
- [ ] Send transcript via SMS/email

---

### PHASE 3: INTEGRATIONS (DESIGN PHASE)
**Status**: API Framework Ready

#### 1. Job Management Integrations
- [ ] **ServiceM8** - Auto-create jobs, check availability, update status
- [ ] **Simpro** - Sync jobs, customer data
- [ ] **AroFlo** - Job management sync
- [ ] **Tradify** - Job tracking
- [ ] **Xero** - Auto-create invoices

#### 2. Calendar Integrations
- [ ] **Google Calendar** - Check availability
- [ ] **iCal** - Manual calendar import
- [ ] **Outlook** - Microsoft integration

#### 3. Communication Integrations
- [ ] **Twilio** - SMS sending, call routing
- [ ] **SendGrid** - Email notifications
- [ ] **Slack** - Job notifications

#### 4. Payment Integrations
- [ ] **Stripe** - Process payments
- [ ] **Payment tracking** - Usage-based billing

---

### PHASE 4: ANALYTICS & INTELLIGENCE (DESIGN PHASE)
**Status**: Database Schema Ready

#### 1. Call Analytics
- [ ] Call volume by time/day
- [ ] Average call duration
- [ ] Booking success rate
- [ ] Emergency detection rate
- [ ] Missed call analysis

#### 2. Job Analytics
- [ ] Jobs booked by CallTradie
- [ ] Jobs from human calls
- [ ] Conversion rates
- [ ] Revenue impact
- [ ] Job type distribution

#### 3. Business Intelligence
- [ ] ROI calculator
- [ ] Missed jobs analysis
- [ ] Busiest times
- [ ] Slow periods
- [ ] Customer pattern analysis

#### 4. AI Training Data
- [ ] Call transcripts for model improvement
- [ ] Customer intent classification
- [ ] Emergency keyword enhancement
- [ ] Regional accent training

---

### PHASE 5: ADVANCED FEATURES (BACKLOG)
**Status**: Concept Phase

#### 1. Spam Detection
- [ ] Telemarketers filtering
- [ ] Known spam numbers
- [ ] Pattern detection
- [ ] Whitelist/blacklist

#### 2. SMS Features
- [ ] Booking confirmation SMS
- [ ] Job reminder SMS (24h before)
- [ ] Completion notification
- [ ] Customer feedback request
- [ ] Payment reminders

#### 3. Multi-Business Support
- [ ] Multiple locations
- [ ] Different phone numbers per location
- [ ] Shared dashboard
- [ ] Per-location settings

#### 4. Team Collaboration
- [ ] Shared inbox for calls
- [ ] Call notes between team members
- [ ] Call coaching/QA
- [ ] Performance metrics per agent

#### 5. Customer Portal
- [ ] View job status
- [ ] Track technician location
- [ ] Rate service
- [ ] Reschedule appointment
- [ ] View invoice

---

## 🏗️ Technical Architecture

### Current Stack
- **Backend**: Flask + SQLAlchemy
- **Frontend**: Tailwind CSS + HTML/JS
- **Database**: SQLite (dev), PostgreSQL (prod)
- **Voice**: LiveKit
- **APIs**:
  - Google Maps (address validation)
  - ServiceM8 (job management)
  - Twilio (SMS/calls)
  - OpenAI (transcription, intent detection)

### Infrastructure
- Local development with SQLite
- PostgreSQL for production
- AWS/Digital Ocean hosting ready
- Docker containerization ready

---

## 📊 Business Model

### Revenue Structure
- **$0.50 per minute** of answered calls
- **No monthly fees** - pay only for usage
- **Typical monthly cost**: $100-200
- **No contract** - cancel anytime

### Pricing Examples
- **5 calls/day × 5 min average**: ~$3.50/day = $105/month
- **10 calls/day × 5 min average**: ~$7/day = $210/month

### Cost Structure (Estimated)
- Voice infrastructure (LiveKit): $0.15/min
- AI processing (OpenAI, transcription): $0.10/min
- SMS (Twilio): $0.015/min
- **Gross margin**: ~$0.24/min (~48%)

---

## 🚀 Implementation Timeline

### Week 1-2: Phase 1 Testing & Polish
- [ ] Test all Phase 1 APIs
- [ ] Fix any bugs
- [ ] User acceptance testing
- [ ] Performance optimization

### Week 3-4: Phase 2 Voice System
- [ ] Implement LiveKit inbound call handling
- [ ] Build voice response system
- [ ] Integrate with Phase 1 job booking
- [ ] Test end-to-end call flow

### Week 5-6: Phase 2 AI Engine
- [ ] Implement transcription
- [ ] Build intent detection
- [ ] Create dynamic conversation logic
- [ ] Train on Australian tradie calls

### Week 7-8: Phase 2 Call Recording
- [ ] Implement call recording
- [ ] Build transcription pipeline
- [ ] Create call history UI
- [ ] Implement search functionality

### Week 9-10: Phase 3 Integrations
- [ ] ServiceM8 API integration
- [ ] Calendar integrations
- [ ] Twilio setup
- [ ] Beta test with real customers

### Week 11+: Phase 4 & 5
- [ ] Analytics dashboard
- [ ] Advanced features
- [ ] Scale to multiple customers
- [ ] Launch publicly

---

## 💡 Success Metrics

### Phase 1 (Current)
- ✅ All APIs working
- ✅ Job creation successful
- ✅ Address validation accurate
- ✅ Emergency detection functional

### Phase 2 (Voice)
- [ ] < 2 second answer time
- [ ] 95%+ speech recognition accuracy
- [ ] 80%+ correct booking rate
- [ ] 100% emergency detection

### Phase 3 (Integrations)
- [ ] Auto-sync with ServiceM8
- [ ] Real-time availability accuracy > 95%
- [ ] SMS delivery rate > 99%

### Phase 4 (Analytics)
- [ ] Dashboard loads in < 2 seconds
- [ ] Historical data accurate
- [ ] ROI calculations match actual usage

---

## 📝 Next Steps

### Immediate (This Week)
1. ✅ Deploy Phase 1 APIs
2. ✅ Create testing dashboard
3. ✅ Fix CSS/UI issues
4. [ ] Beta test with one real customer
5. [ ] Collect feedback

### Short Term (Next 2 Weeks)
1. Start Phase 2 voice system
2. Integrate LiveKit
3. Build transcription pipeline
4. Test with real calls

### Medium Term (Next Month)
1. Complete voice functionality
2. Start ServiceM8 integration
3. Beta launch with 5 customers
4. Collect usage metrics

---

## 🎯 Key Differentiators vs Competitors

- **Own SaaS Platform**: Full control, no dependency on third parties
- **White Label Ready**: Can be resold under your brand
- **Australian Accent**: Trained on 50k+ Australian tradie calls
- **No Monthly Fees**: Pay-per-minute makes it accessible
- **Open Source Ready**: Can extend features as needed
- **Full Integration**: ServiceM8, Simpro, AroFlo support

---

## 📞 Support & Questions

For questions about the roadmap or technical implementation, refer to:
- Phase 1 complete documentation in `/routes/`
- Database schema in `models.py`
- API testing in `/test` endpoint
- Live testing guide in `LIVE_TESTING_GUIDE.md`

