import asyncio
import logging
import os
import time
import json
import aiohttp
import sqlite3
from datetime import datetime
from dotenv import load_dotenv
from livekit import api, rtc
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
from livekit.plugins import noise_cancellation, openai, elevenlabs, google
from livekit.plugins.openai.realtime import RealtimeModel
from openai.types.beta.realtime.session import InputAudioTranscription, TurnDetection

logger = logging.getLogger("agent")
load_dotenv(".env")

# --- Config Cache ---
_agent_config_cache = {}
_cache_ttl = 300  # 5 minutes


# --- Database Helper ---
def get_agent_config(agent_id: int, use_cache=True):
    """Fetch agent configuration from database with caching"""
    # Check cache first
    if use_cache and agent_id in _agent_config_cache:
        cached_data = _agent_config_cache[agent_id]
        if time.time() - cached_data['timestamp'] < _cache_ttl:
            logger.debug(f"📦 Using cached config for agent {agent_id}")
            return cached_data['config']

    try:
        db_path = os.path.join(os.path.dirname(__file__), 'instance', 'voice_agent.db')
        if not os.path.exists(db_path):
            db_path = os.path.join(os.path.dirname(__file__), 'voice_agent.db')

        if not os.path.exists(db_path):
            logger.error(f"❌ Database not found at: {db_path}")
            return None

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, name, prompt, greeting, voice_id, voice_name
            FROM agent
            WHERE id = ?
        """, (agent_id,))

        row = cursor.fetchone()
        conn.close()

        if row:
            config = {
                'id': row['id'],
                'name': row['name'],
                'prompt': row['prompt'],
                'greeting': row['greeting'] if row['greeting'] else 'السلام عليكم ورحمة الله وبركاته، أهلاً وسهلاً فيك. أنا مساعدك الذكي، كيف أقدر أساعدك اليوم؟',
                'voice_id': row['voice_id'],
                'voice_name': row['voice_name']
            }

            # Cache the result
            _agent_config_cache[agent_id] = {
                'config': config,
                'timestamp': time.time()
            }

            logger.info(f"📥 Loaded agent config from database: {config['name']}")
            return config
        else:
            logger.warning(f"⚠️  Agent {agent_id} not found in database")
            return None

    except sqlite3.Error as e:
        logger.error(f"❌ Database error fetching agent config: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Unexpected error fetching agent config: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


def get_default_config():
    """Return default agent configuration"""
    return {
        'id': 0,
        'name': 'Default Assistant',
        'prompt': """أنت مساعد ذكي مفيد يتحدث باللغة العربية فقط.
المستخدم يتفاعل معك عبر الصوت.
أجب على جميع الأسئلة باللغة العربية فقط، بدون أي لغات أخرى.
كن ودوداً وذا حس فكاهي.
استجب بإجابات قصيرة ومباشرة بدون رموز معقدة أو رموز تعبيرية.
[رد فقط باللغة العربية]""",
        'greeting': 'السلام عليكم ورحمة الله وبركاته، أهلاً وسهلاً فيك. أنا مساعدك الذكي، كيف أقدر أساعدك اليوم؟',
        'voice_id': 'KjDucWgG5NYuMBznv52L',
        'voice_name': 'Ali'
    }


# --- Transcription Manager ---
class TranscriptionManager:
    def __init__(self):
        self.messages = []
        self.start_time = datetime.now().isoformat()
        self.seen_messages = set()  # Track unique messages to avoid duplicates
        self.sip_info = {}  # Store SIP participant information

    def add_message(self, role: str, text: str, source: str = ""):
        """Add a message with deduplication"""
        if not isinstance(text, str) or not text.strip():
            return

        # Create unique key for deduplication
        msg_key = f"{role}:{text.strip()}"
        if msg_key in self.seen_messages:
            return

        self.seen_messages.add(msg_key)
        msg = {
            "timestamp": datetime.now().isoformat(),
            "role": role,
            "text": text.strip(),
            "source": source
        }
        self.messages.append(msg)
        logger.info(f"✅ [{role.upper()}] {source}: {text[:100]}")

    def add_user_message(self, text: str, source: str = "user_speech"):
        self.add_message("user", text, source)

    def add_agent_message(self, text: str, source: str = "agent_speech"):
        self.add_message("agent", text, source)

    def set_sip_info(self, participant):
        """Store SIP participant information"""
        if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
            self.sip_info = {
                'call_status': participant.attributes.get('sip.callStatus', 'unknown'),
                'phone_number': participant.attributes.get('sip.phoneNumber', ''),
                'trunk_phone_number': participant.attributes.get('sip.trunkPhoneNumber', ''),
                'call_id': participant.attributes.get('sip.callID', ''),
                'trunk_id': participant.attributes.get('sip.trunkID', ''),
                'participant_kind': 'SIP'
            }
            logger.info(f"📞 SIP Info: Status={self.sip_info['call_status']}, From={self.sip_info['phone_number']}")
        else:
            self.sip_info = {
                'participant_kind': 'NON_SIP',
                'call_status': 'active'
            }

    def get_plain_text(self) -> str:
        """Get transcription as plain text"""
        lines = []
        for msg in self.messages:
            lines.append(f"{msg['role'].upper()}: {msg['text']}")
        return "\n".join(lines)

    def get_json(self) -> dict:
        """Get full transcription as JSON"""
        return {
            "start_time": self.start_time,
            "end_time": datetime.now().isoformat(),
            "message_count": len(self.messages),
            "messages": self.messages,
            "sip_info": self.sip_info
        }


# --- Hangup helper ---
async def hangup_call():
    """Delete room with retry logic to handle network errors"""
    ctx = get_job_context()
    if ctx is None:
        logger.warning("⚠️ No job context available for hangup")
        return

    room_name = ctx.room.name
    max_retries = 3
    retry_delay = 1

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"🔄 Attempting to delete room (attempt {attempt}/{max_retries})")
            await ctx.api.room.delete_room(api.DeleteRoomRequest(room=room_name))
            logger.info(f"✅ Room deleted successfully: {room_name}")
            return
        except Exception as e:
            logger.error(f"❌ Failed to delete room (attempt {attempt}/{max_retries}): {e}")

            if attempt < max_retries:
                logger.info(f"⏳ Retrying in {retry_delay}s...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
            else:
                logger.critical(f"🚨 CRITICAL: Failed to delete room after {max_retries} attempts!")
                try:
                    await ctx.disconnect()
                    logger.info("🔌 Disconnected from room (will auto-delete in 30s due to empty_timeout)")
                except Exception as disconnect_error:
                    logger.error(f"❌ Disconnect also failed: {disconnect_error}")


# --- Prompt builder ---
def build_full_prompt(user_prompt: str) -> str:
    """
    Combine user's custom prompt from database with system instructions

    Args:
        user_prompt: The prompt from database (agent.prompt)

    Returns:
        Complete prompt with system instructions + user prompt
    """
    # System instructions - Add your custom rules here
    system_instructions = """التوجيهات الأساسية:
اللهجة والأسلوب
استخدم لهجة سعودية طبيعية ومهذّبة ومناسبة لكل الفئات العمرية.
تجنّب المبالغة في العامية أو الألفاظ المحلية الثقيلة إلا إذا طلب المستخدم ذلك.
توازن بين البساطة والاحترافية حسب السياق.


طريقة الإجابة
الردود مختصرة وواضحة ومباشرة، مع قيمة ومعلومة مفيدة.
استخدم عبارات لائقة شائعة في السعودية مثل:
 "حاضر"، "أبشر"، "سم"، "تمام" ، "ابشر طال عمرك"، "أمورك طيبة"، "ولا يهمّك".
في المواضيع الرسمية أو الحكومية يميل الأسلوب للفصحى المبسطة مع نكهة سعودية.


المرونة في اللهجات
إن لم يحدد المستخدم لهجته، استخدم لهجة سعودية محايدة مفهومة للجميع (قريبة من النجدية/الحجازية).
إذا استخدم المستخدم لهجة معيّنة، طابق لهجته بشكل طبيعي دون تكلف.


التخصيص والإحترام الثقافي
احترم الثقافة السعودية والقيم والعادات. التزم بحدود الذوق والثقافة السعودية.
تجنب الإفتاء الشرعي، لا تفتي في الدين وقدّم بدلًا عنه مصادر موثوقة أو نصح بالتواصل مع جهات رسمية.
كن على دراية بالبيئة السعودية: الجهات الحكومية، المناسبات، المصطلحات المحلية، الفعاليات، الحياة اليومية، المصطلحات التقنية الشائعة في السعودية.
تجنّب أي معلومة غير دقيقة خصوصًا في الأنظمة والقوانين.


ما يجب تجنّبه
عدم استخدام ألفاظ غير لائقة أو غريبة عن المنطقة.
عدم تقديم معلومات غير دقيقة عن أنظمة أو قوانين سعودية.
عدم الخوض في المواضيع السياسية أو الدينية، القبائل ويمكن التوجيه لرد مهذّب ومحايد.


قيمة مضافة للمستخدم السعودي
حسب الحاجة قدّم أمثلة، روابط رسمية، سياق سعودي وثقافي، وأساليب عملية تناسب الحياة في السعودية.


Dialect and Style
Use a natural, polite Saudi dialect suitable for all age groups.
Avoid excessive use of heavy slang or deeply local expressions unless the user requests it.
Balance simplicity and professionalism according to the context.

Response Method
Keep replies short, clear, and direct, while providing useful value or information.
Use polite expressions commonly used in Saudi Arabia, such as:
“ حاضر ” (Of course), “ أبشر ” (You got it), “ سم ” (Yes sir), “ تمام ” (Okay), “ أبشر طال عمرك ” (Certainly, sir), “ أمورك طيبة ” (All good), “ ولا يهمك ” (Don’t worry about it).
For official or governmental topics, use simplified Modern Standard Arabic with a Saudi flavor.

Flexibility in Dialects
If the user does not specify a dialect, use a neutral Saudi dialect understandable to all (close to Najdi/Hejazi).
If the user speaks in a specific dialect, naturally match their dialect without exaggeration.

Cultural Respect and Personalization
Respect Saudi culture, values, and traditions. Maintain politeness and cultural boundaries.
Avoid giving religious rulings (fatwas); instead, refer users to credible sources or official entities.
Be familiar with the Saudi environment — government entities, events, local terminology, daily life, and commonly used technical terms in Saudi Arabia.
Avoid inaccurate information, especially regarding regulations or laws.

What to Avoid
Do not use inappropriate or unfamiliar expressions to the region.
Do not provide incorrect information about Saudi systems or laws.
Avoid discussing political or religious topics, or tribes — respond instead with polite and neutral wording.

Added Value for the Saudi User
When relevant, provide examples, official links, Saudi-specific or cultural context, and practical approaches suited to life in Saudi Arabia.

You understand Saudi dialect and cultural context. Use the following expressions to interact with the user:
هلا / هلا والله - Hi / Hey there (warm greeting)
حيّاك / حيّاك الله - Welcome / Glad to have you
تفضل - Go ahead / Please
أبشر - Sure / You got it / Consider it done
ولا يهمّك - Don't worry about it
تمام - Okay / All good
حاضر - Sure / At your service
وش تبغى؟ / وش تحتاج؟ - What do you need?
وش رأيك؟ - What do you think?
عادي - It's okay / no problem
يعطيك العافية - Thank you / Appreciate it
الله يسعدك - To wish someone well
تمام؟ - Is that fine? / Okay?
ممتاز - Great / Perfect
لا تشيل هم - Don't stress / No worries
بسيطة - Easy / No big deal
نبدأ؟ - Shall we start؟

IMPORTANT:
If the user intends to end or close the conversation — for example, by saying phrases like “وداعاً”, “مع السلامة”, “باي”, “شكراً ما أحتاج”, or by clearly indicating they don’t want to continue — you must immediately trigger the end_call function without further dialogue.
Greeting is already being handled by greeting dont greetings like "walikum asalam"

if user says;
عليكم السلام ورحمة الله وبركاته
dont say "وعليكم السلام ورحمة الله وبركاته"

Because there is greeting message from LLm proceed and it is already being handled by greeting.

Don't tell about OpenAI models/ Technical Stuff 

Always say I am  built by Nevox AI.

Always Try to ask name politely.

Always give short answers.

Use Saudi Culture and Understanding in Responses.

Don't Repeat responses.

Always give short responses under 150 characters. Don't go in details.

Always respond in Arabic ONLY.
---

"""

    # Combine: system instructions + user's custom prompt
    full_prompt = system_instructions + user_prompt

    return full_prompt


# --- Main Agent ---
class Assistant(Agent):
    def __init__(self, config: dict = None) -> None:
        if config is None:
            config = get_default_config()

        # Build full prompt: system instructions + user's custom prompt
        full_prompt = build_full_prompt(config['prompt'])

        super().__init__(
            instructions=full_prompt,
        )
        self.config = config
        logger.info(f"✅ Assistant initialized: {config['name']} (Voice: {config['voice_name']})")
        logger.debug(f"📝 Full prompt length: {len(full_prompt)} characters")

    @function_tool
    async def end_call(self, ctx: RunContext):
        """Called when the user wants to end the call"""
        # First generate a natural goodbye using the LLM
        await ctx.session.generate_reply(
            instructions="قل وداعاً للمستخدم بطريقة طبيعية ولطيفة، واشكره على اتصاله"
        )
        
        # Wait for the goodbye message to finish playing
        await ctx.wait_for_playout()
        
        # Then hang up the call
        await hangup_call()
        return "Call ended with goodbye"


# --- Entrypoint ---
async def entrypoint(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}
    logger.info(f"🎯 Room: {ctx.room.name}")
    logger.info(f"📊 Participants: {ctx.room.num_participants}")

    # Extract agent_id from room name (format: call-{agent_id}-{timestamp})
    agent_config = get_default_config()
    try:
        room_parts = ctx.room.name.split('-')
        if len(room_parts) >= 2 and room_parts[0] == 'call':
            agent_id = int(room_parts[1])
            logger.info(f"🔍 Fetching config for agent ID: {agent_id}")

            fetched_config = get_agent_config(agent_id)
            if fetched_config:
                agent_config = fetched_config
                logger.info(f"✅ Loaded agent: {agent_config['name']}")
            else:
                logger.warning(f"⚠️  Agent {agent_id} not found, using default config")
        else:
            logger.info("ℹ️  Using default agent configuration")
    except Exception as e:
        logger.error(f"❌ Error parsing agent ID: {e}, using default config")

    # Initialize transcription manager
    transcription = TranscriptionManager()
    call_start_time = time.time()

    # --- ElevenLabs TTS with dynamic voice ---
    logger.info(f"🔊 Initializing TTS with voice: {agent_config['voice_name']} ({agent_config['voice_id']})")
    tts_engine = elevenlabs.TTS(
        voice_id=agent_config['voice_id'],
        model="eleven_turbo_v2_5",  # Fastest model
        language="ar",
        auto_mode=True,
        voice_settings=elevenlabs.VoiceSettings(
            stability=0.75,  # Lower = faster (0.71 recommended for speed)
            similarity_boost=0.5,  # Lower = faster
            style=0.0,  # Keep 0 for speed
            speed=0.91,  # Increase from 0.95 to 1.0 for faster speech
            use_speaker_boost=True
        ),
        streaming_latency=1,  # 0 = Maximum speed, 4 = Maximum quality
        inactivity_timeout=60,
        enable_ssml_parsing=False,  # Disable for speed (unless you need SSML)
        apply_text_normalization="auto"  # "auto" is faster than "on"
    )
    # --- Google STT for transcription ---
    base_stt_engine = google.STT(
            languages=["ar-SA"],         # Arabic (Saudi Arabia)
            model="latest_long",         # For full conversation accuracy
            spoken_punctuation=False,    # Don’t transcribe “comma” literally
            punctuate=True,              # Add punctuation automatically
            interim_results=True,        # For live transcription
            detect_language=False,       # We already set ar-SA
            sample_rate=16000,           # Standard mic sample rate
            credentials_file="aimeetingassistant-448613-1ff1fc705734.json",  # Path to your key
        )


    # --- OpenAI Realtime model with transcription ---
    llm_model = RealtimeModel(
        model="gpt-4o-realtime-preview",
        modalities=["text"],
        temperature=0.5,  # Keep low for consistency
        input_audio_transcription=InputAudioTranscription(
            model="whisper-1",
            language="ar"
        ),
        turn_detection=TurnDetection(
            type="server_vad",
            threshold=0.45,  # Keep at 0.5 for balance
            prefix_padding_ms=50,  # Reduced from 100ms → faster response
            silence_duration_ms=100,  # Reduced from 300ms → faster detection
            create_response=True,
            interrupt_response=True,
        ),
    )
    stt_engine_google = base_stt_engine
    '''
    # --- Google Gemini LLM for Arabic Voice Agent ---
    llm_model_google = google.LLM(
        model="gemini-2.0-flash-001",  # Latest Gemini Flash model (fast & efficient)
        api_key=os.environ.get("GOOGLE_API_KEY"),  # Use API key from .env
        temperature=0.3,  # Balanced creativity for natural Arabic conversation
        max_output_tokens=150,  # Keep responses concise for voice (adjust as needed)
        top_p=0.95,  # Nucleus sampling for quality responses
        top_k=40,  # Top-k sampling for diversity
        # Optional: Uncomment for Vertex AI (if using Google Cloud)
        # vertexai=True,
        # project="your-gcp-project-id",
        # location="us-central1",
    )
    '''
    # --- Create session ---
    # user_away_timeout: seconds of inactivity before user is considered "away"
    session = voice.AgentSession(
        llm=llm_model,
        tts=tts_engine,
        stt=stt_engine_google,
        user_away_timeout=float(os.environ.get('USER_AWAY_TIMEOUT', '60.0'))
    )

    # --- Metrics ---
    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    # --- USER INACTIVITY HANDLING ---
    inactivity_task: asyncio.Task | None = None
    call_ended: bool = False  # Flag to prevent inactivity handling after call ends

    async def user_presence_check():
        """Check if user is still present after being away"""
        try:
            # Ask user if they're still there (in Arabic)
            logger.warning("⏰ User marked as away, checking presence...")
            await session.generate_reply(
                instructions="المستخدم غير نشط. اسأله بلطف إذا كان لا يزال موجودًا"
            )
            await asyncio.sleep(10)  # Wait 10 seconds for response

            # If user still away after check, say goodbye and end call
            logger.warning("⏰ User still inactive after presence check. Ending call...")
            await session.generate_reply(
                instructions="قل للمستخدم: يبدو أنك لم تعد هناك. سأنهي المكالمة الآن. مع السلامة"
            )
            await asyncio.sleep(3)  # Wait for farewell message
            await hangup_call()
        except Exception as e:
            logger.error(f"Error in presence check: {e}")

    @session.on("user_state_changed")
    def _user_state_changed(ev: UserStateChangedEvent):
        """Handle user state changes (listening, speaking, away)"""
        nonlocal inactivity_task, call_ended

        logger.info(f"🔄 User state changed: {ev.new_state}")

        # CRITICAL: Ignore inactivity events if call has already ended
        if call_ended:
            logger.debug(f"⏭️ Ignoring user state change (call already ended)")
            return

        if ev.new_state == "away":
            # User has been inactive - start presence check
            logger.warning(f"⚠️ User away after {os.environ.get('USER_AWAY_TIMEOUT', '60')}s inactivity")
            inactivity_task = asyncio.create_task(user_presence_check())
            return

        # User is active again (listening, speaking, thinking)
        if inactivity_task is not None and not inactivity_task.done():
            logger.info("✅ User active again, cancelling presence check")
            inactivity_task.cancel()
            inactivity_task = None

    # --- TRANSCRIPTION HANDLERS - Set BEFORE starting session ---
    # Track last messages to avoid duplicates
    last_user_msg_committed = None
    last_agent_msg_committed = None

    @session.on("user_speech_committed")
    def on_user_speech_committed(msg: llm.ChatMessage):
        """Capture user speech when committed to conversation"""
        nonlocal last_user_msg_committed
        try:
            text = msg.content if isinstance(msg.content, str) else str(msg.content)
            text = text.strip()

            if text and text != last_user_msg_committed:
                last_user_msg_committed = text
                transcription.add_user_message(text, "user_speech_committed")
                logger.info(f"✅ [USER] speech committed: {text[:80]}")
        except Exception as e:
            logger.error(f"❌ Error capturing user speech: {e}")

    @session.on("agent_speech_committed")
    def on_agent_speech_committed(msg: llm.ChatMessage):
        """Capture agent speech"""
        nonlocal last_agent_msg_committed
        try:
            text = msg.content if isinstance(msg.content, str) else str(msg.content)
            text = text.strip()

            if text and text != last_agent_msg_committed:
                last_agent_msg_committed = text
                transcription.add_agent_message(text, "agent_speech_committed")
                logger.info(f"✅ [AGENT] speech committed: {text[:80]}")
        except Exception as e:
            logger.error(f"❌ Error capturing agent speech: {e}")

    # Track last messages to avoid duplicates (for fallback handlers)
    last_user_msg = None
    last_agent_msg = None

    # Fallback: Capture user transcripts directly from STT (captures ALL transcripts)
    @session.on("user_transcript")
    def on_user_transcript(transcript):
        """Fallback handler - captures ALL user transcripts from STT"""
        nonlocal last_user_msg
        try:
            # Handle different transcript formats
            if hasattr(transcript, 'text'):
                text = transcript.text.strip()
            elif hasattr(transcript, 'transcript'):
                text = transcript.transcript.strip()
            elif isinstance(transcript, str):
                text = transcript.strip()
            else:
                text = str(transcript).strip()

            if text and text != last_user_msg:
                last_user_msg = text
                transcription.add_user_message(text, "user_transcript")
                logger.info(f"✅ [USER] from STT: {text[:80]}")
        except Exception as e:
            logger.error(f"❌ Error capturing user transcript: {e}")

    # NOTE: agent_speech_committed handler is already defined above (line ~445)
    # Removed duplicate to avoid conflicts

    # BACKUP: Monitor session conversation directly - AGGRESSIVE MODE
    async def monitor_conversation():
        """Continuously monitor and extract conversation from session - captures ALL messages"""
        last_msg_count = 0

        try:
            while True:
                await asyncio.sleep(0.5)  # Check every 500ms for faster capture

                try:
                    # Access chat context from session
                    if hasattr(session, 'chat_ctx') and session.chat_ctx:
                        messages = session.chat_ctx.messages

                        # Only process new messages
                        if len(messages) > last_msg_count:
                            new_messages = messages[last_msg_count:]

                            for msg in new_messages:
                                role = msg.role
                                content = msg.content

                                if isinstance(content, str):
                                    text = content.strip()
                                elif isinstance(content, list):
                                    # Handle list of content parts
                                    text = ' '.join([
                                        str(part.text) if hasattr(part, 'text') else str(part)
                                        for part in content
                                    ]).strip()
                                else:
                                    text = str(content).strip()

                                if text:
                                    if role == 'user':
                                        transcription.add_user_message(text, "chat_context_monitor")
                                        logger.info(f"✅ [USER] from monitor: {text[:80]}")
                                    elif role == 'assistant':
                                        transcription.add_agent_message(text, "chat_context_monitor")
                                        logger.info(f"✅ [ASSISTANT] from monitor: {text[:80]}")

                            last_msg_count = len(messages)

                except Exception as e:
                    logger.debug(f"Monitor iteration error: {e}")

        except asyncio.CancelledError:
            logger.debug("Conversation monitor cancelled")
        except Exception as e:
            logger.error(f"Monitor fatal error: {e}")

    # Start conversation monitor
    conversation_monitor_task = asyncio.create_task(monitor_conversation())

    # Add to shutdown to cancel monitor
    async def cleanup_monitor():
        if conversation_monitor_task and not conversation_monitor_task.done():
            conversation_monitor_task.cancel()
            try:
                await conversation_monitor_task
            except asyncio.CancelledError:
                pass

    ctx.add_shutdown_callback(cleanup_monitor)




    # Additional event handlers for comprehensive capture
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

    # NOTE: user_transcript handler is already defined above (line ~454)
    # Removed duplicate handler to avoid conflicts

    @session.on("agent_transcript")
    def on_agent_transcript(transcript):
        """Agent transcript event"""
        try:
            transcription.add_agent_message(str(transcript), "agent_transcript_event")
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

    @session.on("chat_message")
    def on_chat_message(msg):
        """Capture chat messages"""
        try:
            if hasattr(msg, 'role') and hasattr(msg, 'content'):
                transcription.add_message(msg.role, msg.content, "chat_message_event")
        except:
            pass

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"📊 Usage: {summary}")

    async def send_call_data():
        """Send call completion data to Flask webhook"""
        call_duration = int(time.time() - call_start_time)

        logger.info(f"📝 Preparing transcription data...")
        logger.info(f"   Messages captured: {len(transcription.messages)}")
        logger.info(f"   Duration: {call_duration}s")

        # LAST RESORT: Extract from session one final time before sending
        if len(transcription.messages) == 0:
            logger.warning("⚠️ No messages captured! Attempting final extraction...")
            try:
                # Try accessing chat context one more time
                if hasattr(session, 'chat_ctx') and session.chat_ctx:
                    messages = session.chat_ctx.messages
                    logger.info(f"   Found {len(messages)} messages in chat_ctx")
                    
                    for msg in messages:
                        role = msg.role
                        content = msg.content
                        
                        if isinstance(content, str):
                            text = content.strip()
                        elif isinstance(content, list):
                            text = ' '.join([
                                str(part.text) if hasattr(part, 'text') else str(part)
                                for part in content
                            ]).strip()
                        else:
                            text = str(content).strip()
                        
                        if text:
                            transcription.add_message(role, text, "final_extraction")
                            logger.info(f"   Extracted [{role}]: {text[:60]}")
                
                # Try session history
                if hasattr(session, '_agent_output') and hasattr(session._agent_output, 'log'):
                    for entry in session._agent_output.log:
                        if hasattr(entry, 'role') and hasattr(entry, 'content'):
                            transcription.add_message(entry.role, entry.content, "agent_output_log")
            
            except Exception as e:
                logger.error(f"❌ Final extraction failed: {e}")
                import traceback
                logger.error(traceback.format_exc())

        # Log final message list
        logger.info(f"📋 Final transcription: {len(transcription.messages)} messages")
        for i, msg in enumerate(transcription.messages, 1):
            logger.info(f"   {i}. [{msg['role'].upper()}] ({msg['source']}): {msg['text'][:80]}")

        # Even if no messages, send the webhook (for tracking)
        try:
            payload = {
                'room_name': ctx.room.name,
                'duration': call_duration,
                'transcription': transcription.get_plain_text(),
                'metadata': transcription.get_json(),
                'message_count': len(transcription.messages)
            }

            logger.info(f"🚀 Sending webhook: {len(transcription.messages)} messages, {call_duration}s duration")

            async with aiohttp.ClientSession() as http_session:
                webhook_url = os.environ.get('FLASK_WEBHOOK_URL', 'http://localhost:5000/webhook/call-ended')
                async with http_session.post(webhook_url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        response_text = await resp.text()
                        logger.info(f"✅ Webhook delivered successfully!")
                        logger.info(f"   Response: {response_text[:200]}")
                    else:
                        logger.error(f"❌ Webhook failed with status: {resp.status}")
                        logger.error(f"   Response: {await resp.text()}")
        except asyncio.TimeoutError:
            logger.error(f"❌ Webhook timeout after 10 seconds")
        except Exception as e:
            logger.error(f"❌ Failed to send call data: {e}")
            import traceback
            logger.error(traceback.format_exc())

    ctx.add_shutdown_callback(log_usage)
    ctx.add_shutdown_callback(send_call_data)

    # Session monitor to periodically extract conversation
    monitor_task = None

    async def monitor_session():
        """Periodically check session for conversation updates"""
        try:
            while True:
                await asyncio.sleep(10)  # Check every 10 seconds
                try:
                    # Try multiple ways to access conversation data
                    if hasattr(session, 'llm'):
                        llm_obj = session.llm

                        # Check realtime sessions
                        if hasattr(llm_obj, 'sessions'):
                            for rt_session in llm_obj.sessions:
                                if hasattr(rt_session, 'conversation') and hasattr(rt_session.conversation, 'messages'):
                                    for msg in rt_session.conversation.messages:
                                        if hasattr(msg, 'role') and hasattr(msg, 'content'):
                                            transcription.add_message(msg.role, msg.content, "monitor_realtime")

                        # Check llm conversation
                        if hasattr(llm_obj, 'conversation') and hasattr(llm_obj.conversation, 'messages'):
                            for msg in llm_obj.conversation.messages:
                                if hasattr(msg, 'role') and hasattr(msg, 'content'):
                                    transcription.add_message(msg.role, msg.content, "monitor_llm")

                    # Check session chat context
                    if hasattr(session, 'chat_ctx') and hasattr(session.chat_ctx, 'messages'):
                        for msg in session.chat_ctx.messages:
                            if hasattr(msg, 'role') and hasattr(msg, 'content'):
                                transcription.add_message(msg.role, msg.content, "monitor_chat_ctx")

                except Exception as e:
                    logger.debug(f"Monitor error: {e}")
        except asyncio.CancelledError:
            logger.debug("Monitor task cancelled (expected on call end)")

    # --- Start session with dynamic agent ---
    logger.info(f"🚀 Starting session with agent: {agent_config['name']}")
    await session.start(
        room=ctx.room,
        agent=Assistant(config=agent_config),
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVCTelephony(),
        ),
    )

    # Start session monitor in background
    monitor_task = asyncio.create_task(monitor_session())

    # --- Connect room ---
    await ctx.connect()

    # --- Wait for SIP participant and capture info ---
    logger.info("⏳ Waiting for participant...")
    participant = await ctx.wait_for_participant()

    # Store SIP participant information
    transcription.set_sip_info(participant)
    logger.info(f"✅ Participant joined: {participant.identity} (Kind: {participant.kind})")

    # Monitor for participant disconnect to end room
    @ctx.room.on("participant_disconnected")
    def on_participant_disconnected(participant: rtc.RemoteParticipant):
        """End room when phone user disconnects"""
        nonlocal inactivity_task, monitor_task, call_ended

        if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
            logger.info(f"📴 SIP participant disconnected: {participant.identity}")

            # CRITICAL: Set flag to prevent future inactivity events from firing
            call_ended = True

            # CRITICAL: Cancel all background tasks to prevent worker from getting stuck
            if inactivity_task is not None and not inactivity_task.done():
                logger.info("✅ Cancelling inactivity timer (call ended)")
                inactivity_task.cancel()
                inactivity_task = None

            if monitor_task is not None and not monitor_task.done():
                logger.debug("✅ Cancelling monitor task (call ended)")
                monitor_task.cancel()

            logger.info("🔚 Ending room because phone user left...")
            asyncio.create_task(hangup_call())

    # --- Initial greeting ---
    logger.info("🎤 Playing fixed greeting...")
    # Use greeting from agent config (from database)
    greeting_message = agent_config.get('greeting', 'السلام عليكم ورحمة الله وبركاته، أهلاً وسهلاً فيك. أنا مساعدك الذكي، كيف أقدر أساعدك اليوم؟')
    logger.info(f"📢 Greeting: {greeting_message[:50]}...")
    await session.say(greeting_message)


# --- Worker Load Management (Module Level for Multiprocessing) ---
_last_logged_load = None
_last_log_time = 0

def compute_load(worker) -> float:
    """
    Calculate current worker load based on active jobs.
    Returns: 0.0 (no load) to 1.0 (full load)

    Prevents overload by limiting concurrent calls to a safe maximum.
    Must be at module level for multiprocessing pickle compatibility.
    """
    global _last_logged_load, _last_log_time

    active_jobs = len(worker.active_jobs)
    max_concurrent = int(os.environ.get('MAX_CONCURRENT_CALLS', '15'))

    # Calculate load as percentage of max capacity
    load = min(active_jobs / max_concurrent, 1.0)

    # Log only when load changes OR every 30 seconds (reduce spam)
    current_time = time.time()
    should_log = (
        active_jobs != _last_logged_load or  # Load changed
        (active_jobs > 0 and current_time - _last_log_time > 50)  # Every 50s if active
    )

    if should_log:
        if active_jobs > 0:
            logger.info(f"📊 Worker load: {active_jobs}/{max_concurrent} active jobs ({load*100:.0f}% capacity)")
        _last_logged_load = active_jobs
        _last_log_time = current_time

    return load


if __name__ == "__main__":
    # Configure worker with essential production options
    opts = WorkerOptions(
        entrypoint_fnc=entrypoint,

        # Load management - prevents system overload
        load_fnc=compute_load,
        load_threshold=0.9,  # Stop accepting new jobs at 90% capacity (13-14 concurrent calls)

        # Graceful shutdown - allows active calls to complete
        drain_timeout=300,  # Wait up to 5 minutes for active jobs to finish
    )

    logger.info("🚀 Starting LiveKit agent worker with load management...")
    logger.info(f"   Max concurrent calls: {os.environ.get('MAX_CONCURRENT_CALLS', '15')}")
    logger.info(f"   Load threshold: 90%")
    logger.info(f"   Drain timeout: 300 seconds")

    cli.run_app(opts)