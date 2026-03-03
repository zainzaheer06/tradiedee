# Google Realtime API Setup for Arabic Voice Agent

## Overview

Your agent now supports **both OpenAI and Google Realtime APIs**. You can easily switch between them by commenting/uncommenting the configuration in `agent.py`.

---

## Current Configuration

### ✅ **ACTIVE: Google Realtime Model (Gemini 2.0 Flash Live)**

```python
llm_model = GoogleRealtimeModel(
    model="gemini-2.0-flash-exp",  # Gemini 2.0 Flash Live
    api_key=os.environ.get("GOOGLE_API_KEY"),
    modalities=["TEXT"],  # TEXT modality (with external STT/TTS)
    temperature=0.3,  # Natural conversation
    max_output_tokens=150,  # Concise responses
)
```

**Note**: The `language` parameter is not supported by `gemini-2.0-flash-exp`. The model automatically detects and responds in the user's language (including Arabic).

---

## Voice Pipeline

```
Phone Call → Google STT (Arabic) → Google Gemini Realtime → ElevenLabs TTS (Arabic) → Phone
   (Audio)      (Speech-to-Text)      (AI Brain - Auto-detects Arabic)  (Text-to-Speech)  (Audio)
```

**Important**: Gemini 2.0 Flash automatically detects the language from your system prompt and user input. Make sure your agent's prompt is in Arabic to ensure Arabic responses.

---

## Available Models

### Google Realtime Models:
- **`gemini-2.0-flash-exp`** ✅ (Current) - Experimental, fastest
- **`gemini-2.0-flash-live-001`** - Stable version

### OpenAI Realtime Models:
- **`gpt-4o-realtime-preview`** - GPT-4o with realtime capabilities

---

## Available Voices (Google)

Choose from these voices by changing the `voice` parameter:

| Voice | Description |
|-------|-------------|
| **Puck** ✅ | Default, neutral |
| **Charon** | Deep, authoritative |
| **Kore** | Warm, friendly |
| **Fenrir** | Energetic |
| **Aoede** | Calm, soothing |

Example:
```python
voice="Kore",  # Change to Kore for warm, friendly voice
```

---

## Switching Between Models

### To Use Google Realtime (Current):
```python
# Uncomment Google Realtime
llm_model = GoogleRealtimeModel(...)

# Comment out OpenAI Realtime
'''
llm_model = OpenAIRealtimeModel(...)
'''
```

### To Use OpenAI Realtime:
```python
# Comment out Google Realtime
'''
llm_model = GoogleRealtimeModel(...)
'''

# Uncomment OpenAI Realtime
llm_model = OpenAIRealtimeModel(...)
```

---

## Configuration Parameters

### Google Realtime Model

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | str | `gemini-2.0-flash-exp` | Model name |
| `api_key` | str | From `.env` | Google API key |
| `voice` | str | `Puck` | Voice for audio output |
| `language` | str | `ar` | Language (BCP-47 code) |
| `modalities` | list | `["AUDIO"]` | Input/output modalities |
| `temperature` | float | `0.7` | Response creativity (0.0-1.0) |
| `max_output_tokens` | int | Auto | Max response length |
| `top_p` | float | Auto | Nucleus sampling |
| `top_k` | int | Auto | Top-k sampling |

### OpenAI Realtime Model

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | str | `gpt-4o-realtime-preview` | Model name |
| `modalities` | list | `["text"]` | Input/output modalities |
| `temperature` | float | `0.2` | Response creativity |
| `input_audio_transcription` | dict | Whisper-1 | STT configuration |
| `turn_detection` | dict | Server VAD | Turn detection settings |

---

## Advanced Features

### 1. Enable Audio Transcription (Google)

Capture transcripts of both input and output audio:

```python
llm_model = GoogleRealtimeModel(
    model="gemini-2.0-flash-exp",
    api_key=os.environ.get("GOOGLE_API_KEY"),
    voice="Puck",
    language="ar",
    modalities=["AUDIO"],
    temperature=0.7,
    # Enable transcription
    input_audio_transcription={"model": "chirp-2", "language": "ar"},
    output_audio_transcription={"model": "chirp-2", "language": "ar"},
)
```

### 2. Use Vertex AI (Enterprise)

For Google Cloud customers with Vertex AI:

```python
llm_model = GoogleRealtimeModel(
    model="gemini-2.0-flash-exp",
    vertexai=True,  # Enable Vertex AI
    project="your-gcp-project-id",  # Your GCP project
    location="us-central1",  # GCP region
    voice="Puck",
    language="ar",
    modalities=["AUDIO"],
    temperature=0.7,
)
```

**Note**: Requires `GOOGLE_APPLICATION_CREDENTIALS` environment variable pointing to your service account key.

### 3. Adjust Response Style

```python
# More creative/varied responses
temperature=0.9,

# More focused/consistent responses
temperature=0.3,

# Balanced (recommended for Arabic)
temperature=0.7,
```

---

## Supported Languages

Google Realtime API supports these languages (use BCP-47 codes):

- **Arabic**: `ar`
- **English**: `en`
- **Spanish**: `es`
- **French**: `fr`
- **German**: `de`
- **Hindi**: `hi`
- **Japanese**: `ja`
- **Korean**: `ko`
- **Portuguese**: `pt`
- **Chinese**: `zh`

Full list: https://ai.google.dev/gemini-api/docs/live#supported-languages

---

## Testing

### 1. Restart Agent
```bash
# Kill current agent
Ctrl+C

# Restart with Google Realtime
python agent.py dev
```

### 2. Make Test Call
- Call your agent's phone number
- Speak in Arabic
- Verify responses

### 3. Check Logs
Look for:
```
INFO livekit.agents - RealtimeModel metrics {"model_name": "gemini-2.0-flash-exp", ...}
```

---

## Troubleshooting

### Issue: "API key not found"
**Solution**: Check `.env` file has:
```bash
GOOGLE_API_KEY=your-api-key-here
```

### Issue: "Model not available"
**Solution**: Try stable model:
```python
model="gemini-2.0-flash-live-001",
```

### Issue: "Language not supported"
**Solution**: Verify language code:
```python
language="ar",  # Must be BCP-47 code
```

### Issue: "Voice not working"
**Solution**: Check available voices:
```python
voice="Puck",  # Try: Puck, Charon, Kore, Fenrir, Aoede
```

---

## Cost Comparison

| Model | Input | Output | Speed |
|-------|-------|--------|-------|
| **Google Gemini Realtime** | Lower | Lower | Fast |
| **OpenAI GPT-4o Realtime** | Higher | Higher | Fast |

Google Realtime is generally more cost-effective for high-volume applications.

---

## Benefits of Google Realtime

1. **🚀 Low Latency**: Optimized for real-time voice
2. **💰 Cost-Effective**: Lower pricing than OpenAI
3. **🌍 Multilingual**: Excellent Arabic support
4. **🎙️ Native Audio**: Built-in voice synthesis
5. **🔄 Seamless**: Works with LiveKit infrastructure

---

## Next Steps

1. ✅ **Test the agent** with Google Realtime
2. ✅ **Try different voices** (Puck, Kore, etc.)
3. ✅ **Adjust temperature** for response style
4. ✅ **Monitor costs** in Google Cloud Console
5. ✅ **Compare with OpenAI** for your use case

---

## Support

- **Google Realtime API Docs**: https://ai.google.dev/gemini-api/docs/live
- **LiveKit Agents Docs**: https://docs.livekit.io/agents/
- **Supported Languages**: https://ai.google.dev/gemini-api/docs/live#supported-languages

---

**Your Arabic voice agent is now powered by Google Gemini 2.0 Flash Live! 🎉**

