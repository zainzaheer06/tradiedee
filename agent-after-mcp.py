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
from livekit.plugins import noise_cancellation, openai, elevenlabs, google
from livekit.plugins.openai.realtime import RealtimeModel
from openai.types.beta.realtime.session import InputAudioTranscription, TurnDetection

# Import knowledge base service for RAG (imports trigger pre-loading)
from services.knowledge_base_service import kb_service

# Import recording service
from services.recording_service import recording_service

# Import tool service for dynamic tools
from services.tool_service import tool_service

# MCP Client for n8n integration
from mcp_client import MCPServerSse
from mcp_client.agent_tools import MCPToolsIntegration

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

أنت مساعد طبي ذكي متخصص في حجز المواعيد الطبية في العيادة.

## هويتك ومهامك:
- اسمك: مساعد العيادة الذكي
- تتحدث العربية فقط (اللهجة السعودية/الخليجية)
- مهمتك الأساسية: مساعدة المرضى في حجز وإدارة مواعيدهم الطبية
- تتعامل مع جميع الاستفسارات بلطف واحترافية

## الأدوات المتاحة لديك:
لديك 5 أدوات لإدارة المواعيد:
1. **get_available_slots**: البحث عن المواعيد المتاحة
2. **book_appointment**: حجز موعد جديد
3. **check_booking**: التحقق من حالة الحجز
4. **cancel_booking**: إلغاء موعد محجوز
5. **list_doctors**: عرض قائمة الأطباء المتاحين

## خطوات حجز الموعد:
عند طلب حجز موعد، اتبع هذه الخطوات بالترتيب:

### الخطوة 1: فهم احتياج المريض
- اسأل عن نوع التخصص المطلوب (طبيب عام، طبيب أسنان، طبيب أطفال)
- اسأل عن التاريخ المفضل (إذا لم يحدد المريض)

### الخطوة 2: البحث عن المواعيد المتاحة
- استخدم أداة `get_available_slots` للبحث
- اعرض الخيارات المتاحة بوضوح
- اذكر اسم الطبيب والتاريخ والوقت

### الخطوة 3: جمع معلومات المريض
اطلب المعلومات التالية خطوة بخطوة:
1. الاسم الكامل
2. رقم الهاتف (تأكد من الصيغة: +966XXXXXXXXX)
3. تأكيد الموعد المختار

### الخطوة 4: تأكيد الحجز
- أكد جميع التفاصيل مع المريض
- استخدم أداة `book_appointment` لإتمام الحجز
- قدم رقم الحجز للمريض
- ذكّر المريض بالوصول قبل 15 دقيقة

## أسلوب المحادثة:

### النبرة والأسلوب:
- تحدث بلطف واحترافية
- استخدم اللهجة السعودية/الخليجية الطبيعية
- كن واضحاً ومباشراً
- لا تستخدم مصطلحات طبية معقدة

### أمثلة على العبارات:
- الترحيب: "أهلاً وسهلاً، كيف أقدر أساعدك اليوم؟"
- طلب معلومات: "ممكن تعطيني اسمك الكامل؟"
- تأكيد الحجز: "تمام، حجزت لك موعد مع د. [اسم] يوم [التاريخ] الساعة [الوقت]"
- رقم الحجز: "رقم حجزك هو [الرقم]، احتفظ فيه للمراجعة"

### التعامل مع المواقف:

**إذا لم تتوفر مواعيد:**
"للأسف، ما في مواعيد متاحة في هذا التاريخ. تبي أبحث لك في تاريخ ثاني؟"

**إذا نسي المريض معلوماته:**
"لا تشيل هم، ممكن تعطيني رقم جوالك وأتحقق من الحجز؟"

**إذا أراد المريض الإلغاء:**
"ماشي، بس تأكد لي رقم الحجز عشان ألغيه لك"

## التفاصيل المهمة:

### التخصصات الطبية المتاحة:
- طبيب عام
- طبيب أسنان
- طبيب أطفال

### صيغة رقم الهاتف:
- يجب أن يبدأ بـ +966
- متبوع بـ 9 أرقام
- مثال: +966501234567

### المواعيد:
- أوقات العمل: من 8:00 صباحاً إلى 3:00 عصراً
- أيام العمل: الأحد إلى الخميس
- كل موعد مدته 30 دقيقة

## قواعد مهمة:

### ✅ افعل:
- استخدم الأدوات المتاحة لك في كل مرة تحتاجها
- تأكد من جميع المعلومات قبل الحجز
- كن صبوراً ومتفهماً
- كرر المعلومات للتأكيد
- قدم رقم الحجز بوضوح

### ❌ لا تفعل:
- لا تخترع مواعيد غير موجودة
- لا تحجز بدون تأكيد جميع المعلومات
- لا تستخدم اللغة الإنجليزية إطلاقاً
- لا تعطي نصائح طبية
- لا تفصح عن معلومات مرضى آخرين

## أمثلة على المحادثات:

### مثال 1: حجز موعد عادي
مريض: "أبغى أحجز موعد عند طبيب أسنان"
أنت: [تستخدم get_available_slots] "أكيد! لدينا مواعيد متاحة مع د. فاطمة علي. عندنا يوم الإثنين الساعة 10 صباحاً أو الثلاثاء الساعة 2 عصراً. أي وقت يناسبك؟"
مريض: "الإثنين الساعة 10"
أنت: "تمام! ممكن تعطيني اسمك الكامل؟"
مريض: "محمد أحمد"
أنت: "طيب يا محمد، ممكن رقم جوالك؟"
مريض: "0501234567"
أنت: "ممتاز، يعني الموعد بيكون يوم الإثنين 23 ديسمبر الساعة 10 صباحاً مع د. فاطمة علي. صح كذا؟"
مريض: "نعم"
أنت: [تستخدم book_appointment] "تم الحجز بنجاح! رقم حجزك هو BK002. رجاءً احضر قبل 15 دقيقة من موعدك."

### مثال 2: التحقق من حجز موجود
مريض: "أبغى أتأكد من موعدي"
أنت: "أكيد، معك رقم الحجز؟"
مريض: "BK001"
أنت: [تستخدم check_booking] "موعدك مؤكد مع د. أحمد محمد يوم الإثنين 23 ديسمبر الساعة 11 صباحاً. في شي تبغى تغيره؟"

### مثال 3: إلغاء موعد
مريض: "أبغى ألغي موعدي"
أنت: "ماشي، ممكن تعطيني رقم الحجز؟"
مريض: "BK002"
أنت: [تستخدم cancel_booking] "تم إلغاء الحجز بنجاح. إذا احتجت تحجز موعد جديد، أنا جاهز أساعدك."

## ملاحظات نهائية:
- كن طبيعياً في الحوار
- استمع جيداً للمريض
- تأكد من فهم الطلب قبل استخدام الأدوات
- إذا لم تفهم، اطلب التوضيح
- احتفظ بالاحترافية دائماً

تذكر: أنت هنا لتسهيل عملية حجز المواعيد وجعلها تجربة سلسة ومريحة للمرضى. 

استجب بإجابات قصيرة ومباشرة بدون رموز معقدة أو رموز تعبيرية.
[رد فقط باللغة العربية]""",
        'greeting': 'السلام عليكم ورحمة الله وبركاته، أهلاً وسهلاً فيك. أنا مساعدك الذكي، كيف أقدر أساعدك اليوم؟',
        'voice_id': 'KjDucWgG5NYuMBznv52L',
        'voice_name': 'Ali'
    }


# --- Transcription Manager ---
class TranscriptionManager:
    def __init__(self):
        self.messages = []
        self.start_time = datetime.now().isoformat()
        self.seen_messages = set()  # Track unique messages to avoid duplicates
        self.sip_info = {}  # Store SIP participant information
        self.recording_id = None  # Store LiveKit recording/egress ID
        self.greeting_added = False  # FIXED: Track if greeting was already added

    def add_message(self, role: str, text: str, source: str = ""):
        """Add a message with deduplication"""
        if not isinstance(text, str) or not text.strip():
            return

        # Create unique key for deduplication
        msg_key = f"{role}:{text.strip()}"
        if msg_key in self.seen_messages:
            logger.debug(f"⏭️  Skipping duplicate message from {source}")
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
    # System instructions - Add your custom rules here
    system_instructions = """
You are a polite and helpful Saudi Arabic voice assistant.

# DIALECT & STYLE
- Use a natural, polite Saudi dialect suitable for all age groups.
- Avoid heavy slang unless the user requests it.
- Keep a balance between Saudi dialect and simple Modern Standard Arabic, especially in official/government topics.
- Do not respond in JSON, markup,technical responses.

# RESPONSE BEHAVIOR
- Replies must be short, clear, and spoken naturally (1-2 sentences, max 150 characters).
- Always respond in Arabic only.
- Do NOT output JSON, code, or technical formatting.
- Ask for the user's name politely when appropriate.
- Never repeat previous responses.
- Keep every response directly relevant to the user's question.

# GUARDRAILS
## NEVER EVER speak these things out loud:
- Function names like "end_call", "detected_answering_machine"
- Function parameters like {query: ...}, {name: ...}
- JSON structures like {"key": "value"}
- Technical formatting or markup
- Code or system messages

# CULTURAL RULES
- Respect Saudi culture, values, and etiquette.
- Avoid political, religious, tribal, or sensitive discussions.
- Do not give fatwas; instead, redirect politely to official sources.
- Use commonly accepted Saudi expressions when suitable:
  هلا، هلا والله، حيّاك الله، تفضل، أبشر، ولا يهمك، تمام، حاضر، وش تبغى، وش تحتاج، يعطيك العافية، الله يسعدك، ممتاز، بسيطة، لا تشيل هم.

# DIALECT HANDLING
- Default: neutral Saudi dialect (Najdi/Hijazi).
- If the user speaks in a specific dialect, naturally mirror it without exaggeration.

# HANDLING VOICEMAIL
- If you detect an answering machine or voicemail greeting, wait until it finishes.
- Then leave a polite voicemail message in ARABIC letting the user know you'll call back later. 
- detected_answering_machine tool is available for this purpose.
- don't respond in that way; {"name": "detected_answering_machine"}

# GREETING RULES
- Greeting is handled separately by another system.
- If user says: "عليكم السلام ورحمة الله وبركاته", DO NOT repeat "وعليكم السلام".
- Never generate greeting lines that conflict with the greeting system.

# END-OF-CALL LOGIC
If the user indicates they want to end the interaction (e.g., "وداعاً", "مع السلامة", "باي", "شكراً ما أحتاج"):
→ Immediately trigger end_call (no extra goodbye).

# IDENTITY RULES
- Never mention OpenAI, models, or technical systems.
- Always say you are built by Nevox AI when identity is requested.
- If the user speaks another language, politely explain that support is limited to Arabic only.
- No JSON, no markup, no technical responses.

# AVOID
- Off-topic answers.
- Long explanations.
- Any formatting besides normal Arabic speech.
- Incorrect or speculative information about Saudi regulations or entities.

# OUTPUT REQUIREMENTS (CRITICAL)
- Arabic only.
- 1-2 sentences max.
- Under 150 characters.
- Spoken-style, clean, natural, human-like.
- No JSON, no markup, no technical responses.


"""

    # Combine: system instructions + user's custom prompt
    full_prompt = system_instructions + user_prompt

    return full_prompt

class Assistant(Agent):
    def __init__(self, config: dict = None, agent_id: int = None, preloaded_tools: list = None, mcp_servers: list = None) -> None:
        if config is None:
            config = get_default_config()

        # Build full prompt: system instructions + user's custom prompt
        full_prompt = build_full_prompt(config['prompt'])
        
        # Prepare dynamic tools
        all_tools = []
        if preloaded_tools is not None:
            all_tools.extend(preloaded_tools)
        else:
            if agent_id:
                try:
                    dynamic_tools = tool_service.create_function_tools(agent_id)
                    all_tools.extend(dynamic_tools)
                    logger.info(f"📦 Loaded {len(dynamic_tools)} custom tools for agent {agent_id}")
                except Exception as e:
                    logger.error(f"❌ Error loading custom tools: {e}")

        # Pass MCP servers directly to Agent superclass
        super().__init__(
            instructions=full_prompt,
            tools=all_tools,
            mcp_servers=mcp_servers if mcp_servers else [],  # Pass MCP servers here!
        )

        self.config = config
        mcp_info = f" + {len(mcp_servers)} MCP servers" if mcp_servers else ""
        logger.info(f"✅ Assistant initialized: {config['name']} (Voice: {config['voice_name']}) with {len(all_tools)} tools{mcp_info}")
        logger.debug(f"📝 Full prompt length: {len(full_prompt)} characters")
    '''
    async def llm_node(self, chat_ctx, tools, model_settings):
        """Override the llm_node to say a message when a tool call is detected."""
        activity = self._activity
        tool_call_detected = False

        # Get the original response from the parent class
        async for chunk in super().llm_node(chat_ctx, tools, model_settings):
            # Check if this chunk contains a tool call
            if isinstance(chunk, ChatChunk) and chunk.delta and chunk.delta.tool_calls and not tool_call_detected:
                # Check if any of the tool calls are end_call - if so, don't say the checking message
                is_end_call = any(
                    hasattr(tool_call, 'function') and 
                    hasattr(tool_call.function, 'name') and 
                    tool_call.function.name == 'end_call'
                    for tool_call in chunk.delta.tool_calls
                )
                
                if not is_end_call:
                    # Say the checking message only once when we detect the first tool call (excluding end_call)
                    tool_call_detected = True
                    activity.agent.say("Sure, I'll check that for you.")
                else:
                    tool_call_detected = True

            yield chunk
    '''

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
    async def detected_answering_machine(self):
        """Call this tool if you have detected a voicemail system, AFTER hearing the voicemail greeting"""
        await self.session.generate_reply(
            instructions="اترك رسالة صوتية تخبر المستخدم بأنك ستعاود الاتصال لاحقاً."
        )
        await asyncio.sleep(0.5) # Add a natural gap to the end of the voicemail message
        await hangup_call()

async def entrypoint(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}
    
    logger.info(f"🎯 Room: {ctx.room.name}")
    logger.info(f"📊 Initial participants: {ctx.room.num_participants}")

    # Connect to room
    await ctx.connect()
    call_start_time = time.time()

    # Check if campaign call
    agent_config = None
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
                    logger.info(f"✅ Using campaign agent: {agent_config['name']}")
        except Exception as e:
            logger.error(f"❌ Error parsing campaign metadata: {e}")

    # Extract agent_id from room name if not campaign
    if not agent_config:
        agent_config = get_default_config()
        try:
            room_parts = ctx.room.name.split('-')
            if len(room_parts) >= 2 and room_parts[0] == 'call':
                agent_id = int(room_parts[1])
                fetched_config = get_agent_config(agent_id)
                if fetched_config:
                    agent_config = fetched_config
                    logger.info(f"✅ Loaded agent: {agent_config['name']}")
        except Exception as e:
            logger.error(f"❌ Error parsing agent ID: {e}")

    # Initialize transcription
    transcription = TranscriptionManager()

    # ===== OPTIMIZATION 1: Pre-load KB context and tools in parallel =====
    agent_id = agent_config.get('id')
    
    kb_task = None
    if agent_id and agent_id in kb_service._index_cache:
        logger.info(f"📚 Loading KB context for agent {agent_id}...")
        kb_task = asyncio.create_task(kb_service.retrieve_context(
            agent_id,
            query="معلومات عامة عن الشركة والخدمات",
            top_k=10
        ))
    
    # Load tools (cached, very fast)
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

    # ===== OPTIMIZATION 2: Initialize models in parallel =====
    logger.info("🚀 Initializing models in parallel...")
    
    async def init_tts():
        return elevenlabs.TTS(
            voice_id=agent_config['voice_id'],
            model="eleven_turbo_v2_5",
            language="ar",
            auto_mode=True,
            voice_settings=elevenlabs.VoiceSettings(
                stability=0.75,
                similarity_boost=0.5,
                style=0.0,
                speed=0.91,
                use_speaker_boost=True
            ),
            streaming_latency=0,  # Maximum speed
            inactivity_timeout=60,
            enable_ssml_parsing=False,
            apply_text_normalization="auto"
        )
    
    async def init_stt():
        return google.STT(
            languages=["ar-SA"],
            model="latest_long",
            spoken_punctuation=False,
            punctuate=True,
            interim_results=True,
            detect_language=False,
            sample_rate=16000,
            credentials_file="config/google/aimeetingassistant-448613-1ff1fc705734.json",
        )
    
    async def init_llm():
        return RealtimeModel(
            model="gpt-4o-realtime-preview",
            modalities=["text"],
            temperature=0.4,
            input_audio_transcription=InputAudioTranscription(
                model="whisper-1",
                language="ar"
            ),
            turn_detection=TurnDetection(
                type="server_vad",
                threshold=0.45,
                prefix_padding_ms=150,
                silence_duration_ms=250,
                create_response=True,
                interrupt_response=True,
            ),
        )
    
    # Run all initializations in parallel
    tts_engine, stt_engine_google, llm_model_realtime = await asyncio.gather(
        init_tts(),
        init_stt(),
        init_llm()
    )
    
    logger.info("✅ All models initialized!")

    # Create session
    session = voice.AgentSession(
        llm=llm_model_realtime,
        tts=tts_engine,
        stt=stt_engine_google,
        user_away_timeout=float(os.environ.get('USER_AWAY_TIMEOUT', '60.0'))
    )

    # ===== [Keep all your event handlers here - lines 472-751] =====
    usage_collector = metrics.UsageCollector()
    
    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    inactivity_task: asyncio.Task | None = None
    call_ended: bool = False

    async def user_presence_check():
        try:
            logger.warning("⏰ User marked as away, checking presence...")
            await session.generate_reply(
                instructions="المستخدم غير نشط. اسأله بلطف إذا كان لا يزال موجودًا"
            )
            await asyncio.sleep(10)
            logger.warning("⏰ User still inactive after presence check. Ending call...")
            await session.generate_reply(
                instructions="قل للمستخدم: يبدو أنك لم تعد هناك. سأنهي المكالمة الآن. مع السلامة"
            )
            await asyncio.sleep(3)
            await hangup_call()
        except Exception as e:
            logger.error(f"Error in presence check: {e}")

    @session.on("user_state_changed")
    def _user_state_changed(ev: UserStateChangedEvent):
        nonlocal inactivity_task, call_ended
        logger.info(f"🔄 User state changed: {ev.new_state}")
        
        if call_ended:
            logger.debug(f"⏭️ Ignoring user state change (call already ended)")
            return

        if ev.new_state == "away":
            logger.warning(f"⚠️ User away after {os.environ.get('USER_AWAY_TIMEOUT', '60')}s inactivity")
            inactivity_task = asyncio.create_task(user_presence_check())
            return

        if inactivity_task is not None and not inactivity_task.done():
            logger.info("✅ User active again, cancelling presence check")
            inactivity_task.cancel()
            inactivity_task = None

    # Transcription handlers
    last_user_msg_committed = None
    last_agent_msg_committed = None

    @session.on("user_speech_committed")
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

    @session.on("agent_speech_committed")
    def on_agent_speech_committed(msg: llm.ChatMessage):
        nonlocal last_agent_msg_committed
        try:
            text = msg.content if isinstance(msg.content, str) else str(msg.content)
            text = text.strip()
            if text and text != last_agent_msg_committed:
                if transcription.greeting_added and text == agent_config.get('greeting'):
                    logger.debug("⏭️  Skipping greeting (already added manually)")
                    return
                last_agent_msg_committed = text
                transcription.add_agent_message(text, "agent_speech_committed")
        except Exception as e:
            logger.error(f"❌ Error capturing agent speech: {e}")

    last_user_msg = None

    @session.on("user_transcript")
    def on_user_transcript(transcript):
        nonlocal last_user_msg
        try:
            if hasattr(transcript, 'text'):
                text = transcript.text.strip()
            elif hasattr(transcript, 'transcript'):
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
                    if hasattr(session, 'chat_ctx') and session.chat_ctx:
                        messages = session.chat_ctx.messages
                        if len(messages) > last_msg_count:
                            new_messages = messages[last_msg_count:]
                            for msg in new_messages:
                                role = msg.role
                                content = msg.content
                                if isinstance(content, str):
                                    text = content.strip()
                                elif isinstance(content, list):
                                    text = ' '.join([
                                        str(part.text) if hasattr(part, 'text') else str(part)
                                        for part in content
                                    ]).strip()
                                else:
                                    text = str(content).strip()
                                if text:
                                    if role == 'user':
                                        transcription.add_user_message(text, "chat_context_monitor")
                                    elif role == 'assistant':
                                        if transcription.greeting_added and text == agent_config.get('greeting'):
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

    conversation_monitor_task = asyncio.create_task(monitor_conversation())

    async def cleanup_monitor():
        if conversation_monitor_task and not conversation_monitor_task.done():
            conversation_monitor_task.cancel()
            try:
                await conversation_monitor_task
            except asyncio.CancelledError:
                pass

    ctx.add_shutdown_callback(cleanup_monitor)

    @session.on("user_message")
    def on_user_message(msg):
        try:
            if hasattr(msg, 'content'):
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                transcription.add_user_message(content, "user_message_event")
        except:
            pass

    @session.on("agent_message")
    def on_agent_message(msg):
        try:
            if hasattr(msg, 'content'):
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                if transcription.greeting_added and content == agent_config.get('greeting'):
                    return
                transcription.add_agent_message(content, "agent_message_event")
        except:
            pass

    @session.on("agent_transcript")
    def on_agent_transcript(transcript):
        try:
            text = str(transcript)
            if transcription.greeting_added and text == agent_config.get('greeting'):
                return
            transcription.add_agent_message(text, "agent_transcript_event")
        except:
            pass

    @session.on("conversation_item_added")
    def on_conversation_item_added(event):
        try:
            if hasattr(event, 'item'):
                item = event.item
                if hasattr(item, 'role') and hasattr(item, 'content'):
                    content = ' '.join(item.content) if isinstance(item.content, list) else str(item.content)
                    if item.role == 'assistant' and transcription.greeting_added and content == agent_config.get('greeting'):
                        return
                    transcription.add_message(item.role, content, "conversation_item")
        except Exception as e:
            logger.debug(f"Error in conversation_item_added: {e}")

    @session.on("chat_message")
    def on_chat_message(msg):
        try:
            if hasattr(msg, 'role') and hasattr(msg, 'content'):
                content = msg.content
                if msg.role == 'assistant' and transcription.greeting_added and content == agent_config.get('greeting'):
                    return
                transcription.add_message(msg.role, content, "chat_message_event")
        except:
            pass

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"📊 Usage: {summary}")

    async def send_call_data():
        call_duration = int(time.time() - call_start_time)
        logger.info(f"📝 Preparing transcription data...")
        logger.info(f"   Messages captured: {len(transcription.messages)}")
        logger.info(f"   Duration: {call_duration}s")

        if len(transcription.messages) <= 1:
            logger.warning("⚠️ Very few messages captured! Attempting final extraction...")
            try:
                if hasattr(session, 'chat_ctx') and session.chat_ctx:
                    messages = session.chat_ctx.messages
                    logger.info(f"   Found {len(messages)} messages in chat_ctx")
                    for msg in messages:
                        role = msg.role
                        content = msg.content
                        if isinstance(content, str):
                            text = content.strip()
                        elif isinstance(content, list):
                            text = ' '.join([
                                str(part.text) if hasattr(part, 'text') else str(part)
                                for part in content
                            ]).strip()
                        else:
                            text = str(content).strip()
                        if text:
                            if role == 'assistant' and transcription.greeting_added and text == agent_config.get('greeting'):
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
                'room_name': ctx.room.name,
                'duration': call_duration,
                'transcription': transcription.get_plain_text(),
                'metadata': transcription.get_json(),
                'message_count': len(transcription.messages)
            }
            logger.info(f"🚀 Sending webhook: {len(transcription.messages)} messages, {call_duration}s duration")
            async with aiohttp.ClientSession() as http_session:
                webhook_url = os.environ.get('FLASK_WEBHOOK_URL', 'http://localhost:5002/webhook/call-ended')
                async with http_session.post(webhook_url, json=payload, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status == 200:
                        response_text = await resp.text()
                        logger.info(f"✅ Webhook delivered successfully!")
                        logger.info(f"   Response: {response_text[:200]}")
                    else:
                        logger.error(f"❌ Webhook failed with status: {resp.status}")
        except Exception as e:
            logger.error(f"❌ Failed to send call data: {e}")

    ctx.add_shutdown_callback(log_usage)
    ctx.add_shutdown_callback(send_call_data)

    monitor_task = None

    async def monitor_session():
        try:
            while True:
                await asyncio.sleep(10)
                try:
                    if hasattr(session, 'llm'):
                        llm_obj = session.llm
                        if hasattr(llm_obj, 'sessions'):
                            for rt_session in llm_obj.sessions:
                                if hasattr(rt_session, 'conversation') and hasattr(rt_session.conversation, 'messages'):
                                    for msg in rt_session.conversation.messages:
                                        if hasattr(msg, 'role') and hasattr(msg, 'content'):
                                            if msg.role == 'assistant' and transcription.greeting_added and msg.content == agent_config.get('greeting'):
                                                continue
                                            transcription.add_message(msg.role, msg.content, "monitor_realtime")
                    if hasattr(session, 'chat_ctx') and hasattr(session.chat_ctx, 'messages'):
                        for msg in session.chat_ctx.messages:
                            if hasattr(msg, 'role') and hasattr(msg, 'content'):
                                if msg.role == 'assistant' and transcription.greeting_added and msg.content == agent_config.get('greeting'):
                                    continue
                                transcription.add_message(msg.role, msg.content, "monitor_chat_ctx")
                except Exception as e:
                    logger.debug(f"Monitor error: {e}")
        except asyncio.CancelledError:
            logger.debug("Monitor task cancelled (expected on call end)")

    # ===== START SESSION =====
    logger.info(f"🚀 Starting session with agent: {agent_config['name']}")

    # Define MCP server with SSE transport (better for HTTP-based n8n MCP server)
    mcp_server = MCPServerSse(
        params={"url": os.environ.get("N8N_MCP_SERVER_URL", "https://workflows.nevoxai.com/webhook/mcp/excel-reader")},
        cache_tools_list=True,
        name="n8n MCP Server"
    )

    # Create a base assistant instance to pass to MCPToolsIntegration
    base_assistant = Assistant(
        config=agent_config,
        agent_id=agent_id,
        preloaded_tools=dynamic_tools,
        mcp_servers=[]  # Don't pass MCP servers here - will be added by MCPToolsIntegration
    )

    # Wrap the assistant with MCP tools integration
    agent_with_mcp = await MCPToolsIntegration.create_agent_with_tools(
        agent_class=lambda: base_assistant,
        mcp_servers=[mcp_server],
    )

    await session.start(
        room=ctx.room,
        agent=agent_with_mcp,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVCTelephony(),
        ),
    )

    # Start monitors
    monitor_task = asyncio.create_task(monitor_session())
    
    # ===== OPTIMIZATION 3: Wait for participant AFTER session start =====
    logger.info("⏳ Waiting for participant...")
    if not ctx.room.name.startswith('campaign_'):
        participant = await ctx.wait_for_participant()
    
    transcription.set_sip_info(participant)
    logger.info(f"✅ Participant joined: {participant.identity} (Kind: {participant.kind})")

    # ===== OPTIMIZATION 4: Quick audio track check (reduced timeout) =====
    if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
        logger.info("⏳ Quick audio track check...")
        try:
            timeout = 1.5  # Reduced from 5s → 1.5s
            start_wait = time.time()
            while time.time() - start_wait < timeout:
                audio_tracks = [
                    track for track in participant.track_publications.values()
                    if track.kind == rtc.TrackKind.KIND_AUDIO
                ]
                if audio_tracks:
                    elapsed = time.time() - start_wait
                    logger.info(f"✅ Audio track ready in {elapsed:.2f}s")
                    break
                await asyncio.sleep(0.1)  # Faster polling
        except Exception as e:
            logger.debug(f"Audio track check: {e}")

    # ===== OPTIMIZATION 5: Start recording in background (NON-BLOCKING!) =====
    async def start_recording_background():
        """Start recording without blocking greeting"""
        try:
            logger.info("🎙️ Starting recording (background)...")
            recording_id = await recording_service.start_recording(ctx.room.name)
            if recording_id:
                transcription.recording_id = recording_id
                logger.info(f"✅ Recording started: {recording_id}")
            else:
                logger.warning("⚠️ Recording failed")
        except Exception as e:
            logger.error(f"❌ Recording error: {e}")
    
    # Start recording in background - DON'T WAIT FOR IT!
    asyncio.create_task(start_recording_background())

    # ===== Participant disconnect handler =====
    @ctx.room.on("participant_disconnected")
    def on_participant_disconnected(participant: rtc.RemoteParticipant):
        nonlocal inactivity_task, monitor_task, call_ended
        if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
            logger.info(f"📴 SIP participant disconnected: {participant.identity}")
            call_ended = True
            if inactivity_task and not inactivity_task.done():
                logger.info("✅ Cancelling inactivity timer (call ended)")
                inactivity_task.cancel()
            if monitor_task and not monitor_task.done():
                logger.debug("✅ Cancelling monitor task (call ended)")
                monitor_task.cancel()
            asyncio.create_task(hangup_call())

    # ===== OPTIMIZATION 6: IMMEDIATE GREETING (no sleeps!) =====
    logger.info("🎤 Sending greeting IMMEDIATELY...")
    greeting_message = agent_config.get('greeting', 'السلام عليكم ورحمة الله وبركاته')
    
    # Add to transcription first
    transcription.add_agent_message(greeting_message, "initial_greeting")
    transcription.greeting_added = True
    logger.info("✅ Greeting added to transcription")
    
    # Send greeting immediately - no sleeps!
    await session.say(greeting_message, allow_interruptions=True)
    logger.info("✅ Greeting sent!")

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