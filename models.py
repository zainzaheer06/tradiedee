"""
Database Models for NevoxAI Voice Agent Platform
"""
from datetime import datetime, timezone, timedelta
from flask_sqlalchemy import SQLAlchemy

# Saudi Arabia Timezone (UTC+3)
# All new timestamps will use Saudi time going forward
SAUDI_TZ = timezone(timedelta(hours=3))

db = SQLAlchemy()


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_approved = db.Column(db.Boolean, default=False)
    is_email_verified = db.Column(db.Boolean, default=False)
    email_verified_at = db.Column(db.DateTime, nullable=True)
    minutes_balance = db.Column(db.Integer, default=0)
    minutes_used = db.Column(db.Integer, default=0)  # Track total minutes used
    subscription_plan = db.Column(db.String(50), default='free')  # free, basic, pro, enterprise
    subscription_start_date = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))

    # SIP Trunk Configuration (for outbound calls)
    outbound_trunk_id = db.Column(db.String(100), nullable=True)
    outbound_phone_number = db.Column(db.String(20), nullable=True)  # Phone number for the outbound trunk
    sip_configured = db.Column(db.Boolean, default=False)
    sip_configured_at = db.Column(db.DateTime, nullable=True)
    sip_notes = db.Column(db.Text, nullable=True)

    agents = db.relationship('Agent', backref='user', lazy=True, cascade='all, delete-orphan')
    call_logs = db.relationship('CallLog', backref='user', lazy=True, cascade='all, delete-orphan')

class Agent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user_agent_number = db.Column(db.Integer, nullable=True)  # User-specific sequential number
    name = db.Column(db.String(100), nullable=False)
    prompt = db.Column(db.Text, nullable=False)
    greeting = db.Column(db.Text, default='السلام عليكم ورحمة الله وبركاته، أهلاً وسهلاً فيك. أنا مساعدك الذكي، كيف أقدر أساعدك اليوم؟')  # Fixed greeting message
    voice_id = db.Column(db.String(100), default='G1L6zhS0TTaBvSr18eUY')
    voice_name = db.Column(db.String(50), default='Fatima')
    temperature = db.Column(db.Float, default=0.4, nullable=True)  # LLM temperature (0.2-0.8) - controls response creativity
    voice_speed = db.Column(db.Float, default=0.90)  # TTS voice speed (0.5-2.0) - controls speaking rate
    vad_mode = db.Column(db.String(20), default='dynamic')  # 'precise' (no VAD), 'natural' (semantic), 'dynamic' (server VAD)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))
    last_used = db.Column(db.DateTime, nullable=True)  # Track when agent was last used

    # Inbound call fields
    call_type = db.Column(db.String(10), default='outbound')  # 'inbound' or 'outbound'
    dispatch_rule_id = db.Column(db.String(50), nullable=True)  # LiveKit SIP dispatch rule ID
    phone_number = db.Column(db.String(20), nullable=True)  # Inbound phone number
    inbound_trunk_id = db.Column(db.String(100), nullable=True)  # LiveKit inbound trunk ID

    # Agent Handoffs - list of agent IDs this agent can transfer to
    transfer_targets = db.Column(db.JSON, nullable=True)  # e.g. [2, 3, 4]

    # Workflow integration for n8n
    workflow_id = db.Column(db.Integer, db.ForeignKey('workflow.id'), nullable=True)

    call_logs = db.relationship('CallLog', backref='agent', lazy=True, cascade='all, delete-orphan')
    workflow = db.relationship('Workflow', back_populates='agents')

class InboundConfiguration(db.Model):
    """Inbound call configuration - links phone numbers to agents without duplication"""
    __tablename__ = 'inbound_configuration'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)  # e.g., "Main Office Line"
    agent_id = db.Column(db.Integer, db.ForeignKey('agent.id'), nullable=False)  # Links to existing agent
    phone_number = db.Column(db.String(20), nullable=False, unique=True)  # Unique phone number
    dispatch_rule_id = db.Column(db.String(50), nullable=True)  # LiveKit SIP dispatch rule ID
    trunk_id = db.Column(db.String(100), nullable=True)  # LiveKit trunk ID
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))

    # Relationships
    user = db.relationship('User', backref='inbound_configurations')
    agent = db.relationship('Agent', backref='inbound_configurations')

    # Database-level unique constraint on phone_number
    __table_args__ = (
        db.UniqueConstraint('phone_number', name='uq_inbound_phone_number'),
    )

class CallLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    agent_id = db.Column(db.Integer, db.ForeignKey('agent.id'), nullable=True)
    from_number = db.Column(db.String(20), nullable=False)
    to_number = db.Column(db.String(20), nullable=False)
    duration_seconds = db.Column(db.Integer, default=0)
    minutes_used = db.Column(db.Integer, default=0)
    transcription = db.Column(db.Text, default='')
    transcription_data = db.Column(db.Text, default='{}')  # JSON string with full conversation metadata
    sentiment_summary = db.Column(db.Text, default='{}')  # JSON string with sentiment analysis
    room_name = db.Column(db.String(100))
    status = db.Column(db.String(20), default='completed')
    recording_url = db.Column(db.String(500), nullable=True)
    recording_id = db.Column(db.String(100), nullable=True)
    call_type = db.Column(db.String(10), default='outbound')  # 'inbound' or 'outbound'
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))

class Campaign(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user_campaign_number = db.Column(db.Integer, nullable=True)  # User-specific sequential number
    agent_id = db.Column(db.Integer, db.ForeignKey('agent.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default='draft')  # draft, running, paused, completed, stopped
    start_time = db.Column(db.DateTime, nullable=True)
    end_time = db.Column(db.DateTime, nullable=True)
    call_window_start = db.Column(db.String(5), default='09:00')  # e.g., '09:00'
    call_window_end = db.Column(db.String(5), default='18:00')    # e.g., '18:00'
    concurrent_calls = db.Column(db.Integer, default=5)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None), onupdate=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))

    contacts = db.relationship('CampaignContact', backref='campaign', lazy=True, cascade='all, delete-orphan')
    agent = db.relationship('Agent', backref='campaigns', lazy=True)

class CampaignContact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaign.id'), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(100))
    status = db.Column(db.String(20), default='pending')  # pending, calling, completed, failed, no_answer
    interest_level = db.Column(db.String(20))  # Interested, Not Interested
    duration = db.Column(db.Integer, default=0)
    attempts = db.Column(db.Integer, default=0)
    transcription = db.Column(db.Text)
    room_name = db.Column(db.String(100))
    last_attempt = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))

class KnowledgeBase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey('agent.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_type = db.Column(db.String(50))
    file_size = db.Column(db.Integer)
    status = db.Column(db.String(20), default='processing')  # processing, ready, failed
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None), onupdate=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))

class Tool(db.Model):
    """Custom tools that can be dynamically loaded into agents"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    tool_type = db.Column(db.String(20), nullable=False)  # api_call, webhook, rpc
    config = db.Column(db.Text, nullable=False)  # JSON configuration
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None), onupdate=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))

    user = db.relationship('User', backref='tools')
    agents = db.relationship('Agent', secondary='agent_tool', backref='tools')

class AgentTool(db.Model):
    """Many-to-many relationship between agents and tools"""
    __tablename__ = 'agent_tool'
    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey('agent.id'), nullable=False)
    tool_id = db.Column(db.Integer, db.ForeignKey('tool.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))

    __table_args__ = (db.UniqueConstraint('agent_id', 'tool_id', name='uq_agent_tool'),)


class Workflow(db.Model):
    """User-defined workflows for n8n integration with API key authentication"""
    __tablename__ = 'workflow'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    webhook_url = db.Column(db.String(500), nullable=False)
    api_key = db.Column(db.String(64), nullable=False, unique=True)  # Secure random API key
    is_active = db.Column(db.Boolean, default=True)

    post_call_enabled = db.Column(db.Boolean, default=True)  # Enable/disable post-call webhook

    # PRE-call webhook (optional - triggered before call starts to fetch customer data)
    pre_call_enabled = db.Column(db.Boolean, default=False)
    pre_call_webhook_url = db.Column(db.String(500), nullable=True)  # If None, uses webhook_url
    pre_call_timeout = db.Column(db.Integer, default=3)  # Timeout in seconds

    # Stats for monitoring
    total_calls = db.Column(db.Integer, default=0)
    successful_calls = db.Column(db.Integer, default=0)
    failed_calls = db.Column(db.Integer, default=0)
    last_triggered_at = db.Column(db.DateTime, nullable=True)

    # Clinic Platform Phase 2 fields
    clinic_feature_type = db.Column(db.String(50), nullable=True)
    # Values: 'appointment_booking', 'noshow_recovery', 'patient_reminders', 'vaccination_campaign', 'new_patient_intake'
    clinic_config = db.Column(db.JSON, nullable=True)
    # Stores feature-specific config as JSON

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None), onupdate=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))

    # Relationships
    user = db.relationship('User', backref='workflows')
    agents = db.relationship('Agent', back_populates='workflow')

    def __repr__(self):
        return f'<Workflow {self.name}>'


class WebhookLog(db.Model):
    """Log all webhook attempts for debugging and monitoring"""
    __tablename__ = 'webhook_log'

    id = db.Column(db.Integer, primary_key=True)
    workflow_id = db.Column(db.Integer, db.ForeignKey('workflow.id'), nullable=False)
    call_log_id = db.Column(db.Integer, db.ForeignKey('call_log.id'), nullable=True)

    status = db.Column(db.String(20))  # success, failed, retrying
    http_status = db.Column(db.Integer, nullable=True)
    request_payload = db.Column(db.Text)  # JSON payload sent
    response_body = db.Column(db.Text, nullable=True)
    error_message = db.Column(db.Text, nullable=True)

    retry_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))

    workflow = db.relationship('Workflow', backref='logs')
    call_log = db.relationship('CallLog', backref='webhook_logs')


class ApiKey(db.Model):
    """
    API Keys for external integrations
    One key per user - used for /api/v1/* endpoints
    """
    __tablename__ = 'api_key'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)  # One key per user

    # Security: Store hashed key, never raw
    key_hash = db.Column(db.String(64), unique=True, nullable=False)  # SHA-256 hash
    key_prefix = db.Column(db.String(12), nullable=False)  # "nvx_a1b2..." for display

    name = db.Column(db.String(100), default='Default API Key')
    is_active = db.Column(db.Boolean, default=True)

    # Usage tracking
    last_used_at = db.Column(db.DateTime, nullable=True)
    total_calls = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))
    revoked_at = db.Column(db.DateTime, nullable=True)

    # Relationship
    user = db.relationship('User', backref=db.backref('api_key', uselist=False))

    def __repr__(self):
        return f'<ApiKey {self.key_prefix}... user_id={self.user_id}>'


class WhatsAppAgent(db.Model):
    """WhatsApp AI Agent - connects an existing Agent to WhatsApp via auto-generated n8n workflow"""
    __tablename__ = 'whatsapp_agent'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    agent_id = db.Column(db.Integer, db.ForeignKey('agent.id'), nullable=False)

    # Display
    name = db.Column(db.String(100), nullable=False)

    # WhatsApp Provider
    whatsapp_provider = db.Column(db.String(50), default='whapi')  # whapi, meta, unifonic, custom

    # WhatsApp API Configuration (provider-agnostic)
    whatsapp_api_url = db.Column(db.String(500), nullable=True)   # WhatsApp API base URL (not needed for Meta)
    whatsapp_api_key = db.Column(db.String(255), nullable=True)   # Bearer token (not needed for Meta)
    whatsapp_phone_number = db.Column(db.String(20), nullable=True)  # Business phone number

    # Meta Official API fields
    meta_phone_number_id = db.Column(db.String(100), nullable=True)   # Phone Number ID from Facebook Developer Dashboard
    meta_business_account_id = db.Column(db.String(100), nullable=True)  # WhatsApp Business Account ID
    meta_access_token = db.Column(db.String(500), nullable=True)      # Permanent System User Access Token
    meta_app_secret = db.Column(db.String(255), nullable=True)        # App Secret for webhook signature verification
    meta_verify_token = db.Column(db.String(100), nullable=True)      # Webhook verify token (user-defined)
    meta_webhook_verified = db.Column(db.Boolean, default=False)      # Whether webhook verification succeeded

    # Custom endpoint URLs (used when provider='custom')
    send_text_endpoint = db.Column(db.String(500), nullable=True)  # Full URL for sending text messages
    send_voice_endpoint = db.Column(db.String(500), nullable=True)  # Full URL for sending voice messages

    # WhatsApp-specific system prompt (layered on top of agent.prompt)
    whatsapp_system_prompt = db.Column(db.Text, nullable=True)

    # Feature toggles
    enable_voice_response = db.Column(db.Boolean, default=False)  # Reply with voice messages
    enable_image_analysis = db.Column(db.Boolean, default=True)   # Analyze incoming images
    enable_document_analysis = db.Column(db.Boolean, default=True)  # Analyze incoming PDFs
    memory_window = db.Column(db.Integer, default=10)  # Conversation memory size

    # n8n Workflow tracking
    n8n_workflow_id = db.Column(db.String(100), nullable=True)  # ID returned by n8n API
    n8n_workflow_active = db.Column(db.Boolean, default=False)
    webhook_path = db.Column(db.String(200), nullable=True, unique=True)  # Unique webhook slug

    # Status
    is_active = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default='draft')  # draft, deploying, active, paused, error
    error_message = db.Column(db.Text, nullable=True)

    # Stats
    total_messages = db.Column(db.Integer, default=0)
    total_conversations = db.Column(db.Integer, default=0)
    last_message_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None),
                           onupdate=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))

    # Relationships
    user = db.relationship('User', backref='whatsapp_agents')
    agent = db.relationship('Agent', backref='whatsapp_agents')

    def __repr__(self):
        return f'<WhatsAppAgent {self.name} (status={self.status})>'

    @property
    def effective_prompt(self):
        """Combine agent prompt + WhatsApp system prompt"""
        base = self.agent.prompt if self.agent else ''
        if self.whatsapp_system_prompt:
            return f"{base}\n\n--- WhatsApp-Specific Instructions ---\n{self.whatsapp_system_prompt}"
        return base


# ============================================================================
# PHASE 1: CALLTRADIE FEATURES - Scheduling, Emergency, Address Validation
# ============================================================================

class Business(db.Model):
    """Represents a trades business (electrician, plumber, etc.)"""
    __tablename__ = 'business'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)

    # Business Info
    business_name = db.Column(db.String(200), nullable=False)
    business_type = db.Column(db.String(100))  # electrician, plumber, hvac, etc
    phone_number = db.Column(db.String(20), unique=True)

    # Configuration
    greeting_message = db.Column(db.Text)
    after_hours_enabled = db.Column(db.Boolean, default=True)
    tone = db.Column(db.String(20), default='friendly')  # professional, friendly

    # Service areas (JSON: ["Alexandria", "Parramatta"])
    service_areas = db.Column(db.JSON)

    # Working hours
    working_hours_start = db.Column(db.String(5), default='08:00')
    working_hours_end = db.Column(db.String(5), default='17:00')
    timezone = db.Column(db.String(50), default='Australia/Sydney')

    # Availability checking
    availability_check_enabled = db.Column(db.Boolean, default=True)
    availability_check_method = db.Column(db.String(50), default='serviceM8')  # serviceM8, calcom, manual

    # Fallback contacts
    backup_business_phone = db.Column(db.String(20))
    backup_business_name = db.Column(db.String(100))

    # Emergency Configuration (JSON: [{"name": "John", "phone": "+61...", "priority": 1}, ...])
    emergency_contacts = db.Column(db.JSON)
    emergency_escalation_enabled = db.Column(db.Boolean, default=True)
    emergency_transfer_timeout = db.Column(db.Integer, default=30)

    # ServiceM8 Integration
    serviceM8_enabled = db.Column(db.Boolean, default=False)
    serviceM8_api_key = db.Column(db.String(200))
    serviceM8_customer_id = db.Column(db.String(100))

    # Cal.com Integration
    calcom_enabled = db.Column(db.Boolean, default=False)
    calcom_api_key = db.Column(db.String(200))
    calcom_event_type_id = db.Column(db.String(100))

    # Twilio
    twilio_account_sid = db.Column(db.String(100))
    twilio_auth_token = db.Column(db.String(100))
    twilio_phone_number = db.Column(db.String(20))

    # Google Maps API
    google_api_key = db.Column(db.String(200))

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None),
                          onupdate=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))

    # Relationships
    user = db.relationship('User', backref='business', uselist=False)
    jobs = db.relationship('Job', backref='business', lazy=True, cascade='all')

    def __repr__(self):
        return f'<Business {self.business_name}>'


class Customer(db.Model):
    """Represents a customer of a trades business"""
    __tablename__ = 'customer'

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)

    name = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    address = db.Column(db.Text)
    suburb = db.Column(db.String(100))
    postcode = db.Column(db.String(10))
    notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None),
                          onupdate=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))

    # Relationships
    business = db.relationship('Business', backref='customers')
    jobs = db.relationship('Job', backref='customer', lazy=True)

    def __repr__(self):
        return f'<Customer {self.name} - {self.phone}>'


class Job(db.Model):
    """Represents a service job/appointment"""
    __tablename__ = 'job'

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=True)  # Nullable for AI-created jobs
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=True)

    # Customer Info
    customer_name = db.Column(db.String(100), nullable=True)  # Nullable - extracted by AI
    customer_phone = db.Column(db.String(20), nullable=True)  # Nullable - extracted by AI
    customer_email = db.Column(db.String(120))
    customer_address = db.Column(db.Text, nullable=True)  # Nullable - extracted by AI
    customer_suburb = db.Column(db.String(100), nullable=True)  # Nullable - extracted by AI
    customer_postcode = db.Column(db.String(10), nullable=True)  # Nullable - extracted by AI

    # Job Details
    job_type = db.Column(db.String(100), nullable=True)  # Nullable - extracted by AI
    description = db.Column(db.Text, nullable=True)  # Nullable - extracted by AI

    # Urgency & Priority
    urgency = db.Column(db.String(20), default='normal')  # low, normal, high, emergency
    is_emergency = db.Column(db.Boolean, default=False)
    emergency_keywords_detected = db.Column(db.JSON)  # e.g., ["burst pipe", "flooding"]

    # Scheduling
    preferred_datetime = db.Column(db.DateTime)
    scheduled_datetime = db.Column(db.DateTime)

    # Status workflow
    status = db.Column(db.String(20), default='new')
    # new -> scheduled -> assigned -> on_the_way -> in_progress -> completed -> invoiced

    # Tracking
    estimated_duration_minutes = db.Column(db.Integer, default=60)
    actual_duration_minutes = db.Column(db.Integer)
    completion_notes = db.Column(db.Text)

    # Call & Transcription
    original_call_id = db.Column(db.Integer, db.ForeignKey('call_log.id'))
    call_transcript = db.Column(db.Text)
    call_summary = db.Column(db.Text)  # AI-generated summary
    recording_url = db.Column(db.String(500))

    # Booking confirmation
    booking_confirmed_at = db.Column(db.DateTime)
    confirmation_sms_sent = db.Column(db.Boolean, default=False)
    reminder_sms_sent = db.Column(db.Boolean, default=False)

    # ServiceM8 Integration
    serviceM8_job_id = db.Column(db.String(100))
    serviceM8_sync_status = db.Column(db.String(20))  # pending, synced, failed

    # Cal.com Integration
    calcom_booking_id = db.Column(db.String(100))
    calendar_event_url = db.Column(db.String(500))

    # Address Validation
    address_validated = db.Column(db.Boolean, default=False)
    address_validation_status = db.Column(db.String(20))  # pending, validated, invalid, corrected
    address_components = db.Column(db.JSON)  # Parsed address from Google Maps
    address_coordinates = db.Column(db.JSON)  # {'lat': -33.xxx, 'lng': 151.xxx}

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None),
                          onupdate=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))

    def __repr__(self):
        return f'<Job {self.customer_name} - {self.job_type}>'

    @property
    def is_overdue(self):
        """Check if job is overdue"""
        if self.scheduled_datetime:
            return datetime.now(SAUDI_TZ).replace(tzinfo=None) > self.scheduled_datetime
        return False


class EmergencyEscalationLog(db.Model):
    """Track emergency escalations"""
    __tablename__ = 'emergency_escalation_log'

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'))

    emergency_keywords = db.Column(db.JSON)  # Detected keywords

    # Escalation attempts
    contact_1_name = db.Column(db.String(100))
    contact_1_phone = db.Column(db.String(20))
    contact_1_status = db.Column(db.String(20))  # not_called, ringing, answered, no_answer, failed

    contact_2_name = db.Column(db.String(100))
    contact_2_phone = db.Column(db.String(20))
    contact_2_status = db.Column(db.String(20))

    contact_3_name = db.Column(db.String(100))
    contact_3_phone = db.Column(db.String(20))
    contact_3_status = db.Column(db.String(20))

    # SMS fallback
    sms_sent_to = db.Column(db.JSON)  # ['contact1', 'contact2', 'contact3']
    sms_sent_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))

    def __repr__(self):
        return f'<EmergencyEscalation Job#{self.job_id}>'


class SMSLog(db.Model):
    """Track all SMS sent"""
    __tablename__ = 'sms_log'

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'))
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'))

    recipient_phone = db.Column(db.String(20), nullable=False)
    message_type = db.Column(db.String(50))  # booking_confirmation, reminder, technician_eta, completion, review_request
    message_body = db.Column(db.Text, nullable=False)

    twilio_message_id = db.Column(db.String(100))
    status = db.Column(db.String(20), default='sent')  # sent, delivered, failed

    sent_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))

    def __repr__(self):
        return f'<SMS {self.message_type} to {self.recipient_phone}>'


class AddressValidationLog(db.Model):
    """Track address validation attempts"""
    __tablename__ = 'address_validation_log'

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'))

    input_address = db.Column(db.Text)
    validated_address = db.Column(db.Text)

    validation_status = db.Column(db.String(20))  # validated, invalid, suggestion_offered
    coordinates = db.Column(db.JSON)  # {'lat': -33.xxx, 'lng': 151.xxx}

    attempt_number = db.Column(db.Integer, default=1)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))

    def __repr__(self):
        return f'<AddressValidation status={self.validation_status}>'

