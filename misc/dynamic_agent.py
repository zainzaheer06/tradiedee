import asyncio
import logging
import os
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
    metrics,
)
from livekit.plugins import noise_cancellation, openai, elevenlabs
from livekit.plugins.openai import realtime
from openai.types.beta.realtime.session import TurnDetection
from flask_sqlalchemy import SQLAlchemy
from app import db, Agent as AgentModel

logger = logging.getLogger("agent")
load_dotenv(".env")


# --- Hangup helper ---
async def hangup_call():
    ctx = get_job_context()
    if ctx is None:
        return
    await ctx.api.room.delete_room(api.DeleteRoomRequest(room=ctx.room.name))


# --- Dynamic Agent ---
class DynamicAssistant(Agent):
    def __init__(self, prompt: str = None) -> None:
        # Use custom prompt or default
        default_prompt = """
أنت مساعد ذكي مفيد يتحدث باللغة العربية فقط.
المستخدم يتفاعل معك عبر الصوت.
أجب على جميع الأسئلة باللغة العربية فقط، بدون أي لغات أخرى.
كن ودوداً وذا حس فكاهي.
استجب بإجابات قصيرة ومباشرة بدون رموز معقدة أو رموز تعبيرية.
[رد فقط باللغة العربية]
"""
        super().__init__(
            instructions=prompt if prompt else default_prompt,
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
    logger.info(f"Room participants: {ctx.room.num_participants}")
    logger.info(f"Room metadata: {ctx.room.metadata}")

    # Get custom prompt from agent metadata if available
    custom_prompt = None
    try:
        # The metadata contains the agent_id
        agent_id = ctx.job.agent_name
        logger.info(f"Agent ID: {agent_id}")
    except Exception as e:
        logger.error(f"Could not get agent metadata: {e}")

    # --- ElevenLabs TTS (Arabic) ---
    tts_engine = elevenlabs.TTS(
        voice_id="G1L6zhS0TTaBvSr18eUY",
        model="eleven_turbo_v2_5",
        language="ar",
        auto_mode=True,

        # Phone call optimizations
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

    # --- OpenAI Realtime model (text only) ---
    llm_model = openai.realtime.RealtimeModel(
        model="gpt-4o-realtime-preview",
        modalities=["text"],
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

    # --- Combine both engines ---
    session = voice.AgentSession(llm=llm_model, tts=tts_engine)

    # --- Metrics ---
    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"Usage: {summary}")

    ctx.add_shutdown_callback(log_usage)

    # --- Start session ---
    await session.start(
        room=ctx.room,
        agent=DynamicAssistant(custom_prompt),
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVCTelephony(),
        ),
    )

    # --- Connect room ---
    await ctx.connect()

    # --- Initial greeting if no participants ---
    if ctx.room.num_participants == 0:
        logger.info("No participants yet. Generating initial message.")
        await session.generate_reply(
            instructions="مرحباً، هل هناك أحد؟"
        )


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))