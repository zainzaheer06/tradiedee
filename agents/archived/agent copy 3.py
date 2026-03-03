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
    get_job_context,
    llm,
    metrics,
)
from livekit.plugins import noise_cancellation, openai, elevenlabs
from livekit.plugins.openai.realtime import RealtimeModel
from openai.types.beta.realtime.session import InputAudioTranscription, TurnDetection

logger = logging.getLogger("agent")
load_dotenv(".env")


# --- Transcription Manager ---
class TranscriptionManager:
    def __init__(self):
        self.messages = []
        self.start_time = datetime.now().isoformat()
        self.seen_messages = set()  # Track unique messages to avoid duplicates

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
            "messages": self.messages
        }


# --- Hangup helper ---
async def hangup_call():
    ctx = get_job_context()
    if ctx is None:
        return
    await ctx.api.room.delete_room(api.DeleteRoomRequest(room=ctx.room.name))


# --- Main Agent ---
class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="""
أنت مساعد ذكي مفيد يتحدث باللغة العربية فقط. 
المستخدم يتفاعل معك عبر الصوت.
أجب على جميع الأسئلة باللغة العربية فقط، بدون أي لغات أخرى.
كن ودوداً وذا حس فكاهي.
استجب بإجابات قصيرة ومباشرة بدون رموز معقدة أو رموز تعبيرية.
[رد فقط باللغة العربية]
""",
        )

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

    # Initialize transcription manager
    transcription = TranscriptionManager()
    call_start_time = time.time()

    # --- ElevenLabs TTS (Arabic) ---
    tts_engine = elevenlabs.TTS(
        voice_id="YdWLuz4rVsaG3kWAECFE",  
        model="eleven_turbo_v2_5",
        language="ar",
        auto_mode=True,
        voice_settings=elevenlabs.VoiceSettings(
            stability=0.85,
            similarity_boost=0.75,
            style=0.0,
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
    async def monitor_session():
        """Periodically check session for conversation updates"""
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

    # --- Start session ---
    await session.start(
        room=ctx.room,
        agent=Assistant(),
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVCTelephony(),
        ),
    )

    # Start session monitor in background
    asyncio.create_task(monitor_session())

    # --- Connect room ---
    await ctx.connect()

    # --- Initial greeting ---
    if ctx.room.num_participants == 0:
        logger.info("🎤 Generating greeting...")
        await session.generate_reply(
            instructions="قل مرحباً وعرف نفسك كمساعد ذكي"
        )


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))