import asyncio
import logging
import os
import time
import json
import aiohttp
from datetime import datetime
from dotenv import load_dotenv
from livekit import api
from livekit.agents import voice, llm
from livekit.agents import (
    Agent,
    JobContext,
    MetricsCollectedEvent,
    RoomInputOptions,
    RunContext,
    WorkerOptions,
    cli,
    function_tool,
    get_job_context,
    metrics,
)
from livekit.plugins import noise_cancellation, openai, elevenlabs
from livekit.plugins.openai.realtime import RealtimeModel
from openai.types.beta.realtime.session import InputAudioTranscription

from openai.types.beta.realtime.session import TurnDetection

logger = logging.getLogger("agent")
load_dotenv(".env")


class TranscriptionCapture:
    """Capture transcription from session events"""
    def __init__(self):
        self.messages = []
    
    def add_message(self, role: str, content: str, source: str = ""):
        if isinstance(content, str) and content.strip():
            self.messages.append({
                "timestamp": datetime.now().isoformat(),
                "role": role,
                "text": content,
                "source": source
            })
            logger.info(f"💬 [{role.upper()}]: {content[:100]}")
    
    def get_transcript(self) -> str:
        return "\n".join([f"{m['role'].upper()}: {m['text']}" for m in self.messages])


async def hangup_call():
    ctx = get_job_context()
    if ctx is None:
        return
    await ctx.api.room.delete_room(api.DeleteRoomRequest(room=ctx.room.name))


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="""
أنت مساعد ذكي مفيد يتحدث باللغة العربية فقط.
المستخدم يتفاعل معك عبر الصوت.
أجب على جميع الأسئلة باللغة العربية فقط، بدون أي لغات أخرى.
كن ودوداً وذا حس فكاهي.
استجب بإجابات قصيرة ومباشرة بدون رموز معقدة أو رموز تعبيرية.
يجب أن تكون ردودك سريعة وموجزة - لا تطيل في الإجابات.
""",
        )

    @function_tool
    async def end_call(self, ctx: RunContext):
        """Called when the user wants to end the call"""
        await ctx.wait_for_playout()
        await hangup_call()
        return "تم إنهاء المكالمة"


async def entrypoint(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}
    logger.info(f"🎯 Room: {ctx.room.name}")
    logger.info(f"📊 Participants: {ctx.room.num_participants}")

    transcription = TranscriptionCapture()
    call_start_time = time.time()

    # --- ElevenLabs TTS (Optimized for Speed) ---
    tts_engine = elevenlabs.TTS(
        voice_id="YdWLuz4rVsaG3kWAECFE",
        model="eleven_turbo_v2_5",
        language="ar",
        auto_mode=True,
        voice_settings=elevenlabs.VoiceSettings(
            stability=0.7,  # Reduced for faster processing
            similarity_boost=0.65,  # Reduced for faster processing
            style=0.0,
            speed=0.95,  # Slightly faster speech
            use_speaker_boost=False  # Disabled for speed
        ),
        streaming_latency=0,  # Lowest latency (0-4 scale)
        inactivity_timeout=60,
        enable_ssml_parsing=False,  # Disabled for speed
        apply_text_normalization="auto"  # Changed to auto for speed
    )

    # --- OpenAI Realtime (Optimized for Speed) ---
    llm_model = RealtimeModel(
        model="gpt-4o-realtime-preview",
        modalities=["text"],
        temperature=0.7,  # Slightly reduced for more focused responses
        input_audio_transcription=InputAudioTranscription(
            model="whisper-1",
            language="ar"
        ),
        turn_detection=TurnDetection(
            type="server_vad",
            threshold=0.6,  # Higher threshold = faster detection
            prefix_padding_ms=200,  # Reduced padding for faster response
            silence_duration_ms=400,  # Reduced silence duration for quicker turn-taking
            create_response=True,
            interrupt_response=True,  # Allow interruptions for more natural flow
        ),
    )


    # --- Create AgentSession ---
    session = voice.AgentSession(llm=llm_model, tts=tts_engine)

    # --- Metrics ---
    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    # --- Transcription events ---
    @session.on("user_speech_committed")
    def on_user_speech_committed(msg: llm.ChatMessage):
        logger.info(f"✅ User: {msg.content}")
        transcription.add_message("user", msg.content, "user_speech")

    @session.on("agent_speech_committed")
    def on_agent_speech_committed(msg: llm.ChatMessage):
        logger.info(f"✅ Agent: {msg.content}")
        transcription.add_message("agent", msg.content, "agent_speech")

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"📊 Usage: {summary}")

    async def send_call_data():
        """Send call completion data to Flask webhook"""
        call_duration = int(time.time() - call_start_time)
        
        logger.info(f"📝 Final transcription:")
        logger.info(f"   Messages: {len(transcription.messages)}")
        
        for i, msg in enumerate(transcription.messages, 1):
            logger.info(f"      {i}. [{msg['role'].upper()}]: {msg['text'][:80]}")

        try:
            payload = {
                'room_name': ctx.room.name,
                'duration': call_duration,
                'transcription': transcription.get_transcript(),
                'metadata': {
                    'start_time': datetime.now().isoformat(),
                    'end_time': datetime.now().isoformat(),
                    'message_count': len(transcription.messages),
                    'messages': transcription.messages
                },
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
        except Exception as e:
            logger.error(f"❌ Error: {e}")

    ctx.add_shutdown_callback(log_usage)
    ctx.add_shutdown_callback(send_call_data)

    # --- Start session ---
    await session.start(
        room=ctx.room,
        agent=Assistant(),
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVCTelephony(),
            close_on_disconnect=False,
        ),
    )

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