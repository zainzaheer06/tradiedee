# LiveKit Agent Modules Documentation

## Project: Nevox AI Voice Agent Platform
**Date:** November 3, 2025  
**Agent Version:** livekit-agents==1.2.17

---

## 📦 Core LiveKit Packages

### 1. **livekit** (v1.0.17)
```python
from livekit import api, rtc
```
- **api**: Room management, deletion, and control
- **rtc**: Real-time communication, participant handling
- **Usage**: Room lifecycle management, SIP participant detection

### 2. **livekit-agents** (v1.2.17)
```python
from livekit.agents import voice
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    MetricsCollectedEvent,
    RoomInputOptions,
    RunContext,
    UserStateChangedEvent,
    WorkerOptions,
    cli,
    function_tool,
    get_job_context,
    llm,
    metrics,
)
```

---

## 🎯 Key Components Used

### **Agent Framework**
- **`Agent`**: Base class for voice assistants
- **`AgentSession`**: Manages conversation sessions
- **`JobContext`**: Room and participant context
- **`WorkerOptions`**: Worker configuration and load management

### **Voice Components**
- **`voice.AgentSession`**: Main voice session handler
- **`RoomInputOptions`**: Audio input configuration
- **`UserStateChangedEvent`**: User activity detection (listening, speaking, away)

### **Metrics & Monitoring**
- **`MetricsCollectedEvent`**: Usage tracking events
- **`metrics.UsageCollector`**: Token and cost collection
- **`metrics.log_metrics`**: Performance logging

### **Function Tools**
- **`@function_tool`**: Decorator for agent functions
- **`RunContext`**: Function execution context

---

## 🔌 LiveKit Plugins

### 1. **livekit-plugins-openai** (v1.2.17)
```python
from livekit.plugins.openai.realtime import RealtimeModel
from openai.types.beta.realtime.session import InputAudioTranscription, TurnDetection
```

**Features Used:**
- **`RealtimeModel`**: GPT-4o Realtime API integration
- **`InputAudioTranscription`**: Whisper-1 Arabic transcription
- **`TurnDetection`**: Server-side Voice Activity Detection (VAD)

**Configuration:**
```python
llm_model = RealtimeModel(
    model="gpt-4o-realtime-preview",
    modalities=["text"],
    temperature=0.2,
    input_audio_transcription=InputAudioTranscription(
        model="whisper-1",
        language="ar"
    ),
    turn_detection=TurnDetection(
        type="server_vad",
        threshold=0.5,
        prefix_padding_ms=200,
        silence_duration_ms=400,
        create_response=True,
        interrupt_response=True,
    ),
)
```

### 2. **livekit-plugins-elevenlabs** (v1.2.17)
```python
from livekit.plugins import elevenlabs
```

**Features Used:**
- **`elevenlabs.TTS`**: Text-to-speech engine
- **`elevenlabs.VoiceSettings`**: Voice configuration

**Configuration:**
```python
tts_engine = elevenlabs.TTS(
    voice_id=agent_config['voice_id'],  # Dynamic voice selection
    model="eleven_turbo_v2_5",         # Fastest model
    language="ar",                      # Arabic language
    auto_mode=True,
    voice_settings=elevenlabs.VoiceSettings(
        stability=0.71,
        similarity_boost=0.5,
        style=0.0,
        speed=0.95,
        use_speaker_boost=True
    ),
    streaming_latency=1,
    inactivity_timeout=60,
    enable_ssml_parsing=False,
    apply_text_normalization="auto"
)
```

### 3. **livekit-plugins-noise-cancellation** (v0.2.5)
```python
from livekit.plugins import noise_cancellation
```

**Features Used:**
- **`noise_cancellation.BVCTelephony`**: Phone call noise reduction

**Usage:**
```python
room_input_options=RoomInputOptions(
    noise_cancellation=noise_cancellation.BVCTelephony(),
)
```

---

## 🎛️ Event Handlers Used

### **Speech Events**
```python
@session.on("user_speech_committed")
@session.on("agent_speech_committed")
@session.on("user_message")
@session.on("agent_message")
@session.on("user_transcript")
@session.on("agent_transcript")
@session.on("conversation_item_added")
@session.on("chat_message")
```

### **System Events**
```python
@session.on("metrics_collected")
@session.on("user_state_changed")
@ctx.room.on("participant_disconnected")
```

---

## ⚙️ Worker Configuration

### **Load Management**
```python
opts = WorkerOptions(
    entrypoint_fnc=entrypoint,
    load_fnc=compute_load,
    load_threshold=0.9,     # 90% capacity
    drain_timeout=300,      # 5 minutes graceful shutdown
)
```

### **Environment Variables**
- `MAX_CONCURRENT_CALLS`: Maximum simultaneous calls (default: 15)
- `USER_AWAY_TIMEOUT`: Inactivity timeout (default: 60.0 seconds)
- `FLASK_WEBHOOK_URL`: Webhook endpoint for call data

---

## 🔧 Custom Components

### **TranscriptionManager**
- Message deduplication
- Multi-source transcription capture
- SIP participant information storage
- JSON/Plain text export

### **Agent Configuration System**
- Database-driven agent configs
- Caching with TTL (5 minutes)
- Dynamic voice selection
- Custom prompt building

### **Hangup Helper**
- Retry logic for room deletion
- Network error handling
- Graceful disconnection fallback

---

## 📊 Production Features

### **Metrics Collection**
- Token usage tracking
- Cost calculation
- Performance monitoring
- Usage summary reporting

### **Error Handling**
- Comprehensive try-catch blocks
- Retry mechanisms
- Graceful degradation
- Detailed logging

### **Scalability**
- Worker load balancing
- Concurrent call limits
- Resource monitoring
- Background task management

---

## 🚀 Key Functions

### **Core Functions**
- `get_agent_config()`: Database config retrieval
- `build_full_prompt()`: System + user prompt combination
- `hangup_call()`: Safe room termination
- `compute_load()`: Worker load calculation

### **Session Management**
- `user_presence_check()`: Inactivity handling
- `monitor_session()`: Background conversation monitoring
- `send_call_data()`: Webhook data transmission

---

## 📋 Dependencies Summary

| Package | Version | Purpose |
|---------|---------|---------|
| livekit | 1.0.17 | Core LiveKit functionality |
| livekit-agents | 1.2.17 | Agent framework |
| livekit-plugins-openai | 1.2.17 | GPT-4o Realtime API |
| livekit-plugins-elevenlabs | 1.2.17 | Arabic TTS |
| livekit-plugins-noise-cancellation | 0.2.5 | Phone audio enhancement |

---

## 🎯 Integration Points

### **Database Integration**
- SQLite agent configuration storage
- Caching layer for performance
- Dynamic agent loading

### **Flask Webhook Integration**
- Call completion data
- Transcription delivery
- Usage metrics reporting

### **SIP Integration**
- Phone call handling
- Participant monitoring
- Call state management

---

## 🔄 Version Notes

**Current Setup:**
- Using **latest versions** (1.2.17) vs requirements.txt (0.15.0)
- All major features working with current versions
- Backward compatibility maintained

**Recommendations:**
- Update requirements.txt to match installed versions
- Continue using 1.2.17+ for latest features and bug fixes
- Monitor LiveKit releases for new capabilities

---

*Generated on November 3, 2025*  
*For Nevox AI Voice Agent Platform*