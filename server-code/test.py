import asyncio
import logging
import os
import time
import json
import aiohttp
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

from typing import AsyncIterable
import re
import time
from datetime import datetime

# SQLAlchemy ORM database access (replaces sqlite3)
from database import get_readonly_session, check_connection
from models import Agent as AgentModel, InboundConfiguration

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
    ModelSettings,
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





# ==========================================
# 1. GLOBAL COMPILED PATTERNS (Define these once at top of file)
# ==========================================

# Pattern 1: Function Names & Tech Jargon to Remove
REMOVE_LIST = [
    "end_call", "query", "search", "add_sip_participant", "detected_answering_machine",
    "log_participants", "hangup", "execute", "call", "invoke", "trigger", "fetch", "get", "post",
    "function", "callback", "error", "exception", "null", "undefined", "API", "JSON", "HTTP", 
    "async", "await", "params", "payload", "response", "request", "status", "code", "object", 
    "array", "string", "boolean", "number"
]
# Creates a regex like: \b(end_call|query|function|...)\b
REMOVE_PATTERN = re.compile(r'\b(' + '|'.join(map(re.escape, REMOVE_LIST)) + r')\b(?:\(\))?', re.IGNORECASE)

# Pattern 2: Artifacts (brackets, quotes)
ARTIFACTS_PATTERN = re.compile(r'[\{\}\[\]"\'\(\)]')

# Pattern 3: English to Arabic Map
ENG_TO_AR = {
    "ok": "تمام", "yes": "نعم", "no": "لا", "sorry": "آسف", "thank you": "شكراً", 
    "thanks": "شكراً", "please": "من فضلك", "welcome": "أهلاً", "bye": "مع السلامة",
    "hello": "مرحباً", "good": "جيد", "bad": "سيء", "problem": "مشكلة", 
    "no problem": "ما في مشكلة", "goodbye": "مع السلامة", "search": "بحث", 
    "database": "قاعدة البيانات", "voicemail": "البريد الصوتي", "detected": "تم اكتشاف", 
    "executing": "ينفذ", "processing": "يعالج", "loading": "يحمل", "failed": "فشل", 
    "success": "نجح"
}
# Regex to find these specific English words
TRANS_PATTERN = re.compile(r'\b(' + '|'.join(map(re.escape, ENG_TO_AR.keys())) + r')\b', re.IGNORECASE)

def replace_eng_with_ar(match):
    """Helper to swap English match with Arabic value"""
    return ENG_TO_AR.get(match.group(0).lower(), match.group(0))




# --- Database Helper (SQLAlchemy ORM) ---
def get_agent_config(agent_id: int, use_cache=True) -> dict | None:
    """
    Fetch agent configuration from database with caching.
    Uses SQLAlchemy ORM for database-agnostic queries.
    """
    # Check cache first
    if use_cache and agent_id in _agent_config_cache:
        cached_data = _agent_config_cache[agent_id]
        if time.time() - cached_data['timestamp'] < _cache_ttl:
            logger.debug(f"📦 Using cached config for agent {agent_id}")
            return cached_data['config']

    try:
        # Use SQLAlchemy ORM instead of raw sqlite3
        with get_readonly_session() as session:
            agent = session.query(AgentModel).filter_by(id=agent_id).first()

            if agent:
                # Convert to dict INSIDE session (critical to avoid DetachedInstanceError!)
                config = {
                    'id': agent.id,
                    'name': agent.name,
                    'prompt': agent.prompt,
                    'greeting': agent.greeting if agent.greeting else 'السلام عليكم ورحمة الله وبركاته، أهلاً وسهلاً فيك. أنا مساعدك الذكي، كيف أقدر أساعدك اليوم؟',
                    'voice_id': agent.voice_id,
                    'voice_name': agent.voice_name,
                    'temperature': agent.temperature if agent.temperature else 0.4,
                    'vad_mode': agent.vad_mode if agent.vad_mode else 'dynamic'
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

    except Exception as e:
        logger.error(f"❌ Database error fetching agent config: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


def get_inbound_agent_by_number(to_number) -> dict | None:
    """
    Fetch inbound configuration and linked agent by phone number.
    Uses SQLAlchemy ORM for database-agnostic queries.
    """
    try:
        # Clean the phone number
        clean_to_number = to_number.replace('+', '').replace('-', '').replace(' ', '') if to_number else ''

        with get_readonly_session() as session:
            # Query InboundConfiguration with relationship to Agent
            configs = session.query(InboundConfiguration).join(AgentModel).order_by(
                InboundConfiguration.created_at.desc()
            ).all()

            # Convert to list of dicts INSIDE session (critical!)
            rows = []
            for ic in configs:
                rows.append({
                    'config_id': ic.id,
                    'config_name': ic.name,
                    'phone_number': ic.phone_number,
                    'agent_id': ic.agent.id,
                    'agent_name': ic.agent.name,
                    'prompt': ic.agent.prompt,
                    'greeting': ic.agent.greeting,
                    'voice_id': ic.agent.voice_id,
                    'voice_name': ic.agent.voice_name,
                    'temperature': ic.agent.temperature,
                    'vad_mode': ic.agent.vad_mode
                })

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
                        'greeting': row['greeting'] if row['greeting'] else 'السلام عليكم ورحمة الله وبركاته، أهلاً وسهلاً فيك. أنا مساعدك الذكي، كيف أقدر أساعدك اليوم؟',
                        'voice_id': row['voice_id'],
                        'voice_name': row['voice_name'],
                        'temperature': row['temperature'] if row['temperature'] else 0.4,
                        'vad_mode': row['vad_mode'] if row['vad_mode'] else 'dynamic'
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
                'greeting': row['greeting'] if row['greeting'] else 'السلام عليكم ورحمة الله وبركاته، أهلاً وسهلاً فيك. أنا مساعدك الذكي، كيف أقدر أساعدك اليوم؟',
                'voice_id': row['voice_id'],
                'voice_name': row['voice_name'],
                'temperature': row['temperature'] if row['temperature'] else 0.4,
                'vad_mode': row['vad_mode'] if row['vad_mode'] else 'dynamic'
            }
            logger.warning(f"⚠️  No config matched TO number {to_number}, using latest: {config['config_name']}")
            return config
        else:
            logger.warning(f"⚠️  No inbound configurations found")
            return None

    except Exception as e:
        logger.error(f"❌ Error fetching inbound configuration: {e}")
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
        'voice_name': 'Ali',
        'temperature': 0.4,
        'vad_mode': 'dynamic'
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

    # Get current Saudi Arabia time (UTC+3) - separate date and time for clarity
    now = datetime.now(SAUDI_TZ)
    current_date = now.strftime("%A, %B %d, %Y")  # e.g., "Thursday, February 06, 2026"
    current_time = now.strftime("%I:%M %p")        # e.g., "01:55 AM"
    logger.info(f"📅 Injecting date: {current_date}, time: {current_time}")

    system_instructions = f"""
You are a polite and helpful Saudi voice assistant.

# DIALECT & STYLE
- Use a natural, polite Saudi dialect suitable for all age groups.
- Avoid heavy slang unless the user requests it.
- Keep a balance between Saudi dialect and simple Modern Standard Arabic, especially in official/government topics.

Current Date: {current_date}
Current Time: {current_time}

# RESPONSE BEHAVIOR
- Replies must be short, clear, and spoken naturally (1-2 sentences, max 150 characters).
- Always respond in User Language (Arabic/English)
- If user speaks ENGLISH → respond ONLY in English (never switch to Arabic)
- If user speaks ARABIC → respond ONLY in Arabic (never switch to English)
- Do NOT output JSON, code, or technical formatting.
- Ask for the user's name politely when appropriate.
- Never repeat previous responses.
- Keep every response directly relevant to the user's question.

# GUARDRAILS
## NEVER EVER speak these things out loud:
- Function names like "end_call", "detected_answering_machine"
- Function parameters like {{query: ...}}, {{name: ...}}
- JSON structures like {{"key": "value"}}
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
- don't respond in that way; {{"name": "detected_answering_machine"}}

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
- Any formatting besides normal Arabic/English speech.
- Incorrect or speculative information about Saudi regulations or entities.

# OUTPUT REQUIREMENTS (CRITICAL)
- If customer speaks **Arabic**, respond in **Arabic**
- If customer speaks **English**, respond in **English**
- 1-2 sentences max.
- Under 150 characters.
- Spoken-style, clean, natural, human-like.
- No JSON, no markup, no technical responses.

"""

    full_prompt = system_instructions + user_prompt
    return full_prompt




# --- Main Agent ---
class Assistant(Agent):
    def __init__(self, config: dict = None, agent_id: int = None, preloaded_tools: list = None) -> None:
        if config is None:
            config = get_default_config()

        full_prompt = build_full_prompt(config['prompt'])

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
        logger.info(f"✅ Assistant initialized: {config['name']} (Voice: {config['voice_name']})")
        logger.debug(f"📝 Full prompt length: {len(full_prompt)} characters")
        if dynamic_tools:
            logger.info(f"🔧 Tools enabled: {[t.__name__ if hasattr(t, '__name__') else str(t) for t in dynamic_tools]}")
    
    async def tts_node(self, text: AsyncIterable[str], model_settings: ModelSettings):
        """
        🚀 TTS FILTER - Blocks JSON only
        """
        
        async def process_arabic_text():
            has_spoken_content = False
            blocked_json = False

            async for chunk in text:
                if not chunk.strip(): 
                    continue

                # ===== BLOCK JSON ONLY =====
                if '{' in chunk or '}' in chunk:
                    logger.warning(f"🚫 TTS_BLOCKED JSON: '{chunk[:60]}...'")
                    blocked_json = True
                    continue
                # ===========================

                if chunk.strip():
                    has_spoken_content = True
                    yield chunk

            # ===== FALLBACK =====
            if blocked_json and not has_spoken_content:
                yield "عذراً، ممكن تعيد مرة ثانية؟"
            elif not has_spoken_content:
                yield "عذراً، ممكن تعيد مرة ثانية؟"

        return Agent.default.tts_node(self, process_arabic_text(), model_settings)

    @function_tool
    async def end_call(self, ctx: RunContext):
        await ctx.session.generate_reply(
            instructions="قل وداعاً للمستخدم بطريقة طبيعية ولطيفة، واشكره على اتصاله"
        )
        await ctx.wait_for_playout()
        await hangup_call()
        return "Call ended with goodbye"

    @function_tool
    async def detected_answering_machine(self):
        await self.session.generate_reply(
            instructions="اترك رسالة صوتية تخبر المستخدم بأنك ستعاود الاتصال لاحقاً."
        )
        await asyncio.sleep(0.5)
        await hangup_call()


# --- Entrypoint ---
async def entrypoint(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}
    
    logger.info(f"🎯 Room: {ctx.room.name}")
    logger.info(f"📊 Initial participants: {ctx.room.num_participants}")

    # Connect to room
    await ctx.connect()
    call_start_time = time.time()

    # Wait for SIP participant to get phone number
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

    # Initialize transcription
    transcription = TranscriptionManager()

    # ===== OPTIMIZATION 1: Pre-load KB and tools =====
    agent_id = agent_config.get('id')
    
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
            language="ar",
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
            languages=["ar-SA"],
            model="latest_long",
            spoken_punctuation=False,
            punctuate=True,
            interim_results=True,
            detect_language=False,
            sample_rate=16000,
            credentials_file="config/google/aimeetingassistant-448613-1ff1fc705734.json",
        )
    
    async def init_llm():
        llm_temperature = agent_config.get('temperature', 0.4)
        vad_mode = agent_config.get('vad_mode', 'dynamic')
        logger.info(f"🌡️ LLM Temperature: {llm_temperature}, VAD Mode: {vad_mode}")

        model_kwargs = {
            #gpt-4o-realtime-preview
            'model': "gpt-realtime-2025-08-28",
            'modalities': ["text"],
            'temperature': llm_temperature,
            'input_audio_transcription': InputAudioTranscription(
                model="gpt-4o-transcribe",
                language="ar",
                #prompt="Two speakers in Arabic, one customer, one agent."
            ),
        }

        # Configure VAD based on mode
        if vad_mode == 'natural':
            model_kwargs['turn_detection'] = TurnDetection(
                type="semantic_vad",
                eagerness="auto",
                create_response=True,
                interrupt_response=True,
            )
        elif vad_mode != 'precise':  # 'dynamic' (default)
            model_kwargs['turn_detection'] = TurnDetection(
                type="server_vad",
                threshold=0.45,
                prefix_padding_ms=150,
                silence_duration_ms=250,
                create_response=True,
                interrupt_response=True,
            )
        # 'precise' mode = no turn_detection (omitted from kwargs)

        return RealtimeModel(**model_kwargs)
    
    # Run parallel init
    tts_engine, llm_model_realtime = await asyncio.gather(
        init_tts(),
        #init_stt(),
        init_llm()
    )
    
    logger.info("✅ All models initialized!")

    # Create session
    session = voice.AgentSession(
        llm=llm_model_realtime,
        tts=tts_engine,
        preemptive_generation=True,
        #stt=stt_engine_google,
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
                instructions="المستخدم غير نشط. اسأله بلطف إذا كان لا يزال موجودًا"
            )
            await asyncio.sleep(10)
            logger.warning("⏰ User still inactive after presence check. Ending call...")
            await session.generate_reply(
                instructions="قل للمستخدم: يبدو أنك لم تعد هناك. سأنهي المكالمة الآن. مع السلامة"
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

    # ===== START SESSION =====
    logger.info(f"🚀 Starting session with agent: {agent_config['name']}")
    await session.start(
        room=ctx.room,
        agent=Assistant(config=agent_config, agent_id=agent_id, preloaded_tools=dynamic_tools),
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
    greeting_message = agent_config.get('greeting', 'السلام عليكم ورحمة الله وبركاته')
    
    # Add to transcription first
    transcription.add_message("assistant", greeting_message, "initial_greeting")
    transcription.greeting_added = True
    logger.info("✅ Greeting added to transcription")
    
    # Send greeting immediately!
    await session.say(greeting_message, allow_interruptions=True)
    logger.info("✅ Greeting sent!")


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