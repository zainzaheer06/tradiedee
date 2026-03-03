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
from livekit.plugins import noise_cancellation, openai, elevenlabs
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
            SELECT id, name, prompt, voice_id, voice_name
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
        'voice_id': 'YdWLuz4rVsaG3kWAECFE',
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
    system_instructions = """أنت مساعد صوتي ذكي ومحترف تمثّل شركة Nevox AI.

قواعد مهمة:
- تحدث دائمًا بلغةٍ عربية واضحة وطبيعية بلهجةٍ قريبة من الأسلوب السعودي.
- اجعل ردودك قصيرة، مباشرة، وواضحة — كما لو كنت تتحدث مع عميل بشكل طبيعي.
- تحدث بأسلوب لبق، واثق، ودافئ.
- استخدم تعبيرات سعودية أصيلة تناسب الثقافة وطبيعة الحديث اليومي.
- حافظ دائمًا على نبرة محترمة وإيجابية — واجعل في صوتك ابتسامة.
- تجنّب النغمة الآلية أو الرسمية الزائدة.
- إذا لم تفهم السؤال، اطلب التوضيح بطريقة بسيطة.
- لا تقدّم أي معلومات طبية أو قانونية أو مالية.
- إذا طلب المستخدم إنهاء المكالمة أو قال "وداعاً" أو "باي" أو "مع السلامة"، استخدم وظيفة end_call فوراً.

---

"""

    # Combine: system instructions + user's custom prompt
    full_prompt =  user_prompt
    print(full_prompt)
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
            stability=0.71,  # Lower = faster (0.71 recommended for speed)
            similarity_boost=0.5,  # Lower = faster
            style=0.0,  # Keep 0 for speed
            speed=0.95,  # Increase from 0.95 to 1.0 for faster speech
            use_speaker_boost=True
        ),
        streaming_latency=1,  # 0 = Maximum speed, 4 = Maximum quality
        inactivity_timeout=60,
        enable_ssml_parsing=False,  # Disable for speed (unless you need SSML)
        apply_text_normalization="auto"  # "auto" is faster than "on"
    )

    # --- OpenAI Realtime model with transcription ---
    llm_model = RealtimeModel(
        model="gpt-4o-realtime-preview",
        modalities=["text"],
        temperature=0.2,  # Keep low for consistency
        input_audio_transcription=InputAudioTranscription(
            model="whisper-1",
            language="ar"
        ),
        turn_detection=TurnDetection(
            type="server_vad",
            threshold=0.45,  # Keep at 0.5 for balance
            prefix_padding_ms=150,  # Reduced from 300ms → faster response
            silence_duration_ms=350,  # Reduced from 500ms → faster detection
            create_response=True,
            interrupt_response=True,
        ),
    )

    # --- Create session ---
    # user_away_timeout: seconds of inactivity before user is considered "away"
    session = voice.AgentSession(
        llm=llm_model,
        tts=tts_engine,
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

    @session.on("user_transcript")
    def on_user_transcript(transcript):
        """User transcript event"""
        try:
            transcription.add_user_message(str(transcript), "user_transcript_event")
        except:
            pass

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

        # Try to extract conversation from session if no messages captured
        if len(transcription.messages) == 0:
            logger.warning("⚠️ No messages captured via events, trying to extract from session...")
            try:
                # Try to access conversation history from the session
                if hasattr(session, 'conversation') and session.conversation:
                    if hasattr(session.conversation, 'messages'):
                        for msg in session.conversation.messages:
                            if hasattr(msg, 'role') and hasattr(msg, 'content'):
                                transcription.add_message(msg.role, msg.content, "session_conversation")

                # Try accessing chat context
                if hasattr(session, 'chat_ctx') and session.chat_ctx:
                    if hasattr(session.chat_ctx, 'messages'):
                        for msg in session.chat_ctx.messages:
                            if hasattr(msg, 'role') and hasattr(msg, 'content'):
                                transcription.add_message(msg.role, msg.content, "chat_context")

                # Try accessing LLM directly
                if hasattr(session, 'llm') and hasattr(session.llm, 'conversation'):
                    conv = session.llm.conversation
                    if hasattr(conv, 'messages'):
                        for msg in conv.messages:
                            if hasattr(msg, 'role') and hasattr(msg, 'content'):
                                transcription.add_message(msg.role, msg.content, "llm_conversation")

            except Exception as e:
                logger.error(f"⚠️ Error extracting conversation: {e}")

        # Log final message list
        for i, msg in enumerate(transcription.messages, 1):
            logger.info(f"   {i}. [{msg['role'].upper()}]: {msg['text'][:80]}")

        try:
            payload = {
                'room_name': ctx.room.name,
                'duration': call_duration,
                'transcription': transcription.get_plain_text(),
                'metadata': transcription.get_json(),
                'message_count': len(transcription.messages)
            }

            logger.info(f"🚀 Sending webhook: {len(transcription.messages)} messages")

            async with aiohttp.ClientSession() as http_session:
                webhook_url = os.environ.get('FLASK_WEBHOOK_URL', 'http://localhost:5000/webhook/call-ended')
                async with http_session.post(webhook_url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        logger.info(f"✅ Webhook sent!")
                    else:
                        logger.error(f"❌ Webhook failed: {resp.status}")
                        logger.error(f"   Response: {await resp.text()}")
        except asyncio.TimeoutError:
            logger.error(f"❌ Webhook timeout")
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
    logger.info("🎤 Generating greeting...")
    await session.generate_reply(
        instructions=(
            "ابدأ بتحية سعودية ودودة، واضبط نبرة الحديث حسب أسلوب المستخدم (رسمية أو شبابية) "
            "بدون ما تعرّف بنفسك أو تذكر إنك مساعد. "
            "بعد التحية، اسأل المستخدم وش يحتاج أو كيف تقدر تخدمه."
        )
    )



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