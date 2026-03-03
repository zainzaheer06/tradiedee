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
from livekit.plugins.openai import realtime
from openai.types.beta.realtime.session import TurnDetection

logger = logging.getLogger("agent")
load_dotenv(".env")


# --- Transcription Manager ---
class TranscriptionManager:
    def __init__(self):
        self.messages = []
        self.start_time = datetime.now().isoformat()
    
    def add_user_message(self, text: str):
        if text.strip():
            msg = {
                "timestamp": datetime.now().isoformat(),
                "role": "user",
                "text": text
            }
            self.messages.append(msg)
            logger.info(f"✅ User transcribed: {text}")
    
    def add_agent_message(self, text: str):
        if text.strip():
            msg = {
                "timestamp": datetime.now().isoformat(),
                "role": "agent",
                "text": text
            }
            self.messages.append(msg)
            logger.info(f"✅ Agent response: {text}")
    
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
        voice_id="G1L6zhS0TTaBvSr18eUY",  
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

    # --- OpenAI Realtime model ---
    llm_model = openai.realtime.RealtimeModel(
        model="gpt-4o-realtime-preview",
        modalities=["text", "audio"],
        temperature=0.8,
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

    # Fallback: Try alternative event names
    @session.on("user_message")
    def on_user_message(msg: llm.ChatMessage):
        """Fallback for user messages"""
        try:
            if hasattr(msg, 'role') and msg.role == 'user':
                text = msg.content if isinstance(msg.content, str) else ""
                if text.strip():
                    transcription.add_user_message(text)
        except:
            pass

    @session.on("agent_message")
    def on_agent_message(msg: llm.ChatMessage):
        """Fallback for agent messages"""
        try:
            if hasattr(msg, 'role') and msg.role == 'assistant':
                text = msg.content if isinstance(msg.content, str) else ""
                if text.strip():
                    transcription.add_agent_message(text)
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

        try:
            payload = {
                'room_name': ctx.room.name,
                'duration': call_duration,
                'transcription': transcription.get_plain_text(),
                'metadata': transcription.get_json(),
                'message_count': len(transcription.messages)
            }

            logger.info(f"🚀 Sending webhook to: {os.environ.get('FLASK_WEBHOOK_URL', 'http://localhost:5000/webhook/call-ended')}")
            logger.info(f"   Payload: {json.dumps(payload, indent=2, ensure_ascii=False)}")

            async with aiohttp.ClientSession() as http_session:
                webhook_url = os.environ.get('FLASK_WEBHOOK_URL', 'http://localhost:5000/webhook/call-ended')
                async with http_session.post(webhook_url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        logger.info(f"✅ Webhook sent successfully!")
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

    # --- Start session ---
    await session.start(
        room=ctx.room,
        agent=Assistant(),
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVCTelephony(),
        ),
    )

    # --- Connect room ---
    await ctx.connect()

    # --- Initial greeting ---
    if ctx.room.num_participants == 0:
        logger.info("🎤 Generating initial greeting...")
        await session.generate_reply(
            instructions="قل مرحباً وعرف نفسك كمساعد ذكي"
        )


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))