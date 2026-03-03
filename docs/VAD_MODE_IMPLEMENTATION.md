# VAD Mode Implementation Guide

## Overview

Voice Activity Detection (VAD) Mode is a per-agent configuration that controls how the AI agent detects when a user has finished speaking. This allows optimizing agent behavior for different use cases.

**Date Implemented:** 2025-01-30

---

## VAD Mode Options

| Mode | Value | Best For | Behavior |
|------|-------|----------|----------|
| **Precise** | `'precise'` | Collecting phone numbers, addresses, data | No VAD - waits for complete input before responding |
| **Natural** | `'natural'` | General conversations, support calls | Semantic VAD - AI detects natural turn completion |
| **Dynamic** | `'dynamic'` | Quick Q&A, fast support (DEFAULT) | Server VAD - responds after short silence |

---

## Technical Details

### Precise Mode (`vad_mode = 'precise'`)
```python
# turn_detection parameter is OMITTED (not passed at all)
# API uses its default behavior
```
- **No custom VAD configuration**
- `turn_detection` parameter is completely omitted from API call
- API uses its default behavior
- Best when users need to dictate numbers or detailed information

### Natural Mode (`vad_mode = 'natural'`)
```python
turn_detection = TurnDetection(
    type="semantic_vad",
    eagerness="auto",
    create_response=True,
    interrupt_response=True,
)
```
- **AI-based turn detection**
- Uses semantic understanding to detect when user has finished their thought
- Balanced between speed and accuracy
- Good for natural flowing conversations

### Dynamic Mode (`vad_mode = 'dynamic'`) - DEFAULT
```python
turn_detection = TurnDetection(
    type="server_vad",
    threshold=0.45,
    prefix_padding_ms=150,
    silence_duration_ms=250,
    create_response=True,
    interrupt_response=True,
)
```
- **Silence-based detection**
- Responds after 250ms of silence
- Fastest response time
- May occasionally interrupt if user pauses mid-sentence

---

## Implementation Method: **kwargs

We use the `**kwargs` pattern to conditionally include/omit the `turn_detection` parameter:

```python
# Build base model kwargs
model_kwargs = {
    'model': "gpt-realtime-2025-08-28",
    'modalities': ["text"],
    'temperature': llm_temperature,
    'input_audio_transcription': InputAudioTranscription(...),
}

# Only add turn_detection if NOT precise mode
if vad_mode == 'precise':
    # Don't add turn_detection - parameter is omitted entirely
    pass
elif vad_mode == 'natural':
    model_kwargs['turn_detection'] = TurnDetection(type="semantic_vad", ...)
else:  # 'dynamic'
    model_kwargs['turn_detection'] = TurnDetection(type="server_vad", ...)

# Unpack kwargs - precise mode won't have turn_detection key
return RealtimeModel(**model_kwargs)
```

### Why **kwargs?

| Approach | `turn_detection=None` | Omit parameter |
|----------|----------------------|----------------|
| Behavior | ❌ Explicitly disabled (may break) | ✅ API uses default |
| Result | API might not respond | Works correctly |

### Performance Impact

**Zero performance concerns:**

| Operation | Time | Impact |
|-----------|------|--------|
| Dict creation | ~50 ns | Negligible |
| `**kwargs` unpacking | ~100 ns | Negligible |
| API call | ~200,000,000 ns | 99.99999% of time |

The kwargs method adds approximately **0.00008%** overhead - completely negligible.

---

## Files Modified

### 1. Database Model
**File:** `models.py`
**Line:** 48

```python
class Agent(db.Model):
    # ... existing fields ...
    temperature = db.Column(db.Float, default=0.4, nullable=True)
    vad_mode = db.Column(db.String(20), default='dynamic')  # NEW FIELD
    created_at = db.Column(db.DateTime, ...)
```

### 2. Migration Script
**File:** `migrations/add_agent_vad_mode.py`

```bash
# Run migration
python migrations/add_agent_vad_mode.py
```

**What it does:**
- Adds `vad_mode` column to `agent` table
- Sets default value `'dynamic'` for all existing agents
- Creates database backup before migration

### 3. Agent Server (Redis Cache + VAD Logic)
**File:** `agent-after-promotheus-after-precall-webhook.py`

#### SQL Query (Line 137)
```sql
SELECT id, name, prompt, greeting, voice_id, voice_name, temperature, vad_mode
FROM agent
WHERE id = ?
```

#### Config Dict (Line 146-155)
```python
config = {
    'id': row['id'],
    'name': row['name'],
    'prompt': row['prompt'],
    'greeting': row['greeting'] or 'Default greeting...',
    'voice_id': row['voice_id'],
    'voice_name': row['voice_name'],
    'temperature': row['temperature'] or 0.4,
    'vad_mode': row['vad_mode'] or 'dynamic'  # NEW FIELD
}
```

#### VAD Logic in init_llm() using **kwargs (Line 1263-1307)
```python
async def init_llm():
    llm_temperature = agent_config.get('temperature', 0.4)
    vad_mode = agent_config.get('vad_mode', 'dynamic')

    logger.info(f"🎙️ VAD Mode: {vad_mode}")

    # Build base model kwargs
    model_kwargs = {
        'model': "gpt-realtime-2025-08-28",
        'modalities': ["text"],
        'temperature': llm_temperature,
        'input_audio_transcription': InputAudioTranscription(
            model="gpt-4o-transcribe",
            language="ar",
        ),
    }

    # Only add turn_detection if NOT precise mode
    if vad_mode == 'precise':
        # Don't add turn_detection - API uses its default behavior
        logger.info("🎙️ VAD: Not set (Precise mode - API default)")
    elif vad_mode == 'natural':
        # Semantic VAD - AI detects natural turn completion
        model_kwargs['turn_detection'] = TurnDetection(
            type="semantic_vad",
            eagerness="auto",
            create_response=True,
            interrupt_response=True,
        )
        logger.info("🎙️ VAD: Semantic (Natural mode)")
    else:  # 'dynamic' (default)
        # Server VAD - fast, silence-based detection
        model_kwargs['turn_detection'] = TurnDetection(
            type="server_vad",
            threshold=0.45,
            prefix_padding_ms=150,
            silence_duration_ms=250,
            create_response=True,
            interrupt_response=True,
        )
        logger.info("🎙️ VAD: Server with 250ms silence (Dynamic mode)")

    return RealtimeModel(**model_kwargs)
```

### 4. Frontend Form
**File:** `templates/agents/new_agent_form.html`
**Lines:** 158-170

```html
<!-- VAD Mode Selection -->
<div>
    <label for="vad_mode" class="block text-sm font-semibold text-gray-700 mb-2">
        Response Mode
    </label>
    <select id="vad_mode" name="vad_mode"
            class="w-full px-4 py-3 border border-gray-300 rounded-lg ...">
        <option value="precise" {% if agent and agent.vad_mode == 'precise' %}selected{% endif %}>
            Precise (Best for collecting numbers)
        </option>
        <option value="natural" {% if agent and agent.vad_mode == 'natural' %}selected{% endif %}>
            Natural (Balanced conversation)
        </option>
        <option value="dynamic" {% if agent and agent.vad_mode == 'dynamic' %}selected{% elif not agent %}selected{% endif %}>
            Dynamic (Fast responses)
        </option>
    </select>
    <p class="text-xs text-gray-500 mt-1">
        Controls how the agent detects when you've finished speaking
    </p>
</div>
```

### 5. Routes (Form Handler)
**File:** `routes/agents.py`

#### In new_agent_form() POST:
```python
vad_mode = request.form.get('vad_mode', 'dynamic')

new_agent = Agent(
    user_id=session['user_id'],
    name=name,
    prompt=prompt,
    # ... other fields ...
    vad_mode=vad_mode,
)
```

#### In edit_agent_form() POST:
```python
agent.vad_mode = request.form.get('vad_mode', 'dynamic')
```

---

## Deployment Checklist

### Server Deployment

1. **Update model file**
   ```bash
   # Copy updated models.py to server
   ```

2. **Run database migration**
   ```bash
   python migrations/add_agent_vad_mode.py
   ```

3. **Update agent server file**
   ```bash
   # Copy updated agent-after-promotheus-after-precall-webhook.py
   ```

4. **Update routes file**
   ```bash
   # Copy updated routes/agents.py (or agents_server.py)
   ```

5. **Update template file**
   ```bash
   # Copy updated templates/agents/new_agent_form.html
   ```

6. **Restart services**
   ```bash
   # Restart Flask app
   # Restart agent server
   ```

7. **Clear Redis cache** (optional, will auto-refresh)
   ```bash
   redis-cli FLUSHALL
   # Or wait for cache TTL (1 hour) to expire
   ```

---

## Testing

### Test Each Mode

1. **Create agent with Dynamic mode** (default)
   - Should respond quickly after short pauses
   - Best for quick Q&A

2. **Change agent to Precise mode**
   - Should wait for complete input
   - Test with phone number dictation: "9 6 6 5 5 1 2 3 4 5 6 7"
   - Agent should capture all digits

3. **Change agent to Natural mode**
   - Should feel more conversational
   - AI determines when user has finished

### Verify Redis Cache

```python
# Check cached agent config
import redis
r = redis.Redis()
config = r.get('agent:config:123')  # Replace 123 with agent_id
print(config)  # Should include 'vad_mode'
```

### Verify Logs

Look for these log messages:
```
🎙️ VAD Mode: precise
🎙️ VAD: Not set (Precise mode - API default, best for number collection)

🎙️ VAD Mode: natural
🎙️ VAD: Semantic (Natural mode - AI-based turn detection)

🎙️ VAD Mode: dynamic
🎙️ VAD: Server with 250ms silence (Dynamic mode - fast responses)
```

---

## Troubleshooting

### VAD mode not changing?

1. **Clear Redis cache:**
   ```bash
   redis-cli DEL agent:config:123  # Replace with agent_id
   ```

2. **Restart agent server**

3. **Check database:**
   ```sql
   SELECT id, name, vad_mode FROM agent WHERE id = 123;
   ```

### Migration failed?

1. **Check backup file** created by migration script
2. **Manually add column:**
   ```sql
   ALTER TABLE agent ADD COLUMN vad_mode VARCHAR(20) DEFAULT 'dynamic';
   UPDATE agent SET vad_mode = 'dynamic' WHERE vad_mode IS NULL;
   ```

### Form not saving vad_mode?

1. Check routes file has `agent.vad_mode = request.form.get('vad_mode', 'dynamic')`
2. Check form has `name="vad_mode"` attribute

---

## Summary

| Component | Location | Purpose |
|-----------|----------|---------|
| Model | `models.py:48` | Database field definition |
| Migration | `migrations/add_agent_vad_mode.py` | Add column to existing DB |
| Cache | `agent-*.py:137-155` | Include vad_mode in Redis |
| Logic | `agent-*.py:1265-1305` | Apply VAD based on mode |
| UI | `new_agent_form.html:158-170` | User selection dropdown |
| Routes | `routes/agents.py` | Handle form submission |

---

## Future Enhancements

- [ ] Add VAD mode analytics (which mode performs best)
- [ ] Allow per-call VAD override via API
- [ ] Add "Auto" mode that switches based on conversation context
- [ ] Expose VAD parameters (threshold, silence_duration) for power users
