import asyncio
import logging
import os
import time
import json
import aiohttp
import sqlite3
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

# Saudi Arabia Timezone (UTC+3)
SAUDI_TZ = timezone(timedelta(hours=3))
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
            SELECT id, name, prompt, greeting, voice_id, voice_name, workflow_id
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
                'greeting': row['greeting'] if row['greeting'] else "G'day! How can we help you today?",
                'voice_id': row['voice_id'],
                'voice_name': row['voice_name'],
                'workflow_id': row['workflow_id']
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

        # Clean the phone number
        clean_to_number = to_number.replace('+', '').replace('-', '').replace(' ', '') if to_number else ''

        # Query InboundConfiguration with JOIN
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
                a.voice_name,
                a.workflow_id
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
                if clean_to_number and (clean_to_number.endswith(clean_config_number) or clean_config_number.endswith(clean_to_number)):
                    config = {
                        'id': row['agent_id'],
                        'config_id': row['config_id'],
                        'config_name': row['config_name'],
                        'name': row['agent_name'],
                        'prompt': row['prompt'],
                        'greeting': row['greeting'] if row['greeting'] else "G'day! How can we help you today?",
                        'voice_id': row['voice_id'],
                        'voice_name': row['voice_name'],
                        'workflow_id': row['workflow_id']
                    }
                    logger.info(f"📞 Matched TO number {to_number} → Config: {config['config_name']}, Agent: {config['name']} (ID: {config['id']})")
                    return config

        # No match - return latest
        if rows:
            row = rows[0]
            config = {
                'id': row['agent_id'],
                'config_id': row['config_id'],
                'config_name': row['config_name'],
                'name': row['agent_name'],
                'prompt': row['prompt'],
                'greeting': row['greeting'] if row['greeting'] else "G'day! How can we help you today?",
                'voice_id': row['voice_id'],
                'voice_name': row['voice_name'],
                'workflow_id': row['workflow_id']
            }
            logger.warning(f"⚠️  No config matched TO number {to_number}, using latest: {config['config_name']}")
            return config
        else:
            logger.warning(f"⚠️  No inbound configurations found")
            return None

    except Exception as e:
        logger.error(f"❌ Error fetching inbound configuration: {e}")
        return None


def get_default_config():
    """Return default agent configuration"""
    return {
        'id': 0,
        'name': 'CallTradie Receptionist',
        'prompt': """You are a friendly Australian trades receptionist answering calls for a plumbing, electrical, or HVAC business.
Your job is to:
1. Greet customers warmly
2. Understand what service they need
3. Check if it's an emergency
4. Get their contact details and address
5. Check available appointment times
6. Book their appointment
7. Confirm with SMS

Be casual, friendly, and professional. Use natural Australian English.""",
        'greeting': "G'day! You've reached us. How can I help you today?",
        'voice_id': 'EXAVITQu4vr4xnSDxMaL',  # Bella - English female voice
        'voice_name': 'Bella',
        'workflow_id': None
    }


# --- Transcription Manager ---
class TranscriptionManager:
    def __init__(self):
        self.messages = []
        self.start_time = datetime.now(SAUDI_TZ).isoformat()
        self.seen_messages = set()
        self.sip_info = {}
        self.recording_id = None
        self.greeting_added = False

    def add_message(self, role: str, text: str, source: str = ""):
        if not isinstance(text, str) or not text.strip():
            return

        msg_key = f"{role}:{text.strip()}"
        if msg_key in self.seen_messages:
            logger.debug(f"⏭️  Skipping duplicate message from {source}")
            return

        self.seen_messages.add(msg_key)
        msg = {
            "timestamp": datetime.now(SAUDI_TZ).isoformat(),
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
        lines = []
        for msg in self.messages:
            lines.append(f"{msg['role'].upper()}: {msg['text']}")
        return "\n".join(lines)

    def get_json(self) -> dict:
        return {
            "start_time": self.start_time,
            "end_time": datetime.now(SAUDI_TZ).isoformat(),
            "message_count": len(self.messages),
            "messages": self.messages,
            "sip_info": self.sip_info,
            "recording_id": self.recording_id
        }


# --- Hangup helper ---
async def hangup_call():
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
                    logger.info("🔌 Disconnected from room")
                except Exception as disconnect_error:
                    logger.error(f"❌ Disconnect also failed: {disconnect_error}")


# --- Prompt builder ---
def build_full_prompt(user_prompt: str) -> str:
    system_instructions = """
You are a friendly and professional CallTradie phone receptionist for Australian trades businesses.
Your job is to answer calls, understand customer problems, check availability, and book appointments.

# PERSONALITY & TONE
- Warm, friendly, natural Australian English
- Professional yet approachable (like a real receptionist)
- Use casual Australian expressions naturally: "G'day", "No worries", "She'll be right", "No dramas"
- Never sound robotic or scripted
- Show genuine interest in customer problems

# RESPONSE BEHAVIOR
- Keep responses SHORT: 1-2 sentences max, under 150 characters where possible
- Always respond in ENGLISH ONLY
- Speak naturally as if having a real conversation
- NO JSON, code, function names, or technical output
- Ask for customer name, phone, and address when needed
- Never repeat yourself
- Keep responses directly relevant to what customer said

# GUARDRAILS - NEVER EVER SAY:
- Function names: "end_call", "check_availability", "detected_answering_machine"
- Function params: {business_id: 1}, {days_ahead: 7}
- JSON structures: {"key": "value"}, {}, []
- Technical words: "API", "webhook", "function", "async", "payload"
- Meta-talk: "I'm an AI", "As a language model", "According to my instructions"

# AUSTRALIAN ENGLISH
- Use natural Australian accent and expressions
- Common phrases: "G'day mate", "No worries", "She'll be right", "How ya going?", "What can I do ya for?"
- Friendly and relaxed tone, never formal
- Understand Australian locations, postcodes, suburbs
- Be casual but still professional

# APPOINTMENT BOOKING
When customer needs to book:
1. Ask what day/time works for them
2. Use check_availability tool to get available slots
3. Offer 2-3 time options clearly
4. Confirm the booking
5. Let them know they'll get an SMS confirmation

# EMERGENCY HANDLING
If customer mentions emergency keywords (burst pipe, gas leak, flooding, power out, no hot water):
- Take it seriously and respond urgently
- Get their address immediately
- Offer fastest available time
- Don't waste time with small talk

# HANDLING VOICEMAIL
If you detect an answering machine:
- Wait for beep
- Leave a brief, polite voicemail message
- Use detected_answering_machine tool

# GREETING RULES
- Greeting is handled automatically at start
- Don't repeat the greeting
- Jump straight into helping the customer

# END-OF-CALL LOGIC
When customer indicates they're done (e.g., "thanks mate", "that's all", "cheers", "bye"):
→ Say quick friendly goodbye and trigger end_call immediately

# IDENTITY
- Never mention technical systems, AI, or OpenAI
- Just be "the receptionist" taking their call
- If asked who you are, say "This is the receptionist for [business name]"

# WHAT TO AVOID
- Long explanations
- Off-topic chat (stay focused on their job)
- Formal or robotic language
- Anything other than natural spoken English
- Making promises about pricing or timelines

# OUTPUT REQUIREMENTS (CRITICAL)
- English only
- 1-2 sentences max
- Under 150 characters when possible
- Spoken-style, casual, friendly
- Natural human conversation
- NO JSON, NO MARKUP, NO TECHNICAL RESPONSES

"""
    full_prompt = system_instructions + user_prompt
    return full_prompt


# --- Main Agent ---
class Assistant(Agent):
    def __init__(self, config: dict = None, agent_id: int = None, preloaded_tools: list = None, webhook_context: dict = None) -> None:
        if config is None:
            config = get_default_config()

        full_prompt = build_full_prompt(config['prompt'])

        # ✅ INJECT WEBHOOK CONTEXT INTO PROMPT (if available)
        if webhook_context:
            logger.info(f"📦 Injecting webhook context into prompt: {list(webhook_context.keys())}")
            webhook_prompt = "\n\n## Customer Information from Database:\n"
            for key, value in webhook_context.items():
                webhook_prompt += f"- {key}: {value}\n"
            webhook_prompt += "\nUse this information naturally in the conversation.\n"
            full_prompt = full_prompt + webhook_prompt

        if preloaded_tools is not None:
            dynamic_tools = preloaded_tools
        else:
            dynamic_tools = []
            if agent_id:
                try:
                    dynamic_tools = tool_service.create_function_tools(agent_id)
                    logger.info(f"📦 Loaded {len(dynamic_tools)} custom tools for agent {agent_id}")
                except Exception as e:
                    logger.error(f"❌ Error loading custom tools: {e}")

        super().__init__(
            instructions=full_prompt,
            tools=dynamic_tools,
        )
        self.config = config
        self.agent_id = agent_id
        self.webhook_context = webhook_context
        logger.info(f"✅ Assistant initialized: {config['name']} (Voice: {config['voice_name']})")
        logger.debug(f"📝 Full prompt length: {len(full_prompt)} characters")
        if dynamic_tools:
            logger.info(f"🔧 Tools enabled: {[t.__name__ if hasattr(t, '__name__') else str(t) for t in dynamic_tools]}")
        if webhook_context:
            logger.info(f"📦 Webhook data included in prompt: {list(webhook_context.keys())}")

    @function_tool
    async def end_call(self, ctx: RunContext):
        await ctx.session.generate_reply(
            instructions="Say a brief, friendly goodbye to the customer. Thank them for calling. Keep it short and natural."
        )
        await ctx.wait_for_playout()
        await hangup_call()
        return "Call ended with goodbye"

    @function_tool
    async def detected_answering_machine(self):
        await self.session.generate_reply(
            instructions="Leave a brief voicemail message. Say you're from the business, why you called, and that you'll try back later. Keep it under 20 seconds."
        )
        await asyncio.sleep(0.5)
        await hangup_call()

    @function_tool
    async def check_availability(self, ctx: RunContext, business_id: int, days_ahead: int = 7):
        """
        Check available time slots for a business (CallTradie feature)
        Returns available appointment slots to offer to customer
        """
        try:
            from services.calltradie_integration import calltradie as ct_integration

            logger.info(f"🔍 Checking availability for business {business_id}")

            # Call availability check service
            result = await ct_integration.check_availability(business_id, days_ahead)

            if result['success']:
                slots = result.get('slots', [])
                if slots:
                    # Format slots for natural speech
                    slot_descriptions = []
                    for i, slot in enumerate(slots[:3], 1):  # Offer up to 3 slots
                        slot_descriptions.append(
                            f"{i}. {slot.get('display', slot.get('datetime'))}"
                        )

                    availability_text = "\n".join(slot_descriptions)
                    logger.info(f"✅ Found {len(slots)} available slots")

                    # Let agent know about availability
                    await ctx.session.generate_reply(
                        instructions=f"Tell the customer about these available times:\n{availability_text}\nAsk them to pick one that works best."
                    )

                    return {
                        'status': 'success',
                        'slots': slots,
                        'count': len(slots),
                        'message': 'Available slots found'
                    }
                else:
                    logger.warning("⚠️ No available slots found")
                    await ctx.session.generate_reply(
                        instructions="Sorry, no times available in the next week. Ask the customer when they'd prefer to come in."
                    )
                    return {
                        'status': 'no_slots',
                        'message': 'No available slots, ask customer for preferred date'
                    }
            else:
                logger.warning(f"⚠️ Availability check failed: {result.get('message')}")
                await ctx.session.generate_reply(
                    instructions="Sorry, I can't check the calendar right now. Let them know we'll confirm the time via SMS."
                )
                return {
                    'status': 'error',
                    'message': result.get('message', 'Availability check failed'),
                    'fallback': True
                }

        except Exception as e:
            logger.error(f"❌ Error checking availability: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }


# --- Entrypoint ---
async def entrypoint(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}
    
    logger.info(f"🎯 Room: {ctx.room.name}")
    logger.info(f"📊 Initial participants: {ctx.room.num_participants}")

    # Connect to room
    await ctx.connect()
    call_start_time = time.time()

    # Wait for SIP participant
    logger.info("⏳ Waiting for participant...")
    participant = await ctx.wait_for_participant()
    logger.info(f"✅ Participant joined: {participant.identity} (Kind: {participant.kind})")

    # Extract TO number (number dialed by customer)
    to_number = None
    if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
        to_number = participant.attributes.get('sip.trunkPhoneNumber', '')
        logger.info(f"📞 TO Number (dialed): {to_number}")

    # Try to match agent by TO number
    agent_config = get_inbound_agent_by_number(to_number) if to_number else None

    # If no match, try room name
    if not agent_config:
        try:
            room_parts = ctx.room.name.split('-')
            if len(room_parts) >= 2 and room_parts[0] == 'call':
                agent_id = int(room_parts[1])
                fetched_config = get_agent_config(agent_id)
                if fetched_config:
                    agent_config = fetched_config
                    logger.info(f"✅ Loaded agent: {agent_config['name']}")
        except Exception as e:
            logger.error(f"❌ Error parsing agent ID: {e}")

    # Fall back to default
    if not agent_config:
        logger.warning("⚠️  No agent config found, using default")
        agent_config = get_default_config()

    # ===== PREPARE FOR PRE-CALL WEBHOOK FETCH =====
    agent_id = agent_config.get('id')
    webhook_fetch_task = None

    # Get FROM number for webhook
    from_number = participant.name if participant.name else 'unknown'
    if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
        from_number = participant.attributes.get('sip.phoneNumber', from_number)

    # Initialize transcription
    transcription = TranscriptionManager()

    # ===== OPTIMIZATION 1: Pre-load KB and tools =====
    
    kb_task = None
    if agent_id and agent_id in kb_service._index_cache:
        logger.info(f"📚 Loading KB context for agent {agent_id}...")
        kb_task = asyncio.create_task(kb_service.retrieve_context(
            agent_id,
            query="معلومات عامة عن الشركة والخدمات",
            top_k=10
        ))
    
    # Load tools (cached)
    dynamic_tools = []
    if agent_id:
        try:
            dynamic_tools = tool_service.create_function_tools(agent_id)
            logger.info(f"✅ Tools loaded: {len(dynamic_tools)} tools")
        except Exception as e:
            logger.warning(f"⚠️ Skipping tools: {e}")

    # Wait for KB
    if kb_task:
        try:
            kb_context = await kb_task
            if kb_context:
                agent_config['prompt'] = agent_config['prompt'] + "\n\n" + kb_context
                logger.info(f"✅ KB context injected ({len(kb_context)} chars)")
        except Exception as e:
            logger.error(f"❌ Error loading KB: {e}")

    # ===== OPTIMIZATION 2: Initialize models in parallel =====
    logger.info("🚀 Initializing models in parallel...")
    
    async def init_tts():
        return elevenlabs.TTS(
            voice_id=agent_config['voice_id'],
            model="eleven_turbo_v2_5",
            language="en",  # English
            auto_mode=True,
            voice_settings=elevenlabs.VoiceSettings(
                stability=0.75,
                similarity_boost=0.5,
                style=0.0,
                speed=0.91,
                use_speaker_boost=True
            ),
            streaming_latency=0,  # Maximum speed
            inactivity_timeout=60,
            enable_ssml_parsing=False,
            apply_text_normalization="auto"
        )
    
    async def init_stt():
        return google.STT(
            languages=["en-AU"],  # Australian English
            model="latest_long",
            spoken_punctuation=False,
            punctuate=True,
            interim_results=True,
            detect_language=False,
            sample_rate=16000,
            credentials_file="config/google/aimeetingassistant-448613-1ff1fc705734.json",
        )
    
    async def init_llm():
        return RealtimeModel(
            model="gpt-4o-realtime-preview",
            modalities=["text"],
            temperature=0.3,
            input_audio_transcription=InputAudioTranscription(
                model="whisper-1",
                language="en"
            ),
            turn_detection=TurnDetection(
                type="server_vad",
                threshold=0.45,
                prefix_padding_ms=150,
                silence_duration_ms=250,
                create_response=True,
                interrupt_response=True,
            ),
        )
    
    # Run parallel init
    tts_engine, stt_engine_google, llm_model_realtime = await asyncio.gather(
        init_tts(),
        init_stt(),
        init_llm()
    )
    
    logger.info("✅ All models initialized!")

    # Create session
    session = voice.AgentSession(
        llm=llm_model_realtime,
        tts=tts_engine,
        stt=stt_engine_google,
        user_away_timeout=float(os.environ.get('USER_AWAY_TIMEOUT', '60.0'))
    )

    # ===== [Event handlers - same as before, lines 472-751] =====
    usage_collector = metrics.UsageCollector()
    
    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    inactivity_task: asyncio.Task | None = None
    call_ended: bool = False

    async def user_presence_check():
        try:
            logger.warning("⏰ User marked as away, checking presence...")
            await session.generate_reply(
                instructions="The customer hasn't said anything for a while. Politely ask if they're still there."
            )
            await asyncio.sleep(10)
            logger.warning("⏰ User still inactive after presence check. Ending call...")
            await session.generate_reply(
                instructions="It sounds like they've gone. Say goodbye and end the call."
            )
            await asyncio.sleep(3)
            await hangup_call()
        except Exception as e:
            logger.error(f"Error in presence check: {e}")

    @session.on("user_state_changed")
    def _user_state_changed(ev: UserStateChangedEvent):
        nonlocal inactivity_task, call_ended
        logger.info(f"🔄 User state changed: {ev.new_state}")
        
        if call_ended:
            logger.debug(f"⏭️ Ignoring user state change (call already ended)")
            return

        if ev.new_state == "away":
            logger.warning(f"⚠️ User away after {os.environ.get('USER_AWAY_TIMEOUT', '60')}s inactivity")
            inactivity_task = asyncio.create_task(user_presence_check())
            return

        if inactivity_task is not None and not inactivity_task.done():
            logger.info("✅ User active again, cancelling presence check")
            inactivity_task.cancel()
            inactivity_task = None

    # Transcription handlers
    last_user_msg_committed = None
    last_agent_msg_committed = None

    @session.on("user_speech_committed")
    def on_user_speech_committed(msg: llm.ChatMessage):
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
        nonlocal last_agent_msg_committed
        try:
            text = msg.content if isinstance(msg.content, str) else str(msg.content)
            text = text.strip()
            if text and text != last_agent_msg_committed:
                if transcription.greeting_added and text == agent_config.get('greeting'):
                    logger.debug("⏭️  Skipping greeting (already added manually)")
                    return
                last_agent_msg_committed = text
                transcription.add_agent_message(text, "agent_speech_committed")
        except Exception as e:
            logger.error(f"❌ Error capturing agent speech: {e}")

    last_user_msg = None

    @session.on("user_transcript")
    def on_user_transcript(transcript):
        nonlocal last_user_msg
        try:
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

    async def monitor_conversation():
        last_msg_count = 0
        try:
            while True:
                await asyncio.sleep(0.5)
                try:
                    if hasattr(session, 'chat_ctx') and session.chat_ctx:
                        messages = session.chat_ctx.messages
                        if len(messages) > last_msg_count:
                            new_messages = messages[last_msg_count:]
                            for msg in new_messages:
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
                                    if role == 'user':
                                        transcription.add_user_message(text, "chat_context_monitor")
                                    elif role == 'assistant':
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

    conversation_monitor_task = asyncio.create_task(monitor_conversation())

    async def cleanup_monitor():
        if conversation_monitor_task and not conversation_monitor_task.done():
            conversation_monitor_task.cancel()
            try:
                await conversation_monitor_task
            except asyncio.CancelledError:
                pass

    ctx.add_shutdown_callback(cleanup_monitor)

    @session.on("user_message")
    def on_user_message(msg):
        try:
            if hasattr(msg, 'content'):
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                transcription.add_user_message(content, "user_message_event")
        except:
            pass

    @session.on("agent_message")
    def on_agent_message(msg):
        try:
            if hasattr(msg, 'content'):
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                if transcription.greeting_added and content == agent_config.get('greeting'):
                    return
                transcription.add_agent_message(content, "agent_message_event")
        except:
            pass

    @session.on("agent_transcript")
    def on_agent_transcript(transcript):
        try:
            text = str(transcript)
            if transcription.greeting_added and text == agent_config.get('greeting'):
                return
            transcription.add_agent_message(text, "agent_transcript_event")
        except:
            pass

    @session.on("conversation_item_added")
    def on_conversation_item_added(event):
        try:
            if hasattr(event, 'item'):
                item = event.item
                if hasattr(item, 'role') and hasattr(item, 'content'):
                    content = ' '.join(item.content) if isinstance(item.content, list) else str(item.content)
                    if item.role == 'assistant' and transcription.greeting_added and content == agent_config.get('greeting'):
                        return
                    transcription.add_message(item.role, content, "conversation_item")
        except Exception as e:
            logger.debug(f"Error in conversation_item_added: {e}")

    @session.on("chat_message")
    def on_chat_message(msg):
        try:
            if hasattr(msg, 'role') and hasattr(msg, 'content'):
                content = msg.content
                if msg.role == 'assistant' and transcription.greeting_added and content == agent_config.get('greeting'):
                    return
                transcription.add_message(msg.role, content, "chat_message_event")
        except:
            pass

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"📊 Usage: {summary}")

    async def send_call_data():
        call_duration = int(time.time() - call_start_time)
        logger.info(f"📝 Preparing transcription data...")
        logger.info(f"   Messages captured: {len(transcription.messages)}")
        logger.info(f"   Duration: {call_duration}s")

        if len(transcription.messages) <= 1:
            logger.warning("⚠️ Very few messages captured! Attempting final extraction...")
            try:
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
                            if role == 'assistant' and transcription.greeting_added and text == agent_config.get('greeting'):
                                continue
                            transcription.add_message(role, text, "final_extraction")
                            logger.info(f"   Extracted [{role}]: {text[:60]}")
            except Exception as e:
                logger.error(f"❌ Final extraction failed: {e}")

        logger.info(f"📋 Final transcription: {len(transcription.messages)} messages")
        for i, msg in enumerate(transcription.messages, 1):
            logger.info(f"   {i}. [{msg['role'].upper()}] ({msg['source']}): {msg['text'][:80]}")

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
                webhook_url = os.environ.get('FLASK_WEBHOOK_URL', 'http://localhost:5003/webhook/call-ended')
                async with http_session.post(webhook_url, json=payload, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status == 200:
                        response_text = await resp.text()
                        logger.info(f"✅ Webhook delivered successfully!")
                        logger.info(f"   Response: {response_text[:200]}")
                    else:
                        logger.error(f"❌ Webhook failed with status: {resp.status}")
        except Exception as e:
            logger.error(f"❌ Failed to send call data: {e}")

    ctx.add_shutdown_callback(log_usage)
    ctx.add_shutdown_callback(send_call_data)

    monitor_task = None

    async def monitor_session():
        try:
            while True:
                await asyncio.sleep(10)
                try:
                    if hasattr(session, 'llm'):
                        llm_obj = session.llm
                        if hasattr(llm_obj, 'sessions'):
                            for rt_session in llm_obj.sessions:
                                if hasattr(rt_session, 'conversation') and hasattr(rt_session.conversation, 'messages'):
                                    for msg in rt_session.conversation.messages:
                                        if hasattr(msg, 'role') and hasattr(msg, 'content'):
                                            if msg.role == 'assistant' and transcription.greeting_added and msg.content == agent_config.get('greeting'):
                                                continue
                                            transcription.add_message(msg.role, msg.content, "monitor_realtime")
                    if hasattr(session, 'chat_ctx') and hasattr(session.chat_ctx, 'messages'):
                        for msg in session.chat_ctx.messages:
                            if hasattr(msg, 'role') and hasattr(msg, 'content'):
                                if msg.role == 'assistant' and transcription.greeting_added and msg.content == agent_config.get('greeting'):
                                    continue
                                transcription.add_message(msg.role, msg.content, "monitor_chat_ctx")
                except Exception as e:
                    logger.debug(f"Monitor error: {e}")
        except asyncio.CancelledError:
            logger.debug("Monitor task cancelled (expected on call end)")

    # ===== FETCH WEBHOOK DATA (if configured) =====
    webhook_data = None
    if agent_id and agent_config.get('workflow_id'):
        logger.info("🚀 Fetching pre-call webhook data...")
        try:
            # Import async webhook service for scalable concurrent requests
            from services.webhook_service_async import AsyncWebhookService
            import sqlite3

            workflow_id = agent_config.get('workflow_id')

            # Get workflow config
            db_path = os.path.join(os.path.dirname(__file__), 'instance', 'voice_agent.db')
            if not os.path.exists(db_path):
                db_path = os.path.join(os.path.dirname(__file__), 'voice_agent.db')

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, webhook_url, api_key, pre_call_enabled, pre_call_timeout,
                       pre_call_webhook_url, is_active
                FROM workflow
                WHERE id = ?
            """, (workflow_id,))
            workflow_row = cursor.fetchone()
            conn.close()

            if workflow_row and workflow_row['pre_call_enabled'] and workflow_row['is_active']:
                webhook_url = workflow_row['pre_call_webhook_url'] or workflow_row['webhook_url']
                api_key = workflow_row['api_key']
                timeout = workflow_row['pre_call_timeout'] or 3

                pre_call_request = {
                    'event_type': 'pre_call',
                    'agent_name': agent_config['name'],
                    'agent_id': agent_id,
                    'phone_number': from_number,
                    'dialed_number': to_number,
                    'call_type': 'inbound'
                }

                logger.info("=" * 80)
                logger.info("📤 PRE-CALL WEBHOOK REQUEST:")
                logger.info(f"  URL: {webhook_url}")
                logger.info(f"  Timeout: {timeout}s")
                logger.info(f"  Request Data: {pre_call_request}")
                logger.info("=" * 80)

                # Fetch data (TRUE ASYNC - scalable to 100+ concurrent calls via aiohttp)
                webhook_data = await AsyncWebhookService.fetch_pre_call_data(
                    workflow_url=webhook_url,
                    api_key=api_key,
                    call_context=pre_call_request,
                    timeout=timeout
                )

                if webhook_data:
                    logger.info("=" * 80)
                    logger.info("📥 PRE-CALL WEBHOOK RESPONSE:")
                    logger.info(f"  Keys: {list(webhook_data.keys())}")
                    logger.info(f"  Full Data: {webhook_data}")
                    logger.info("=" * 80)
                else:
                    logger.warning("⚠️ Webhook returned empty")
        except Exception as e:
            logger.error(f"❌ Webhook fetch error: {e}")
            import traceback
            logger.error(traceback.format_exc())

    # ===== CREATE ASSISTANT WITH WEBHOOK DATA IN PROMPT =====
    logger.info(f"🚀 Creating assistant: {agent_config['name']}")
    assistant = Assistant(
        config=agent_config,
        agent_id=agent_id,
        preloaded_tools=dynamic_tools,
        webhook_context=webhook_data  # Pass webhook data to include in prompt
    )

    # ===== START SESSION =====
    logger.info(f"🚀 Starting session with agent: {agent_config['name']}")
    await session.start(
        room=ctx.room,
        agent=assistant,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVCTelephony(),
        ),
    )

    # Start monitors
    monitor_task = asyncio.create_task(monitor_session())
    
    # Store SIP info (participant already obtained earlier)
    transcription.set_sip_info(participant)

    # ===== OPTIMIZATION 3: Wait for SIP call to be ANSWERED =====
    if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
        call_status = participant.attributes.get('sip.callStatus', 'unknown')
        logger.info(f"📞 Initial SIP status: {call_status}")
        
        if call_status == 'dialing':
            logger.info("📞 Waiting for call to be answered...")
            
            max_wait = 30  # Wait up to 30 seconds
            start_wait = time.time()
            
            # Poll for status change
            while time.time() - start_wait < max_wait:
                await asyncio.sleep(0.5)
                
                # Get updated participant
                if participant.sid not in ctx.room.remote_participants:
                    logger.warning("⚠️ Participant disconnected before answering")
                    return
                
                updated_participant = ctx.room.remote_participants.get(participant.sid)
                if updated_participant:
                    current_status = updated_participant.attributes.get('sip.callStatus', 'unknown')
                    
                    if current_status == 'active':
                        elapsed = time.time() - start_wait
                        logger.info(f"✅ Call answered! ({elapsed:.1f}s)")
                        transcription.set_sip_info(updated_participant)
                        participant = updated_participant
                        break
            else:
                logger.warning(f"⚠️ Call status still '{call_status}' after {max_wait}s - continuing anyway")
        else:
            logger.info(f"✅ Call already in status: {call_status}")

    # ===== OPTIMIZATION 4: Quick audio track check =====
    if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
        logger.info("⏳ Quick audio track check...")
        try:
            timeout = 1.5
            start_wait = time.time()
            while time.time() - start_wait < timeout:
                audio_tracks = [
                    track for track in participant.track_publications.values()
                    if track.kind == rtc.TrackKind.KIND_AUDIO
                ]
                if audio_tracks:
                    elapsed = time.time() - start_wait
                    logger.info(f"✅ Audio track ready in {elapsed:.2f}s")
                    break
                await asyncio.sleep(0.1)
        except Exception as e:
            logger.debug(f"Audio track check: {e}")

    # ===== OPTIMIZATION 5: Start recording in background =====
    async def start_recording_background():
        try:
            logger.info("🎙️ Starting recording (background)...")
            recording_id = await recording_service.start_recording(ctx.room.name)
            if recording_id:
                transcription.recording_id = recording_id
                logger.info(f"✅ Recording started: {recording_id}")
            else:
                logger.warning("⚠️ Recording failed")
        except Exception as e:
            logger.error(f"❌ Recording error: {e}")
    
    # Start recording in background - DON'T WAIT!
    asyncio.create_task(start_recording_background())

    # Participant disconnect handler
    @ctx.room.on("participant_disconnected")
    def on_participant_disconnected(participant: rtc.RemoteParticipant):
        nonlocal inactivity_task, monitor_task, call_ended
        if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
            logger.info(f"📴 SIP participant disconnected: {participant.identity}")
            call_ended = True
            if inactivity_task and not inactivity_task.done():
                logger.info("✅ Cancelling inactivity timer (call ended)")
                inactivity_task.cancel()
            if monitor_task and not monitor_task.done():
                logger.debug("✅ Cancelling monitor task (call ended)")
                monitor_task.cancel()
            asyncio.create_task(hangup_call())

    # ===== OPTIMIZATION 6: IMMEDIATE GREETING (no sleeps!) =====
    logger.info("🎤 Sending greeting IMMEDIATELY...")
    greeting_message = agent_config.get('greeting', "G'day! How can we help?")

    # Add to transcription first
    transcription.add_message("assistant", greeting_message, "initial_greeting")
    transcription.greeting_added = True
    logger.info("✅ Greeting added to transcription")

    # Send greeting immediately!
    await session.say(greeting_message, allow_interruptions=True)
    logger.info("✅ Greeting sent!")

    # Webhook data already fetched during ring time - injected via Assistant init


# --- Worker Load Management ---
_last_logged_load = None
_last_log_time = 0

def compute_load(worker) -> float:
    global _last_logged_load, _last_log_time

    active_jobs = len(worker.active_jobs)
    max_concurrent = int(os.environ.get('MAX_CONCURRENT_CALLS', '15'))
    load = min(active_jobs / max_concurrent, 1.0)

    current_time = time.time()
    should_log = (
        active_jobs != _last_logged_load or
        (active_jobs > 0 and current_time - _last_log_time > 50)
    )

    if should_log:
        if active_jobs > 0:
            logger.info(f"📊 Worker load: {active_jobs}/{max_concurrent} active jobs ({load*100:.0f}% capacity)")
        _last_logged_load = active_jobs
        _last_log_time = current_time

    return load


if __name__ == "__main__":
    tool_service.preload_all_agents()
    opts = WorkerOptions(
        entrypoint_fnc=entrypoint,
        agent_name="agent-inbound",
        load_fnc=compute_load,
        load_threshold=0.9,
        drain_timeout=300,
    )

    logger.info("🚀 Starting LiveKit inbound agent worker...")
    logger.info(f"   Agent name: agent-inbound")
    logger.info(f"   Max concurrent calls: {os.environ.get('MAX_CONCURRENT_CALLS', '15')}")
    logger.info(f"   Load threshold: 90%")

    cli.run_app(opts)