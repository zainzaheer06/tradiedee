# Troubleshooting Guide

## Issue: Agent Not Speaking on Phone Call

### Symptoms
- Call connects and shows "initiated" status
- Room is created successfully
- But agent doesn't speak or respond

### Root Cause
The agent was configured with `modalities=["text"]` which means it only processes text, not audio from the phone call.

### Solution Applied
Updated `agent.py` to include:

1. **Deepgram STT (Speech-to-Text)** - Converts phone audio to text
   ```python
   stt_engine = deepgram.STT(
       language="ar",
       model="nova-2-phonecall",  # Optimized for phone calls
   )
   ```

2. **Complete AgentSession** with all three components:
   ```python
   session = voice.AgentSession(
       stt=stt_engine,  # Speech-to-text (Deepgram)
       llm=llm_model,   # Language model (OpenAI)
       tts=tts_engine   # Text-to-speech (ElevenLabs)
   )
   ```

### How It Works Now

```
Phone Call → Deepgram STT → OpenAI LLM → ElevenLabs TTS → Phone Call
   (Audio)      (Text)         (Text)        (Audio)
```

1. **User speaks** → Deepgram converts speech to text
2. **OpenAI** processes the text and generates response
3. **ElevenLabs** converts response text to Arabic speech
4. **Agent speaks** back to the user

## Issue: Make Call Button Not Visible

### Location
The "Make Call" button is on the **Agent Detail Page**, not the main dashboard.

### How to Access
1. Login to dashboard
2. Click on any agent from "Your Agents" table
3. On the agent detail page, you'll see "Make Call" section on the right side
4. Enter phone number and click "Make Call"

## Issue: Call Not Connecting

### Checklist

1. **Is the agent running?**
   ```bash
   python agent.py dev
   ```
   You should see: "Connected to LiveKit server"

2. **Are environment variables set?**
   Check `.env` file for:
   - LIVEKIT_URL
   - LIVEKIT_API_KEY
   - LIVEKIT_API_SECRET
   - SIP_OUTBOUND_TRUNK_ID
   - DEEPGRAM_API_KEY
   - OPENAI_API_KEY
   - ELEVEN_LABS_API_KEY

3. **Is the SIP trunk configured?**
   - Login to LiveKit dashboard
   - Check SIP trunk ID matches your .env
   - Verify trunk is active

4. **Phone number format**
   - Must include country code
   - Format: +[country code][number]
   - Example: +966501234567 (Saudi Arabia)
   - Example: +923001234567 (Pakistan)

## Issue: Agent Speaks Wrong Language

### Solution
Update the prompt in the agent settings or in `agent.py`:

```python
instructions="""
أنت مساعد ذكي مفيد يتحدث باللغة العربية فقط.
المستخدم يتفاعل معك عبر الصوت.
أجب على جميع الأسئلة باللغة العربية فقط.
"""
```

Also ensure:
- Deepgram STT language is set to "ar"
- ElevenLabs TTS voice ID is an Arabic voice

## Issue: Poor Audio Quality

### Solutions

1. **Use phone-optimized models**
   - Deepgram: `model="nova-2-phonecall"`
   - Already configured in the updated agent.py

2. **Adjust ElevenLabs settings**
   ```python
   voice_settings=elevenlabs.VoiceSettings(
       stability=0.85,           # Higher = more consistent
       similarity_boost=0.75,    # Balance clarity
       style=0.0,                # Minimal style for clarity
       speed=0.95,               # Slightly slower
       use_speaker_boost=True    # Boost for phone
   )
   ```

3. **Network issues**
   - Check internet connection
   - Ensure low latency to LiveKit servers

## Issue: High Latency (Delayed Responses)

### Solutions

1. **Use faster models**
   - Deepgram nova-2 is already optimized
   - ElevenLabs turbo_v2_5 is already configured

2. **Reduce streaming latency**
   ```python
   streaming_latency=1  # Lowest setting
   ```

3. **Check server location**
   - Use LiveKit server closest to your region

## Issue: Insufficient Minutes

### For Users
- Contact admin to add more minutes
- Check your balance on the dashboard

### For Admins
1. Go to admin dashboard
2. Find the user
3. Click "Add Minutes"
4. Enter amount and submit

## Issue: Database Errors

### Reset Database
```bash
# Stop the app
# Delete database
rm voice_agent.db

# Restart app (recreates database)
python app.py
```

Default admin will be recreated:
- Username: admin
- Password: admin123

## Getting Logs

### Agent Logs
When running `python agent.py dev`, you'll see:
```
INFO:agent:Room: call-1-xxxxx
INFO:agent:Room participants: 1
INFO:livekit:Participant phone_user joined
```

### Flask Logs
The Flask app shows:
```
INFO:werkzeug:POST /agent/1/make-call HTTP/1.1 200
```

### LiveKit Dashboard
Login to your LiveKit dashboard to see:
- Active rooms
- Participant connections
- SIP call logs
- Agent dispatches

## Common Error Messages

### "Insufficient minutes"
**Solution:** Admin needs to add minutes to your account

### "Access denied"
**Solution:**
- You're trying to access another user's agent
- Or your account isn't approved yet

### "Agent not found"
**Solution:** The agent was deleted or doesn't exist

### "SIP trunk not configured"
**Solution:** Set SIP_OUTBOUND_TRUNK_ID in .env file

## Need More Help?

1. Check the main README.md
2. Review LiveKit documentation: https://docs.livekit.io
3. Check your API service dashboards:
   - LiveKit: https://cloud.livekit.io
   - Deepgram: https://console.deepgram.com
   - OpenAI: https://platform.openai.com
   - ElevenLabs: https://elevenlabs.io
