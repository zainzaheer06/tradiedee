"""
Contact Collection Tasks for Nevox AI Voice Agent
Collects: Name, Phone Number, and Email (with confirmation)
"""

import logging
from dataclasses import dataclass
from livekit.agents import AgentTask, function_tool, RunContext
from livekit.agents.beta.workflows import GetEmailTask, TaskGroup

logger = logging.getLogger("contact_tasks")


# ==========================================
# RESULT TYPES
# ==========================================

@dataclass
class NameResult:
    """Result from collecting name"""
    name: str

@dataclass
class PhoneResult:
    """Result from collecting phone number"""
    phone_number: str

@dataclass
class EmailResult:
    """Result from collecting email"""
    email_address: str


# ==========================================
# TASK 1: COLLECT NAME (WITH CONFIRMATION)
# ==========================================

class GetNameTask(AgentTask[NameResult]):
    """Collects customer name in Arabic with confirmation"""

    def __init__(self, chat_ctx=None):
        super().__init__(
            instructions="""
            # CRITICAL MISSION
            You MUST collect the customer's full name using the function tools provided.
            DO NOT just have a conversation - you MUST call the function tools to record the name.

            # WORKFLOW (MANDATORY):
            1. Ask: "ممكن اعرف اسمك الكامل لو سمحت؟"
            2. Customer responds with name → IMMEDIATELY call heard_name(name)
            3. Repeat name to customer: "الاسم [name]، صح؟"
            4. Customer confirms:
               - If "نعم/صح/تمام" → call name_confirmed_correct()
               - If "لا/غلط" + correction → call name_is_wrong(corrected_name)

            # CRITICAL RULES:
            - ALWAYS call heard_name() when you hear a name - don't skip this!
            - NEVER proceed without calling the confirmation tools
            - Get the FULL name (first and last name)

            # EXAMPLE CONVERSATION:
            You: "ممكن اعرف اسمك الكامل؟"
            User: "اسمي محمد أحمد العتيبي"
            You: [CALL heard_name("محمد أحمد العتيبي")] then say "الاسم محمد أحمد العتيبي، صح؟"
            User: "نعم"
            You: [CALL name_confirmed_correct()] - TASK COMPLETE!
            """,
            chat_ctx=chat_ctx,
        )
        self._temp_name = None  # Temporary storage before confirmation
        self._confirmed_name = None  # Confirmed name

    async def on_enter(self) -> None:
        """Start by asking for name"""
        await self.session.generate_reply(
            instructions="اطلب من العميل اسمه الكامل بطريقة ودية"
        )

    @function_tool()
    async def heard_name(self, context: RunContext, name_heard: str) -> None:
        """
        Call this IMMEDIATELY when the customer tells you their name.

        Use when customer says things like:
        - "اسمي محمد"
        - "أنا أحمد بن سعود"
        - "My name is Mohammed"

        Args:
            name_heard: The full name you heard from the customer
        """
        self._temp_name = name_heard
        logger.info(f"📝 Heard name: {name_heard} (waiting for confirmation)")

        # Ask customer to confirm
        await context.session.generate_reply(
            instructions=f"كرر الاسم للعميل بوضوح: '{name_heard}' واسأله: صح؟ أو صحيح؟"
        )

    @function_tool()
    async def name_confirmed_correct(self, context: RunContext) -> None:
        """
        Call this when the customer confirms their name is correct.

        Use when customer says:
        - "نعم" / "Yes"
        - "صح" / "صحيح"
        - "تمام" / "Correct"
        - "أيوه"
        """
        if not self._temp_name:
            await context.session.generate_reply(
                instructions="اطلب الاسم أولاً"
            )
            return

        self._confirmed_name = self._temp_name
        logger.info(f"✅ Name confirmed: {self._confirmed_name}")

        # Complete the task (BEFORE generating reply to avoid race condition)
        result = NameResult(name=self._confirmed_name)
        self.complete(result)

        # Then thank the customer
        await context.session.generate_reply(
            instructions="شكر العميل على تقديم اسمه"
        )

    @function_tool()
    async def name_is_wrong(self, context: RunContext, correct_name: str) -> None:
        """
        Call this when the customer says the name you repeated is WRONG and provides the correct name.

        Use when customer says:
        - "لا، اسمي أحمد مو محمد" (No, my name is Ahmed not Mohammed)
        - "غلط، الاسم الصحيح هو..." (Wrong, the correct name is...)

        Args:
            correct_name: The corrected name provided by the customer
        """
        self._confirmed_name = correct_name
        logger.info(f"✅ Name corrected to: {correct_name}")

        # Complete the task with corrected name (BEFORE generating reply to avoid race condition)
        result = NameResult(name=correct_name)
        self.complete(result)

        # Then apologize and thank the customer
        await context.session.generate_reply(
            instructions=f"اعتذر واشكره. الاسم الصحيح: {correct_name}"
        )


# ==========================================
# TASK 2: COLLECT PHONE NUMBER (WITH CONFIRMATION)
# ==========================================

class GetPhoneTask(AgentTask[PhoneResult]):
    """Collects customer phone number in Arabic with confirmation"""

    def __init__(self, chat_ctx=None):
        super().__init__(
            instructions="""
            # CRITICAL MISSION
            You MUST collect the customer's phone number using the function tools provided.
            DO NOT just have a conversation - you MUST call the function tools to record the phone.

            # WORKFLOW (MANDATORY):
            1. Ask: "ممكن رقم جوالك لو سمحت؟"
            2. Customer responds with phone → IMMEDIATELY call heard_phone_number(phone)
            3. Repeat phone digit by digit: "الرقم [0 5 1 2...]، صح؟"
            4. Customer confirms:
               - If "نعم/صح/تمام" → call phone_confirmed_correct()
               - If "لا/غلط" + correction → call phone_is_wrong(corrected_phone)

            # CRITICAL RULES:
            - ALWAYS call heard_phone_number() when you hear a phone - don't skip this!
            - NEVER proceed without calling the confirmation tools
            - Phone must be 10 digits starting with 05

            # EXAMPLE CONVERSATION:
            You: "ممكن رقم جوالك؟"
            User: "0512345678"
            You: [CALL heard_phone_number("0512345678")] then say "الرقم صفر خمسة واحد اثنين ثلاثة أربعة خمسة ستة سبعة ثمانية، صح؟"
            User: "نعم"
            You: [CALL phone_confirmed_correct()] - TASK COMPLETE!
            """,
            chat_ctx=chat_ctx,
        )
        self._temp_phone = None  # Temporary storage before confirmation
        self._confirmed_phone = None  # Confirmed phone

    async def on_enter(self) -> None:
        """Start by asking for phone"""
        await self.session.generate_reply(
            instructions="اطلب من العميل رقم جواله (10 أرقام يبدأ بـ 05)"
        )

    @function_tool()
    async def heard_phone_number(self, context: RunContext, phone_heard: str) -> None:
        """
        Call this IMMEDIATELY when the customer tells you their phone number.

        Use when customer says things like:
        - "رقمي 0512345678"
        - "05 123 456 78"
        - "My number is 0512345678"

        Args:
            phone_heard: The phone number you heard (will be validated automatically)
        """
        # Clean the phone number
        phone_clean = phone_heard.replace(" ", "").replace("-", "").replace("٠", "0").replace("٥", "5")

        # Validate format
        if not phone_clean.startswith("05") or len(phone_clean) != 10:
            logger.warning(f"⚠️ Invalid phone format: {phone_heard}")
            await context.session.generate_reply(
                instructions=f"الرقم {phone_heard} غير صحيح. اطلب رقم جوال سعودي صحيح (10 أرقام يبدأ بـ 05)"
            )
            return

        self._temp_phone = phone_clean
        logger.info(f"📝 Heard phone: {phone_clean} (waiting for confirmation)")

        # Read digits slowly for confirmation
        digits = " ".join(phone_clean)
        await context.session.generate_reply(
            instructions=f"كرر الرقم للعميل رقم رقم بوضوح: {digits} واسأله: صح؟"
        )

    @function_tool()
    async def phone_confirmed_correct(self, context: RunContext) -> None:
        """
        Call this when the customer confirms their phone number is correct.

        Use when customer says:
        - "نعم" / "Yes"
        - "صح" / "صحيح"
        - "تمام" / "Correct"
        - "أيوه" / "صحيح الرقم"
        """
        if not self._temp_phone:
            await context.session.generate_reply(
                instructions="اطلب رقم الجوال أولاً"
            )
            return

        self._confirmed_phone = self._temp_phone
        logger.info(f"✅ Phone confirmed: {self._confirmed_phone}")

        # Complete the task (BEFORE generating reply to avoid race condition)
        result = PhoneResult(phone_number=self._confirmed_phone)
        self.complete(result)

        # Then thank the customer
        await context.session.generate_reply(
            instructions="شكر العميل على تقديم رقم جواله"
        )

    @function_tool()
    async def phone_is_wrong(self, context: RunContext, correct_phone: str) -> None:
        """
        Call this when the customer says the phone you repeated is WRONG and provides the correct number.

        Use when customer says:
        - "لا، الرقم غلط" (No, the number is wrong)
        - "الرقم الصحيح هو..." (The correct number is...)

        Args:
            correct_phone: The corrected phone number provided by the customer
        """
        # Validate the corrected phone
        phone_clean = correct_phone.replace(" ", "").replace("-", "").replace("٠", "0").replace("٥", "5")

        if not phone_clean.startswith("05") or len(phone_clean) != 10:
            logger.warning(f"⚠️ Corrected phone still invalid: {correct_phone}")
            await context.session.generate_reply(
                instructions="الرقم المصحح غير صحيح. اطلب رقم جوال سعودي (10 أرقام يبدأ بـ 05)"
            )
            return

        self._confirmed_phone = phone_clean
        logger.info(f"✅ Phone corrected to: {phone_clean}")

        # Complete the task with corrected phone (BEFORE generating reply to avoid race condition)
        result = PhoneResult(phone_number=phone_clean)
        self.complete(result)

        # Then apologize and thank the customer
        await context.session.generate_reply(
            instructions=f"اعتذر واشكره. الرقم الصحيح: {phone_clean}"
        )


# ==========================================
# TASK 3: COLLECT EMAIL (WITH CONFIRMATION)
# ==========================================

class GetEmailTask(AgentTask[EmailResult]):
    """Collects customer email in Arabic/English with confirmation"""

    def __init__(self, chat_ctx=None):
        super().__init__(
            instructions="""
            # CRITICAL MISSION
            You MUST collect the customer's email address using the function tools provided.
            DO NOT just have a conversation - you MUST call the function tools to record the email.

            # WORKFLOW (MANDATORY):
            1. Ask: "ممكن الإيميل لو سمحت؟" or "ممكن بريدك الإلكتروني؟"
            2. Customer responds with email → IMMEDIATELY call heard_email(email)
            3. Repeat email to customer clearly: "الإيميل [email]، صح؟"
            4. Customer confirms:
               - If "نعم/صح/تمام" → call email_confirmed_correct()
               - If "لا/غلط" + correction → call email_is_wrong(corrected_email)

            # CRITICAL RULES:
            - ALWAYS call heard_email() when you hear an email - don't skip this!
            - NEVER proceed without calling the confirmation tools
            - Email must contain @ and a domain (e.g., user@domain.com)
            - Spell out the email slowly when confirming

            # EXAMPLE CONVERSATION:
            You: "ممكن بريدك الإلكتروني؟"
            User: "ahmed@gmail.com"
            You: [CALL heard_email("ahmed@gmail.com")] then say "الإيميل ahmed at gmail dot com، صح؟"
            User: "نعم"
            You: [CALL email_confirmed_correct()] - TASK COMPLETE!
            """,
            chat_ctx=chat_ctx,
        )
        self._temp_email = None  # Temporary storage before confirmation
        self._confirmed_email = None  # Confirmed email

    async def on_enter(self) -> None:
        """Start by asking for email"""
        await self.session.generate_reply(
            instructions="اطلب من العميل بريده الإلكتروني (الإيميل)"
        )

    @function_tool()
    async def heard_email(self, context: RunContext, email_heard: str) -> None:
        """
        Call this IMMEDIATELY when the customer tells you their email.

        Use when customer says things like:
        - "ahmed@gmail.com"
        - "my email is john@example.com"
        - "البريد تبعي user@domain.com"

        Args:
            email_heard: The email address you heard
        """
        # Basic validation
        if '@' not in email_heard or '.' not in email_heard:
            logger.warning(f"⚠️ Invalid email format: {email_heard}")
            await context.session.generate_reply(
                instructions=f"الإيميل {email_heard} غير صحيح. اطلب إيميل صحيح يحتوي على @ و ."
            )
            return

        self._temp_email = email_heard.lower().strip()
        logger.info(f"📝 Heard email: {self._temp_email} (waiting for confirmation)")

        # Ask customer to confirm
        await context.session.generate_reply(
            instructions=f"كرر الإيميل للعميل بوضوح: '{self._temp_email}' واسأله: صح؟"
        )

    @function_tool()
    async def email_confirmed_correct(self, context: RunContext) -> None:
        """
        Call this when the customer confirms their email is correct.

        Use when customer says:
        - "نعم" / "Yes"
        - "صح" / "صحيح"
        - "تمام" / "Correct"
        - "أيوه"
        """
        if not self._temp_email:
            await context.session.generate_reply(
                instructions="اطلب الإيميل أولاً"
            )
            return

        self._confirmed_email = self._temp_email
        logger.info(f"✅ Email confirmed: {self._confirmed_email}")

        # Complete the task (BEFORE generating reply to avoid race condition)
        result = EmailResult(email_address=self._confirmed_email)
        self.complete(result)

        # Then thank the customer
        await context.session.generate_reply(
            instructions="شكر العميل على تقديم إيميله"
        )

    @function_tool()
    async def email_is_wrong(self, context: RunContext, correct_email: str) -> None:
        """
        Call this when the customer says the email you repeated is WRONG and provides the correct one.

        Use when customer says:
        - "لا، الإيميل غلط" (No, the email is wrong)
        - "الإيميل الصحيح هو..." (The correct email is...)

        Args:
            correct_email: The corrected email provided by the customer
        """
        # Validate the corrected email
        if '@' not in correct_email or '.' not in correct_email:
            logger.warning(f"⚠️ Corrected email still invalid: {correct_email}")
            await context.session.generate_reply(
                instructions="الإيميل المصحح غير صحيح. اطلب إيميل صحيح يحتوي على @ و ."
            )
            return

        self._confirmed_email = correct_email.lower().strip()
        logger.info(f"✅ Email corrected to: {self._confirmed_email}")

        # Complete the task with corrected email (BEFORE generating reply to avoid race condition)
        result = EmailResult(email_address=self._confirmed_email)
        self.complete(result)

        # Then thank the customer
        await context.session.generate_reply(
            instructions=f"اعتذر واشكره. الإيميل الصحيح: {self._confirmed_email}"
        )


# ==========================================
# TASK GROUP: COLLECT ALL CONTACT INFO
# ==========================================

class ContactCollectionGroup(TaskGroup):
    """
    Workflow to collect: Name, Phone, and Email (all with confirmation)

    Each piece of information is collected separately and confirmed with the user.

    Usage in your agent:

    @function_tool()
    async def collect_contact_info(self, context: RunContext) -> str:
        '''Collect customer contact information'''
        task_group = ContactCollectionGroup(chat_ctx=self.chat_ctx)
        results = await task_group

        # Access the results from three separate tasks
        name = results.task_results['name'].name
        phone = results.task_results['phone'].phone_number
        email = results.task_results['email'].email_address

        # Store in your database
        contact_data = {
            'name': name,
            'phone': phone,
            'email': email
        }

        # Save to database here...

        return f"تم تسجيل معلومات {name}"
    """

    def __init__(self, chat_ctx=None):
        super().__init__(summarize_chat_ctx=True)

        # Task 1: Get name (with confirmation)
        self.add(
            lambda: GetNameTask(chat_ctx=chat_ctx),
            id="name",
            description="جمع اسم العميل الكامل مع التأكيد"
        )

        # Task 2: Get phone number (with confirmation)
        self.add(
            lambda: GetPhoneTask(chat_ctx=chat_ctx),
            id="phone",
            description="جمع رقم جوال العميل مع التأكيد"
        )

        # Task 3: Get email (with confirmation)
        self.add(
            lambda: GetEmailTask(chat_ctx=chat_ctx),
            id="email",
            description="جمع الإيميل مع التأكيد"
        )


# ==========================================
# HELPER FUNCTIONS (Mix and Match!)
# ==========================================

async def collect_contact_information(chat_ctx=None) -> dict:
    """
    Collect ALL: name, phone, and email (all confirmed)

    Returns:
        dict with keys: name, phone, email
    """
    task_group = ContactCollectionGroup(chat_ctx=chat_ctx)
    results = await task_group

    return {
        'name': results.task_results['name'].name,
        'phone': results.task_results['phone'].phone_number,
        'email': results.task_results['email'].email_address
    }


async def collect_name_and_email(chat_ctx=None) -> dict:
    """
    Collect ONLY name and email (skip phone)

    Returns:
        dict with keys: name, email
    """
    task_group = TaskGroup()

    task_group.add(
        lambda: GetNameTask(chat_ctx=chat_ctx),
        id="name",
        description="جمع الاسم"
    )

    task_group.add(
        lambda: GetEmailTask(chat_ctx=chat_ctx),
        id="email",
        description="جمع الإيميل"
    )

    results = await task_group

    return {
        'name': results.task_results['name'].name,
        'email': results.task_results['email'].email_address
    }


async def collect_name_and_phone(chat_ctx=None) -> dict:
    """
    Collect ONLY name and phone (skip email)

    Returns:
        dict with keys: name, phone
    """
    task_group = TaskGroup()

    task_group.add(
        lambda: GetNameTask(chat_ctx=chat_ctx),
        id="name",
        description="جمع الاسم"
    )

    task_group.add(
        lambda: GetPhoneTask(chat_ctx=chat_ctx),
        id="phone",
        description="جمع رقم الجوال"
    )

    results = await task_group

    return {
        'name': results.task_results['name'].name,
        'phone': results.task_results['phone'].phone_number
    }


async def collect_name_only(chat_ctx=None) -> dict:
    """
    Collect ONLY name (no phone, no email)

    Returns:
        dict with key: name
    """
    task = GetNameTask(chat_ctx=chat_ctx)
    result = await task

    return {
        'name': result.name
    }


async def collect_phone_only(chat_ctx=None) -> dict:
    """
    Collect ONLY phone (no name, no email)

    Returns:
        dict with key: phone
    """
    task = GetPhoneTask(chat_ctx=chat_ctx)
    result = await task

    return {
        'phone': result.phone_number
    }


async def collect_email_only(chat_ctx=None) -> dict:
    """
    Collect ONLY email (no name, no phone)

    Returns:
        dict with key: email
    """
    task = GetEmailTask(chat_ctx=chat_ctx)
    result = await task

    return {
        'email': result.email_address
    }
