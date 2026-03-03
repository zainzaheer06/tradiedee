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

# Import knowledge base service for RAG (imports trigger pre-loading)
from services.knowledge_base_service import kb_service

# Import recording service
from services.recording_service import recording_service

# Import tool service for dynamic tools
from services.tool_service import tool_service

logger = logging.getLogger("agent-inbound")
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


def get_inbound_agent_by_number(to_number):
    """Fetch inbound configuration and linked agent by phone number (TO number - number dialed by customer)"""
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

        # Clean the phone number (remove spaces, dashes, plus signs for comparison)
        clean_to_number = to_number.replace('+', '').replace('-', '').replace(' ', '') if to_number else ''

        # Query InboundConfiguration with JOIN to get linked agent details
        cursor.execute("""
            SELECT
                ic.id as config_id,
                ic.name as config_name,
                ic.phone_number,
                a.id as agent_id,
                a.name as agent_name,
                a.prompt,
                a.greeting,
                a.voice_id,
                a.voice_name
            FROM inbound_configuration ic
            INNER JOIN agent a ON ic.agent_id = a.id
            ORDER BY ic.created_at DESC
        """)

        rows = cursor.fetchall()
        conn.close()

        # Try to match by phone number
        for row in rows:
            if row['phone_number']:
                clean_config_number = row['phone_number'].replace('+', '').replace('-', '').replace(' ', '')
                # Check if the TO number ends with the config's number or vice versa
                if clean_to_number and (clean_to_number.endswith(clean_config_number) or clean_config_number.endswith(clean_to_number)):
                    config = {
                        'id': row['agent_id'],  # Use linked agent ID
                        'config_id': row['config_id'],
                        'config_name': row['config_name'],
                        'name': row['agent_name'],
                        'prompt': row['prompt'],
                        'greeting': row['greeting'] if row['greeting'] else 'السلام عليكم ورحمة الله وبركاته، أهلاً وسهلاً فيك. أنا مساعدك الذكي، كيف أقدر أساعدك اليوم؟',
                        'voice_id': row['voice_id'],
                        'voice_name': row['voice_name']
                    }
                    logger.info(f"📞 Matched TO number {to_number} → Config: {config['config_name']}, Agent: {config['name']} (ID: {config['id']})")
                    return config

        # No match found - return latest config as fallback
        if rows:
            row = rows[0]  # Most recent
            config = {
                'id': row['agent_id'],  # Use linked agent ID
                'config_id': row['config_id'],
                'config_name': row['config_name'],
                'name': row['agent_name'],
                'prompt': row['prompt'],
                'greeting': row['greeting'] if row['greeting'] else 'السلام عليكم ورحمة الله وبركاته، أهلاً وسهلاً فيك. أنا مساعدك الذكي، كيف أقدر أساعدك اليوم؟',
                'voice_id': row['voice_id'],
                'voice_name': row['voice_name']
            }
            logger.warning(f"⚠️  No config matched TO number {to_number}, using latest: {config['config_name']} → {config['name']}")
            return config
        else:
            logger.warning(f"⚠️  No inbound configurations found in database")
            return None

    except sqlite3.Error as e:
        logger.error(f"❌ Database error fetching inbound configuration: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Unexpected error fetching inbound configuration: {e}")
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
        self.recording_id = None  # Store LiveKit recording/egress ID
        self.greeting_added = False  # FIXED: Track if greeting was already added

    def add_message(self, role: str, text: str, source: str = ""):
        """Add a message with deduplication"""
        if not isinstance(text, str) or not text.strip():
            return

        # Create unique key for deduplication
        msg_key = f"{role}:{text.strip()}"
        if msg_key in self.seen_messages:
            logger.debug(f"⏭️  Skipping duplicate message from {source}")
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
            "sip_info": self.sip_info,
            "recording_id": self.recording_id
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
    system_instructions = """
You are a polite and helpful Saudi Arabic voice assistant.

# DIALECT & STYLE
- Use a natural, polite Saudi dialect suitable for all age groups.
- Avoid heavy slang unless the user requests it.
- Keep a balance between Saudi dialect and simple Modern Standard Arabic, especially in official/government topics.

# RESPONSE BEHAVIOR
- Replies must be short, clear, and spoken naturally (1-2 sentences, max 150 characters).
- Always respond in Arabic only.
- Do NOT output JSON, code, or technical formatting.
- Ask for the user's name politely when appropriate.
- Never repeat previous responses.
- Keep every response directly relevant to the user's question.

# GUARDRAILS
## NEVER EVER speak these things out loud:
- Function names like "end_call", "detected_answering_machine"
- Function parameters like {query: ...}, {name: ...}
- JSON structures like {"key": "value"}
- Technical formatting or markup
- Code or system messages

# CULTURAL RULES
- Respect Saudi culture, values, and etiquette.
- Avoid political, religious, tribal, or sensitive discussions.
- Do not give fatwas; instead, redirect politely to official sources.
- Use commonly accepted Saudi expressions when suitable:
  هلا، هلا والله، حيّاك الله، تفضل، أبشر، ولا يهمك، تمام، حاضر، وش تبغى، وش تحتاج، يعطيك العافية، الله يسعدك، ممتاز، بسيطة، لا تشيل هم.

# DIALECT HANDLING
- Default: neutral Saudi dialect (Najdi/Hijazi).
- If the user speaks in a specific dialect, naturally mirror it without exaggeration.

# HANDLING VOICEMAIL
- If you detect an answering machine or voicemail greeting, wait until it finishes.
- Then leave a polite voicemail message in ARABIC letting the user know you'll call back later. 
- detected_answering_machine tool is available for this purpose.
- don't respond in that way; {"name": "detected_answering_machine"}

# GREETING RULES
- Greeting is handled separately by another system.
- If user says: "عليكم السلام ورحمة الله وبركاته", DO NOT repeat "وعليكم السلام".
- Never generate greeting lines that conflict with the greeting system.
- No JSON, no markup, no technical responses.

# END-OF-CALL LOGIC
If the user indicates they want to end the interaction (e.g., "وداعاً", "مع السلامة", "باي", "شكراً ما أحتاج"):
→ Immediately trigger end_call (no extra goodbye).

# IDENTITY RULES
- Never mention OpenAI, models, or technical systems.
- Always say you are built by Nevox AI when identity is requested.

# AVOID
- Off-topic answers.
- Long explanations.
- Any formatting besides normal Arabic speech.
- Incorrect or speculative information about Saudi regulations or entities.

# OUTPUT REQUIREMENTS (CRITICAL)
- Arabic only.
- 1-2 sentences max.
- Under 150 characters.
- Spoken-style, clean, natural, human-like.
- No JSON, no markup, no technical responses.


"""

    # Combine: system instructions + user's custom prompt
    full_prompt = system_instructions + user_prompt

    return full_prompt


# --- Main Agent ---
class Assistant(Agent):
    def __init__(self, config: dict = None, agent_id: int = None) -> None:
        if config is None:
            config = get_default_config()

        # Build full prompt: system instructions + user's custom prompt
        full_prompt = build_full_prompt(config['prompt'])

        # Load dynamic tools if agent_id is provided
        dynamic_tools = []
        if agent_id:
            try:
                dynamic_tools = tool_service.create_function_tools(agent_id)
                logger.info(f"📦 Loaded {len(dynamic_tools)} custom tools for agent {agent_id}")
            except Exception as e:
                logger.error(f"❌ Error loading custom tools: {e}")

        super().__init__(
            instructions=full_prompt,
            tools=dynamic_tools,  # Pass dynamic tools to agent
        )
        self.config = config
        self.agent_id = agent_id
        logger.info(f"✅ Assistant initialized: {config['name']} (Voice: {config['voice_name']})")
        logger.debug(f"📝 Full prompt length: {len(full_prompt)} characters")
        if dynamic_tools:
            logger.info(f"🔧 Tools enabled: {[t.__name__ if hasattr(t, '__name__') else str(t) for t in dynamic_tools]}")

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

    @function_tool
    async def detected_answering_machine(self):
        """Call this tool if you have detected a voicemail system, AFTER hearing the voicemail greeting"""
        await self.session.generate_reply(
            instructions="اترك رسالة صوتية تخبر المستخدم بأنك ستعاود الاتصال لاحقاً."
        )
        await asyncio.sleep(0.5) # Add a natural gap to the end of the voicemail message
        await hangup_call()


# --- Entrypoint ---
async def entrypoint(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}
    
    # FIXED: Add debug info to detect multiple room spawning
    logger.info(f"🎯 Room: {ctx.room.name}")
    logger.info(f"📊 Initial participants: {ctx.room.num_participants}")

    # --- Connect room first to get participant info ---
    await ctx.connect()

    # --- Wait for SIP participant to get the TO number ---
    logger.info("⏳ Waiting for participant to get phone number...")
    participant = await ctx.wait_for_participant()
    logger.info(f"✅ Participant joined: {participant.identity} (Kind: {participant.kind})")

    # Extract TO number (number dialed by customer) from SIP attributes
    to_number = None
    if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
        to_number = participant.attributes.get('sip.trunkPhoneNumber', '')
        logger.info(f"📞 TO Number (dialed): {to_number}")

    # Try to match agent by TO number
    agent_config = get_inbound_agent_by_number(to_number) if to_number else None

    # If no match by TO number, try to extract agent_id from room name (format: call-{agent_id}-{timestamp})
    if not agent_config:
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
                    logger.warning(f"⚠️  Agent {agent_id} not found in database")
            else:
                logger.info("ℹ️  Room name doesn't contain agent ID")
        except Exception as e:
            logger.error(f"❌ Error parsing agent ID: {e}")

    # Fall back to default config if still not found
    if not agent_config:
        logger.warning("⚠️  No agent config found, using default configuration")
        agent_config = get_default_config()

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
            spoken_punctuation=False,    # Don't transcribe "comma" literally
            punctuate=True,              # Add punctuation automatically
            interim_results=True,        # For live transcription
            detect_language=False,       # We already set ar-SA
            sample_rate=16000,           # Standard mic sample rate
            credentials_file="config/google/aimeetingassistant-448613-1ff1fc705734.json",  # Path to your key
        )

    # --- OpenAI Realtime model with transcription ---
    llm_model_realtime = RealtimeModel(
        model="gpt-4o-realtime-preview",
        modalities=["text"], # Enable audio input for better context and remove verbalization bug
        temperature=0.3,  # Keep low for consistency
        input_audio_transcription=InputAudioTranscription(
            model="whisper-1",
            language="ar"
        ),
        turn_detection=TurnDetection(
            type="server_vad",
            threshold=0.45,  # Keep at 0.5 for balance
            prefix_padding_ms=150,  # Reduced from 100ms → faster response
            silence_duration_ms=250,  # Reduced from 300ms → faster detection
            create_response=True,
            interrupt_response=True,
        ),
    )
    stt_engine_google = base_stt_engine
    llm_model = openai.LLM(
        model="gpt-4o-mini",  # Best Arabic performance + cost balance
        temperature=0.4,
    )
    # --- Create session ---
    # user_away_timeout: seconds of inactivity before user is considered "away"
    session = voice.AgentSession(
        llm=llm_model_realtime,
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
        except Exception as e:
            logger.error(f"❌ Error capturing user speech: {e}")

    @session.on("agent_speech_committed")
    def on_agent_speech_committed(msg: llm.ChatMessage):
        """Capture agent speech when committed to conversation"""
        nonlocal last_agent_msg_committed
        try:
            text = msg.content if isinstance(msg.content, str) else str(msg.content)
            text = text.strip()

            # FIXED: Skip greeting if it was already added manually
            if text and text != last_agent_msg_committed:
                # Check if this is the greeting (don't add twice)
                if transcription.greeting_added and text == agent_config.get('greeting'):
                    logger.debug("⏭️  Skipping greeting (already added manually)")
                    return
                
                last_agent_msg_committed = text
                transcription.add_agent_message(text, "agent_speech_committed")
        except Exception as e:
            logger.error(f"❌ Error capturing agent speech: {e}")

    # Track last messages to avoid duplicates (for fallback handlers)
    last_user_msg = None

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
        except Exception as e:
            logger.error(f"❌ Error capturing user transcript: {e}")

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
                                    elif role == 'assistant':
                                        # FIXED: Skip greeting in monitor too
                                        if transcription.greeting_added and text == agent_config.get('greeting'):
                                            logger.debug("⏭️  Monitor: Skipping greeting duplicate")
                                            continue
                                        transcription.add_agent_message(text, "chat_context_monitor")

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

    # Additional event handlers for comprehensive capture (FIXED: removed duplicates)
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
                # FIXED: Skip greeting
                if transcription.greeting_added and content == agent_config.get('greeting'):
                    return
                transcription.add_agent_message(content, "agent_message_event")
        except:
            pass

    @session.on("agent_transcript")
    def on_agent_transcript(transcript):
        """Agent transcript event"""
        try:
            text = str(transcript)
            # FIXED: Skip greeting
            if transcription.greeting_added and text == agent_config.get('greeting'):
                return
            transcription.add_agent_message(text, "agent_transcript_event")
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
                    # FIXED: Skip greeting
                    if item.role == 'assistant' and transcription.greeting_added and content == agent_config.get('greeting'):
                        return
                    transcription.add_message(item.role, content, "conversation_item")
        except Exception as e:
            logger.debug(f"Error in conversation_item_added: {e}")

    @session.on("chat_message")
    def on_chat_message(msg):
        """Capture chat messages"""
        try:
            if hasattr(msg, 'role') and hasattr(msg, 'content'):
                content = msg.content
                # FIXED: Skip greeting
                if msg.role == 'assistant' and transcription.greeting_added and content == agent_config.get('greeting'):
                    return
                transcription.add_message(msg.role, content, "chat_message_event")
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
        if len(transcription.messages) <= 1:  # Only greeting
            logger.warning("⚠️ Very few messages captured! Attempting final extraction...")
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
                            # FIXED: Skip greeting in final extraction
                            if role == 'assistant' and transcription.greeting_added and text == agent_config.get('greeting'):
                                continue
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
                webhook_url = os.environ.get('FLASK_WEBHOOK_URL', 'http://localhost:5002/webhook/call-ended')
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
                                            # FIXED: Skip greeting
                                            if msg.role == 'assistant' and transcription.greeting_added and msg.content == agent_config.get('greeting'):
                                                continue
                                            transcription.add_message(msg.role, msg.content, "monitor_realtime")

                        # Check llm conversation
                        if hasattr(llm_obj, 'conversation') and hasattr(llm_obj.conversation, 'messages'):
                            for msg in llm_obj.conversation.messages:
                                if hasattr(msg, 'role') and hasattr(msg, 'content'):
                                    # FIXED: Skip greeting
                                    if msg.role == 'assistant' and transcription.greeting_added and msg.content == agent_config.get('greeting'):
                                        continue
                                    transcription.add_message(msg.role, msg.content, "monitor_llm")

                    # Check session chat context
                    if hasattr(session, 'chat_ctx') and hasattr(session.chat_ctx, 'messages'):
                        for msg in session.chat_ctx.messages:
                            if hasattr(msg, 'role') and hasattr(msg, 'content'):
                                # FIXED: Skip greeting
                                if msg.role == 'assistant' and transcription.greeting_added and msg.content == agent_config.get('greeting'):
                                    continue
                                transcription.add_message(msg.role, msg.content, "monitor_chat_ctx")

                except Exception as e:
                    logger.debug(f"Monitor error: {e}")
        except asyncio.CancelledError:
            logger.debug("Monitor task cancelled (expected on call end)")

    # --- Pre-load KB context into agent instructions ---
    agent_id = agent_config.get('id')
    if agent_id and agent_id in kb_service._index_cache:
        logger.info(f"📚 Injecting KB context for agent {agent_id} into instructions...")
        try:
            # Retrieve full KB context (pre-loaded, so this is FAST)
            kb_context = await kb_service.retrieve_context(
                agent_id,
                query="معلومات عامة عن الشركة والخدمات",  # General query to get all relevant info
                top_k=10  # Get more chunks since this is pre-session
            )

            if kb_context:
                # Inject KB context into the agent's prompt
                agent_config['prompt'] = agent_config['prompt'] + "\n\n" + kb_context
                logger.info(f"✅ KB context injected ({len(kb_context)} chars) - Agent will ALWAYS have this info")
            else:
                logger.info("ℹ️  No KB content found for this agent")
        except Exception as e:
            logger.error(f"❌ Error injecting KB context: {e}")
    else:
        logger.info(f"ℹ️  No knowledge base for agent {agent_id}")

    # --- Start session with dynamic agent ---
    logger.info(f"🚀 Starting session with agent: {agent_config['name']}")
    agent_id = agent_config.get('id', None)
    await session.start(
        room=ctx.room,
        agent=Assistant(config=agent_config, agent_id=agent_id),
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVCTelephony(),
        ),
    )

    # Start session monitor in background
    monitor_task = asyncio.create_task(monitor_session())

    # Store SIP participant information (participant already obtained earlier)
    transcription.set_sip_info(participant)

    # CRITICAL: Wait for participant's audio track to be published (SIP media negotiation)
    logger.info("⏳ Waiting for participant audio track...")
    try:
        # Wait up to 5 seconds for audio track
        timeout = 5.0
        start_wait = time.time()
        while time.time() - start_wait < timeout:
            audio_tracks = [track for track in participant.track_publications.values()
                           if track.kind == rtc.TrackKind.KIND_AUDIO]
            if audio_tracks:
                logger.info(f"✅ Found {len(audio_tracks)} audio track(s) from participant")
                break
            await asyncio.sleep(0.2)
        else:
            logger.warning("⚠️ No audio tracks found from participant after 5 seconds - continuing anyway")
    except Exception as e:
        logger.warning(f"⚠️ Error waiting for audio tracks: {e} - continuing anyway")

    # START RECORDING: Now that call is answered and audio is flowing
    logger.info("🎙️ Starting call recording...")
    try:
        recording_id = await recording_service.start_recording(ctx.room.name)
        if recording_id:
            transcription.recording_id = recording_id
            logger.info(f"✅ Recording started with ID: {recording_id}")
        else:
            logger.warning("⚠️ Failed to start recording, continuing without recording")
    except Exception as e:
        logger.error(f"❌ Error starting recording: {e} - continuing without recording")

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

    # --- FIXED: Initial greeting with proper deduplication ---
    # CRITICAL: Wait for media tracks to be fully established (especially for SIP)
    logger.info("⏳ Waiting for media tracks to establish...")
    await asyncio.sleep(1.5)  # Give SIP time to establish media connection

    logger.info("🎤 Playing fixed greeting...")
    greeting_message = agent_config.get('greeting', 'السلام عليكم ورحمة الله وبركاته، أهلاً وسهلاً فيك. أنا مساعدك الذكي، كيف أقدر أساعدك اليوم؟')
    logger.info(f"📢 Greeting: {greeting_message[:50]}...")
    
    # FIXED: Add greeting to transcription FIRST (before session.say)
    # This marks it as already added, so event handlers will skip it
    transcription.add_message("assistant", greeting_message, "initial_greeting")
    transcription.greeting_added = True  # Set flag to prevent duplicates
    logger.info("✅ Greeting added to transcription (marked as added)")
    
    # Now play greeting via session (this will trigger events, but they'll be skipped)
    await session.say(greeting_message, allow_interruptions=True)
    logger.info("✅ Greeting sent to TTS")
    
    # Wait a moment for greeting to start playing
    await asyncio.sleep(0.5)
    logger.info("✅ Greeting should now be playing to user")


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

        # IMPORTANT: agent_name must match the dispatch rule's agentName field
        agent_name="agent-inbound",

        # Load management - prevents system overload
        load_fnc=compute_load,
        load_threshold=0.9,  # Stop accepting new jobs at 90% capacity (13-14 concurrent calls)

        # Graceful shutdown - allows active calls to complete
        drain_timeout=300,  # Wait up to 5 minutes for active jobs to finish
    )

    logger.info("🚀 Starting LiveKit inbound agent worker with recording & KB...")
    logger.info(f"   Agent name: agent-inbound (explicit dispatch)")
    logger.info(f"   Max concurrent calls: {os.environ.get('MAX_CONCURRENT_CALLS', '15')}")
    logger.info(f"   Load threshold: 90%")
    logger.info(f"   Drain timeout: 300 seconds")

    cli.run_app(opts)