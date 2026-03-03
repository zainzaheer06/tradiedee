# Temperature Control Feature Documentation

## Overview

The Temperature Control feature allows you to configure the creativity level of your AI voice agents on a per-agent basis. This setting controls how deterministic or creative the LLM responses will be during voice calls.

## What is Temperature?

Temperature is a parameter that controls the randomness of the AI's responses:

| Temperature | Behavior | Best For |
|-------------|----------|----------|
| **0.2** | Very Consistent | Scripted responses, surveys, strict workflows |
| **0.3** | Consistent | Customer support, appointment booking |
| **0.4** | Balanced (Default) | General-purpose agents |
| **0.5** | Slightly Creative | Conversational assistants |
| **0.6** | Creative | General assistants, FAQs |
| **0.7** | More Creative | Sales agents, persuasion |
| **0.8** | Very Creative | Objection handling, dynamic conversations |

### How It Works

- **Lower temperature (0.2-0.3)**: The AI picks the most likely response. Responses are predictable and consistent across similar inputs.
- **Higher temperature (0.7-0.8)**: The AI considers less likely options. Responses are more varied and creative.

## Implementation Details

### Database Schema

The `temperature` column was added to the `Agent` model:

```python
# models.py
class Agent(db.Model):
    # ... other fields ...
    temperature = db.Column(db.Float, default=0.4, nullable=True)
```

### Database Migration

Run this SQL to add the column to existing databases:

```sql
ALTER TABLE agent ADD COLUMN temperature FLOAT DEFAULT 0.4;
```

Or using Flask-Migrate:

```bash
flask db migrate -m "Add temperature column to agent"
flask db upgrade
```

### Files Modified

| File | Changes |
|------|---------|
| `models.py` | Added `temperature` column to Agent model |
| `routes/agents.py` | Handle temperature in create/edit agent routes |
| `templates/agents/new_agent_form.html` | Added temperature dropdown selector |
| `agent-after-promotheus-after-precall-webhook.py` | Use temperature from agent config in LLM initialization |

---

## Code Changes (Before & After)

### 1. models.py (Line 47)

**BEFORE:**
```python
# Line 45-48
voice_id = db.Column(db.String(100), default='G1L6zhS0TTaBvSr18eUY')
voice_name = db.Column(db.String(50), default='Fatima')
created_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))
```

**AFTER:**
```python
# Line 45-48
voice_id = db.Column(db.String(100), default='G1L6zhS0TTaBvSr18eUY')
voice_name = db.Column(db.String(50), default='Fatima')
temperature = db.Column(db.Float, default=0.4, nullable=True)  # LLM temperature (0.2-0.8) - controls response creativity
created_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))
```

---

### 2. routes/agents.py - Create Agent (Lines 118-130)

**BEFORE:**
```python
# Line 114-126
max_agent = db.session.query(db.func.max(Agent.user_agent_number)).filter_by(user_id=session['user_id']).scalar()
next_agent_number = (max_agent or 0) + 1

new_agent = Agent(
    user_id=session['user_id'],
    user_agent_number=next_agent_number,
    name=name,
    prompt=prompt,
    greeting=greeting,
    voice_id=voice_id,
    voice_name=voice_name
)
```

**AFTER:**
```python
# Line 114-130
max_agent = db.session.query(db.func.max(Agent.user_agent_number)).filter_by(user_id=session['user_id']).scalar()
next_agent_number = (max_agent or 0) + 1

# Get temperature value from form (default: 0.4)
temperature = float(request.form.get('temperature', 0.4))

new_agent = Agent(
    user_id=session['user_id'],
    user_agent_number=next_agent_number,
    name=name,
    prompt=prompt,
    greeting=greeting,
    voice_id=voice_id,
    voice_name=voice_name,
    temperature=temperature
)
```

---

### 3. routes/agents.py - Edit Agent (Lines 213-214)

**BEFORE:**
```python
# Line 208-216
generic_voice_id = request.form.get('voice_id', 'voice_1')
agent.voice_id = generic_to_elevenlabs_mapping.get(generic_voice_id, 'G1L6zhS0TTaBvSr18eUY')
agent.voice_name = voice_mapping.get(agent.voice_id, 'Fatima')

# Update workflow assignment
workflow_id = request.form.get('workflow_id')
```

**AFTER:**
```python
# Line 208-220
generic_voice_id = request.form.get('voice_id', 'voice_1')
agent.voice_id = generic_to_elevenlabs_mapping.get(generic_voice_id, 'G1L6zhS0TTaBvSr18eUY')
agent.voice_name = voice_mapping.get(agent.voice_id, 'Fatima')

# Update temperature (LLM creativity control)
agent.temperature = float(request.form.get('temperature', agent.temperature or 0.4))

# Update workflow assignment
workflow_id = request.form.get('workflow_id')
```

---

### 4. templates/agents/new_agent_form.html (Lines 140-156)

**BEFORE:**
```html
<!-- Line 138 - After Voice Selection div -->
                    </div>

                    <!-- Nevox Workflow Integration -->
```

**AFTER:**
```html
<!-- Line 138-156 - After Voice Selection div -->
                    </div>

                    <!-- Temperature Control (LLM Creativity) -->
                    <div>
                        <label for="temperature" class="block text-sm font-semibold text-gray-700 mb-2">
                            Temperature (Creativity Level)
                        </label>
                        <select id="temperature" name="temperature"
                                class="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none">
                            <option value="0.2" {% if agent and agent.temperature == 0.2 %}selected{% endif %}>0.2 - Very Consistent (Scripts, Surveys)</option>
                            <option value="0.3" {% if agent and agent.temperature == 0.3 %}selected{% endif %}>0.3 - Consistent (Support, Booking)</option>
                            <option value="0.4" {% if agent and agent.temperature == 0.4 %}selected{% elif not agent %}selected{% endif %}>0.4 - Balanced (Default)</option>
                            <option value="0.5" {% if agent and agent.temperature == 0.5 %}selected{% endif %}>0.5 - Slightly Creative</option>
                            <option value="0.6" {% if agent and agent.temperature == 0.6 %}selected{% endif %}>0.6 - Creative (General Assistant)</option>
                            <option value="0.7" {% if agent and agent.temperature == 0.7 %}selected{% endif %}>0.7 - More Creative (Sales)</option>
                            <option value="0.8" {% if agent and agent.temperature == 0.8 %}selected{% endif %}>0.8 - Very Creative (Objection Handling)</option>
                        </select>
                        <p class="text-xs text-gray-500 mt-1">Lower = more consistent responses, Higher = more creative/varied responses</p>
                    </div>

                    <!-- Nevox Workflow Integration -->
```

---

### 5. agent-after-promotheus-after-precall-webhook.py - SQL Query (Line 137)

**BEFORE:**
```python
# Line 136-140
cursor.execute("""
    SELECT id, name, prompt, greeting, voice_id, voice_name
    FROM agent
    WHERE id = ?
""", (agent_id,))
```

**AFTER:**
```python
# Line 136-140
cursor.execute("""
    SELECT id, name, prompt, greeting, voice_id, voice_name, temperature
    FROM agent
    WHERE id = ?
""", (agent_id,))
```

---

### 6. agent-after-promotheus-after-precall-webhook.py - Config Dict (Line 153)

**BEFORE:**
```python
# Line 146-154
config = {
    'id': row['id'],
    'name': row['name'],
    'prompt': row['prompt'],
    'greeting': row['greeting'] if row['greeting'] else '...',
    'voice_id': row['voice_id'],
    'voice_name': row['voice_name']
}
```

**AFTER:**
```python
# Line 146-154
config = {
    'id': row['id'],
    'name': row['name'],
    'prompt': row['prompt'],
    'greeting': row['greeting'] if row['greeting'] else '...',
    'voice_id': row['voice_id'],
    'voice_name': row['voice_name'],
    'temperature': row['temperature'] if row['temperature'] else 0.4  # LLM temperature (0.2-0.8)
}
```

---

### 7. agent-after-promotheus-after-precall-webhook.py - Default Config (Line 372)

**BEFORE:**
```python
# Line 369-373
'greeting': 'السلام عليكم ورحمة الله وبركاته؟',
'voice_id': 'KjDucWgG5NYuMBznv52L',
'voice_name': 'Hiba-Demo'
}
```

**AFTER:**
```python
# Line 369-374
'greeting': 'السلام عليكم ورحمة الله وبركاته؟',
'voice_id': 'KjDucWgG5NYuMBznv52L',
'voice_name': 'Hiba-Demo',
'temperature': 0.4  # Default LLM temperature
}
```

---

### 8. agent-after-promotheus-after-precall-webhook.py - init_llm() (Lines 1247-1261)

**BEFORE:**
```python
# Line 1249-1257
async def init_llm():
    return RealtimeModel(
        model="gpt-realtime-2025-08-28",
        modalities=["text"],
        temperature=0.4,
        input_audio_transcription=InputAudioTranscription(
            model="gpt-4o-transcribe",
            language="ar",
        ),
```

**AFTER:**
```python
# Line 1247-1265
async def init_llm():
    # Get temperature from agent config (default: 0.4)
    llm_temperature = agent_config.get('temperature', 0.4)
    logger.info(f"🌡️ LLM Temperature: {llm_temperature}")

    return RealtimeModel(
        model="gpt-realtime-2025-08-28",
        modalities=["text"],
        temperature=llm_temperature,  # Dynamic temperature from agent config
        input_audio_transcription=InputAudioTranscription(
            model="gpt-4o-transcribe",
            language="ar",
        ),
```

## Usage

### Creating a New Agent

1. Navigate to **Agents** → **Create New Agent**
2. Fill in the basic information (Name, Voice, Greeting)
3. Select the **Temperature** level from the dropdown
4. Complete the prompt builder and create the agent

### Editing an Existing Agent

1. Navigate to **Agents** → Select your agent → **Edit**
2. In the **Basic Info** tab, find the **Temperature** dropdown
3. Select your desired temperature level
4. Click **Save Changes**

### Recommended Settings by Use Case

| Use Case | Recommended Temperature | Reason |
|----------|------------------------|--------|
| **Survey/Feedback Collection** | 0.2 | Need consistent question phrasing |
| **Appointment Booking** | 0.3 | Structured flow, minimal variation |
| **Customer Support** | 0.3-0.4 | Consistent answers, some flexibility |
| **General Assistant** | 0.4-0.5 | Balanced approach |
| **Sales Outbound** | 0.6-0.7 | Creative responses for objection handling |
| **Lead Qualification** | 0.5-0.6 | Natural conversation flow |
| **Debt Collection** | 0.3 | Compliance-focused, consistent messaging |

## Technical Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    Agent Creation/Edit                       │
├─────────────────────────────────────────────────────────────┤
│  1. User selects temperature in UI dropdown                 │
│  2. Form submits temperature value (0.2 - 0.8)              │
│  3. Flask route saves to database                           │
│  4. Redis cache is invalidated                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Call Initialization                       │
├─────────────────────────────────────────────────────────────┤
│  1. get_agent_config() fetches from Redis/DB                │
│  2. Temperature included in config dict                     │
│  3. init_llm() uses agent_config['temperature']             │
│  4. RealtimeModel initialized with dynamic temperature      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    During Call                               │
├─────────────────────────────────────────────────────────────┤
│  LLM generates responses based on configured temperature    │
│  - Lower temp = more deterministic, consistent              │
│  - Higher temp = more varied, creative                      │
└─────────────────────────────────────────────────────────────┘
```

## Logging

Temperature is logged during LLM initialization:

```
🌡️ LLM Temperature: 0.6
```

This appears in the agent logs when a call starts, confirming the temperature setting being used.

## API Reference

### Agent Config Structure

```python
agent_config = {
    'id': 1,
    'name': 'Sales Agent',
    'prompt': '...',
    'greeting': '...',
    'voice_id': 'abc123',
    'voice_name': 'Fatima',
    'temperature': 0.6  # NEW: Temperature setting
}
```

### Valid Temperature Values

- Minimum: `0.2`
- Maximum: `0.8`
- Default: `0.4`
- Step: `0.1`

## Future Enhancements (Backlog)

### Dynamic Temperature (Option 3)

A future enhancement could allow temperature to change during a conversation based on context:

- **Greeting phase**: Lower temperature (0.3) for consistency
- **Qualification phase**: Medium temperature (0.4-0.5)
- **Objection handling**: Higher temperature (0.7-0.8) for creative responses
- **Closing phase**: Lower temperature (0.4) for clarity

This would use LiveKit's `update_options()` method:

```python
llm_model_realtime.update_options(temperature=new_value)
```

## Troubleshooting

### Temperature Not Changing

1. **Check Redis Cache**: Clear the agent cache after updating
   ```python
   redis_service.invalidate_agent_config(agent_id)
   ```

2. **Verify Database**: Confirm the temperature value is saved
   ```sql
   SELECT id, name, temperature FROM agent WHERE id = ?;
   ```

3. **Check Logs**: Look for the temperature log line during call start
   ```
   🌡️ LLM Temperature: 0.6
   ```

### Migration Issues

If the column doesn't exist:
```sql
ALTER TABLE agent ADD COLUMN temperature FLOAT DEFAULT 0.4;
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-01-16 | Initial implementation - Database-level temperature control |
