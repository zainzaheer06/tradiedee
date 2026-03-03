import asyncio
import logging
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# LiveKit v1.x Imports
from livekit import api
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    cli,
    room_io,
)
from livekit.agents.llm import function_tool
from livekit.plugins import google, elevenlabs, silero
from google.genai.types import Modality

# --- 1. SETUP DETAILED LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("assistant_logger")

load_dotenv(".env")

# --- 2. STATIC CONFIGURATION (No DB) ---
def get_test_config():
    return {
        'prompt': (
            "You are a versatile English AI assistant. "
            "You have tools for weather, time, and placing orders. "
            "Always be concise and speak ONLY in English."
        ),
        'greeting': "Hello! I'm your test agent. I can check weather, tell time, or place orders. How can I help?",
        'voice_id': "pNInz6obpg8ndclKuztW" # Standard English Voice
    }

# --- 3. THE ASSISTANT CLASS ---
class TestAssistant(Agent):
    def __init__(self, config, job_ctx: JobContext):
        self.job_ctx = job_ctx
        
        super().__init__(
            instructions=config['prompt'],
            llm=google.realtime.RealtimeModel(
                model="models/gemini-2.0-flash-exp",
                modalities=[Modality.TEXT],
                temperature=0.4,
            ),
            tts=elevenlabs.TTS(
                voice_id="YdWLuz4rVsaG3kWAECFE",
                model="eleven_turbo_v2_5"
            ),
            vad=silero.VAD.load()
        )

    # --- TOOL 1: Weather ---
    @function_tool
    async def get_weather(self, location: str):
        """Get the current weather for a specific location."""
        logger.info(f"🛠️ TOOL: get_weather -> {location}")
        return f"The weather in {location} is currently 75 degrees and sunny."

    # --- TOOL 2: Current Time ---
    @function_tool
    async def get_current_time(self):
        """Get the current local time."""
        logger.info("🛠️ TOOL: get_current_time")
        now = datetime.now().strftime("%I:%M %p")
        return f"The current time is {now}."

    # --- TOOL 3: Mock Ordering ---
    @function_tool
    async def create_mock_order(self, item: str, quantity: int = 1):
        """Create a mock order for a specific item and quantity."""
        logger.info(f"🛠️ TOOL: create_mock_order -> {quantity}x {item}")
        # In a real app, you'd call an API here
        return f"Success! I have placed an order for {quantity} {item}(s)."

    # --- TOOL 4: End Call ---
    @function_tool
    async def end_call(self):
        """Call this to end the conversation and hang up."""
        logger.info("🛠️ TOOL: end_call")
        asyncio.create_task(self._delayed_hangup())
        return "It was a pleasure helping you. Goodbye!"

    async def _delayed_hangup(self):
        await asyncio.sleep(3) 
        logger.info("🔌 Hanging up...")
        try:
            await self.job_ctx.api.room.delete_room(
                api.DeleteRoomRequest(room=self.job_ctx.room.name)
            )
        except Exception as e:
            logger.error(f"Hangup failed: {e}")

# --- 4. SERVER & SESSION ---
server = AgentServer()

@server.rtc_session()
async def entrypoint(ctx: JobContext):
    logger.info(f"🌐 Room connected: {ctx.room.name}")
    await ctx.connect()

    config = get_test_config()
    agent = TestAssistant(config, ctx) 
    session = AgentSession()

    @session.on("agent_message")
    def _agent_msg(msg):
        logger.info(f"🤖 AI MESSAGE: {msg}")

    # Start the session
    await session.start(
        agent=agent,
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_output=True,
            text_output=True
        ),
    )

    # Trigger Greeting
    session.generate_reply(instructions=f"Say: {config['greeting']}")

if __name__ == "__main__":
    cli.run_app(server)