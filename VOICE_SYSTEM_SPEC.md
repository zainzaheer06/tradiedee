# CallTradie Voice System - Technical Implementation Spec

> **24/7 AI Phone Answering System for Australian Trades**
>
> This document defines the complete voice system implementation for CallTradie

---

## 🎯 Core Requirements

### 1. Always-On Call Answering ✅
- **Requirement**: Answer every incoming call automatically
- **Must Not**: Let any calls go to voicemail
- **Must Sound**: Natural with Australian accent
- **Must Be**: Friendly, professional, yet efficient
- **Must Work**: During business hours AND after hours (24/7)

### 2. Emergency Detection (CRITICAL) 🚨
**Detection Keywords**:
- Burst pipe / Leaking
- Power outage / No electricity
- No hot water
- Gas leak
- Flooding / Water damage
- System down / Not working

**When Emergency Detected**:
- ✅ Mark job as **HIGH PRIORITY**
- ✅ Notify business owner **INSTANTLY** via SMS
- ✅ Optionally forward call to on-call technician
- ✅ Put emergency jobs at TOP of dashboard
- ✅ Store emergency flag in job record

### 3. Automatic Job Creation ✅
**Every call automatically creates a job with**:
- Customer name
- Phone number
- Address (validated via Google Maps)
- Suburb
- Type of job
- Description of issue
- Urgency level (normal/emergency)
- Preferred date/time
- Call summary/transcript
- **NO manual data entry needed**

### 4. Smart Appointment Booking ✅
**AI must**:
- Offer next available time slots
- Confirm selected time with customer
- Send confirmation SMS **immediately**
- Add booking to calendar/ServiceM8
- Send reminder SMS before job

**Customer Capabilities**:
- Reschedule appointment
- Cancel appointment
- Confirm time via SMS reply

---

## 📋 Complete Call Flow

```
┌─────────────────────────────────────────────────────────────┐
│ 1. GREETING                                                 │
│    "Hello! You've reached [Business Name]. How can I help?" │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. ASK FOR HELP                                             │
│    "What service do you need today?"                        │
│    [AI listens and understands service type]               │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
        ┌──────────────┐
        │ Emergency?   │
        └──┬───────┬──┘
           │       │
       YES │       │ NO
           ▼       ▼
        EMERGENCY  ┌─────────────────────────────────────────┐
        ESCALATION │ 3. COLLECT DETAILS                      │
                   │    - "What's your name?"                │
                   │    - "What's your address?"             │
                   │    - "What's your phone number?"        │
                   │    (Validate address with Google Maps)  │
                   └──────────────┬────────────────────────┘
                                  │
                                  ▼
                   ┌─────────────────────────────────────────┐
                   │ 4. OFFER BOOKING TIMES                  │
                   │    "We have availability on..."         │
                   │    - Show 3 time options                │
                   │    - Listen for customer choice         │
                   └──────────────┬────────────────────────┘
                                  │
                                  ▼
                   ┌─────────────────────────────────────────┐
                   │ 5. CONFIRM BOOKING                      │
                   │    "Confirming [details]..."            │
                   │    - Create job in database             │
                   │    - Save to ServiceM8                  │
                   └──────────────┬────────────────────────┘
                                  │
                                  ▼
                   ┌─────────────────────────────────────────┐
                   │ 6. SEND SMS CONFIRMATION                │
                   │    "SMS sent to [phone]"                │
                   │    - Booking confirmation SMS           │
                   │    - Job reference number               │
                   │    - Can reschedule via SMS             │
                   └──────────────┬────────────────────────┘
                                  │
                                  ▼
                   ┌─────────────────────────────────────────┐
                   │ 7. END CALL                             │
                   │    Save transcript & analytics          │
                   └─────────────────────────────────────────┘
```

---

## 🔧 Technical Architecture

### Voice Processing Pipeline

```
┌────────────────┐
│ Inbound Call   │ (from phone system/Twilio)
└────────┬───────┘
         │
         ▼
┌────────────────────────────────────────┐
│ LiveKit Voice Handler                  │
│ - Receive audio stream                 │
│ - Detect speech onset/offset           │
│ - Audio normalization                  │
└────────┬─────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────┐
│ Speech-to-Text (Whisper)               │
│ - Convert audio to transcript          │
│ - Real-time transcription              │
│ - ~2-3 second latency                  │
└────────┬─────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────┐
│ NLU Engine (Intent Detection)          │
│ - Parse customer intent                │
│ - Extract entities (name, address)     │
│ - Detect emergency keywords            │
└────────┬─────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────┐
│ State Machine                          │
│ - Manage conversation flow             │
│ - Track collected information          │
│ - Route to appropriate handler         │
└────────┬─────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────┐
│ Response Generation                    │
│ - Create contextual response           │
│ - Format for natural speech            │
│ - Prepare next question                │
└────────┬─────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────┐
│ Text-to-Speech (Australian Voice)      │
│ - Convert text to natural speech       │
│ - Australian accent/dialect            │
│ - Natural intonation                   │
└────────┬─────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────┐
│ Audio Output                           │
│ - Send audio back to caller            │
│ - Real-time delivery                   │
└────────────────────────────────────────┘
```

---

## 📊 Database Schema

### New Fields Required in CallLog

```python
class CallLog(db.Model):
    # Existing fields
    id
    user_id
    from_number
    to_number
    duration_seconds
    transcription
    status
    created_at

    # NEW FIELDS NEEDED
    call_state = db.Column(db.String(50))  # greeting, ask_help, collect_name, etc.
    customer_name = db.Column(db.String(100))
    customer_address = db.Column(db.Text)
    job_type = db.Column(db.String(100))
    is_emergency = db.Column(db.Boolean, default=False)
    emergency_keywords = db.Column(db.JSON)  # ["burst pipe", "flooding"]
    booking_confirmed = db.Column(db.Boolean, default=False)
    preferred_datetime = db.Column(db.DateTime)
    scheduled_datetime = db.Column(db.DateTime)
    sms_sent = db.Column(db.Boolean, default=False)
    created_job_id = db.Column(db.Integer, db.ForeignKey('job.id'))
```

---

## 🔌 Integration Points

### 1. Phone System Integration
**Incoming calls from**:
- Twilio (preferred - managed easily)
- Other SIP/VoIP providers
- Local phone system
- Business phone number routing

**Webhook**: `POST /voice/inbound`

### 2. Voice & Audio
**LiveKit**:
- WebRTC audio streaming
- Real-time bidirectional audio
- Call recording
- Low latency (<100ms)

### 3. Transcription
**OpenAI Whisper**:
- Real-time speech-to-text
- 99%+ accuracy for Australian accent
- Fast processing (<2 seconds)

### 4. Text-to-Speech (TTS)
**Google Cloud TTS or ElevenLabs**:
- Natural Australian voice
- Fast synthesis (<1 second)
- Natural intonation
- Lip sync support (future)

### 5. Address Validation
**Google Maps API** (already implemented):
- Auto-correct addresses
- Get GPS coordinates
- Validate suburb/postcode

### 6. Job Management
**ServiceM8 Integration**:
- Auto-create jobs
- Check availability
- Update job status
- Sync calendars

### 7. SMS Notifications
**Twilio SMS**:
- Send confirmation SMS
- Send reminders (24h before)
- Allow SMS-based rescheduling
- Emergency alerts

### 8. Emergency Escalation
**Already implemented**:
- SMS to 3 emergency contacts
- Call transfer to on-call tech
- Mark job as high priority
- Log escalation attempt

---

## 🎤 Voice Specifications

### Australian Accent Requirements
- Natural Australian English
- Friendly, professional tone
- Not robotic or mechanical
- Regional variations supported
- Appropriate pace and pauses

### Voice Quality
- Clear pronunciation
- 16kHz+ sample rate
- Low background noise
- Natural breathing patterns
- Appropriate volume levels

### Response Times
- **Greeting**: <500ms
- **Question generation**: <1 second
- **TTS**: <1 second
- **Total latency**: <2.5 seconds

---

## 🧠 AI Intelligence Required

### Intent Detection
```python
intents = {
    'emergency': ['burst', 'leak', 'power', 'gas', 'flood', 'urgent'],
    'plumbing': ['pipe', 'water', 'drain', 'tap', 'toilet'],
    'electrical': ['power', 'light', 'wire', 'switch', 'circuit'],
    'hvac': ['heat', 'cool', 'air', 'conditioning', 'temperature'],
    'general': ['repair', 'fix', 'help', 'maintenance']
}
```

### Entity Extraction
```python
entities = {
    'person_name': ["I'm John", "My name is Sarah", "This is Mike"],
    'address': ["42 Smith Street", "apartment 5, level 3"],
    'phone': ["+61412345678", "0412 345 678"],
    'time_preference': ["morning", "afternoon", "tomorrow", "ASAP"]
}
```

### Context Management
- Remember what was said previously
- Build conversation history
- Maintain job details
- Handle interruptions
- Clarify ambiguities

---

## 📱 Customer SMS Templates

### Booking Confirmation
```
Hi [Name]! Your [Service] appointment is confirmed for
[Date] at [Time].
Reference: #[JobID]
Reply with RESCHEDULE to change time
```

### Reminder (24h before)
```
Reminder: Your [Service] appointment is tomorrow at [Time]
at [Address]. We'll be there!
Reply CANCEL to cancel
```

### Emergency Alert (to owner)
```
EMERGENCY: [Customer] called about "[Issue]"
Address: [Address]
Phone: [Phone]
Action: Job created #[JobID]
URGENT - Contact customer ASAP
```

---

## 🎯 Success Metrics

### Performance
- ✅ Answer time: <2 seconds
- ✅ Transcription accuracy: >95%
- ✅ Booking completion rate: >85%
- ✅ Emergency detection: >99%
- ✅ Call duration: 3-7 minutes avg

### Customer Experience
- ✅ Natural conversation flow
- ✅ No dropped calls
- ✅ Clear confirmations
- ✅ Accurate job details
- ✅ Timely SMS delivery

### Business Metrics
- ✅ Jobs created per call: >95%
- ✅ Customer satisfaction: >90%
- ✅ Emergency response: <5 min
- ✅ No missed bookings
- ✅ Correct customer details: >98%

---

## 📅 Implementation Timeline

### Week 1: Voice Pipeline
- [ ] LiveKit inbound call handler
- [ ] Audio streaming setup
- [ ] Speech-to-text integration
- [ ] Text-to-speech integration

### Week 2: Conversation Engine
- [ ] Intent detection system
- [ ] Entity extraction
- [ ] State machine implementation
- [ ] Context management

### Week 3: Job Creation & Booking
- [ ] Auto-create jobs from calls
- [ ] Smart availability checking
- [ ] Booking confirmation logic
- [ ] SMS integration

### Week 4: Emergency System
- [ ] Emergency keyword detection
- [ ] Escalation logic
- [ ] SMS alerts
- [ ] Dashboard notifications

### Week 5: Integration & Testing
- [ ] ServiceM8 integration
- [ ] Google Maps integration
- [ ] Twilio SMS setup
- [ ] End-to-end testing

### Week 6: Refinement & Launch
- [ ] Call quality optimization
- [ ] Voice training (Australian accent)
- [ ] Performance tuning
- [ ] Documentation
- [ ] Beta launch

---

## 🚀 Deployment Checklist

- [ ] Voice system fully tested
- [ ] Australian accent verified
- [ ] Emergency detection 99%+ accurate
- [ ] Job creation automation working
- [ ] SMS delivery confirmed
- [ ] ServiceM8 integration live
- [ ] Call recording working
- [ ] Dashboard updated for calls
- [ ] Documentation complete
- [ ] Support team trained
- [ ] Customer SLAs defined
- [ ] Monitoring & alerts set up

---

## 📞 Support & Monitoring

### Monitoring Points
- Call success rate
- Transcription accuracy
- Response time latency
- SMS delivery status
- Emergency escalation logs
- Job creation accuracy
- Customer satisfaction

### Alert Triggers
- >10% call failure rate
- <90% transcription accuracy
- Response time >3 seconds
- SMS delivery failures
- Emergency detection miss
- System errors

---

## 💡 Future Enhancements

- [ ] Customer portal to reschedule/cancel
- [ ] Call transfer to human agent
- [ ] Multi-language support
- [ ] Predictive scheduling
- [ ] Customer history lookup
- [ ] Callback option if busy
- [ ] Integration with CRM
- [ ] Advanced analytics dashboard

