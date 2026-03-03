import asyncio
import logging
import os
import sys
import time
import json
import aiohttp
import sqlite3
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from typing import AsyncIterable
import re

# Saudi Arabia Timezone (UTC+3)
SAUDI_TZ = timezone(timedelta(hours=3))

# LiveKit v1.x Imports (matching test structure)
from livekit import api, rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    cli,
    room_io,
    function_tool,
    get_job_context,
)
from livekit.plugins import google, elevenlabs, silero, noise_cancellation
from google.genai.types import Modality

# Import services
from services.knowledge_base_service import kb_service
from services.recording_service import audio_recorder
from services.tool_service import tool_service

# --- SETUP DETAILED LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("agent_gemini")

load_dotenv(".env")

# --- Config Cache ---
_agent_config_cache = {}
_cache_ttl = 300  # 5 minutes

# ==========================================
# TEXT FILTERING PATTERNS
# ==========================================
REMOVE_LIST = [
    "end_call", "query", "search", "add_sip_participant", "detected_answering_machine",
    "log_participants", "hangup", "execute", "call", "invoke", "trigger", "fetch", "get", "post",
    "function", "callback", "error", "exception", "null", "undefined", "API", "JSON", "HTTP", 
    "async", "await", "params", "payload", "response", "request", "status", "code", "object", 
    "array", "string", "boolean", "number"
]
REMOVE_PATTERN = re.compile(r'\b(' + '|'.join(map(re.escape, REMOVE_LIST)) + r')\b(?:\(\))?', re.IGNORECASE)
ARTIFACTS_PATTERN = re.compile(r'[\{\}\[\]"\'\(\)]')

ENG_TO_AR = {
    "ok": "تمام", "yes": "نعم", "no": "لا", "sorry": "آسف", "thank you": "شكراً", 
    "thanks": "شكراً", "please": "من فضلك", "welcome": "أهلاً", "bye": "مع السلامة",
    "hello": "مرحباً", "good": "جيد", "bad": "سيء", "problem": "مشكلة", 
    "no problem": "ما في مشكلة", "goodbye": "مع السلامة", "search": "بحث", 
    "database": "قاعدة البيانات", "voicemail": "البريد الصوتي", "detected": "تم اكتشاف", 
    "executing": "ينفذ", "processing": "يعالج", "loading": "يحمل", "failed": "فشل", 
    "success": "نجح"
}
TRANS_PATTERN = re.compile(r'\b(' + '|'.join(map(re.escape, ENG_TO_AR.keys())) + r')\b', re.IGNORECASE)

def replace_eng_with_ar(match):
    return ENG_TO_AR.get(match.group(0).lower(), match.group(0))


# --- Database Helper ---
def get_agent_config(agent_id: int, use_cache=True):
    """Fetch agent configuration from database with caching"""
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
        logger.error(f"❌ Error fetching agent config: {e}")
        return None


def get_default_config():
    """Return default agent configuration"""
    return {
        'id': 0,
        'name': 'Default Assistant',
        'prompt': """
# Role & Objective
You are a sales representative for Nevox AI, a Saudi-based company specializing in AI voice agent solutions.

# Personality & Tone
Professional yet warm - like a trusted business consultant.
Use Saudi dialect naturally and conversationally.
Keep responses brief and engaging - 1-2 sentences per turn.

# Instructions / Rules
- Speak ONLY in Arabic (Saudi dialect)
- Be concise and natural
- Use tools when needed
- Never speak JSON or technical jargon
- End call when user says goodbye

# Common Saudi Expressions
أبشر، تمام، ولا يهمك، يسعدني أخدمك، على راحتك، بإذن الله

# Services
Nevox AI provides 24/7 AI voice agents for:
- Restaurants (order taking)
- Clinics (appointments)
- Real estate (inquiries)
- E-commerce (customer service)
        """,
        'greeting': 'السلام عليكم ورحمة الله وبركاته؟',
        'voice_id': 'KjDucWgG5NYuMBznv52L',
        'voice_name': 'Hiba-Demo'
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
        """Add a message with deduplication and JSON filtering"""
        if not isinstance(text, str) or not text.strip():
            return

        # Block JSON/technical jargon
        if '{' in text or '}' in text:
            logger.warning(f"🚫 TRANSCRIPTION_BLOCKED: '{text[:60]}'")
            if role in ["assistant", "agent"]:
                text = "عذراً، ممكن تعيد مرة ثانية؟"
            else:
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
            self.sip_info = {'participant_kind': 'NON_SIP', 'call_status': 'active'}

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


# --- Hangup Helper ---
async def hangup_call():
    """Delete room with retry logic"""
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


# --- Prompt Builder ---
def build_full_prompt(user_prompt: str) -> str:
    """Combine user's custom prompt with system instructions"""
    system_instructions = """
You are a polite and helpful Saudi Arabic voice assistant.

# VOICE RESPONSE RULES
- Respond in natural spoken Arabic
- Use tools when needed (calling tools is OK and expected)
- Only speak your verbal responses - tool calls are silent/internal
- Never read JSON output to the user

# POST-GREETING BEHAVIOR (CRITICAL!)
The greeting "السلام عليكم ورحمة الله وبركاته" is ALREADY PLAYED by the system.

When user responds with any variation:
- "وعليكم السلام"
- "عليكم السلام"  
- "السلام عليكم"
- "هلا"

YOU MUST:
1. DO NOT repeat "وعليكم السلام" again
2. Immediately proceed to introduce yourself
3. Ask how you can help
4. NEVER generate {error} or technical messages

# RESPONSE BEHAVIOR
- Replies must be short, clear, and spoken naturally (1-2 sentences, max 150 characters)
- Always respond in Arabic only
- DO NOT output JSON, code, or technical formatting
- Never repeat previous responses

# GUARDRAILS - NEVER speak these out loud:
- Function names like "end_call", "query"
- Function parameters like {query: ...}, {error: ...}
- JSON structures like {"key": "value"}
- Technical formatting or markup

# CULTURAL RULES
- Respect Saudi culture, values, and etiquette
- Use common Saudi expressions: هلا، أبشر، تمام، ولا يهمك

# END-OF-CALL LOGIC
If user wants to end (وداعاً، مع السلامة، باي):
→ Immediately trigger end_call (no extra goodbye)

# OUTPUT REQUIREMENTS
- Arabic only
- 1-2 sentences max
- Under 150 characters
- Spoken-style, clean, natural
- No JSON, no markup, no technical responses

"""
    return system_instructions + user_prompt


def build_prompt_with_raw_webhook_data(user_prompt: str, raw_data: dict) -> str:
    """Inject webhook data into prompt for pre-call context"""
    base_prompt = build_full_prompt(user_prompt)

    if raw_data:
        webhook_text = json.dumps(raw_data, ensure_ascii=False, indent=2)
        webhook_section = f"""

# 📊 بيانات العميل من النظام (Customer Data from CRM)

```json
{webhook_text}
```

"""
        return base_prompt + webhook_section
    else:
        return base_prompt


# --- Main Assistant Class (Gemini-based) ---
class GeminiAssistant(Agent):
    def __init__(self, config: dict, job_ctx: JobContext, preloaded_tools: list = None, webhook_context: dict = None):
        self.job_ctx = job_ctx
        self.config = config
        self.webhook_context = webhook_context
        
        # Build prompt with optional webhook data
        if webhook_context:
            full_prompt = build_prompt_with_raw_webhook_data(config['prompt'], webhook_context)
            logger.info(f"✅ Prompt built WITH webhook data: {list(webhook_context.keys())}")
        else:
            full_prompt = build_full_prompt(config['prompt'])
            logger.info(f"ℹ️ Prompt built WITHOUT webhook data")

        # Combine built-in tools with dynamic tools
        all_tools = []
        
        # Add dynamic tools if provided
        if preloaded_tools:
            all_tools.extend(preloaded_tools)
            logger.info(f"📦 Loaded {len(preloaded_tools)} custom tools")

        super().__init__(
            instructions=full_prompt,
            llm=google.realtime.RealtimeModel(
                model="models/gemini-2.0-flash-exp",
                modalities=[Modality.TEXT],
                temperature=0.4,
            ),
            tts=elevenlabs.TTS(
                voice_id=config['voice_id'],
                model="eleven_flash_v2_5",
                language="ar",
                auto_mode=True,
                voice_settings=elevenlabs.VoiceSettings(
                    stability=0.75,
                    similarity_boost=0.5,
                    style=0.0,
                    speed=0.91,
                    use_speaker_boost=True
                ),
                streaming_latency=0,
                inactivity_timeout=60,
                enable_ssml_parsing=False,
                apply_text_normalization="auto"
            ),
            vad=silero.VAD.load(
                min_silence_duration=0.1,
                min_speech_duration=0.03,
                activation_threshold=0.35,
            )
        )

        logger.info(f"✅ Gemini Assistant initialized: {config['name']} (Voice: {config['voice_name']})")

    @function_tool
    async def end_call(self):
        """Call this when the user wants to end the call"""
        logger.info("🛠️ TOOL: end_call")
        asyncio.create_task(self._delayed_hangup())

        return "It was a pleasure helping you. Goodbye!"

    async def _delayed_hangup(self):
        await asyncio.sleep(3)
        logger.info("🔌 Hanging up...")
        
        # Stop recording first
        if self.job_ctx.room.name:
            await audio_recorder.stop_recording(self.job_ctx.room.name)
        
        # Then hang up
        await hangup_call()


# --- Server & Session ---
server = AgentServer()

@server.rtc_session()
async def entrypoint(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}
    
    logger.info(f"🎯 Room: {ctx.room.name}")
    logger.info(f"📊 Initial participants: {ctx.room.num_participants}")

    await ctx.connect()
    call_start_time = time.time()

    # === EXTRACT AGENT CONFIG AND WEBHOOK CONTEXT ===
    agent_config = None
    webhook_context = None

    # CAMPAIGN CALLS
    if ctx.room.name.startswith('campaign_'):
        logger.info("📞 Campaign call detected, waiting for participant metadata...")
        participant = await ctx.wait_for_participant()
        logger.info(f"✅ Participant joined: {participant.identity}")

        try:
            if participant.metadata:
                logger.info(f"🔍 Participant metadata: {participant.metadata[:200]}...")
                metadata = json.loads(participant.metadata)
                if metadata.get('type') == 'campaign':
                    agent_config = {
                        'id': metadata.get('agent_id'),
                        'name': metadata.get('agent_name'),
                        'prompt': metadata.get('agent_prompt'),
                        'greeting': metadata.get('agent_greeting'),
                        'voice_id': metadata.get('agent_voice_id'),
                        'voice_name': metadata.get('agent_voice_name')
                    }
                    webhook_context = metadata.get('webhook_context')
                    logger.info(f"✅ Using campaign agent: {agent_config['name']}")
        except Exception as e:
            logger.error(f"❌ Error parsing campaign metadata: {e}")

    # NON-CAMPAIGN CALLS
    if not agent_config:
        agent_config = get_default_config()
        try:
            participant = await ctx.wait_for_participant()
            logger.info(f"✅ Participant joined: {participant.identity}")

            if participant.metadata:
                try:
                    metadata = json.loads(participant.metadata)
                    if metadata.get('type') == 'outbound_api':
                        agent_id = metadata.get('agent_id')
                        webhook_context = metadata.get('webhook_context')

                        if agent_id:
                            fetched_config = get_agent_config(agent_id)
                            if fetched_config:
                                agent_config = fetched_config
                                logger.info(f"✅ Loaded agent: {agent_config['name']}")
                except Exception as e:
                    logger.error(f"❌ Error parsing outbound API metadata: {e}")

            # Fallback: Extract from room name
            if not agent_config or agent_config == get_default_config():
                room_parts = ctx.room.name.split('-')
                if len(room_parts) >= 2 and room_parts[0] == 'call':
                    agent_id = int(room_parts[1])
                    fetched_config = get_agent_config(agent_id)
                    if fetched_config:
                        agent_config = fetched_config
                        logger.info(f"✅ Loaded agent from room name: {agent_config['name']}")
        except Exception as e:
            logger.error(f"❌ Error parsing agent ID: {e}")

    # Initialize transcription
    transcription = TranscriptionManager()
    transcription.webhook_context = webhook_context

    # === PRE-LOAD KB CONTEXT AND TOOLS ===
    agent_id = agent_config.get('id')
    
    kb_task = None
    if agent_id and agent_id in kb_service._index_cache:
        logger.info(f"📚 Loading KB context for agent {agent_id}...")
        kb_task = asyncio.create_task(kb_service.retrieve_context(
            agent_id,
            query="معلومات عامة عن الشركة والخدمات",
            top_k=10
        ))
    
    # Load tools
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

    # === CREATE ASSISTANT AND SESSION ===
    agent = GeminiAssistant(
        config=agent_config,
        job_ctx=ctx,
        preloaded_tools=dynamic_tools,
        webhook_context=webhook_context
    )

    session = AgentSession()

    # === EVENT HANDLERS ===
    @session.on("agent_message")
    def on_agent_msg(msg):
        try:
            text = msg.content if isinstance(msg.content, str) else str(msg.content)
            text = text.strip()
            if text:
                if transcription.greeting_added and text == agent_config.get('greeting'):
                    return
                transcription.add_agent_message(text, "agent_message")
        except Exception as e:
            logger.debug(f"Error in agent_message: {e}")

    @session.on("user_message")
    def on_user_msg(msg):
        try:
            text = msg.content if isinstance(msg.content, str) else str(msg.content)
            text = text.strip()
            if text:
                transcription.add_user_message(text, "user_message")
        except Exception as e:
            logger.debug(f"Error in user_message: {e}")

    # === CLEANUP CALLBACKS ===
    async def send_call_data():
        call_duration = int(time.time() - call_start_time)
        logger.info(f"📝 Preparing transcription data...")
        logger.info(f"   Messages captured: {len(transcription.messages)}")
        logger.info(f"   Duration: {call_duration}s")

        # Wait for recording upload
        recording_url = None
        for attempt in range(50):
            recording_url = audio_recorder.get_recording_url(ctx.room.name)
            if recording_url:
                logger.info(f"✅ Recording URL available after {attempt * 0.5}s")
                break
            await asyncio.sleep(0.5)

        try:
            payload = {
                'room_name': ctx.room.name,
                'duration': call_duration,
                'transcription': transcription.get_plain_text(),
                'metadata': transcription.get_json(),
                'message_count': len(transcription.messages),
                'recording_url': recording_url
            }
            
            logger.info(f"🚀 Sending webhook: {len(transcription.messages)} messages, {call_duration}s duration")
            async with aiohttp.ClientSession() as http_session:
                webhook_url = os.environ.get('FLASK_WEBHOOK_URL', 'http://localhost:5003/webhook/call-ended')
                async with http_session.post(webhook_url, json=payload, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status == 200:
                        response_text = await resp.text()
                        logger.info(f"✅ Webhook delivered successfully!")
                    else:
                        logger.error(f"❌ Webhook failed with status: {resp.status}")
        except Exception as e:
            logger.error(f"❌ Failed to send call data: {e}")

    ctx.add_shutdown_callback(send_call_data)

    # === START SESSION ===
    logger.info(f"🚀 Starting Gemini session with agent: {agent_config['name']}")
    await session.start(
        agent=agent,
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_output=True,
            text_output=True
        ),
    )

    # === START RECORDING (BACKGROUND) ===
    async def start_recording_background():
        try:
            logger.info("🎙️ Starting recording (background)...")
            recording_id = await audio_recorder.start_recording(ctx.room)
            if recording_id:
                transcription.recording_id = recording_id
                logger.info(f"✅ Recording started: {recording_id}")
        except Exception as e:
            logger.error(f"❌ Recording error: {e}")
    
    asyncio.create_task(start_recording_background())

    # === PARTICIPANT DISCONNECT HANDLER ===
    @ctx.room.on("participant_disconnected")
    def on_participant_disconnected(participant: rtc.RemoteParticipant):
        if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
            logger.info(f"📴 SIP participant disconnected: {participant.identity}")

            async def handle_disconnect():
                await audio_recorder.stop_recording(ctx.room.name)
                await send_call_data()
                await asyncio.sleep(0.5)
                await hangup_call()

            asyncio.create_task(handle_disconnect())

    # === WAIT FOR PARTICIPANT & SET SIP INFO ===
    if not ctx.room.name.startswith('campaign_'):
        participant = await ctx.wait_for_participant()
    
    transcription.set_sip_info(participant)
    logger.info(f"✅ Participant ready: {participant.identity}")

    # === SEND GREETING IMMEDIATELY ===
    logger.info("🎤 Sending greeting IMMEDIATELY...")
    greeting_message = agent_config.get('greeting', 'السلام عليكم ورحمة الله وبركاته')
    
    transcription.add_agent_message(greeting_message, "initial_greeting")
    transcription.greeting_added = True
    logger.info("✅ Greeting added to transcription")

    logger.info("🎤 Sending greeting IMMEDIATELY...")
    greeting_message = agent_config.get('greeting', 'السلام عليكم ورحمة الله وبركاته')
    
    # Add to transcription first
    transcription.add_agent_message(greeting_message, "initial_greeting")
    transcription.greeting_added = True
    logger.info("✅ Greeting added to transcription")


    
    # Send greeting immediately - no sleeps!
    await session.say(greeting_message, allow_interruptions=True)
    logger.info("✅ Greeting sent!")

    # Trigger greeting via session
    session.generate_reply(instructions=f"Say: {greeting_message}")
    logger.info("✅ Greeting sent!")


if __name__ == "__main__":
    # Preload tools for all agents
    tool_service.preload_all_agents()
    
    logger.info("🚀 Starting LiveKit agent worker with Gemini 2.0 Flash...")
    logger.info(f"   Model: gemini-2.0-flash-exp")
    logger.info(f"   TTS: ElevenLabs Flash v2.5")
    logger.info(f"   VAD: Silero")
    
    cli.run_app(server)