# CallTradie Frontend Updates

## Summary of Changes (2026-03-02)

### Files Updated:
1. **templates/jobs/dashboard.html** - Redesigned with CallTradie card view
2. **templates/jobs/detail.html** - Enhanced SMS confirmation display

---

## Job Dashboard (`/jobs/`) - New Card View

### Layout
- **Grid Layout**: 2 columns on large screens, 1 column on mobile
- **Card Style**: Individual job cards with status-based styling
- **New Feature**: Quick overview of all job data in a single card

### Each Job Card Shows:

```
┌────────────────────────────────────────────┐
│ John Smith              [Status Badge] 🚨  │
│ Job #456                                   │
├────────────────────────────────────────────┤
│ 📞 Phone                                   │
│ +61412345678                               │
│                                            │
│ 🔧 Service Type                           │
│ [Plumbing Badge]                          │
│                                            │
│ 📍 Address                                 │
│ 42 Smith Street, Sydney NSW 2000          │
│                                            │
│ 🕐 Appointment                            │
│ Thursday 10:00 AM                         │
│                                            │
│ ⚡ Priority                                │
│ [URGENT / High / Normal Badge]            │
│                                            │
│ Issue: Leaking tap in kitchen...          │
│                                            │
│ 💬 SMS Status: [Sent / Queued / Failed]   │
│                                            │
│ [View Details] [Call Customer]            │
└────────────────────────────────────────────┘
```

### Status Badge Colors:
- **New** (Yellow): Just created from call
- **Scheduled** (Blue): Time booked
- **In Progress** (Info Blue): Currently working
- **Completed** (Green): Job finished

### Emergency Highlighting:
- Emergency jobs have **RED left border**
- 🚨 EMERGENCY badge in red
- Shows urgency at glance

### Priority Display:
- 🚨 **URGENT** - Emergency detected
- ⚠️ **High** - High priority
- Normal - Regular appointment

---

## Job Detail Page (`/jobs/{id}`) - Enhanced View

### Sections Updated:

#### 1. Customer Information
- Name
- Phone (clickable to call)
- Email
- Full Address
- All extracted from call transcription

#### 2. Job Details
- Job Type (Plumbing, Electrical, HVAC, etc.)
- Description (from customer's first message)
- Call Summary (AI generated)

#### 3. Scheduling
- Scheduled Date & Time
- Estimated Duration
- Actual Duration (after completion)

#### 4. Address Validation
- Validation Status (Pending/Valid/Invalid)
- GPS Coordinates (lat, lng)
- Maps integration ready

#### 5. Emergency Information (if applicable)
- Emergency Status: YES/NO
- Keywords Detected: [burst, leak, flooding, etc.]
- Escalation Log

#### 6. **SMS Confirmations** (NEW - ENHANCED)

```
┌────────────────────────────────────┐
│ 💬 SMS Confirmations              │
├────────────────────────────────────┤
│ ✅ Appointment Confirmation        │
│    Sent to: +61412345678          │
│    01 Mar 2026 at 03:45 PM        │
│    Status: [Sent ✓]               │
│                                    │
│    "Hi John! Your plumbing        │
│    appointment confirmed for      │
│    Thursday 10am at 42 Smith St." │
│                                    │
│ 🔔 Appointment Reminder            │
│    Sent to: +61412345678          │
│    02 Mar 2026 at 09:00 AM        │
│    Status: [Delivered ✓✓]         │
│                                    │
│    "Reminder: Your appointment    │
│    is today at 10am..."           │
└────────────────────────────────────┘
```

### SMS Display Features:
- **Message Type Icons**:
  - ✅ Confirmation
  - 🔔 Reminder
  - 🚨 Emergency Alert
  - 📨 Other

- **Status Badge**:
  - Green: Delivered ✓✓
  - Blue: Sent ✓
  - Yellow: Queued (waiting to send)
  - Red: Failed

- **Full Message Text**: Shows complete SMS content

---

## Data Displayed on Frontend

### From Job Record:
```python
job = {
    'id': 456,
    'customer_name': 'John Smith',           # Extracted from "My name is..."
    'customer_phone': '+61412345678',        # Extracted from phone spoken
    'customer_address': '42 Smith Street',   # Extracted from address spoken
    'customer_suburb': 'Sydney',             # Extracted from address
    'job_type': 'plumbing',                  # Extracted from keywords
    'description': 'Leaking tap in kitchen', # Extracted from first message
    'is_emergency': False,                   # Detected from keywords
    'urgency': 'normal',                     # Calculated from keywords
    'scheduled_datetime': '2026-03-05 10:00',# From booking
    'call_transcript': '...',                # Full conversation
    'status': 'new',                         # Current job status
    'created_at': '2026-03-02 03:45:00'     # When call was recorded
}
```

### From SMS Log:
```python
sms = {
    'id': 789,
    'job_id': 456,
    'recipient_phone': '+61412345678',           # Customer phone
    'message_type': 'confirmation',              # confirmation/reminder/emergency
    'message_text': 'Hi John! Your appointment...', # Full SMS text
    'delivery_status': 'sent',                   # queued/sent/delivered/failed
    'sent_at': '2026-03-02 03:45:00'            # When SMS was sent
}
```

---

## Visual Examples

### Example 1: Fresh Call - "New" Job Card
```
┌─────────────────────────────────────┐
│ John Smith          [NEW] [YELLOW]  │
│ Job #456                            │
├─────────────────────────────────────┤
│ 📞 +61412345678                     │
│ 🔧 [Plumbing]                      │
│ 📍 42 Smith Street, Sydney          │
│ 🕐 Thursday 10:00 AM                │
│ ⚡ Normal                            │
│ Issue: Leaking tap in kitchen...    │
│ 💬 SMS: [Sent]                      │
│ [View Details] [Call Customer]      │
└─────────────────────────────────────┘
```

### Example 2: Emergency Job Card
```
┌─────────────────────────────────────┐
│█ Sarah Jones       [IN PROGRESS] 🚨 │
│ Job #457                            │
├─────────────────────────────────────┤
│ 📞 +61487654321                     │
│ 🔧 [Electrical]                    │
│ 📍 88 Main Street, Melbourne        │
│ 🕐 Today 1:30 PM                    │
│ ⚡ 🚨 URGENT                         │
│ Issue: Power outage - no electri... │
│ 💬 SMS: [Delivered]                 │
│ [View Details] [Call Customer]      │
└─────────────────────────────────────┘
```

---

## Key Features Added

### ✅ Card-Based Layout
- Modern, responsive grid layout
- Touch-friendly for mobile
- Hover effects for interactivity

### ✅ Status Indicators
- Color-coded status badges
- Emergency highlighting with left border
- Priority level badges

### ✅ Customer Information
- Phone number (clickable)
- Full address display
- Service type badge
- Issue description preview

### ✅ SMS Confirmations
- Message type icons
- Delivery status indicator
- Full message text display
- Timestamp for sent date/time

### ✅ Quick Actions
- "View Details" button → Full job detail page
- "Call Customer" button → Initiates phone call

### ✅ Responsive Design
- 2-column grid on desktop
- 1-column stack on mobile
- All cards expand smoothly on hover

---

## Testing the Frontend

### 1. Create a Test Job via Webhook
```bash
curl -X POST http://localhost:5003/webhook/call-ended \
  -H "Content-Type: application/json" \
  -d '{
    "room_name": "call-test-123",
    "duration": 300,
    "transcription": "AGENT: Hello. CUSTOMER: Hi, I am John Smith and I have a burst pipe at 42 Smith Street",
    "metadata": {
      "messages": [
        {"role": "agent", "text": "Hello"},
        {"role": "user", "text": "Hi, I am John Smith and I have a burst pipe at 42 Smith Street"}
      ],
      "sip_info": {
        "phone_number": "+61412345678",
        "trunk_phone_number": "+61298765432",
        "call_status": "active"
      }
    }
  }'
```

### 2. View in Dashboard
```
Navigate to: http://localhost:5000/jobs/
You should see the new job card with:
- Customer Name: John Smith
- Phone: +61412345678
- Address: 42 Smith Street
- Job Type: Plumbing (extracted from "burst pipe")
- Is Emergency: YES (detected from "burst pipe")
- Status: New
- SMS Status: Queued
```

### 3. View Job Details
Click "View Details" button to see:
- Full customer information
- Call transcript
- SMS confirmations sent
- Emergency information (if applicable)

---

## CSS Classes Added

```css
.job-card              /* Main job card container */
.job-card:hover        /* Hover effect */
.job-card.border-danger /* Emergency jobs */
.job-card.border-primary /* New jobs */
.job-card .card-title  /* Customer name */
.job-card .badge       /* Status badges */
.job-card .btn-sm      /* Action buttons */
```

---

**Status:** ✅ **FRONTEND READY FOR TESTING**

The frontend now displays:
- Job records with all extracted customer details
- SMS confirmation status and content
- Emergency indicators
- Professional card-based UI
- Responsive design for all devices
