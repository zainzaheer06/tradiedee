import asyncio
import logging
import os
import time
import json
import aiohttp

from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv


from types import SimpleNamespace
from typing import AsyncIterable
import re

# Redis caching service (40x speedup!)
from services.redis_service import redis_service

# SQLAlchemy ORM database access (replaces sqlite3)
from database import get_readonly_session, check_connection
from models import Agent as AgentModel  # Renamed to avoid conflict with livekit.agents.Agent

from datetime import datetime




# Saudi Arabia Timezone (UTC+3)
SAUDI_TZ = timezone(timedelta(hours=3))
from livekit import api, rtc
from livekit.agents import voice
from livekit.agents import (
    Agent,
    AgentSession,
    AudioConfig,
    BackgroundAudioPlayer,
    JobContext,
    ModelSettings,
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

logger = logging.getLogger("agent-tradie")
load_dotenv(".env")



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



# --- Database Helper with Redis Caching (40x speedup!) ---
# Now using SQLAlchemy ORM instead of raw sqlite3
def get_agent_config(agent_id: int, use_cache=True) -> dict | None:
    """
    Fetch agent configuration with Redis caching.
    Uses SQLAlchemy ORM for database-agnostic queries.

    PERFORMANCE IMPROVEMENT:
    - Redis cache: ~0.5ms (40x faster than DB!)
    - Database queries reduced by 95%

    Args:
        agent_id: Agent ID to fetch
        use_cache: Whether to use Redis cache (default: True)

    Returns:
        dict: Agent configuration or None if not found
    """
    # STEP 1: Try Redis cache first (FAST! ~0.5ms)
    if use_cache:
        cached_config = redis_service.get_agent_config(agent_id)
        if cached_config:
            logger.debug(f"Redis cache HIT: agent {agent_id}")
            return cached_config

    # STEP 2: Cache miss - load from database using SQLAlchemy ORM
    logger.debug(f"Redis cache MISS: agent {agent_id} - loading from DB")

    try:
        # Use get_readonly_session for SELECT queries (more efficient)
        with get_readonly_session() as session:
            agent = session.query(AgentModel).filter_by(id=agent_id).first()

            if agent:
                # Convert to dict INSIDE session (critical to avoid DetachedInstanceError!)
                config = {
                    'id': agent.id,
                    'name': agent.name,
                    'prompt': agent.prompt,
                    'greeting': agent.greeting or "G'day! You've reached us. How can I help you today?",
                    'voice_id': agent.voice_id,
                    'voice_name': agent.voice_name,
                    'voice_speed': agent.voice_speed if agent.voice_speed is not None else 0.95,
                    'temperature': agent.temperature if agent.temperature else 0.7,
                    'vad_mode': agent.vad_mode if agent.vad_mode else 'dynamic',
                    'transfer_targets': agent.transfer_targets or None,
                }

                # STEP 3: Cache it in Redis for next time (TTL: 1 hour)
                redis_service.cache_agent_config(agent_id, config, ttl=3600)

                logger.info(f"Loaded agent config from database: {config['name']}")
                logger.info(f"  🎤 Voice: {config['voice_name']} (ID: {config['voice_id']})")
                logger.info(f"  🔊 Voice Speed: {config['voice_speed']}x")
                return config  # Return dict, not model object!
            else:
                logger.warning(f"Agent {agent_id} not found in database")
                return None

    except Exception as e:
        logger.error(f"Database error fetching agent config: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


def get_default_config():
    """Return default agent configuration - CallTradie Receptionist"""
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
        'voice_speed': 0.95,  # Default TTS voice speed
        'temperature': 0.7,  # Default LLM temperature (more casual for trades)
        'vad_mode': 'dynamic',
        'transfer_targets': None
    }

# --- Transcription Manager ---
class TranscriptionManager:
    def __init__(self):
        self.messages = []
        self.start_time = datetime.now(SAUDI_TZ).isoformat()
        self.seen_messages = set()  # Track unique messages to avoid duplicates
        self.sip_info = {}  # Store SIP participant information
        self.recording_id = None  # Store LiveKit recording/egress ID
        self.greeting_added = False  # FIXED: Track if greeting was already added

    def add_message(self, role: str, text: str, source: str = ""):
        """Add a message with deduplication"""
        if not isinstance(text, str) or not text.strip():
            return

        # Block JSON/technical markup in transcriptions
        if '{' in text or '}' in text:
            logger.warning(f"🚫 TRANSCRIPTION_BLOCKED: '{text[:60]}'")
            if role in ["assistant", "agent"]:
                text = "Sorry, can you say that again?"
            else:
                return      

        # Create unique key for deduplication
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
            "end_time": datetime.now(SAUDI_TZ).isoformat(),
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
    # Get current date/time - separate date and time for clarity
    now = datetime.now(SAUDI_TZ)
    current_date = now.strftime("%A, %B %d, %Y")  # e.g., "Thursday, February 06, 2026"
    current_time = now.strftime("%I:%M %p")        # e.g., "01:55 AM"
    logger.info(f"📅 Injecting date: {current_date}, time: {current_time}")

    # System instructions - Add your custom rules here
    system_instructions = f"""
You are a friendly Australian trades receptionist for phone calls.

# CRITICAL RULE - NO JSON EVER
- You are a VOICE assistant for phone calls
- Speak naturally in casual Australian English
- NEVER generate JSON, code, or technical syntax
- NEVER use: {{}}, [], "key": "value", error:, status:, etc.
- If you don't understand → say naturally: "Sorry, can you say that again?"
- If there's a problem → say naturally: "There's a small issue, can you hang tight for a moment?"

Current Date: {current_date}
Current Time: {current_time}

# COMMUNICATION STYLE
- Speak naturally in casual, friendly Australian English
- Be professional but approachable - like a real receptionist
- Listen actively to understand customer needs
- Keep responses short and conversational (1-2 sentences max, under 150 characters)

# POST-GREETING BEHAVIOR (CRITICAL!)
The greeting is ALREADY PLAYED by the system.
YOU MUST:
1. DO NOT repeat the greeting
2. Immediately listen to what the customer needs
3. Ask clarifying questions to understand their issue
4. NEVER generate {{error}} or technical messages
5. Continue naturally as a helpful receptionist

# CUSTOMER INTERACTION STYLE
- Ask for their name and contact details when booking appointments
- Be empathetic if they have an emergency
- Check availability and suggest appointment times
- Confirm their address and phone number
- Offer to send SMS confirmation

# RESPONSE BEHAVIOR
- Keep every response directly relevant to the customer's question
- Do NOT output JSON, code, or technical formatting
- Be conversational and natural, like a real person
- Never repeat previous responses
- Use common Australian expressions: "G'day", "No worries", "Mate", "How can I help?"

# GUARDRAILS
## NEVER EVER speak these things out loud:
- Function names like "end_call", "book_appointment"
- Function parameters like {{name: ...}}, {{error: ...}}
- JSON structures like {{"key": "value"}}
- Technical formatting or markup
- Code or system messages

# VOICEMAIL DETECTION
Voicemail is when you hear automated English messages like:
- "The number you have dialed is not available"
- "Please leave a message after the beep"
- "The person you are calling is unavailable"

If you detect voicemail:
1. Leave a brief message
2. Wait 2 seconds
3. Call end_call()

# IDENTITY RULES
- Never mention technical systems or models
- You're a friendly receptionist for the trades business
- If customers ask, say you're the business receptionist
- No JSON, no markup, no technical responses

# EMERGENCY HANDLING
- If customer mentions emergency: immediately acknowledge
- Offer to dispatch someone urgently
- Get their address and phone number quickly
- Be reassuring and professional

# OUTPUT REQUIREMENTS (CRITICAL)
- English only, casual Australian style
- 1-2 sentences max
- Under 150 characters
- Spoken-style, clean, natural, human-like
- No JSON, no markup, no technical responses


"""

    # Combine: system instructions + user's custom prompt
    full_prompt = system_instructions + user_prompt

    return full_prompt


def build_prompt_with_webhook_context(user_prompt: str, webhook_context: dict) -> str:
    """
    Inject webhook data into prompt for pre-call context

    Args:
        user_prompt: The prompt from database (agent.prompt)
        webhook_context: Dict with customer/call data (e.g., customer_name, order_id)

    Returns:
        Complete prompt with system instructions + user prompt + webhook data
    """
    # Get base prompt with system instructions
    base_prompt = build_full_prompt(user_prompt)

    # Add webhook data section if available
    if webhook_context:
        webhook_text = json.dumps(webhook_context, ensure_ascii=False, indent=2)

        webhook_section = f"""

# 📊 Customer Data from System
```json
{webhook_text}
```

Use this context to personalize the conversation. Address the customer by name if provided. Reference their appointment history or service details naturally in conversation. Be helpful and professional based on their background.
"""

        full_prompt = base_prompt + webhook_section
        logger.info(f"✅ Prompt built WITH webhook context: {list(webhook_context.keys())}")
        return full_prompt
    else:
        # No webhook data, use default prompt
        logger.info(f"ℹ️ Prompt built WITHOUT webhook context")
        return base_prompt


# --- Main Agent ---
class Assistant(Agent):
    def __init__(self, config: dict = None, agent_id: int = None, preloaded_tools: list = None, chat_ctx=None, is_transferred: bool = False, background_audio=None, webhook_context: dict = None) -> None:
        if config is None:
            config = get_default_config()

        # Build full prompt with optional webhook context
        if webhook_context:
            full_prompt = build_prompt_with_webhook_context(config['prompt'], webhook_context)
            logger.info(f"✅ Assistant initialized WITH webhook context")
        else:
            full_prompt = build_full_prompt(config['prompt'])
            logger.info(f"ℹ️ Assistant initialized WITHOUT webhook context")

        # Use pre-loaded tools if provided, otherwise load them
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

        # transfer_to_agent is registered automatically via @function_tool decorator
        # No need to append manually — doing so causes duplicate function name error
        if config.get('transfer_targets'):
            logger.info(f"🔄 Handoffs enabled: targets={config['transfer_targets']}")

        super().__init__(
            instructions=full_prompt,
            tools=list(dynamic_tools),
            chat_ctx=chat_ctx,
        )

        self.config = config
        self.is_transferred = is_transferred
        self.background_audio = background_audio
        self._session = None
        self.webhook_context = webhook_context
        logger.info(f"✅ Assistant initialized: {config['name']} (Voice: {config['voice_name']})")
        logger.debug(f"📝 Full prompt length: {len(full_prompt)} characters")
    
    async def on_enter(self):
        """Called when agent enters session - save reference and handle transfer setup"""
        self._session = self.session
        logger.info("✅ Session reference saved")

        if self.is_transferred:
            # Swap TTS voice to match this agent's config
            try:
                new_tts = build_tts_engine(self.config)
                # AgentSession.tts is read-only property; update via private attribute
                if hasattr(self.session, '_tts'):
                    self.session._tts = new_tts
                    logger.info(f"🔊 TTS voice updated (_tts) to: {self.config.get('voice_name')} ({self.config.get('voice_id')})")
                elif hasattr(self.session, 'update_options'):
                    await self.session.update_options(tts=new_tts)
                    logger.info(f"🔊 TTS voice updated (update_options) to: {self.config.get('voice_name')}")
                else:
                    logger.warning("⚠️ Cannot update TTS: no known method found")
            except Exception as e:
                logger.error(f"❌ Failed to update TTS voice: {e}")

            # Play transfer chime / pause before new agent greets
            chime_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sounds', 'transfer.mp3')
            if self.background_audio and os.path.exists(chime_path):
                try:
                    logger.info(f"🎵 Playing transfer chime (max 3s): {chime_path}")
                    handle = self.background_audio.play(chime_path)
                    await asyncio.sleep(3.0)
                    handle.stop()
                    logger.info("🎵 Transfer chime done — new agent greeting starting")
                except Exception as e:
                    logger.error(f"❌ Failed to play chime: {e}")
                    logger.info("⏸️ Fallback pause (1.2s)...")
                    await asyncio.sleep(1.2)
                    logger.info("▶️ Resuming — new agent greeting starting")
            else:
                if not os.path.exists(chime_path):
                    logger.warning(f"⚠️ Chime file not found: {chime_path} — using silent pause")
                logger.info("⏸️ Handoff pause (1.2s)...")
                await asyncio.sleep(1.2)
                logger.info("▶️ Resuming — new agent greeting starting")

            # Say this agent's greeting
            greeting = self.config.get('greeting', '')
            agent_name = self.config.get('name', '?')
            if greeting:
                try:
                    logger.info(f"🎤 [{agent_name}] saying its own greeting: {greeting[:60]}")
                    await self.session.say(greeting)
                except Exception as e:
                    logger.error(f"❌ Transfer greeting error: {e}")
    
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

    async def llm_node(self, chat_ctx, tools, model_settings=None):
        """
        🚀 LLM FILTER - Removes JSON, adds fallback with logging
        """
        logger.info("🔄 llm_node started")
        
        async def process_stream():
            inside_json = False
            has_content = False
            chunk_count = 0
            blocked_count = 0
            blocked_content = []

            try:
                async with self.llm.chat(chat_ctx=chat_ctx, tools=tools, tool_choice=None) as stream:
                    async for chunk in stream:
                        chunk_count += 1
                        
                        if chunk is None:
                            logger.debug(f"📦 Chunk {chunk_count}: None")
                            continue

                        content = getattr(chunk.delta, 'content', None) if hasattr(chunk, 'delta') else str(chunk)
                        
                        if content is None:
                            logger.debug(f"📦 Chunk {chunk_count}: No content, passing through")
                            yield chunk
                            continue

                        logger.debug(f"📦 Chunk {chunk_count}: '{content[:50]}'")

                        # ===== JSON STATE TRACKING =====
                        if '{' in content:
                            inside_json = True
                            blocked_count += 1
                            blocked_content.append(content)
                            logger.warning(f"🚫 LLM_BLOCKED (JSON start): '{content[:40]}'")
                            continue
                        
                        if inside_json:
                            blocked_count += 1
                            blocked_content.append(content)
                            if '}' in content:
                                inside_json = False
                                logger.warning(f"🚫 LLM_BLOCKED (JSON end): '{content[:40]}'")
                            else:
                                logger.warning(f"🚫 LLM_BLOCKED (inside JSON): '{content[:40]}'")
                            continue
                        # ================================
                        
                        has_content = True
                        logger.info(f"✅ LLM_PASSED: '{content[:50]}'")
                        yield chunk

                # ===== SUMMARY =====
                logger.info(f"📊 LLM Stream Summary: {chunk_count} chunks, {blocked_count} blocked")
                
                if blocked_content:
                    full_blocked = ''.join(blocked_content)
                    logger.warning(f"🚫 Total blocked content: '{full_blocked[:100]}'")

                # ===== FALLBACK IF NOTHING YIELDED =====
                if not has_content:
                    fallback = "عفواً؟"
                    logger.warning(f"⚠️ No content after filtering!")
                    logger.info(f"✅ Yielding fallback: {fallback}")
                    # Yield chunk-like object so downstream (TTS/pipeline) gets .delta.content
                    fallback_chunk = SimpleNamespace(delta=SimpleNamespace(content=fallback))
                    # Add to chat history
                    try:
                        from livekit.agents import llm
                        chat_ctx.messages.append(
                            llm.ChatMessage(role="assistant", content=fallback)
                        )
                        logger.info("✅ Fallback added to chat history")
                    except Exception as e:
                        logger.error(f"❌ Error adding to chat: {e}")
                    yield fallback_chunk
                else:
                    logger.info("✅ Content passed through successfully")

            except Exception as e:
                logger.error(f"❌ llm_node stream error: {e}")
                import traceback
                logger.error(traceback.format_exc())
                raise

        return process_stream()

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
    async def transfer_to_agent(self, ctx: RunContext, agent_id: int):
        """Transfer the call to a different agent.
        Only call this when your prompt's transfer rules say to.
        CRITICAL: Only use the exact agent_id values written in your transfer rules. Never guess or invent an agent_id."""
        allowed = self.config.get('transfer_targets') or []
        if agent_id not in allowed:
            logger.warning(f"⚠️ Transfer blocked: agent_id={agent_id} not in allowed targets {allowed}")
            return "Transfer not allowed to that agent"

        target_config = get_agent_config(agent_id)
        if not target_config:
            logger.error(f"❌ Transfer failed: agent_id={agent_id} config not found")
            return "Agent not found"

        logger.info(f"🔄 Transferring call to agent: {target_config['name']} (id={agent_id})")

        # Brief handoff announcement, then the new agent will greet
        await ctx.session.generate_reply(
            instructions="أخبر المستخدم بجملة واحدة فقط أنك ستحوله الآن إلى وكيل آخر."
        )
        await ctx.wait_for_playout()

        # Strip old system prompt - keep only conversation history
        # self.chat_ctx may be _ReadOnlyChatContext (Realtime model) - iterate directly
        try:
            raw_messages = list(self.chat_ctx)
        except Exception:
            raw_messages = []
        clean_messages = [m for m in raw_messages if m.role != "system"]
        clean_ctx = llm.ChatContext(messages=clean_messages) if clean_messages else None

        # Load tools for target agent
        target_tools = []
        try:
            target_tools = tool_service.create_function_tools(agent_id)
        except Exception as e:
            logger.warning(f"⚠️ Could not load tools for target agent {agent_id}: {e}")

        return Assistant(
            config=target_config,
            agent_id=agent_id,
            preloaded_tools=target_tools,
            chat_ctx=clean_ctx,
            is_transferred=True,
            background_audio=self.background_audio,
        )

    #@function_tool
    #async def detected_answering_machine(self):
    #    """Call this tool if you have detected a voicemail system, AFTER hearing the voicemail greeting"""
    #    await self.session.generate_reply(
    #        instructions="اترك رسالة صوتية تخبر المستخدم بأنك ستعاود الاتصال لاحقاً."
    #    )
    #    await asyncio.sleep(0.5) # Add a natural gap to the end of the voicemail message
    #    await hangup_call()

def build_tts_engine(config):
    """Build a TTS engine from agent config. Module-level so it can be called from anywhere."""
    voice_speed = config.get('voice_speed', 0.90)
    logger.info(f"🎙️ Building TTS engine: Voice={config.get('voice_name', '?')}, Speed={voice_speed}x")
    return elevenlabs.TTS(
        voice_id=config['voice_id'],
        model="eleven_turbo_v2_5",
        language="ar",
        auto_mode=True,
        voice_settings=elevenlabs.VoiceSettings(
            stability=0.75,
            similarity_boost=0.5,
            style=0.0,
            speed=voice_speed,
            use_speaker_boost=True
        ),
        streaming_latency=0,
        inactivity_timeout=60,
        enable_ssml_parsing=False,
        apply_text_normalization="auto"
    )


async def entrypoint(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}
    # Shared state for handlers (call start time updated after connect in both paths)
    state = {
        "start": time.time(),
        "inactivity_task": None,
        "call_ended": False,
        "call_data_sent": False,
        "monitor_task": None,
        "conversation_monitor_task": None,
    }

    logger.info(f"🎯 Room: {ctx.room.name}")
    logger.info(f"📊 Initial participants: {ctx.room.num_participants}")

    # ===== WEBHOOK CONTEXT: Initialize for outbound API calls =====
    webhook_context = None

    # ===== OPTIMIZATION: Load agent config BEFORE connecting =====
    # For call/api rooms, we can extract agent_id from room name immediately
    agent_config = None
    preloaded_agent_id = None

    if not ctx.room.name.startswith('campaign_'):
        # Pre-load config for call/api rooms (don't wait for connect)
        try:
            room_parts = ctx.room.name.split('-')
            if len(room_parts) >= 2 and room_parts[0] in ['call', 'api']:
                preloaded_agent_id = int(room_parts[1])
                logger.info(f"📦 Pre-loading agent {preloaded_agent_id} config BEFORE connect...")
                fetched_config = get_agent_config(preloaded_agent_id)
                if fetched_config:
                    agent_config = fetched_config
                    logger.info(f"✅ Pre-loaded agent: {agent_config['name']}")
        except Exception as e:
            logger.error(f"❌ Error pre-loading agent config: {e}")

    # Use default if pre-load failed
    if not agent_config and not ctx.room.name.startswith('campaign_'):
        agent_config = get_default_config()

    # ===== OPTIMIZATION: Define model initializers BEFORE connect =====
    # These will be run in parallel with ctx.connect() for non-campaign rooms

    def create_tts_engine(config):
        """Alias to module-level build_tts_engine"""
        return build_tts_engine(config)

    def create_llm_model(config):
        """Create LLM model with given config"""
        llm_temperature = config.get('temperature', 0.4)
        vad_mode = config.get('vad_mode', 'dynamic')
        logger.info(f"🎛️ LLM Temp: {llm_temperature}, VAD Mode: {vad_mode}")

        model_kwargs = {
            'model': "gpt-realtime",
            'modalities': ["text"],
            'temperature': llm_temperature,
            'input_audio_transcription': InputAudioTranscription(
                model="gpt-4o-transcribe",
                language="ar",
                prompt=(
                    "Transcribe speech only. "
                    "If the speaker uses Arabic, output Arabic script. "
                    "If the speaker uses English, output English text. "
                    "Do NOT translate between languages. "
                    "Do NOT add explanations or annotations."
                ),
            ),
        }

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

        return RealtimeModel(**model_kwargs)

    def _register_session_handlers(sess, transcription, agent_config, ctx, state):
        """Register all session/room event handlers. Call before session.start() so no events are missed."""
        usage_collector = metrics.UsageCollector()

        @sess.on("metrics_collected")
        def _on_metrics_collected(ev: MetricsCollectedEvent):
            metrics.log_metrics(ev.metrics)
            usage_collector.collect(ev.metrics)

        async def user_presence_check():
            try:
                logger.warning("⏰ User marked as away, checking presence...")
                await sess.generate_reply(
                    instructions="المستخدم غير نشط. اسأله بلطف إذا كان لا يزال موجودًا"
                )
                await asyncio.sleep(10)
                logger.warning("⏰ User still inactive after presence check. Ending call...")
                await sess.generate_reply(
                    instructions="قل للمستخدم: يبدو أنك لم تعد هناك. سأنهي المكالمة الآن. مع السلامة"
                )
                await asyncio.sleep(3)
                await hangup_call()
            except Exception as e:
                logger.error(f"Error in presence check: {e}")

        @sess.on("user_state_changed")
        def _user_state_changed(ev: UserStateChangedEvent):
            logger.info(f"🔄 User state changed: {ev.new_state}")
            if state["call_ended"]:
                logger.debug("⏭️ Ignoring user state change (call already ended)")
                return
            if ev.new_state == "away":
                logger.warning(f"⚠️ User away after {os.environ.get('USER_AWAY_TIMEOUT', '60')}s inactivity")
                state["inactivity_task"] = asyncio.create_task(user_presence_check())
                return
            if state["inactivity_task"] is not None and not state["inactivity_task"].done():
                logger.info("✅ User active again, cancelling presence check")
                state["inactivity_task"].cancel()
                state["inactivity_task"] = None

        last_user_msg_committed = None
        last_agent_msg_committed = None

        @sess.on("user_speech_committed")
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

        @sess.on("agent_speech_committed")
        def on_agent_speech_committed(msg: llm.ChatMessage):
            nonlocal last_agent_msg_committed
            try:
                text = msg.content if isinstance(msg.content, str) else str(msg.content)
                text = text.strip()
                if text and text != last_agent_msg_committed:
                    if transcription.greeting_added and text == agent_config.get("greeting"):
                        logger.debug("⏭️  Skipping greeting (already added manually)")
                        return
                    last_agent_msg_committed = text
                    transcription.add_agent_message(text, "agent_speech_committed")
            except Exception as e:
                logger.error(f"❌ Error capturing agent speech: {e}")

        last_user_msg = None

        @sess.on("user_transcript")
        def on_user_transcript(transcript):
            nonlocal last_user_msg
            try:
                if hasattr(transcript, "text"):
                    text = transcript.text.strip()
                elif hasattr(transcript, "transcript"):
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
                        if hasattr(sess, "chat_ctx") and sess.chat_ctx:
                            messages = sess.chat_ctx.messages
                            if len(messages) > last_msg_count:
                                for msg in messages[last_msg_count:]:
                                    role = msg.role
                                    content = msg.content
                                    if isinstance(content, str):
                                        text = content.strip()
                                    elif isinstance(content, list):
                                        text = " ".join(
                                            str(part.text) if hasattr(part, "text") else str(part)
                                            for part in content
                                        ).strip()
                                    else:
                                        text = str(content).strip()
                                    if text:
                                        if role == "user":
                                            transcription.add_user_message(text, "chat_context_monitor")
                                        elif role == "assistant":
                                            if transcription.greeting_added and text == agent_config.get("greeting"):
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

        state["conversation_monitor_task"] = asyncio.create_task(monitor_conversation())

        async def cleanup_monitor():
            t = state.get("conversation_monitor_task")
            if t and not t.done():
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass

        ctx.add_shutdown_callback(cleanup_monitor)

        @sess.on("user_message")
        def on_user_message(msg):
            try:
                if hasattr(msg, "content"):
                    content = msg.content if isinstance(msg.content, str) else str(msg.content)
                    transcription.add_user_message(content, "user_message_event")
            except Exception as e:
                logger.debug(f"Error in user_message handler: {e}")

        @sess.on("agent_message")
        def on_agent_message(msg):
            try:
                if hasattr(msg, "content"):
                    content = msg.content if isinstance(msg.content, str) else str(msg.content)
                    if transcription.greeting_added and content == agent_config.get("greeting"):
                        return
                    transcription.add_agent_message(content, "agent_message_event")
            except Exception as e:
                logger.debug(f"Error in agent_message handler: {e}")

        @sess.on("agent_transcript")
        def on_agent_transcript(transcript):
            try:
                text = str(transcript)
                if transcription.greeting_added and text == agent_config.get("greeting"):
                    return
                transcription.add_agent_message(text, "agent_transcript_event")
            except Exception as e:
                logger.debug(f"Error in agent_transcript handler: {e}")

        @sess.on("conversation_item_added")
        def on_conversation_item_added(event):
            try:
                if hasattr(event, "item"):
                    item = event.item
                    if hasattr(item, "role") and hasattr(item, "content"):
                        content = " ".join(item.content) if isinstance(item.content, list) else str(item.content)
                        if item.role == "assistant" and transcription.greeting_added and content == agent_config.get("greeting"):
                            return
                        transcription.add_message(item.role, content, "conversation_item")
            except Exception as e:
                logger.debug(f"Error in conversation_item_added: {e}")

        @sess.on("chat_message")
        def on_chat_message(msg):
            try:
                if hasattr(msg, "role") and hasattr(msg, "content"):
                    content = msg.content
                    if msg.role == "assistant" and transcription.greeting_added and content == agent_config.get("greeting"):
                        return
                    transcription.add_message(msg.role, content, "chat_message_event")
            except Exception as e:
                logger.debug(f"Error in chat_message handler: {e}")

        async def log_usage():
            logger.info(f"📊 Usage: {usage_collector.get_summary()}")

        async def send_call_data():
            if state["call_data_sent"]:
                logger.debug("⏭️ Webhook already sent, skipping")
                return
            state["call_data_sent"] = True
            call_duration = int(time.time() - state["start"])
            logger.info("📝 Preparing transcription data...")
            logger.info(f"   Messages captured: {len(transcription.messages)}")
            logger.info(f"   Duration: {call_duration}s")
            if len(transcription.messages) <= 1:
                logger.warning("⚠️ Very few messages captured! Attempting final extraction...")
                try:
                    if hasattr(sess, "chat_ctx") and sess.chat_ctx:
                        messages = sess.chat_ctx.messages
                        logger.info(f"   Found {len(messages)} messages in chat_ctx")
                        for msg in messages:
                            role = msg.role
                            content = msg.content
                            if isinstance(content, str):
                                text = content.strip()
                            elif isinstance(content, list):
                                text = " ".join(
                                    str(part.text) if hasattr(part, "text") else str(part) for part in content
                                ).strip()
                            else:
                                text = str(content).strip()
                            if text:
                                if role == "assistant" and transcription.greeting_added and text == agent_config.get("greeting"):
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
                    "room_name": ctx.room.name,
                    "duration": call_duration,
                    "transcription": transcription.get_plain_text(),
                    "metadata": transcription.get_json(),
                    "message_count": len(transcription.messages),
                }
                logger.info(f"🚀 Sending webhook: {len(transcription.messages)} messages, {call_duration}s duration")
                async with aiohttp.ClientSession() as http_session:
                    webhook_url = os.environ.get("FLASK_WEBHOOK_URL", "http://localhost:5016/webhook/call-ended")
                    # Properly encode JSON to avoid encoding issues with timezone-aware strings
                    json_data = json.dumps(payload, ensure_ascii=False, default=str)
                    async with http_session.post(webhook_url, data=json_data, headers={"Content-Type": "application/json"}, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                        if resp.status == 200:
                            response_text = await resp.text()
                            logger.info("✅ Webhook delivered successfully!")
                            logger.info(f"   Response: {response_text[:200]}")
                        else:
                            logger.error(f"❌ Webhook failed with status: {resp.status}")
            except Exception as e:
                logger.error(f"❌ Failed to send call data: {e}")

        ctx.add_shutdown_callback(log_usage)
        ctx.add_shutdown_callback(send_call_data)

        async def monitor_session():
            try:
                while True:
                    await asyncio.sleep(10)
                    try:
                        if hasattr(sess, "llm"):
                            llm_obj = sess.llm
                            if hasattr(llm_obj, "sessions"):
                                for rt_session in llm_obj.sessions:
                                    if hasattr(rt_session, "conversation") and hasattr(rt_session.conversation, "messages"):
                                        for msg in rt_session.conversation.messages:
                                            if hasattr(msg, "role") and hasattr(msg, "content"):
                                                if msg.role == "assistant" and transcription.greeting_added and msg.content == agent_config.get("greeting"):
                                                    continue
                                                transcription.add_message(msg.role, msg.content, "monitor_realtime")
                        if hasattr(sess, "chat_ctx") and hasattr(sess.chat_ctx, "messages"):
                            for msg in sess.chat_ctx.messages:
                                if hasattr(msg, "role") and hasattr(msg, "content"):
                                    if msg.role == "assistant" and transcription.greeting_added and msg.content == agent_config.get("greeting"):
                                        continue
                                    transcription.add_message(msg.role, msg.content, "monitor_chat_ctx")
                    except Exception as e:
                        logger.debug(f"Monitor error: {e}")
            except asyncio.CancelledError:
                logger.debug("Monitor task cancelled (expected on call end)")

        state["monitor_task"] = asyncio.create_task(monitor_session())

        @ctx.room.on("participant_disconnected")
        def on_participant_disconnected(participant: rtc.RemoteParticipant):
            if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
                logger.info(f"📴 SIP participant disconnected: {participant.identity}")
                state["call_ended"] = True
                if state["inactivity_task"] and not state["inactivity_task"].done():
                    logger.info("✅ Cancelling inactivity timer (call ended)")
                    state["inactivity_task"].cancel()
                if state["monitor_task"] and not state["monitor_task"].done():
                    logger.debug("✅ Cancelling monitor task (call ended)")
                    state["monitor_task"].cancel()

                async def handle_disconnect():
                    await send_call_data()
                    await asyncio.sleep(0.5)
                    await hangup_call()

                asyncio.create_task(handle_disconnect())

    # ===== FOR NON-CAMPAIGN CALLS: Do ALL setup BEFORE connect =====
    # This ensures greeting plays immediately when user picks up

    tts_engine = None
    llm_model_realtime = None
    transcription = None
    dynamic_tools = []
    session = None
    agent_id = None

    if not ctx.room.name.startswith('campaign_') and agent_config:
        logger.info("🚀 Setting up EVERYTHING before connect...")

        # 1. Initialize models
        logger.info("   🔊 Initializing TTS...")
        tts_engine = create_tts_engine(agent_config)

        logger.info("   🧠 Initializing LLM...")
        llm_model_realtime = create_llm_model(agent_config)

        # 2. Initialize transcription
        transcription = TranscriptionManager()

        # 3. Load tools
        agent_id = agent_config.get('id')
        if agent_id:
            try:
                dynamic_tools = tool_service.create_function_tools(agent_id)
                logger.info(f"   ✅ Tools loaded: {len(dynamic_tools)} tools")
            except Exception as e:
                logger.warning(f"   ⚠️ Skipping tools: {e}")

        # 4. Load KB context (if available)
        if agent_id and agent_id in kb_service._index_cache:
            try:
                kb_context = await kb_service.retrieve_context(
                    agent_id,
                    query="معلومات عامة عن الشركة والخدمات",
                    top_k=10
                )
                if kb_context:
                    agent_config = {**agent_config, "prompt": agent_config["prompt"] + "\n\n" + kb_context}
                    logger.info(f"   ✅ KB context injected ({len(kb_context)} chars)")
            except Exception as e:
                logger.error(f"   ❌ Error loading KB: {e}")

        # 5. Create session
        session = voice.AgentSession(
            llm=llm_model_realtime,
            tts=tts_engine,
            preemptive_generation=True,
            user_away_timeout=float(os.environ.get('USER_AWAY_TIMEOUT', '60.0'))
        )

        logger.info("✅ ALL setup complete! Registering handlers (before connect)...")
        _register_session_handlers(session, transcription, agent_config, ctx, state)

        # 6. Connect (agent joins room; user's phone rings)
        logger.info("🔗 Connecting to room...")
        await ctx.connect()
        logger.info("✅ Agent connected. Waiting for participant (user) to join...")

        # 7. Wait for participant (user) to join BEFORE starting session or greeting
        participant = await ctx.wait_for_participant()
        state["start"] = time.time()  # Call duration starts when user joins
        transcription.set_sip_info(participant)
        logger.info(f"✅ Participant joined: {participant.identity} (Kind: {participant.kind})")

        # ===== EXTRACT WEBHOOK CONTEXT from participant metadata =====
        if participant.metadata:
            try:
                logger.info(f"🔍 Checking participant metadata for webhook_context...")
                metadata = json.loads(participant.metadata)

                if metadata.get('type') == 'outbound_api':
                    webhook_context = metadata.get('webhook_context')
                    if webhook_context:
                        logger.info(f"✅ Webhook context found: {list(webhook_context.keys())}")
                    else:
                        logger.info(f"ℹ️ No webhook context in metadata")
            except Exception as e:
                logger.debug(f"Could not parse participant metadata: {e}")

        # 8. Now start session and greeting (only after user is in the room)
        background_audio = BackgroundAudioPlayer()
        await session.start(
            room=ctx.room,
            agent=Assistant(config=agent_config, agent_id=agent_id, preloaded_tools=dynamic_tools,
                            background_audio=background_audio, webhook_context=webhook_context),
            room_input_options=RoomInputOptions(
                noise_cancellation=noise_cancellation.BVCTelephony(),
            ),
        )
        await background_audio.start(room=ctx.room, agent_session=session)
        logger.info("🎵 BackgroundAudioPlayer started (ready for transfer chimes)")
        Assistant.last_session = session
        logger.info("✅ Session started (after participant joined)!")

        greeting_message = agent_config.get('greeting', 'السلام عليكم ورحمة الله وبركاته')
        transcription.add_agent_message(greeting_message, "initial_greeting")
        transcription.greeting_added = True

        async def send_greeting_async():
            try:
                greeting_start = time.time()
                logger.info("🎤 Sending greeting...")
                await session.say(greeting_message)
                greeting_elapsed = time.time() - greeting_start
                logger.info(f"✅ Greeting sent! (took {greeting_elapsed:.2f}s)")
            except Exception as e:
                logger.error(f"❌ Greeting error: {e}")

        asyncio.create_task(send_greeting_async())

        # Start recording in background
        async def start_recording_background():
            try:
                logger.info("🎙️ Starting recording (background)...")
                recording_id = await recording_service.start_recording(ctx.room.name)
                if recording_id:
                    transcription.recording_id = recording_id
                    logger.info(f"✅ Recording started: {recording_id}")
            except Exception as e:
                logger.error(f"❌ Recording error: {e}")

        asyncio.create_task(start_recording_background())

        # Skip to end (all setup already done for non-campaign)
        # The rest of the function handles campaign calls and event handlers

    else:
        # Campaign calls: Connect first, then get config from metadata
        logger.info("🔗 Connecting to room...")
        await ctx.connect()
        state["start"] = time.time()
        logger.info("✅ Connected to room!")

    # Handle campaign calls (needs participant metadata)
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
                        'voice_name': metadata.get('agent_voice_name'),
                        'temperature': metadata.get('agent_temperature', 0.4),
                        'vad_mode': metadata.get('agent_vad_mode', 'dynamic'),
                        'transfer_targets': metadata.get('agent_transfer_targets'),
                    }
                    logger.info(f"✅ Using campaign agent: {agent_config['name']}")
        except Exception as e:
            logger.error(f"❌ Error parsing campaign metadata: {e}")

        # Fallback for campaign if metadata parsing failed
        if not agent_config:
            agent_config = get_default_config()

        # Initialize transcription for campaign
        transcription = TranscriptionManager()
        agent_id = agent_config.get('id')

    # ===== CAMPAIGN-ONLY: Load KB and tools (non-campaign already done above) =====
    kb_task = None
    if ctx.room.name.startswith('campaign_'):
        if agent_id and agent_id in kb_service._index_cache:
            logger.info(f"📚 Loading KB context for agent {agent_id}...")
            kb_task = asyncio.create_task(kb_service.retrieve_context(
                agent_id,
                query="معلومات عامة عن الشركة والخدمات",
                top_k=10
            ))

        # Load tools (cached, very fast)
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
                    agent_config = {**agent_config, "prompt": agent_config["prompt"] + "\n\n" + kb_context}
                    logger.info(f"✅ KB context injected ({len(kb_context)} chars)")
            except Exception as e:
                logger.error(f"❌ Error loading KB: {e}")

    # ===== CAMPAIGN-ONLY: Initialize models and create session =====
    # (Non-campaign calls already have session created before connect)
    if session is None:
        logger.info("🚀 Initializing models (campaign mode)...")

        async def init_tts():
            voice_speed = agent_config.get('voice_speed', 0.90)
            logger.info(f"🎙️ Campaign TTS: Voice={agent_config.get('voice_name', '?')}, Speed={voice_speed}x")
            return elevenlabs.TTS(
                voice_id=agent_config['voice_id'],
                model="eleven_turbo_v2_5",
                language="ar",
                auto_mode=True,
                voice_settings=elevenlabs.VoiceSettings(
                    stability=0.75,
                    similarity_boost=0.5,
                    style=0.0,
                    speed=voice_speed,
                    use_speaker_boost=True
                ),
                streaming_latency=0,
                inactivity_timeout=60,
                enable_ssml_parsing=False,
                apply_text_normalization="auto"
            )

        async def init_llm():
            llm_temperature = agent_config.get('temperature', 0.4)
            vad_mode = agent_config.get('vad_mode', 'dynamic')
            logger.info(f"🌡️ LLM Temperature: {llm_temperature}, VAD Mode: {vad_mode}")

            model_kwargs = {
                'model': "gpt-realtime-2025-08-28",
                'modalities': ["text"],
                'temperature': llm_temperature,
                'input_audio_transcription': InputAudioTranscription(
                    model="gpt-4o-transcribe",
                    language="ar",
                ),
            }

            if vad_mode == 'natural':
                model_kwargs['turn_detection'] = TurnDetection(
                    type="semantic_vad",
                    eagerness="auto",
                    create_response=True,
                    interrupt_response=True,
                )
            elif vad_mode != 'precise':
                model_kwargs['turn_detection'] = TurnDetection(
                    type="server_vad",
                    threshold=0.45,
                    prefix_padding_ms=150,
                    silence_duration_ms=250,
                    create_response=True,
                    interrupt_response=True,
                )

            return RealtimeModel(**model_kwargs)

        tts_engine, llm_model_realtime = await asyncio.gather(
            init_tts(),
            init_llm()
        )
        logger.info("✅ Models initialized!")

        # Create session for campaign
        session = voice.AgentSession(
            llm=llm_model_realtime,
            tts=tts_engine,
            preemptive_generation=True,
            user_away_timeout=float(os.environ.get('USER_AWAY_TIMEOUT', '60.0'))
        )

    # Register handlers before session.start() (campaign only; non-campaign already did this before connect)
    if ctx.room.name.startswith("campaign_"):
        _register_session_handlers(session, transcription, agent_config, ctx, state)

    # ===== CAMPAIGN-ONLY: Start session and greeting (non-campaign already done above) =====
    if ctx.room.name.startswith('campaign_'):
        logger.info(f"🚀 Starting session with agent: {agent_config['name']}")
        background_audio = BackgroundAudioPlayer()
        await session.start(
            room=ctx.room,
            agent=Assistant(config=agent_config, agent_id=agent_id, preloaded_tools=dynamic_tools,
                            background_audio=background_audio),
            room_input_options=RoomInputOptions(
                noise_cancellation=noise_cancellation.BVCTelephony(),
            ),
        )
        await background_audio.start(room=ctx.room, agent_session=session)
        logger.info("🎵 BackgroundAudioPlayer started (ready for transfer chimes)")

        # Store session reference
        Assistant.last_session = session
        logger.info("✅ Session started!")

        # Send greeting
        greeting_message = agent_config.get('greeting', 'السلام عليكم ورحمة الله وبركاته')
        transcription.add_agent_message(greeting_message, "initial_greeting")
        transcription.greeting_added = True

        async def send_greeting_async():
            try:
                greeting_start = time.time()
                logger.info("🎤 Sending greeting...")
                await session.say(greeting_message)
                greeting_elapsed = time.time() - greeting_start
                logger.info(f"✅ Greeting sent! (took {greeting_elapsed:.2f}s)")
            except Exception as e:
                logger.error(f"❌ Greeting error: {e}")

        asyncio.create_task(send_greeting_async())

        # Start recording in background
        async def start_recording_background():
            try:
                logger.info("🎙️ Starting recording (background)...")
                recording_id = await recording_service.start_recording(ctx.room.name)
                if recording_id:
                    transcription.recording_id = recording_id
                    logger.info(f"✅ Recording started: {recording_id}")
            except Exception as e:
                logger.error(f"❌ Recording error: {e}")

        asyncio.create_task(start_recording_background())

    # (Participant disconnect + monitor tasks are registered in _register_session_handlers.)
    logger.info("✅ Call setup complete - greeting is playing")

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
    tool_service.preload_all_agents()
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