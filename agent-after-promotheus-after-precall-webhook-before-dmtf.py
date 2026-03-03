import asyncio
import logging
import os
import time
import json
import aiohttp
import sqlite3
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv


from typing import AsyncIterable
import re
import time


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

# Prometheus metrics service
from services.redis_metrics import track_call_metrics, increment_active_calls, decrement_active_calls
# Redis caching service (40x speedup!)
from services.redis_service import redis_service
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
def get_agent_config(agent_id: int, use_cache=True):
    """
    Fetch agent configuration with Redis caching

    PERFORMANCE IMPROVEMENT:
    - OLD: 20ms (database query on every call)
    - NEW: 0.5ms (Redis cache, 40x faster!)
    - Database queries reduced by 95%

    Args:
        agent_id: Agent ID to fetch
        use_cache: Whether to use Redis cache (default: True)

    Returns:
        dict: Agent configuration or None if not found
    """
    # ✅ STEP 1: Try Redis cache first (FAST! ~0.5ms)
    if use_cache:
        cached_config = redis_service.get_agent_config(agent_id)
        if cached_config:
            logger.debug(f"✅ Redis cache HIT: agent {agent_id}")
            return cached_config

    # ❌ STEP 2: Cache miss - load from database (SLOW! ~20ms)
    logger.debug(f"❌ Redis cache MISS: agent {agent_id} - loading from DB")

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

            # ✅ STEP 3: Cache it in Redis for next time (TTL: 1 hour)
            redis_service.cache_agent_config(agent_id, config, ttl=3600)

            logger.info(f"📥 Loaded agent config from database: {config['name']}")
            return config
        else:
            logger.warning(f"⚠️ Agent {agent_id} not found in database")
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
        'voice_name': 'Hiba-Demo'
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
- ALWAYS respond in natural spoken Arabic ONLY
- NEVER generate JSON, code, or technical syntax
- NEVER use: {}, [], "key": "value", error:, status:, etc.
- If you don't understand → say naturally: "عذراً، ما فهمت. ممكن تعيد؟"
- If there's a problem → say naturally: "في مشكلة صغيرة، ممكن تنتظر لحظة؟"

# POST-GREETING BEHAVIOR (CRITICAL!)
The greeting "السلام عليكم ورحمة الله وبركاته" is ALREADY PLAYED by the system.



#  CALL ENDING - HIGHEST PRIORITY RULE 

## GOODBYE DETECTION (Common Saudi Farewell Phrases):
When user says ANY of these phrases, IMMEDIATELY call end_call():

### Direct Goodbyes:
- وداعاً، مع السلامة، باي، سلام، الله يسلمك
- يعطيك العافية (when said alone or with goodbye tone)
- الله يعافيك (as farewell)
- في أمان الله، بإذن الله نلقاك

### Polite Closings (Context: After order/task completion):
- تمام شكراً، خلاص شكراً، زين شكراً، طيب شكراً
- حسناً (when said alone after completing a task)
- ماشي، تمام، زين، أوكي (when ending conversation)
- شكراً كافي، شكراً كذا، شكراً ما أحتاج شي ثاني

### Morning/Evening Farewells:
- صباح الخير (when used as goodbye, not greeting)
- مساء الخير (when used as goodbye)
- تصبح على خير، الله يمسيك بالخير

### Completion Phrases:
- كذا تمام، كذا زين، هذا كل شي
- ما أحتاج شي ثاني، ما عندي شي ثاني
- خلصنا، انتهينا

##  CRITICAL BEHAVIOR WHEN GOODBYE DETECTED:
1. **IMMEDIATELY** call end_call() function
2. **DO NOT** speak any response
3. **DO NOT** say goodbye back
4. **DO NOT** thank them
5. **JUST CALL** end_call() with NO spoken output

##  CORRECT Examples:
```
User: "صباح الخير" (after completing order)
You: [calls end_call() - NO speech]

User: "حسناً" (after confirming everything)
You: [calls end_call() - NO speech]

User: "تمام شكراً"
You: [calls end_call() - NO speech]

User: "يعطيك العافية"
You: [calls end_call() - NO speech]
```

## ❌ WRONG Examples:
```
User: "صباح الخير"
You: "صباح النور، الطلب بيوصلك" ← WRONG! Should end call

User: "حسناً"
You: "تمام، شكراً لك" ← WRONG! Should end call

User: "يعطيك العافية"
You: "الله يعافيك، مع السلامة" [then calls end_call()] ← WRONG! Call function FIRST
```



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
- Always respond in Arabic only.
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

# Handling Voiemails/Answering Machines
- Double check if it is voicemail by listening for common phrases.
- if yes then call end_call after leaving a polite voicemail message.
- if no then continue the conversation naturally.


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


def build_prompt_with_raw_webhook_data(user_prompt: str, raw_data: dict) -> str:
    """
    Inject RAW webhook data into prompt for pre-call context
    Args:
        user_prompt: The prompt from database (agent.prompt)
        raw_data: Raw dict from n8n webhook response (any fields)
    Returns:
        Complete prompt with system instructions + user prompt + webhook data
    """
    # Get base prompt with system instructions
    base_prompt = build_full_prompt(user_prompt)

    # Add raw webhook data section if available
    if raw_data:
        webhook_text = json.dumps(raw_data, ensure_ascii=False, indent=2)

        webhook_section = f"""
# 📊 بيانات العميل من النظام (Customer Data from CRM)
```json
{webhook_text}
```
"""

        full_prompt = base_prompt + webhook_section
        print(full_prompt)
        return full_prompt
    else:
        # No webhook data, use default prompt
        return base_prompt


# --- Main Agent ---
class Assistant(Agent):
    def __init__(self, config: dict = None, agent_id: int = None, preloaded_tools: list = None, webhook_context: dict = None) -> None:
        if config is None:
            config = get_default_config()

        
        # Build full prompt with optional webhook data
        if webhook_context:
            full_prompt = build_prompt_with_raw_webhook_data(config['prompt'], webhook_context)
            logger.info(f"✅ Prompt built WITH webhook data: {list(webhook_context.keys())}")
        else:
            full_prompt = build_full_prompt(config['prompt'])
            logger.info(f"ℹ️ Prompt built WITHOUT webhook data (default)")    

        # Build full prompt: system instructions + user's custom prompt
        #full_prompt = build_full_prompt(config['prompt'])
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
        self.webhook_context = webhook_context # Store for reference
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
                    
                    # Add to chat history
                    try:
                        from livekit.agents import llm
                        chat_ctx.messages.append(
                            llm.ChatMessage(role="assistant", content=fallback)
                        )
                        logger.info("✅ Fallback added to chat history")
                    except Exception as e:
                        logger.error(f"❌ Error adding to chat: {e}")
                    
                    yield fallback
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
        """
        Ends the current voice call with the user in a polite and natural way.

        This function is intended to be called when the user explicitly or implicitly 
        signals that they want to finish the conversation. The steps performed are:

        1. Sends a polite, static goodbye message to the user using TTS (Text-to-Speech).
        - Example message: "شكراً جزيلاً على وقتك. مع السلامة!"
        - Interruptions are disabled to ensure the message is fully delivered.

        2. Waits briefly to ensure the goodbye message has been played.

        3. Hangs up the call, ensuring the session is properly closed.

        Returns:
            str: Confirmation that the call ended, e.g., "Call ended with goodbye".
        """
        # First generate a natural goodbye using the LLM

        # ✅ Static goodbye - no cache break!
        await ctx.session.say(
            "شكراً جزيلاً على وقتك. مع السلامة!",
            allow_interruptions=False
        )
        
        # Wait for message to complete
        await asyncio.sleep(0.6)
       
        # Then hang up the call
        await hangup_call()
        return "Call ended with goodbye"
    
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
    '''
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
    
    logger.info(f"🎯 Room: {ctx.room.name}")
    logger.info(f"📊 Initial participants: {ctx.room.num_participants}")

    # Connect to room
    await ctx.connect()
    call_start_time = time.time()

    # Check if campaign call
    agent_config = None
    webhook_context = None
    # CAMPAIGN CALLS: Extract from participant metadata
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
                    }                    # Extract webhook context (can be None)
                    webhook_context = metadata.get('webhook_context')

                    if webhook_context:
                        logger.info(f"✅ Webhook context found: {list(webhook_context.keys())}")
                    else:
                        logger.info(f"ℹ️ No webhook context (disabled or failed)")

                    logger.info(f"✅ Using campaign agent: {agent_config['name']}")
        except Exception as e:
            logger.error(f"❌ Error parsing campaign metadata: {e}")

    # NON-CAMPAIGN CALLS: Check for outbound API calls with participant metadata
    if not agent_config:
        agent_config = get_default_config()
        try:
            # Wait for participant to get metadata (for outbound API calls)
            participant = await ctx.wait_for_participant()
            logger.info(f"✅ Participant joined: {participant.identity}")

            # Check if participant has metadata (outbound API calls with pre-call webhook)
            if participant.metadata:
                try:
                    logger.info(f"🔍 Participant metadata: {participant.metadata[:200]}...")
                    metadata = json.loads(participant.metadata)

                    if metadata.get('type') == 'outbound_api':
                        # Extract agent_id and webhook_context from metadata
                        agent_id = metadata.get('agent_id')
                        webhook_context = metadata.get('webhook_context')

                        if agent_id:
                            fetched_config = get_agent_config(agent_id)
                            if fetched_config:
                                agent_config = fetched_config
                                logger.info(f"✅ Loaded agent: {agent_config['name']}")

                                if webhook_context:
                                    logger.info(f"✅ Pre-call webhook context found: {list(webhook_context.keys())}")
                                else:
                                    logger.info(f"ℹ️ No pre-call webhook context (disabled or failed)")
                except Exception as e:
                    logger.error(f"❌ Error parsing outbound API metadata: {e}")

            # Fallback: Extract agent_id from room name
            if not agent_config or agent_config == get_default_config():
                room_parts = ctx.room.name.split('-')
                if len(room_parts) >= 2 and room_parts[0] == 'call':
                    agent_id = int(room_parts[1])
                    fetched_config = get_agent_config(agent_id)
                    if fetched_config:
                        agent_config = fetched_config
                        logger.info(f"✅ Loaded agent from room name: {agent_config['name']}")
                        logger.info(f"ℹ️ No participant metadata (inbound call or old format)")
        except Exception as e:
            logger.error(f"❌ Error parsing agent ID: {e}")

    # Initialize transcription
    transcription = TranscriptionManager()
    transcription.webhook_context = webhook_context  # Store for post-call analysis

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
            #language="ar",
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
            #gpt-realtime-mini-2025-10-06 vs gpt-4o-mini-realtime-preview-2024-12-17 vs gpt-realtime-2025-08-28
            #gpt-4o-realtime-preview
            #gpt-realtime-2025-08-28
            #gpt-realtime-mini-2025-12-15
            model="gpt-realtime-2025-08-28",
            modalities=["text"],
            temperature=0.4,
            #input_audio_transcription=InputAudioTranscription(
            #    #model="gpt-4o-mini-transcribe-2025-12-15",
            #    model="gpt-4o-transcribe",
            #    language="ar",
            #    prompt="Two speakers in Arabic, one customer, one agent."
            #),
            #turn_detection=TurnDetection(
            #    type="server_vad",
            #    threshold=0.45,
            #    prefix_padding_ms=150,
            #    silence_duration_ms=250,
            #    create_response=True,
            #    interrupt_response=True,
            #),
        )
    
    # Run all initializations in parallel
    tts_engine,stt_engine_google, llm_model_realtime = await asyncio.gather(
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

        # Track metrics to Prometheus
        call_duration = int(time.time() - call_start_time)
        track_call_metrics(
            usage_summary=summary,
            agent_id=agent_id,
            call_duration=call_duration,
            message_count=len(transcription.messages),
            voice_id=agent_config.get('voice_id', 'unknown'),
            call_status='completed'
        )

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
                webhook_url = os.environ.get('FLASK_WEBHOOK_URL', 'http://localhost:5004/webhook/call-ended')
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
    await session.start(
        room=ctx.room,
        agent=Assistant(config=agent_config, agent_id=agent_id, preloaded_tools=dynamic_tools,webhook_context=webhook_context),
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
            timeout = 5  # Reduced from 5s → 1.5s
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
    #@ctx.room.on("participant_disconnected")
    #def on_participant_disconnected(participant: rtc.RemoteParticipant):
    #    nonlocal inactivity_task, monitor_task, call_ended
    #    if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
    #        logger.info(f"📴 SIP participant disconnected: {participant.identity}")
    #        call_ended = True
    #        if inactivity_task and not inactivity_task.done():
    #            logger.info("✅ Cancelling inactivity timer (call ended)")
    #            inactivity_task.cancel()
    #        if monitor_task and not monitor_task.done():
    #            logger.debug("✅ Cancelling monitor task (call ended)")
    #            monitor_task.cancel()
    #        asyncio.create_task(hangup_call())
    
    @ctx.room.on("participant_disconnected")
    def on_participant_disconnected(participant: rtc.RemoteParticipant):
        nonlocal inactivity_task, monitor_task, call_ended
        if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
            logger.info(f"📴 SIP participant disconnected: {participant.identity}")
            call_ended = True
            
            # Cancel tasks
            if inactivity_task and not inactivity_task.done():
                logger.info("✅ Cancelling inactivity timer (call ended)")
                inactivity_task.cancel()
            if monitor_task and not monitor_task.done():
                logger.debug("✅ Cancelling monitor task (call ended)")
                monitor_task.cancel()
            
            # ✅ HANG UP CALL (shutdown callback will send complete webhook with full transcription)
            # 🔴 DISABLED: Commented out to prevent duplicate webhooks
            # The shutdown callback (line 1388) already sends complete webhook data
            # This was causing 2 webhooks per call:
            #   - First: disconnect handler (6s duration, incomplete data)
            #   - Second: shutdown callback (22s duration, complete data)
            # async def handle_disconnect():
            #     await send_call_data()  # Send webhook
            #     await asyncio.sleep(0.5)  # Give webhook time to send
            #     await hangup_call()  # Then delete room
            # asyncio.create_task(handle_disconnect())

            # Just hang up - shutdown callback handles webhook
            asyncio.create_task(hangup_call())

    # ===== OPTIMIZATION 6: IMMEDIATE GREETING (no sleeps!) =====
    logger.info("🎤 Sending greeting IMMEDIATELY...")
    greeting_message = agent_config.get('greeting', 'السلام عليكم ورحمة الله وبركاته')
    
    # Add to transcription first
    transcription.add_agent_message(greeting_message, "initial_greeting")
    transcription.greeting_added = True
    logger.info("✅ Greeting added to transcription")
    
    # Send greeting immediately - no sleeps!
    await session.say(greeting_message, allow_interruptions=False)
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

    # Configure worker with essential production option
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
    logger.info(f"   Prometheus metrics: http://localhost:8000/metrics")

    cli.run_app(opts)