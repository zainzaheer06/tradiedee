# Room Name Format Feature

**Date:** 2026-02-03
**Purpose:** Add username and phone number to room_name for better call identification and debugging

---

## Problem (Before)

The `room_name` only contained `agent_id` and `timestamp`, making it difficult to:
- Identify which user initiated the call
- Know which phone number was being called
- Debug issues in LiveKit dashboard

### Previous Code:

**routes/agents.py:426**
```python
room_name = f"call-{agent_id}-{datetime.now(SAUDI_TZ).timestamp()}"
```

**agents/app.py:810**
```python
room_name = f"call-{agent_id}-{datetime.now(timezone.utc).timestamp()}"
```

**routes/api_v1.py:240**
```python
room_name = f"api-{agent_id}-{int(timestamp)}"
```

---

## Solution (After)

Added `username` and last 4 digits of `phone_number` to the room_name format for better identification.

**New Format:**
```
call-{agent_id}-{username}-{phone_last_4}-{timestamp}
```

**Example:**
```
call-15-mzain-1234-1738590000.123456
```

---

## Files to Change

### 1. routes/agents.py (Line 426) - Outbound Call

**Before:**
```python
# Make the call with formatted number
room_name = f"call-{agent_id}-{datetime.now(SAUDI_TZ).timestamp()}"
asyncio.run(make_livekit_call(formatted_number, room_name, agent.name, outbound_trunk_id, agent_id, webhook_context))
```

**After:**
```python
# Make the call with formatted number
room_name = f"call-{agent_id}-{user.username}-{phone_number[-4:]}-{datetime.now(SAUDI_TZ).timestamp()}"
asyncio.run(make_livekit_call(formatted_number, room_name, agent.name, outbound_trunk_id, agent_id, webhook_context))
```

---

### 2. agents/app.py (Line 810) - Outbound Call (Legacy)

**Before:**
```python
# Make the call with formatted number
room_name = f"call-{agent_id}-{datetime.now(timezone.utc).timestamp()}"
asyncio.run(make_livekit_call(formatted_number, room_name, agent.name, outbound_trunk_id))
```

**After:**
```python
# Make the call with formatted number
room_name = f"call-{agent_id}-{user.username}-{phone_number[-4:]}-{datetime.now(timezone.utc).timestamp()}"
asyncio.run(make_livekit_call(formatted_number, room_name, agent.name, outbound_trunk_id))
```

---

### 3. routes/api_v1.py (Line 240) - API Call

**Before:**
```python
room_name = f"api-{agent_id}-{int(timestamp)}"
```

**After:**
```python
room_name = f"api-{agent_id}-{user.username}-{formatted_number[-4:]}-{int(timestamp)}"
```

---

### 4. routes/agents.py (Line 803) - Inbound Call (Optional)

**Before:**
```python
room_name = f"inbound-{agent.id}-{int(time.time())}"
```

**After:**
```python
room_name = f"inbound-{agent.id}-{caller_number[-4:]}-{int(time.time())}"
```

*Note: Inbound calls may not have username context, only caller number.*

---

### 5. routes/public_api.py (Line 210) - Website Call (Optional)

**Before:**
```python
room_name = f"website-{datetime.now(SAUDI_TZ).timestamp()}"
```

**After:**
```python
room_name = f"website-{user.username}-{formatted_number[-4:]}-{datetime.now(SAUDI_TZ).timestamp()}"
```

---

### 6. services/campaign_worker.py (Line 284) - Campaign Call

**Before:**
```python
room_name = f"campaign_{campaign['id']}_contact_{contact['id']}_{int(time.time())}"
```

**After:**
```python
room_name = f"campaign_{campaign['id']}_contact_{contact['id']}_user_{campaign['user_id']}_{int(time.time())}"
```

*Added `user_id` for tracking which user initiated the campaign.*

---

## Available Variables Per File

| File | user.username | phone_number | Notes |
|------|---------------|--------------|-------|
| routes/agents.py | Yes | Yes | From request.form |
| agents/app.py | Yes | Yes | From request.form |
| routes/api_v1.py | Yes | Yes (formatted_number) | From JSON body |
| routes/public_api.py | Yes | Yes (formatted_number) | From JSON body |
| routes/agents.py (inbound) | No | caller_number | Inbound context |
| services/campaign_worker.py | No | contact['phone'] | Campaign context |

---

## Room Name Patterns Summary

| Call Type | Old Format | New Format |
|-----------|------------|------------|
| Outbound | `call-{agent_id}-{timestamp}` | `call-{agent_id}-{username}-{phone_last4}-{timestamp}` |
| API | `api-{agent_id}-{timestamp}` | `api-{agent_id}-{username}-{phone_last4}-{timestamp}` |
| Website | `website-{timestamp}` | `website-{username}-{phone_last4}-{timestamp}` |
| Inbound | `inbound-{agent_id}-{timestamp}` | `inbound-{agent_id}-{caller_last4}-{timestamp}` |
| Campaign | `campaign_{id}_contact_{id}_{timestamp}` | `campaign_{id}_contact_{id}_user_{user_id}_{timestamp}` |
| Demo | `demo-{random}` | No change needed |
| Test | `call-{agent_id}-test-{timestamp}` | No change needed |

---

## Benefits

1. **Better Debugging** - Easily identify calls in LiveKit dashboard
2. **User Tracking** - Know which user initiated each call
3. **Phone Identification** - See destination number at a glance
4. **Call Correlation** - Match room names with call logs more easily

---

## Implementation Notes

- Using `phone_number[-4:]` to keep room names reasonably short
- Username is included directly (should not contain special characters)
- Timestamp remains for uniqueness
- No database changes required - this only affects runtime room naming
