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
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))
    last_used = db.Column(db.DateTime, nullable=True)  # Track when agent was last used

    # Inbound call fields
    call_type = db.Column(db.String(10), default='outbound')  # 'inbound' or 'outbound'
    dispatch_rule_id = db.Column(db.String(50), nullable=True)  # LiveKit SIP dispatch rule ID
    phone_number = db.Column(db.String(20), nullable=True)  # Inbound phone number
    inbound_trunk_id = db.Column(db.String(100), nullable=True)  # LiveKit inbound trunk ID

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

    # Stats for monitoring
    total_calls = db.Column(db.Integer, default=0)
    successful_calls = db.Column(db.Integer, default=0)
    failed_calls = db.Column(db.Integer, default=0)
    last_triggered_at = db.Column(db.DateTime, nullable=True)

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

