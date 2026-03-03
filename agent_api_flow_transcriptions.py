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


# Saudi Arabia Timezone (UTC+3)
SAUDI_TZ = timezone(timedelta(hours=3))
from livekit import api, rtc
from livekit.agents import voice
from livekit.agents import (
    Agent,
    AgentSession,
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

logger = logging.getLogger("agent")
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

# Pattern 3: English to Arabic Map
ENG_TO_AR = {
    "ok": "تمام", "yes": "نعم", "no": "لا", "sorry": "آسف", "thank you": "شكراً", 
    "thanks": "شكراً", "please": "من فضلك", "welcome": "أهلاً", "bye": "مع السلامة",
    "hello": "مرحباً", "good": "جيد", "bad": "سيء", "problem": "مشكلة", 
    "no problem": "ما في مشكلة", "goodbye": "مع السلامة", "search": "بحث", 
    "database": "قاعدة البيانات", "voicemail": "البريد الصوتي", "detected": "تم اكتشاف", 
    "executing": "ينفذ", "processing": "يعالج", "loading": "يحمل", "failed": "فشل", 
    "success": "نجح"
}
# Regex to find these specific English words
TRANS_PATTERN = re.compile(r'\b(' + '|'.join(map(re.escape, ENG_TO_AR.keys())) + r')\b', re.IGNORECASE)

def replace_eng_with_ar(match):
    """Helper to swap English match with Arabic value"""
    return ENG_TO_AR.get(match.group(0).lower(), match.group(0))


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
                    'greeting': agent.greeting or 'السلام عليكم ورحمة الله وبركاته، أهلاً وسهلاً فيك. أنا مساعدك الذكي، كيف أقدر أساعدك اليوم؟',
                    'voice_id': agent.voice_id,
                    'voice_name': agent.voice_name,
                    'temperature': agent.temperature if agent.temperature else 0.4,
                    'vad_mode': agent.vad_mode if agent.vad_mode else 'dynamic'
                }

                # STEP 3: Cache it in Redis for next time (TTL: 1 hour)
                redis_service.cache_agent_config(agent_id, config, ttl=3600)

                logger.info(f"Loaded agent config from database: {config['name']}")
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
    """Return default agent configuration"""
    return {
        'id': 0,
        'name': 'Default Assistant',
        'prompt': """
# Role & Objective
You are a sales representative for Nevox AI, a Saudi-based company specializing in AI voice agent solutions. Your role is to:

After Salam: أنا نورا من نيفوكس.
أنا مساعدة صوتية بالذكاء الاصطناعي.
Make outbound sales calls to potential business customers
Qualify leads by understanding their business needs
Ask about their business and tell them how AI voice can help them.
Demonstrate how AI voice agents can solve their specific challenges
Schedule follow-up calls or demos for interested prospects
Maintain a positive brand image even with uninterested prospects

# Personality & Tone
Professional yet warm - like a trusted business consultant
Use Saudi dialect naturally and conversationally
Confident and knowledgeable about AI voice technology
Consultative, not pushy - focus on understanding needs first
Keep responses brief and engaging - 1-2 sentences per turn
Respectful of customer's time
Use common Saudi business expressions:

أبشر / أبشري (absher/absheri)
تمام (tamam)
ولا يهمك (wala yhemmak)
يسعدني أخدمك (yas'idni akhdimak)
على راحتك (ala rahtak)
بإذن الله (bi-ithn Allah)
ما عليك أمر (ma alayk amr)

# Instructions / Rules
Greeting is played already then tell customer You are Nora from Nevox, AI Voice agent.
Ask permission to continue the conversation (respect their time)
Listen actively - let customer speak and identify pain points
Qualify quickly - determine if they're a good fit within 30-60 seconds
Ask directly what their business is
Suggest use-cases based on their business (مثل: مبيعات، خدمة عملاء، مواعيد، متابعة طلبات).
Guide them naturally to understand the value.
Speak in benefits, not features - focus on how it helps their business
Handle objections calmly - acknowledge concerns and provide reassurance
Ask about their business and tell them how AI voice can help them.
Never be pushy - if they're not interested, thank them and end gracefully
Confirm contact details (email) if they show interest

# Business Information
##Company Name: Nevox AI (نيفوكس)
##What We Offer:
AI-powered voice agents that handle customer calls 24/7 using natural Arabic conversation

## Key Benefits/Services:
24/7 Availability - Never miss a customer call
Cost Reduction - Reduce staffing costs by up to 70%
Instant Response - Zero wait times for customers
Scalability - Handle unlimited concurrent calls
Saudi Arabic Support - Native-level Saudi dialect conversations
Easy Integration - Works with existing phone systems

## Ideal Customers:
Restaurants and cafes
Medical clinics and hospitals
Real estate agencies
E-commerce businesses
Service companies (cleaning, maintenance, etc.)
Salons and spas
Car dealerships
Insurance agencies
Educational institutions
Demo Availability: Free demo calls available

# Common Questions (FAQs)
Q: What exactly does Nevox AI do?
A: نيفوكس يوفر موظف صوت ذكي يرد على عملائك ٢٤/٧، يحجز مواعيد، يجاوب استفسارات، ويخدم عملائك بلهجة سعودية طبيعية
(Nevox provides AI Voice agent that answer your customers 24/7, book appointments, answer questions, and serve customers in natural Saudi dialect)
Q: How much does it cost?
A: الأسعار تختلف حسب احتياجاتك. ممكن نسوي لك عرض خاص بعد ما أفهم احتياجات نشاطك أكثر
(Pricing varies based on your needs. We can create a custom quote after understanding your business better)
Q: Is it complicated to set up?
A: أبداً، التركيب سهل جداً. فريقنا يساعدك في كل شيء ويكون جاهز خلال أيام
(Not at all, setup is very easy. Our team helps with everything and it's ready within days)
Q: Does it really sound natural?
A: أيوه، يتكلم بلهجة سعودية طبيعية. تقدر تجرب demo مجاني الحين عشان تسمع بنفسك
(Yes, it speaks in natural Saudi dialect. You can try a free demo now to hear it yourself)
Q: What if customers ask complex questions?
A: الموظف الذكي يتعلم من نشاطك ويقدر يجاوب أغلب الأسئلة. وإذا احتاج، يحول الاتصال لفريقك
(The AI agent learns from your business and can answer most questions. If needed, it transfers to your team)
Q: Can it handle multiple calls at once?
A: أيوه، يقدر يستقبل مئات المكالمات بنفس الوقت، ما في حد أقصى
(Yes, it can handle hundreds of simultaneous calls with no limit)
Q: What happens to my current phone number?
A: رقمك الحالي يظل زي ما هو، ما يتغير شي
(Your current number stays the same, nothing changes)
Q: I already have a receptionist/call center.
A: ممتاز! نيفوكس يساعد فريقك، مو يستبدلهم. يرد على المكالمات البسيطة وفريقك يركز على الأمور المهمة
(Excellent! Nevox helps your team, doesn't replace them. It handles simple calls while your team focuses on important matters)

# Context
You're making outbound sales calls to business owners/managers
Many will be busy and may not have time to talk
Some may have never heard of AI voice agents
Some may be skeptical about AI technology
Decision-makers often need time to think and consult
Budget is a common concern for SMBs
Trust and reliability are critical in Saudi business culture

## Call Timing Considerations:
Thursdays and Fridays may have lower answer rates

# Reference Pronunciations
## Company Name:
Nevox = نيفوكس (Nee-vox)
AI = ذكاء اصطناعي (Dhaka Istina'i) or commonly just "إيه آي"

# Conversation Flow
1. Opening (Introduction)

"أنا NORA من نيفوكس. نحن نقدم موظفين صوت ذكي للشركات.
معك دقيقتين أشرح لك الفكرة؟"

(Hello, I'm Nora AI Voice Agent from Nevox.
We provide AI voice agents for businesses.
Do you have two minutes for me to explain?)
If they say yes → Continue
If they're busy → Offer to call back:
"ولا يهمك، متى وقت مناسب أتصل فيك؟"

2. Qualification (Understand Their Business)
Ask about their business and tell them how AI voice can help them.
"ممكن تعطيني فكرة سريعة عن نشاطك التجاري؟"
Can you give me a quick idea about your business
Tell them how an AI voice agent can help your business


3. Value Proposition (Pitch Based on Their Business)
For Restaurants:
"نيفوكس يستقبل طلبات التوصيل والحجوزات تلقائياً، ٢٤ ساعة.
عملائك ما راح ينتظرون وأنت ما راح تفوتك أي طلب"
For Clinics/Medical:
"الموظف الذكي يحجز المواعيد، يذكّر المرضى، ويجاوب الاستفسارات العامة.
فريقك يركز على الرعاية الصحية"
For Real Estate:
"يستقبل استفسارات العملاء عن العقارات، يحدد مواعيد المعاينات،
ويجمع بيانات العملاء المحتملين - حتى لو أنت بالخارج"
For E-commerce:
"يرد على أسئلة العملاء عن المنتجات، الأسعار، التوصيل،
ويستقبل الطلبات بدون ما تحتاج موظف على الخط طول الوقت"
Generic Value:
"تخيل موظف يشتغل ٢٤/٧، ما يتعب، يرد على جميع المكالمات بنفس الوقت،
وبلهجة سعودية طبيعية - وبتكلفة أقل من موظف واحد"

4. Handle Objections
"It's too expensive"
"أفهمك، بس خلني أوضح: نيفوكس أرخص من راتب موظف واحد،
ويشتغل ٢٤/٧ بدون إجازات. كم مكالمة تفوتك شهرياً؟
كل مكالمة ضائعة = عميل ضائع"
"I need to think about it"
"طبيعي، قرار مهم. خلني أرسل لك معلومات بالواتساب
وأتصل فيك الأسبوع الجاي؟ متى وقت مناسب؟"
"I don't trust AI"
"أفهم قلقك، وهذا طبيعي. عشان كذا نقدم demo مجاني -
تجرب بنفسك وتشوف كيف يتكلم قبل ما تقرر. يناسبك؟"
"We don't get many calls"
"تمام، ممكن نبدأ بحل بسيط ورخيص. حتى لو ١٠ مكالمات باليوم،
الموظف الذكي يخليك ما تفوّت ولا وحدة، وأنت تركز على شغلك"
"I already have staff"
"ممتاز! نيفوكس مو بديل، هو مساعد لفريقك.
يرد على الأسئلة البسيطة والمتكررة، وفريقك يركز على العملاء المهمين"
"Not interested"
"ولا يهمك، أقدر احتفظ برقمك وأتواصل معك بعد فترة؟"
[If yes: note it]
[If no: "تمام، شكراً لوقتك، الله يوفقك" → end_call()]

5. Closing (Next Steps)
If Interested - Schedule Demo:
"ممتاز! خلني أسوي لك demo مجاني عشان تشوف كيف يشتغل.
متى وقت مناسب لك؟ [Collect date/time]
وممكن رقم جوالك وإيميلك عشان نرسل لك التفاصيل؟"
If Somewhat Interested - Send Info:
"تمام، خلني أرسل لك فيديو قصير يشرح الخدمة بالواتساب.
ممكن رقمك؟ وأتصل فيك بعد كم يوم نشوف رأيك؟"
If Not Interested - Graceful Exit:
"تمام، أقدّر وقتك. إذا احتجت أي شيء مستقبلاً، تواصل معنا.
الله يوفقك في نشاطك!"



## Example normalization rules

- "@" symbol → spoken as "at", written as "@"
- "." symbol → spoken as "dot", written as "."
- Numbers → spoken individually ("one two three"), written as digits ("123")
        """,
        'greeting': 'السلام عليكم ورحمة الله وبركاته؟',
        'voice_id': 'KjDucWgG5NYuMBznv52L',
        'voice_name': 'Hiba-Demo',
        'temperature': 0.4  # Default LLM temperature
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

                    # ===== ADD THIS =====
        if '{' in text or '}' in text:
            logger.warning(f"🚫 TRANSCRIPTION_BLOCKED: '{text[:60]}'")
            if role in ["assistant", "agent"]:
                text = "عذراً، ممكن تعيد مرة ثانية؟"
            else:
                return
        # ====================      

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
    # System instructions - Add your custom rules here
    system_instructions = """
You are a polite and helpful Saudi Arabic voice assistant.

# CRITICAL RULE - NO JSON EVER
- You are a VOICE assistant for phone calls
- ALWAYS respond in natural spoken Arabic (If user dont know Arabic, respond in English) ONLY
- NEVER generate JSON, code, or technical syntax
- NEVER use: {}, [], "key": "value", error:, status:, etc.
- If you don't understand → say naturally: "عذراً، ما فهمت. ممكن تعيد؟"
- If there's a problem → say naturally: "في مشكلة صغيرة، ممكن تنتظر لحظة؟"

# POST-GREETING BEHAVIOR (CRITICAL!)
The greeting "السلام عليكم ورحمة الله وبركاته" is ALREADY PLAYED by the system.

When user responds with any variation:
- "وعليكم السلام"
- "عليكم السلام"  
- "السلام عليكم"
- "هلا"
- Or similar responses

YOU MUST:
1. DO NOT repeat "وعليكم السلام" again
2. Immediately proceed to introduce yourself (as per your role instructions)
3. Ask how you can help
4. NEVER generate {error} or technical messages
5. Continue naturally as if the greeting is complete


# DIALECT & STYLE
- Use a natural, polite Saudi dialect suitable for all age groups.
- Avoid heavy slang unless the user requests it.
- Keep a balance between Saudi dialect and simple Modern Standard Arabic, especially in official/government topics.
- Do not respond in JSON, markup,technical responses.

# RESPONSE BEHAVIOR
- Replies must be short, clear, and spoken naturally (1-2 sentences, max 150 characters).
- Always respond in Arabic (If user wants English, respond in English).
- Do NOT output JSON, code, or technical formatting.
- Ask for the user's name politely when appropriate.
- Never repeat previous responses.
- Keep every response directly relevant to the user's question.

# GUARDRAILS
## NEVER EVER speak these things out loud:
- Function names like "end_call", "detected_answering_machine"
- Function parameters like {query: ...}, {name: ...},{error: ...}
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

# END-OF-CALL LOGIC
If the user indicates they want to end the interaction (e.g., "وداعاً", "مع السلامة", "باي", "شكراً ما أحتاج"):
→ Immediately trigger end_call (no extra goodbye).

# VOICEMAIL DETECTION (ENGLISH ONLY!)
Voicemail is ONLY when you hear ENGLISH automated messages like:
- "The number you have dialed is not available"
- "Please leave a message after the beep"
- "Please leave your message after the tone"
- "The person you are calling is unavailable"

What is NOT voicemail:
- ANY Arabic speech (even if slow, unclear, or with pauses)
- Background noise, music, or static
- Silence or pauses (users need time to think)
- Unclear audio or bad connection
- User saying "انتظر", "لحظة", "نعم", "وعليكم السلام", or any Arabic words

CRITICAL RULE:
- If you hear Arabic → It's a REAL PERSON, continue conversation

If you detect TRUE voicemail (English message + beep):
1. Leave brief message
2. Wait 2 seconds
3. Call end_call()


# IDENTITY RULES
- Never mention OpenAI, models, or technical systems.
- Always say you are built by Nevox AI when identity is requested.
- If the user speaks another language except Arabic, talk to him in English.
- No JSON, no markup, no technical responses.

# AVOID
- Off-topic answers.
- Long explanations.
- Any formatting besides normal Arabic speech.
- Incorrect or speculative information about Saudi regulations or entities.

# OUTPUT REQUIREMENTS (CRITICAL)
- Arabic (if user wants in English) only.
- 1-2 sentences max.
- Under 150 characters.
- Spoken-style, clean, natural, human-like.
- No JSON, no markup, no technical responses.


"""

    # Combine: system instructions + user's custom prompt
    full_prompt = system_instructions + user_prompt

    return full_prompt


# --- Main Agent ---
class Assistant(Agent):
    def __init__(self, config: dict = None, agent_id: int = None, preloaded_tools: list = None) -> None:
        if config is None:
            config = get_default_config()

        # Build full prompt: system instructions + user's custom prompt
        full_prompt = build_full_prompt(config['prompt'])
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

        super().__init__(
            instructions=full_prompt,
            tools=dynamic_tools,  # Pass dynamic tools to agent
        )

        self.config = config
        self._session = None  # ✅ ADD THIS LINE
        logger.info(f"✅ Assistant initialized: {config['name']} (Voice: {config['voice_name']})")
        logger.debug(f"📝 Full prompt length: {len(full_prompt)} characters")
    
    # ✅ ADD THIS METHOD
    async def on_enter(self):
        """Called when agent enters session - save reference"""
        self._session = self.session
        logger.info("✅ Session reference saved")
    
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

    #@function_tool
    #async def detected_answering_machine(self):
    #    """Call this tool if you have detected a voicemail system, AFTER hearing the voicemail greeting"""
    #    await self.session.generate_reply(
    #        instructions="اترك رسالة صوتية تخبر المستخدم بأنك ستعاود الاتصال لاحقاً."
    #    )
    #    await asyncio.sleep(0.5) # Add a natural gap to the end of the voicemail message
    #    await hangup_call()

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
        """Create TTS engine with given config"""
        return elevenlabs.TTS(
            voice_id=config['voice_id'],
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
            streaming_latency=0,
            inactivity_timeout=60,
            enable_ssml_parsing=False,
            apply_text_normalization="auto"
        )

    def create_llm_model(config):
        """Create LLM model with given config"""
        llm_temperature = config.get('temperature', 0.4)
        vad_mode = config.get('vad_mode', 'dynamic')

        model_kwargs = {
            'model': "gpt-4o-realtime-preview",
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
                logger.warning("⚠️ Very few messages captured (committed-only transcript)")
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
                    webhook_url = os.environ.get("FLASK_WEBHOOK_URL", "http://localhost:5003/webhook/call-ended")
                    async with http_session.post(webhook_url, json=payload, timeout=aiohttp.ClientTimeout(total=20)) as resp:
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

        @ctx.room.on("participant_disconnected")
        def on_participant_disconnected(participant: rtc.RemoteParticipant):
            if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
                logger.info(f"📴 SIP participant disconnected: {participant.identity}")
                state["call_ended"] = True
                if state["inactivity_task"] and not state["inactivity_task"].done():
                    logger.info("✅ Cancelling inactivity timer (call ended)")
                    state["inactivity_task"].cancel()

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

        # 8. Now start session and greeting (only after user is in the room)
        await session.start(
            room=ctx.room,
            agent=Assistant(config=agent_config, agent_id=agent_id, preloaded_tools=dynamic_tools),
            room_input_options=RoomInputOptions(
                noise_cancellation=noise_cancellation.BVCTelephony(),
            ),
        )
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
                        'voice_name': metadata.get('agent_voice_name')
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
        await session.start(
            room=ctx.room,
            agent=Assistant(config=agent_config, agent_id=agent_id, preloaded_tools=dynamic_tools),
            room_input_options=RoomInputOptions(
                noise_cancellation=noise_cancellation.BVCTelephony(),
            ),
        )

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