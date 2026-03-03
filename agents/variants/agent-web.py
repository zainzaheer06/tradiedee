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

logger = logging.getLogger("agent-web")
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


class WebDemoAssistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=("""التوجيهات الأساسية:

ChatGPT said:

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


You are a helpful and polite Arabic-speaking Nevox AI assistant. Who understand Saudi dialect and cultural context. Use the following expressions to interact with the user:
Saudi Expression Table:
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
- إذا طلب المستخدم إنهاء المكالمة أو قال "وداعاً" أو "باي" أو "مع السلامة"، استخدم وظيفة end_call فوراً.
Greeting is already being handled by greeting dont greetings like "walikum asalam"

if user says;
عليكم السلام ورحمة الله وبركاته
dont say "وعليكم السلام ورحمة الله وبركاته"


Don't tell about OpenAI models/ Technical Stuff 

Always say I am  built by Nevox AI.

Always Try to ask name politely.

Use Saudi Culture and Understanding in Responses.

Don't Repeat responses.

Always give short responses under 150 characters. Don't go in details.

Always respond in Arabic ONLY.

Because there is greeting message from LLm proceed and it is already being handled by greeting.

---

"""
)
        )

    @function_tool
    async def end_call(self, ctx: RunContext):
        """Called when the user wants to end the session"""
        await ctx.wait_for_playout()
        await hangup_call()
        return "Session ended. Thank you for trying the demo!"


async def entrypoint(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}
    logger.info(f"🎯 Room: {ctx.room.name}")
    logger.info(f"📊 Participants: {ctx.room.num_participants}")

    transcription = TranscriptionCapture()
    call_start_time = time.time()
    last_activity_time = [time.time()]  # Use list to allow modification in nested functions
    inactivity_timeout = 50  # seconds
    inactivity_check_task = None

    def reset_activity_timer():
        """Reset the inactivity timer"""
        last_activity_time[0] = time.time()
        logger.debug("⏰ Activity detected, timer reset")

    async def check_inactivity():
        """Monitor for inactivity and close room if no activity for 20 seconds"""
        while True:
            await asyncio.sleep(1)  # Check every second
            inactive_time = time.time() - last_activity_time[0]

            if inactive_time >= inactivity_timeout:
                logger.warning(f"⚠️ No activity for {inactivity_timeout} seconds. Closing room...")
                try:
                    await ctx.api.room.delete_room(api.DeleteRoomRequest(room=ctx.room.name))
                    logger.info("🔚 Room deleted due to inactivity")
                except Exception as e:
                    logger.error(f"Error deleting room: {e}")
                break

    # --- ElevenLabs TTS (Optimized for Speed) ---
    tts_engine = elevenlabs.TTS(
        voice_id="kgxi5e6hsB6HuAGpjbQ5",
        model="eleven_turbo_v2_5",
        language="ar",
        auto_mode=True,
        voice_settings=elevenlabs.VoiceSettings(
            stability=0.7,
            similarity_boost=0.65,
            style=0.0,
            speed=0.95,
            use_speaker_boost=False
        ),
        streaming_latency=0,
        inactivity_timeout=30,
        enable_ssml_parsing=False,
        apply_text_normalization="auto"
    )

    # --- OpenAI Realtime (Semantic VAD) ---
    llm_model = RealtimeModel(
        model="gpt-4o-realtime-preview",
        modalities=["text"],
        temperature=0.5,
        input_audio_transcription=InputAudioTranscription(
            model="whisper-1",
            language="ar"
        ),
        turn_detection=TurnDetection(
            type="semantic_vad",
            eagerness="auto",  # Options: "auto", "low", "medium", "high"
            create_response=True,
            interrupt_response=True,
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
        reset_activity_timer()  # Reset timer on user speech

    @session.on("agent_speech_committed")
    def on_agent_speech_committed(msg: llm.ChatMessage):
        logger.info(f"✅ Agent: {msg.content}")
        transcription.add_message("agent", msg.content, "agent_speech")
        reset_activity_timer()  # Reset timer on agent speech

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"📊 Web Demo Usage: {summary}")

    async def cleanup_room():
        """Cleanup demo room after session"""
        call_duration = int(time.time() - call_start_time)

        logger.info(f"📝 Web Demo Session Summary:")
        logger.info(f"   Duration: {call_duration}s")
        logger.info(f"   Messages: {len(transcription.messages)}")

        # Note: We don't send webhook for demo sessions to avoid cluttering logs
        # Demo sessions are not logged in the database
        logger.info(f"🧹 Cleaning up demo room: {ctx.room.name}")

    ctx.add_shutdown_callback(log_usage)
    ctx.add_shutdown_callback(cleanup_room)

    # --- Start session ---
    await session.start(
        room=ctx.room,
        agent=WebDemoAssistant(),
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVCTelephony(),
            close_on_disconnect=True,  # Auto-cleanup for web demos
        ),
    )

    # --- Connect room ---
    await ctx.connect()

    # Wait for user to join
    logger.info("⏳ Waiting for user participant...")
    await asyncio.sleep(3)  # Give more time for user to fully connect

    # Check participant count
    logger.info(f"👥 Participants in room: {len(ctx.room.remote_participants)}")

    # --- Initial greeting for web demo ---
    logger.info("🎤 Generating web demo greeting...")
    await session.say("السلام عليكم ورحمة الله وبركاته، أهلاً وسهلاً فيك. أنا مساعدك الذكي، كيف أقدر أساعدك اليوم؟", allow_interruptions=True)
    logger.info("✅ Greeting sent!")

    

    # --- Start inactivity monitoring ---
    logger.info(f"⏰ Starting inactivity monitor (timeout: {inactivity_timeout}s)")
    inactivity_check_task = asyncio.create_task(check_inactivity())

    # Wait for the inactivity task to complete (which happens when room is closed)
    try:
        await inactivity_check_task
    except asyncio.CancelledError:
        logger.info("⏰ Inactivity check cancelled")
    except Exception as e:
        logger.error(f"Error in inactivity check: {e}")



if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
