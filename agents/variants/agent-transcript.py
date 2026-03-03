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
        print("🎙️ TRANSCRIPTION CAPTURE INITIALIZED")
        print("=" * 60)
    
    def add_message(self, role: str, content: str, source: str = ""):
        if isinstance(content, str) and content.strip():
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.messages.append({
                "timestamp": datetime.now().isoformat(),
                "role": role,
                "text": content,
                "source": source
            })
            
            # Enhanced console output
            print(f"\n[{timestamp}] 💬 {role.upper()} ({source}):")
            print(f"📝 {content}")
            print("-" * 40)
            
            logger.info(f"💬 [{role.upper()}]: {content[:100]}")
    
    def get_transcript(self) -> str:
        return "\n".join([f"{m['role'].upper()}: {m['text']}" for m in self.messages])
    
    def print_full_transcript(self):
        """Print the complete transcript to console"""
        print("\n" + "=" * 60)
        print("📋 COMPLETE TRANSCRIPT")
        print("=" * 60)
        for i, msg in enumerate(self.messages, 1):
            timestamp = datetime.fromisoformat(msg['timestamp']).strftime("%H:%M:%S")
            print(f"{i:2d}. [{timestamp}] {msg['role'].upper()}: {msg['text']}")
        print("=" * 60)


async def hangup_call():
    ctx = get_job_context()
    if ctx is None:
        return
    await ctx.api.room.delete_room(api.DeleteRoomRequest(room=ctx.room.name))


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=(
                "أنت مساعد ذكي ومفيد تتحدث باللغة العربية فقط.\n"
                "يتفاعل معك المستخدم عبر الصوت.\n"
                "أجب على جميع الأسئلة بالعربية فقط، ولا تستخدم أي لغة أخرى.\n"
                "كن ودوداً وذا روح مرحة، وتحدث بطريقة طبيعية قريبة من الناس.\n"
                "اجعل إجاباتك قصيرة وواضحة ومباشرة، من دون رموز معقدة أو رموز تعبيرية.\n"
                "لديك فهم عميق للهجة السعودية وثقافة المنطقة، وتستطيع التعبير بطبيعة ولهجة تناسب المتحدثين في السعودية."
            )
        )
        logging.info("🤖 Assistant initialized with Arabic instructions")

    @function_tool
    async def end_call(self, ctx: RunContext):
        """Called when the user wants to end the call"""
        print("📞 END CALL FUNCTION TRIGGERED")
        await ctx.wait_for_playout()
        await hangup_call()
        print("✅ Call ended successfully")
        return "تم إنهاء المكالمة"


async def entrypoint(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}
    
    # Enhanced console output for debugging
    print("\n🚀 AGENT STARTING...")
    print(f"🎯 Room: {ctx.room.name}")
    print(f"📊 Participants: {ctx.room.num_participants}")
    print("⏰ Start time:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 60)
    
    logger.info(f"🎯 Room: {ctx.room.name}")
    logger.info(f"📊 Participants: {ctx.room.num_participants}")

    transcription = TranscriptionCapture()
    call_start_time = time.time()

    # --- ElevenLabs TTS ---
    print("🔊 Initializing ElevenLabs TTS...")
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
    print("✅ TTS Engine ready!")

    # --- OpenAI Realtime with proper transcription ---
    print("🧠 Initializing OpenAI Realtime Model...")
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
    print("✅ LLM Model ready!")


    # --- Create AgentSession ---
    print("🤖 Creating Agent Session...")
    session = voice.AgentSession(llm=llm_model, tts=tts_engine)
    print("✅ Agent Session created!")

    # --- Metrics ---
    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        print(f"📊 Metrics collected: {ev.metrics}")
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    # --- Transcription events ---
    @session.on("user_speech_committed")
    def on_user_speech_committed(msg: llm.ChatMessage):
        print(f"\n🎤 USER SPEECH DETECTED:")
        print(f"   Content: {msg.content}")
        logger.info(f"✅ User: {msg.content}")
        transcription.add_message("user", msg.content, "user_speech")

    @session.on("agent_speech_committed")
    def on_agent_speech_committed(msg: llm.ChatMessage):
        print(f"\n🤖 AGENT RESPONSE GENERATED:")
        print(f"   Content: {msg.content}")
        logger.info(f"✅ Agent: {msg.content}")
        transcription.add_message("agent", msg.content, "agent_speech")
        
    # Handle the actual events we see in the logs
    @session.on("user_input_transcribed")
    def on_user_input_transcribed(event):
        print(f"\n🎤 USER INPUT TRANSCRIBED:")
        print(f"   Transcript: {event.transcript}")
        print(f"   Is Final: {event.is_final}")
        if event.is_final and event.transcript.strip():
            transcription.add_message("user", event.transcript, "user_input_transcribed")
            
    @session.on("conversation_item_added")
    def on_conversation_item_added(event):
        print(f"\n💬 CONVERSATION ITEM ADDED:")
        print(f"   Role: {event.item.role}")
        print(f"   Content: {event.item.content}")
        if hasattr(event.item, 'content') and event.item.content:
            # Content is a list, join it
            content = ' '.join(event.item.content) if isinstance(event.item.content, list) else str(event.item.content)
            transcription.add_message(event.item.role, content, "conversation_item_added")
        
    # More comprehensive event handling for RealtimeModel
    @session.on("user_started_speaking")
    def on_user_started_speaking():
        print("🎙️ User started speaking...")
        
    @session.on("user_stopped_speaking")
    def on_user_stopped_speaking():
        print("🎙️ User stopped speaking")
        
    @session.on("agent_started_speaking")
    def on_agent_started_speaking():
        print("🗣️ Agent started speaking...")
        
    @session.on("agent_stopped_speaking") 
    def on_agent_stopped_speaking():
        print("🗣️ Agent stopped speaking")
        
    # Try different event names that might be used by RealtimeModel
    @session.on("user_transcript")
    def on_user_transcript(transcript):
        print(f"\n📝 USER TRANSCRIPT: {transcript}")
        transcription.add_message("user", str(transcript), "user_transcript_event")
        
    @session.on("agent_transcript")
    def on_agent_transcript(transcript):
        print(f"\n📝 AGENT TRANSCRIPT: {transcript}")
        transcription.add_message("agent", str(transcript), "agent_transcript_event")
        
    @session.on("user_message")
    def on_user_message(msg):
        print(f"\n📨 USER MESSAGE: {msg}")
        if hasattr(msg, 'content'):
            transcription.add_message("user", msg.content, "user_message_event")
        else:
            transcription.add_message("user", str(msg), "user_message_event")
            
    @session.on("agent_message")
    def on_agent_message(msg):
        print(f"\n🤖 AGENT MESSAGE: {msg}")
        if hasattr(msg, 'content'):
            transcription.add_message("agent", msg.content, "agent_message_event")
        else:
            transcription.add_message("agent", str(msg), "agent_message_event")
    
    # Catch conversation events from chat context
    @session.on("chat_message")
    def on_chat_message(msg):
        print(f"\n💬 CHAT MESSAGE: {msg}")
        if hasattr(msg, 'role') and hasattr(msg, 'content'):
            transcription.add_message(msg.role, msg.content, "chat_message_event")
    
    # Debug: Print all events being fired
    original_emit = session.emit
    def debug_emit(event_name, *args, **kwargs):
        print(f"🔍 EVENT: {event_name}")
        if args:
            print(f"   Args: {args[:2]}")  # Show first 2 args only
        return original_emit(event_name, *args, **kwargs)
    
    session.emit = debug_emit

    async def log_usage():
        summary = usage_collector.get_summary()
        print(f"\n📊 USAGE SUMMARY:")
        print(f"   {summary}")
        logger.info(f"📊 Usage: {summary}")

    async def send_call_data():
        """Send call completion data to Flask webhook"""
        call_duration = int(time.time() - call_start_time)
        
        print(f"\n📞 CALL ENDED - Duration: {call_duration} seconds")
        print(f"📝 Final transcription:")
        print(f"   Messages: {len(transcription.messages)}")
        
        # Try to extract conversation from session if no messages captured
        if len(transcription.messages) == 0:
            print("⚠️ No messages captured via events, trying to extract from session...")
            try:
                # Try to access conversation history from the session
                if hasattr(session, 'conversation') and session.conversation:
                    print(f"🔍 Found conversation in session: {len(session.conversation.messages)} messages")
                    for msg in session.conversation.messages:
                        if hasattr(msg, 'role') and hasattr(msg, 'content'):
                            transcription.add_message(msg.role, msg.content, "session_conversation")
                
                # Try alternative access methods
                if hasattr(session, 'chat_ctx') and session.chat_ctx:
                    print(f"🔍 Found chat context: {session.chat_ctx}")
                    if hasattr(session.chat_ctx, 'messages'):
                        for msg in session.chat_ctx.messages:
                            if hasattr(msg, 'role') and hasattr(msg, 'content'):
                                transcription.add_message(msg.role, msg.content, "chat_context")
                                
                # Try accessing LLM directly
                if hasattr(session, 'llm') and hasattr(session.llm, 'conversation'):
                    print(f"🔍 Found LLM conversation")
                    conv = session.llm.conversation
                    if hasattr(conv, 'messages'):
                        for msg in conv.messages:
                            if hasattr(msg, 'role') and hasattr(msg, 'content'):
                                transcription.add_message(msg.role, msg.content, "llm_conversation")
                                
            except Exception as e:
                print(f"⚠️ Error extracting conversation: {e}")
        
        # Print full transcript to console
        transcription.print_full_transcript()
        
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

            print(f"🚀 Sending webhook with {len(transcription.messages)} messages...")
            logger.info(f"🚀 Sending webhook: {len(transcription.messages)} messages")

            async with aiohttp.ClientSession() as http_session:
                webhook_url = os.environ.get('FLASK_WEBHOOK_URL', 'http://localhost:5000/webhook/call-ended')
                async with http_session.post(webhook_url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        print("✅ Webhook sent successfully!")
                        logger.info(f"✅ Webhook sent!")
                    else:
                        print(f"❌ Webhook failed with status: {resp.status}")
                        logger.error(f"❌ Webhook failed: {resp.status}")
        except Exception as e:
            print(f"❌ Webhook error: {e}")
            logger.error(f"❌ Error: {e}")

    ctx.add_shutdown_callback(log_usage)
    ctx.add_shutdown_callback(send_call_data)
    
    # Enhanced periodic session monitor 
    async def monitor_session():
        message_count_cache = 0
        while True:
            await asyncio.sleep(5)  # Check every 5 seconds
            try:
                current_count = len(transcription.messages)
                print(f"\n🔍 SESSION MONITOR - Messages: {current_count} (prev: {message_count_cache})")
                
                # Try multiple ways to access conversation data
                conversation_sources = []
                
                # 1. Check session conversation
                if hasattr(session, 'conversation'):
                    conversation_sources.append(('session.conversation', session.conversation))
                
                # 2. Check session chat_ctx
                if hasattr(session, 'chat_ctx'):
                    conversation_sources.append(('session.chat_ctx', session.chat_ctx))
                    
                # 3. Check session._chat_ctx (private)
                if hasattr(session, '_chat_ctx'):
                    conversation_sources.append(('session._chat_ctx', session._chat_ctx))
                
                # 4. Check llm model's conversation
                if hasattr(session, 'llm'):
                    if hasattr(session.llm, 'conversation'):
                        conversation_sources.append(('session.llm.conversation', session.llm.conversation))
                    if hasattr(session.llm, '_conversation'):
                        conversation_sources.append(('session.llm._conversation', session.llm._conversation))
                    if hasattr(session.llm, 'sessions') and session.llm.sessions:
                        for i, rt_session in enumerate(session.llm.sessions):
                            if hasattr(rt_session, 'conversation'):
                                conversation_sources.append((f'realtime_session[{i}].conversation', rt_session.conversation))
                
                # Process each conversation source
                for source_name, conv in conversation_sources:
                    if conv and hasattr(conv, 'messages'):
                        msg_count = len(conv.messages)
                        if msg_count > 0:
                            print(f"  📚 {source_name}: {msg_count} messages")
                            for msg in conv.messages:
                                if hasattr(msg, 'role') and hasattr(msg, 'content'):
                                    # Only add if not already captured
                                    existing = any(
                                        existing_msg['text'] == msg.content and existing_msg['role'] == msg.role 
                                        for existing_msg in transcription.messages
                                    )
                                    if not existing:
                                        print(f"    🆕 New: {msg.role} - {msg.content[:50]}...")
                                        transcription.add_message(msg.role, msg.content, f"monitor_{source_name}")
                
                message_count_cache = current_count
                                
            except Exception as e:
                print(f"⚠️ Monitor error: {e}")
    
    # Start the monitor as a background task
    asyncio.create_task(monitor_session())

    # --- Start session ---
    print("🚀 Starting Agent Session...")
    await session.start(
        room=ctx.room,
        agent=Assistant(),
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVCTelephony(),
            close_on_disconnect=False,
        ),
    )
    print("✅ Agent Session started!")
    
    # Inspect session immediately after start
    print("\n🔍 INSPECTING SESSION STRUCTURE:")
    print(f"   Session type: {type(session)}")
    print(f"   Session attributes: {[attr for attr in dir(session) if not attr.startswith('_')]}")
    
    if hasattr(session, 'conversation'):
        print(f"   ✅ Has conversation: {type(session.conversation)}")
    if hasattr(session, 'chat_ctx'):
        print(f"   ✅ Has chat_ctx: {type(session.chat_ctx)}")
    if hasattr(session, 'llm'):
        print(f"   ✅ Has llm: {type(session.llm)}")
        llm_obj = session.llm
        print(f"   📋 LLM attributes: {[attr for attr in dir(llm_obj) if not attr.startswith('_')]}")
        
        if hasattr(llm_obj, 'conversation'):
            print(f"   ✅ LLM has conversation: {type(llm_obj.conversation)}")
        if hasattr(llm_obj, 'sessions'):
            print(f"   ✅ LLM has sessions: {len(llm_obj.sessions)} realtime sessions")
            for i, rt_session in enumerate(llm_obj.sessions):
                print(f"     📡 RT Session {i}: {type(rt_session)}")
                if hasattr(rt_session, 'conversation'):
                    print(f"       ✅ Has conversation: {type(rt_session.conversation)}")
                    
    # Hook into RealtimeModel sessions for direct conversation access
    if hasattr(session, 'llm') and hasattr(session.llm, 'sessions'):
        def hook_realtime_sessions():
            for rt_session in session.llm.sessions:
                if hasattr(rt_session, 'conversation'):
                    original_append = None
                    if hasattr(rt_session.conversation, 'append'):
                        original_append = rt_session.conversation.append
                        
                        def hooked_append(message):
                            print(f"🪝 CONVERSATION APPEND: {message}")
                            if hasattr(message, 'role') and hasattr(message, 'content'):
                                transcription.add_message(message.role, message.content, "realtime_conversation_hook")
                            return original_append(message)
                        
                        rt_session.conversation.append = hooked_append
                        print(f"   🪝 Hooked conversation.append for RT session")
        
        # Apply hooks after a short delay to ensure sessions are initialized
        async def delayed_hook():
            await asyncio.sleep(2)
            hook_realtime_sessions()
        
        asyncio.create_task(delayed_hook())

    # --- Connect room ---
    print("🔗 Connecting to room...")
    await ctx.connect()
    print("✅ Connected to room!")

    # --- Initial greeting ---
    if ctx.room.num_participants == 0:
        print("🎤 Generating initial greeting...")
        logger.info("🎤 Generating greeting...")
        await session.generate_reply(
            instructions="قل مرحباً وعرف نفسك كمساعد ذكي"
        )
        print("✅ Initial greeting sent!")
    
    print("\n🎧 AGENT IS NOW ACTIVE - Listening for user input...")
    print("=" * 60)


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🚀 STARTING LIVEKIT AGENT")
    print("=" * 60)
    print("📋 Configuration:")
    print(f"   - Language: Arabic")
    print(f"   - TTS: ElevenLabs")
    print(f"   - LLM: OpenAI GPT-4o Realtime")
    print(f"   - Transcription: Whisper")
    print("=" * 60)
    
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))