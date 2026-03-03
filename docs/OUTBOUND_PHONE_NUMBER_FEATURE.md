# Outbound Phone Number Feature

**Date:** 2026-02-03
**Purpose:** Store phone number alongside trunk ID so call logs display the correct "From Number" per user

---

## Problem (Before)

The "From Number" column in call logs was showing a **hardcoded value** from an environment variable, regardless of which user made the call or which trunk they had configured.

### Previous Code:

**routes/agents.py:432**
```python
from_number=os.environ.get('SAUDI_PHONE_NUMBER', '966115108724'),
```

**routes/api_v1.py:258**
```python
from_number=os.environ.get('SAUDI_PHONE_NUMBER', 'API'),
```

**routes/public_api.py:219**
```python
from_number=os.environ.get('SAUDI_PHONE_NUMBER', '966115108724'),
```

This meant all users saw the same "From Number" in their call logs, even though each user could have a different SIP trunk with a different phone number.

---

## Solution (After)

Added `outbound_phone_number` field to the User model, allowing admins to configure a phone number for each user's trunk. The CallLog now uses this user-specific phone number with a fallback to the environment variable.

---

## Files Changed

### 1. models.py (Line 31)

**Before:**
```python
# SIP Trunk Configuration (for outbound calls)
outbound_trunk_id = db.Column(db.String(100), nullable=True)
sip_configured = db.Column(db.Boolean, default=False)
```

**After:**
```python
# SIP Trunk Configuration (for outbound calls)
outbound_trunk_id = db.Column(db.String(100), nullable=True)
outbound_phone_number = db.Column(db.String(20), nullable=True)  # Phone number for the outbound trunk
sip_configured = db.Column(db.Boolean, default=False)
```

---

### 2. routes/core.py (Lines 574-582)

**Before:**
```python
if request.method == 'POST':
    outbound_trunk_id = request.form.get('outbound_trunk_id', '').strip()
    sip_notes = request.form.get('sip_notes', '').strip()

    # Update user trunk configuration
    user.outbound_trunk_id = outbound_trunk_id if outbound_trunk_id else None
    user.sip_configured = bool(outbound_trunk_id)
    user.sip_configured_at = datetime.now(SAUDI_TZ).replace(tzinfo=None) if outbound_trunk_id else None
    user.sip_notes = sip_notes if sip_notes else None
```

**After:**
```python
if request.method == 'POST':
    outbound_trunk_id = request.form.get('outbound_trunk_id', '').strip()
    outbound_phone_number = request.form.get('outbound_phone_number', '').strip()
    sip_notes = request.form.get('sip_notes', '').strip()
    
    #outbound_phone_number = request.form.get('outbound_phone_number', '').strip()

    # Update user trunk configuration
    user.outbound_trunk_id = outbound_trunk_id if outbound_trunk_id else None
    user.outbound_phone_number = outbound_phone_number if outbound_phone_number else None
    user.sip_configured = bool(outbound_trunk_id)
    user.sip_configured_at = datetime.now(SAUDI_TZ).replace(tzinfo=None) if outbound_trunk_id else None
    user.sip_notes = sip_notes if sip_notes else None
```

---

### 3. routes/core.py - remove_user_trunk() (Line 605)

**Before:**
```python
user.outbound_trunk_id = None
user.sip_configured = False
user.sip_configured_at = None
user.sip_notes = None
```

**After:**
```python
user.outbound_trunk_id = None
user.outbound_phone_number = None
user.sip_configured = False
user.sip_configured_at = None
user.sip_notes = None
```

---

### 4. routes/agents.py (Line 432)

**Before:**
```python
call_log = CallLog(
    user_id=user.id,
    agent_id=agent_id,
    from_number=os.environ.get('SAUDI_PHONE_NUMBER', '966115108724'),
    to_number=phone_number,
    room_name=room_name,
    status='initiated'
)
```

**After:**
```python
call_log = CallLog(
    user_id=user.id,
    agent_id=agent_id,
    from_number=user.outbound_phone_number or os.environ.get('SAUDI_PHONE_NUMBER', '966115108724'),
    to_number=phone_number,
    room_name=room_name,
    status='initiated'
)
```

---

### 5. routes/api_v1.py (Line 258)

**Before:**
```python
call_log = CallLog(
    user_id=user.id,
    agent_id=agent_id,
    from_number=os.environ.get('SAUDI_PHONE_NUMBER', 'API'),
    to_number=formatted_number,
    room_name=room_name,
    status='initiated',
    call_type='outbound'
)
```

**After:**
```python
call_log = CallLog(
    user_id=user.id,
    agent_id=agent_id,
    from_number=user.outbound_phone_number or os.environ.get('SAUDI_PHONE_NUMBER', 'API'),
    to_number=formatted_number,
    room_name=room_name,
    status='initiated',
    call_type='outbound'
)
```

---

### 6. routes/public_api.py (Line 219)

**Before:**
```python
call_log = CallLog(
    user_id=user.id,
    agent_id=54,
    from_number=os.environ.get('SAUDI_PHONE_NUMBER', '966115108724'),
    to_number=formatted_number,
    room_name=room_name,
    status='initiated',
    call_type='outbound'
)
```

**After:**
```python
call_log = CallLog(
    user_id=user.id,
    agent_id=54,
    from_number=user.outbound_phone_number or os.environ.get('SAUDI_PHONE_NUMBER', '966115108724'),
    to_number=formatted_number,
    room_name=room_name,
    status='initiated',
    call_type='outbound'
)
```

---

### 7. routes/core.py - Campaign Call Log (Lines 1032-1044)

**Before:**
```python
call_log = CallLog(
    user_id=campaign.user_id,
    agent_id=campaign.agent_id,
    from_number=sip_info.get('trunk_phone_number', 'campaign'),
    to_number=sip_info.get('phone_number', contact.phone_number),
    ...
)
```

**After:**
```python
# Get user's configured phone number (consistent with agents.py)
campaign_user = db.session.get(User, campaign.user_id)
user_from_number = (
    campaign_user.outbound_phone_number
    if campaign_user and campaign_user.outbound_phone_number
    else sip_info.get('trunk_phone_number', 'campaign')
)

call_log = CallLog(
    user_id=campaign.user_id,
    agent_id=campaign.agent_id,
    from_number=user_from_number,
    to_number=sip_info.get('phone_number', contact.phone_number),
    ...
)
```

This ensures campaign outbound calls also use `user.outbound_phone_number` consistently with manual outbound calls.

---

### 9. templates/admin/admin_configure_trunk.html (After Line 103)

**Added new input field:**
```html
<!-- Outbound Phone Number -->
<div class="mb-6">
    <label for="outbound_phone_number" class="block text-sm font-semibold text-gray-700 mb-2 flex items-center gap-2">
        <i class="bi bi-telephone text-indigo-600"></i>
        Outbound Phone Number
    </label>
    <input type="text"
           class="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all text-gray-900 font-mono text-sm"
           id="outbound_phone_number"
           name="outbound_phone_number"
           value="{{ user.outbound_phone_number or '' }}"
           placeholder="e.g., 966115108724">
    <p class="mt-2 text-sm text-gray-600">
        <i class="bi bi-info-circle"></i>
        Enter the phone number associated with this trunk (will be shown as "From Number" in call logs)
    </p>
</div>
```

---

### 10. templates/admin/admin_trunk_management.html

**Added table header (Line 71):**
```html
<th class="text-left py-3 px-6 text-xs font-semibold text-gray-600 uppercase tracking-wider">Phone Number</th>
```

**Added table cell (After Line 111):**
```html
<!-- Phone Number -->
<td class="py-4 px-6">
    {% if user.outbound_phone_number %}
    <code class="text-xs bg-blue-50 px-2 py-1 rounded font-mono text-blue-800">{{ user.outbound_phone_number }}</code>
    {% else %}
    <span class="text-sm text-gray-400 italic">None</span>
    {% endif %}
</td>
```

---

## New Files Created

### migrations/add_outbound_phone_number.py

Python migration script to add the column to the database.

### migrations/add_outbound_phone_number.sql

SQL migration script (reference only):
```sql
ALTER TABLE user ADD COLUMN outbound_phone_number VARCHAR(20);
```

---

## Database Migration

Run the Python migration script:
```bash
python migrations/add_outbound_phone_number.py
```

Or manually run the SQL:
```sql
ALTER TABLE user ADD COLUMN outbound_phone_number VARCHAR(20);
```

---

## How It Works Now

1. **Admin configures trunk** at `/admin/trunk-management`
2. Admin enters both **Trunk ID** and **Phone Number** for each user
3. When a call is made, the system uses:
   - `user.outbound_phone_number` if configured
   - Falls back to `SAUDI_PHONE_NUMBER` environment variable if not configured
4. **Call Logs** now display the correct "From Number" per user

---

## Fallback Logic

```python
from_number = user.outbound_phone_number or os.environ.get('SAUDI_PHONE_NUMBER', '966115108724')
```

- If user has `outbound_phone_number` configured: Use that
- If not: Fall back to environment variable (existing behavior)

---

## Summary: All Outbound Call Locations

| File | Call Type | `from_number` Source | Status |
|------|-----------|---------------------|--------|
| `routes/agents.py:432` | Manual outbound | `user.outbound_phone_number` | ✅ Fixed |
| `routes/api_v1.py:258` | API outbound | `user.outbound_phone_number` | ✅ Fixed |
| `routes/public_api.py:219` | Public API outbound | `user.outbound_phone_number` | ✅ Fixed |
| `routes/core.py:1044` | Campaign outbound | `user.outbound_phone_number` | ✅ Fixed |

All outbound call types now consistently use `user.outbound_phone_number` with fallback to environment variable.
