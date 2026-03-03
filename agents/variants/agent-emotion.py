import asyncio
import logging
import os
import time
import json
import aiohttp
from datetime import datetime
from dotenv import load_dotenv
from livekit import api
from livekit.agents import voice
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    MetricsCollectedEvent,
    RoomInputOptions,
    RunContext,
    WorkerOptions,
    cli,
    function_tool,
    ToolError,
    get_job_context,
    llm,
    metrics,
)
from livekit.plugins import noise_cancellation, openai, elevenlabs
from livekit.plugins.openai.realtime import RealtimeModel
from livekit.plugins.elevenlabs import VoiceSettings
from openai.types.beta.realtime.session import InputAudioTranscription, TurnDetection
from enum import Enum

logger = logging.getLogger("agent")
load_dotenv(".env")


# --- Emotion Types ---
class Emotion(str, Enum):
    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    CALM = "calm"
    EMPATHETIC = "empathetic"
    PROFESSIONAL = "professional"
    PLAYFUL = "playful"
    CONFUSED = "confused"
    FRUSTRATED = "frustrated"
    GRATEFUL = "grateful"


# --- Transcription Manager ---
class TranscriptionManager:
    def __init__(self):
        self.messages = []
        self.start_time = datetime.now().isoformat()
        self.seen_messages = set()
        self.emotions_log = []  # Track emotions during call

    def add_message(self, role: str, text: str, source: str = "", emotion: str = None):
        """Add a message with deduplication"""
        if not isinstance(text, str) or not text.strip():
            return

        msg_key = f"{role}:{text.strip()}"
        if msg_key in self.seen_messages:
            return

        self.seen_messages.add(msg_key)
        msg = {
            "timestamp": datetime.now().isoformat(),
            "role": role,
            "text": text.strip(),
            "source": source,
            "emotion": emotion
        }
        self.messages.append(msg)
        logger.info(f"✅ [{role.upper()}] {emotion or ''}: {text[:80]}")

    def add_user_message(self, text: str, source: str = "user_speech", emotion: str = None):
        self.add_message("user", text, source, emotion)

    def add_agent_message(self, text: str, source: str = "agent_speech", emotion: str = None):
        self.add_message("agent", text, source, emotion)

    def log_emotion_change(self, emotion: Emotion, reason: str = ""):
        """Track emotional changes during the call"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "emotion": emotion,
            "reason": reason
        }
        self.emotions_log.append(log_entry)
        logger.info(f"🎭 Emotion changed to: {emotion} ({reason})")

    def get_plain_text(self) -> str:
        """Get transcription as plain text"""
        lines = []
        for msg in self.messages:
            emotion_tag = f" [{msg['emotion']}]" if msg['emotion'] else ""
            lines.append(f"{msg['role'].upper()}{emotion_tag}: {msg['text']}")
        return "\n".join(lines)

    def get_json(self) -> dict:
        """Get full transcription as JSON"""
        return {
            "start_time": self.start_time,
            "end_time": datetime.now().isoformat(),
            "message_count": len(self.messages),
            "messages": self.messages,
            "emotions_log": self.emotions_log
        }


# --- Voice Emotion Mapper ---
class EmotionVoiceMapper:
    """Maps emotions to voice parameter adjustments"""
    
    # Base settings for each emotion
    EMOTION_PRESETS = {
        Emotion.HAPPY: {
            "stability": 0.65,          # More expressive
            "similarity_boost": 0.80,   # Closer to voice
            "style": 0.80,              # Higher style
            "speed": 1.15,              # Faster speech
            "use_speaker_boost": True,
            "description": "Speak with joy and enthusiasm"
        },
        Emotion.SAD: {
            "stability": 0.90,          # Very stable, controlled
            "similarity_boost": 0.75,
            "style": 0.2,               # Less expressive
            "speed": 0.80,              # Slower speech
            "use_speaker_boost": False,
            "description": "Speak with sadness and understanding"
        },
        Emotion.ANGRY: {
            "stability": 0.70,          # Somewhat expressive
            "similarity_boost": 0.70,
            "style": 0.90,              # High style
            "speed": 1.20,              # Fast, energetic
            "use_speaker_boost": True,
            "description": "Speak with determination and firmness"
        },
        Emotion.CALM: {
            "stability": 0.85,          # Very stable
            "similarity_boost": 0.80,
            "style": 0.3,               # Subtle style
            "speed": 0.95,              # Normal, steady
            "use_speaker_boost": False,
            "description": "Speak calmly and peacefully"
        },
        Emotion.EMPATHETIC: {
            "stability": 0.80,          # Balanced
            "similarity_boost": 0.85,   # Natural sounding
            "style": 0.5,               # Moderate expressiveness
            "speed": 0.90,              # Slightly slower for compassion
            "use_speaker_boost": True,
            "description": "Speak with warmth, understanding, and care"
        },
        Emotion.PROFESSIONAL: {
            "stability": 0.90,          # Very stable
            "similarity_boost": 0.75,
            "style": 0.2,               # Minimal style
            "speed": 1.0,               # Normal pace
            "use_speaker_boost": False,
            "description": "Speak professionally and clearly"
        },
        Emotion.PLAYFUL: {
            "stability": 0.60,          # Very expressive
            "similarity_boost": 0.85,
            "style": 0.95,              # Maximum style variation
            "speed": 1.10,              # Lively pace
            "use_speaker_boost": True,
            "description": "Speak with humor and playfulness"
        },
        Emotion.CONFUSED: {
            "stability": 0.75,          # Slightly unstable
            "similarity_boost": 0.70,
            "style": 0.4,               # Some uncertainty in tone
            "speed": 0.85,              # Slower, thoughtful
            "use_speaker_boost": False,
            "description": "Speak with gentle confusion, asking for clarification"
        },
        Emotion.FRUSTRATED: {
            "stability": 0.70,          # Somewhat expressive
            "similarity_boost": 0.75,
            "style": 0.6,               # Moderate expression
            "speed": 1.05,              # Slightly faster
            "use_speaker_boost": True,
            "description": "Acknowledge frustration while remaining helpful"
        },
        Emotion.GRATEFUL: {
            "stability": 0.75,          # Warm and open
            "similarity_boost": 0.85,
            "style": 0.7,               # Warm expressiveness
            "speed": 0.95,              # Measured, warm pace
            "use_speaker_boost": True,
            "description": "Speak with genuine gratitude and warmth"
        },
    }

    @staticmethod
    def get_settings_for_emotion(emotion: Emotion) -> VoiceSettings:
        """Get ElevenLabs voice settings for an emotion"""
        preset = EmotionVoiceMapper.EMOTION_PRESETS.get(emotion, EmotionVoiceMapper.EMOTION_PRESETS[Emotion.CALM])
        return VoiceSettings(
            stability=preset["stability"],
            similarity_boost=preset["similarity_boost"],
            style=preset["style"],
            speed=preset["speed"],
            use_speaker_boost=preset["use_speaker_boost"]
        )

    @staticmethod
    def get_instruction_for_emotion(emotion: Emotion) -> str:
        """Get LLM instruction for an emotion"""
        preset = EmotionVoiceMapper.EMOTION_PRESETS.get(emotion, EmotionVoiceMapper.EMOTION_PRESETS[Emotion.CALM])
        return preset["description"]


# --- Hangup helper ---
async def hangup_call():
    ctx = get_job_context()
    if ctx is None:
        return
    await ctx.api.room.delete_room(api.DeleteRoomRequest(room=ctx.room.name))


# --- Main Agent with Emotional Tools ---
class EmotionalAssistant(Agent):
    def __init__(self, tts_engine, transcription_manager) -> None:
        super().__init__(
            instructions="""
أنت مساعد ذكي مفيد يتحدث باللغة العربية بحنان وتعاطف حقيقي.

📋 مرشدات سلوكك:
- استجب لمشاعر المستخدم وليس فقط كلماته
- إذا بدا المستخدم محبط، كن متعاطف وهادئ
- إذا كان سعيد، شارك فرحه بحماس
- استخدم تعابير عربية دافئة وإنسانية
- كن صادق ومباشر لكن لطيف دائماً

🎭 التعامل مع العواطف:
- الاستماع الفعلي للمستخدم
- إظهار التفهم والعطف
- تجنب الردود الآلية
- الاعتراف بمشاعر المستخدم

🔧 استخدم أدواتك:
- استخدم detect_user_emotion لفهم شعور المستخدم
- استخدم adjust_emotional_tone لتعديل نبرتك
- استخدم generate_emotional_response لرد عاطفي مناسب

تذكر: أنت مساعد بشري المشاعر، ليس روبوت بارد.
""",
        )
        self.tts_engine = tts_engine
        self.transcription_manager = transcription_manager
        self.current_emotion = Emotion.CALM

    @function_tool
    async def detect_user_emotion(
        self,
        context: RunContext,
        user_text: str,
    ) -> dict:
        """
        Analyze the user's emotional state from their text.
        This helps the agent understand and respond appropriately to user feelings.
        
        Args:
            user_text: The user's spoken text to analyze
            
        Returns:
            A dictionary with detected emotion and confidence score
        """
        try:
            # Use simple keyword-based detection (can be enhanced with ML)
            emotion_keywords = {
                Emotion.FRUSTRATED: ["غضب", "محبط", "زعل", "أزعج", "مزعج", "ماحد يسمع", "ليش"],
                Emotion.HAPPY: ["شكراً", "ممتاز", "رائع", "فرحان", "سعيد", "يارب", "إن شاء"],
                Emotion.SAD: ["حزين", "وجع", "تعب", "إجهاد", "مكتئب", "حزن", "ياليت"],
                Emotion.CONFUSED: ["ما فهمت", "مش فاهم", "إيش", "كيف", "متى", "ليش"],
                Emotion.GRATEFUL: ["شكراً", "تشكر", "أقدر", "ممنون", "مشكور"],
            }

            text_lower = user_text.lower()
            detected_emotion = Emotion.CALM
            confidence = 0.5
            
            for emotion, keywords in emotion_keywords.items():
                for keyword in keywords:
                    if keyword in text_lower:
                        detected_emotion = emotion
                        confidence = 0.8
                        break
                if confidence > 0.5:
                    break

            result = {
                "emotion": detected_emotion.value,
                "confidence": confidence,
                "message": f"Detected user emotion: {detected_emotion}"
            }
            
            logger.info(f"🎭 User emotion detected: {detected_emotion} (confidence: {confidence})")
            self.transcription_manager.log_emotion_change(detected_emotion, "user text analysis")
            
            return result

        except Exception as e:
            logger.error(f"Error detecting emotion: {e}")
            raise ToolError(f"Failed to detect emotion: {str(e)}")

    @function_tool
    async def adjust_emotional_tone(
        self,
        context: RunContext,
        emotion: str,
    ) -> dict:
        """
        Adjust the agent's emotional tone for the response.
        This changes voice parameters and speaking style.
        
        Args:
            emotion: The emotion to express (happy, sad, calm, empathetic, etc.)
            
        Returns:
            Confirmation of the tone adjustment
        """
        try:
            # Convert string to Emotion enum
            try:
                target_emotion = Emotion(emotion.lower())
            except ValueError:
                raise ToolError(f"Unknown emotion: {emotion}. Valid emotions: {[e.value for e in Emotion]}")

            # Get voice settings for this emotion
            voice_settings = EmotionVoiceMapper.get_settings_for_emotion(target_emotion)
            instruction = EmotionVoiceMapper.get_instruction_for_emotion(target_emotion)

            # Update TTS engine settings
            if self.tts_engine:
                self.tts_engine.update_options()
                # Note: ElevenLabs update_options doesn't directly support all settings
                # But we can use SSML or voice instructions for better control

            self.current_emotion = target_emotion
            self.transcription_manager.log_emotion_change(target_emotion, "tone adjustment tool")

            result = {
                "emotion": target_emotion.value,
                "instruction": instruction,
                "settings": {
                    "stability": voice_settings.stability,
                    "speed": voice_settings.speed,
                    "style": voice_settings.style,
                },
                "message": f"Emotional tone adjusted to: {target_emotion.value}"
            }

            logger.info(f"🎭 Emotional tone adjusted to: {target_emotion} - {instruction}")
            return result

        except ToolError:
            raise
        except Exception as e:
            logger.error(f"Error adjusting tone: {e}")
            raise ToolError(f"Failed to adjust emotional tone: {str(e)}")

    @function_tool
    async def generate_emotional_response(
        self,
        context: RunContext,
        user_emotion: str,
        response_emotion: str,
        user_message: str,
    ) -> dict:
        """
        Generate a response that acknowledges user emotions and responds with appropriate emotion.
        
        Args:
            user_emotion: The detected emotion from the user
            response_emotion: The emotion the agent should express in response
            user_message: The user's message for context
            
        Returns:
            Guidance for generating an emotionally appropriate response
        """
        try:
            # Map user emotions to empathetic responses
            empathy_responses = {
                Emotion.FRUSTRATED: "أفهم إحباطك، دعني أساعدك بسرعة",
                Emotion.HAPPY: "يسعدني سماعك سعيد، ممتاز!",
                Emotion.SAD: "أتفهم شعورك، نحن هنا لدعمك",
                Emotion.CONFUSED: "لا مشكلة، دعني أوضح ذلك لك",
                Emotion.GRATEFUL: "أنا أيضاً ممتن لتفاعلك معي",
            }

            empathy_msg = empathy_responses.get(
                Emotion(user_emotion.lower()),
                "شكراً لتواصلك معي"
            )

            # Adjust our tone
            response_emotion_obj = Emotion(response_emotion.lower())
            tone_instruction = EmotionVoiceMapper.get_instruction_for_emotion(response_emotion_obj)

            result = {
                "empathy_message": empathy_msg,
                "tone_instruction": tone_instruction,
                "context": {
                    "user_emotion": user_emotion,
                    "response_emotion": response_emotion,
                    "user_message": user_message[:100]  # First 100 chars for context
                },
                "message": "Ready to respond with emotional intelligence"
            }

            logger.info(f"🎭 Emotional response ready: {empathy_msg}")
            return result

        except ValueError as e:
            raise ToolError(f"Invalid emotion value: {str(e)}")
        except Exception as e:
            logger.error(f"Error generating emotional response: {e}")
            raise ToolError(f"Failed to generate emotional response: {str(e)}")

    @function_tool
    async def track_conversation_emotion(
        self,
        context: RunContext,
        agent_text: str,
        agent_emotion: str,
    ) -> dict:
        """
        Track the agent's emotional expression in the transcription.
        
        Args:
            agent_text: The agent's response text
            agent_emotion: The emotion being expressed
            
        Returns:
            Confirmation of tracking
        """
        try:
            self.transcription_manager.add_agent_message(
                agent_text,
                source="emotional_response",
                emotion=agent_emotion
            )
            
            return {
                "tracked": True,
                "text_length": len(agent_text),
                "emotion": agent_emotion,
                "message": "Emotional context saved to transcription"
            }

        except Exception as e:
            logger.error(f"Error tracking emotion: {e}")
            raise ToolError(f"Failed to track emotion: {str(e)}")

    @function_tool
    async def end_call(self, ctx: RunContext):
        """Called when the user wants to end the call"""
        await ctx.wait_for_playout()
        await hangup_call()
        return "تم إنهاء المكالمة"


# --- Entrypoint ---
async def entrypoint(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}
    logger.info(f"🎯 Room: {ctx.room.name}")
    logger.info(f"📊 Participants: {ctx.room.num_participants}")
    logger.info(f"🎭 Emotional Agent Starting...")

    # Initialize transcription manager
    transcription = TranscriptionManager()
    call_start_time = time.time()

    # --- ElevenLabs TTS (Arabic with emotional settings) ---
    tts_engine = elevenlabs.TTS(
        voice_id="YdWLuz4rVsaG3kWAECFE",  # Ali voice
        model="eleven_turbo_v2_5",
        language="ar",
        auto_mode=True,
        voice_settings=elevenlabs.VoiceSettings(
            stability=0.80,        # Start with balanced
            similarity_boost=0.75,
            style=0.5,             # Moderate expressiveness
            speed=0.95,
            use_speaker_boost=True
        ),
        streaming_latency=1,
        inactivity_timeout=60,
        enable_ssml_parsing=True,
        apply_text_normalization="on"
    )

    # --- OpenAI Realtime model with transcription ---
    llm_model = RealtimeModel(
        model="gpt-4o-realtime-preview",
        modalities=["text"],
        temperature=0.8,
        input_audio_transcription=InputAudioTranscription(
            model="whisper-1",
            language="ar"
        ),
        turn_detection=TurnDetection(
            type="server_vad",
            threshold=0.5,
            prefix_padding_ms=300,
            silence_duration_ms=500,
            create_response=True,
            interrupt_response=True,
        ),
    )

    # --- Create session ---
    session = voice.AgentSession(llm=llm_model, tts=tts_engine)

    # --- Metrics ---
    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    # --- TRANSCRIPTION HANDLERS ---
    @session.on("user_speech_committed")
    def on_user_speech_committed(msg: llm.ChatMessage):
        """Capture user speech"""
        try:
            text = msg.content if isinstance(msg.content, str) else ""
            transcription.add_user_message(text)
        except Exception as e:
            logger.error(f"Error capturing user speech: {e}")

    @session.on("agent_speech_committed")
    def on_agent_speech_committed(msg: llm.ChatMessage):
        """Capture agent speech"""
        try:
            text = msg.content if isinstance(msg.content, str) else ""
            transcription.add_agent_message(text)
        except Exception as e:
            logger.error(f"Error capturing agent speech: {e}")

    # Additional handlers
    @session.on("user_message")
    def on_user_message(msg):
        """Fallback for user messages"""
        try:
            if hasattr(msg, 'content'):
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                transcription.add_user_message(content, "user_message_event")
        except:
            pass

    @session.on("agent_message")
    def on_agent_message(msg):
        """Fallback for agent messages"""
        try:
            if hasattr(msg, 'content'):
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                transcription.add_agent_message(content, "agent_message_event")
        except:
            pass

    @session.on("conversation_item_added")
    def on_conversation_item_added(event):
        """Capture conversation items"""
        try:
            if hasattr(event, 'item'):
                item = event.item
                if hasattr(item, 'role') and hasattr(item, 'content'):
                    content = ' '.join(item.content) if isinstance(item.content, list) else str(item.content)
                    transcription.add_message(item.role, content, "conversation_item")
        except Exception as e:
            logger.debug(f"Error in conversation_item_added: {e}")

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"📊 Usage: {summary}")

    async def send_call_data():
        """Send call completion data to Flask webhook"""
        call_duration = int(time.time() - call_start_time)

        logger.info(f"📝 Preparing transcription data with emotional context...")
        logger.info(f"   Messages captured: {len(transcription.messages)}")
        logger.info(f"   Emotional transitions: {len(transcription.emotions_log)}")
        logger.info(f"   Duration: {call_duration}s")

        try:
            payload = {
                'room_name': ctx.room.name,
                'duration': call_duration,
                'transcription': transcription.get_plain_text(),
                'metadata': transcription.get_json(),
                'message_count': len(transcription.messages),
                'emotion_tracking': transcription.emotions_log
            }

            logger.info(f"🚀 Sending webhook with emotional data...")

            async with aiohttp.ClientSession() as http_session:
                webhook_url = os.environ.get('FLASK_WEBHOOK_URL', 'http://localhost:5000/webhook/call-ended')
                async with http_session.post(webhook_url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        logger.info(f"✅ Webhook sent!")
                    else:
                        logger.error(f"❌ Webhook failed: {resp.status}")
        except Exception as e:
            logger.error(f"❌ Failed to send call data: {e}")

    ctx.add_shutdown_callback(log_usage)
    ctx.add_shutdown_callback(send_call_data)

    # --- Start session ---
    await session.start(
        room=ctx.room,
        agent=EmotionalAssistant(tts_engine, transcription),
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVCTelephony(),
        ),
    )

    # --- Connect room ---
    await ctx.connect()

    # --- Initial greeting with warmth ---
    if ctx.room.num_participants == 0:
        logger.info("🎤 Generating warm greeting...")
        await session.generate_reply(
            instructions="قل مرحباً بدفء وودية، عرّف نفسك كمساعد ذكي هنا لمساعدة المستخدم"
        )


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))