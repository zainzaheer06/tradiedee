import os
import math
import json
import re
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import joinedload
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import asyncio
from livekit import api
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from services.recording_service import recording_service

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///voice_agent.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Email Configuration
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True') == 'True'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER')

db = SQLAlchemy(app)
mail = Mail(app)

# Email token serializer
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

# Helper function to clean text
def clean_text(text):
    """Remove extra spaces and normalize whitespace"""
    if not text:
        return text

    # Replace multiple spaces with single space
    text = re.sub(r' +', ' ', text)

    # Replace multiple newlines with max 2 newlines
    text = re.sub(r'\n\n\n+', '\n\n', text)

    # Remove trailing spaces on each line
    text = '\n'.join(line.rstrip() for line in text.split('\n'))

    # Strip leading/trailing whitespace from entire text
    text = text.strip()

    return text

# Custom Jinja2 filter for JSON parsing
@app.template_filter('from_json')
def from_json_filter(value):
    """Parse JSON string to Python object"""
    if not value or value == '{}':
        return {}
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {}

# --- Models ---
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
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

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
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_used = db.Column(db.DateTime, nullable=True)  # Track when agent was last used

    # Inbound call fields
    call_type = db.Column(db.String(10), default='outbound')  # 'inbound' or 'outbound'
    dispatch_rule_id = db.Column(db.String(50), nullable=True)  # LiveKit SIP dispatch rule ID
    phone_number = db.Column(db.String(20), nullable=True)  # Inbound phone number
    inbound_trunk_id = db.Column(db.String(100), nullable=True)  # LiveKit inbound trunk ID

    call_logs = db.relationship('CallLog', backref='agent', lazy=True, cascade='all, delete-orphan')

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
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

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
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

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
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

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
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class KnowledgeBase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey('agent.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_type = db.Column(db.String(50))
    file_size = db.Column(db.Integer)
    status = db.Column(db.String(20), default='processing')  # processing, ready, failed
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class Tool(db.Model):
    """Custom tools that can be dynamically loaded into agents"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    tool_type = db.Column(db.String(20), nullable=False)  # api_call, webhook, rpc
    config = db.Column(db.Text, nullable=False)  # JSON configuration
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref='tools')
    agents = db.relationship('Agent', secondary='agent_tool', backref='tools')

class AgentTool(db.Model):
    """Many-to-many relationship between agents and tools"""
    __tablename__ = 'agent_tool'
    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey('agent.id'), nullable=False)
    tool_id = db.Column(db.Integer, db.ForeignKey('tool.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (db.UniqueConstraint('agent_id', 'tool_id', name='uq_agent_tool'),)

# --- Email Helper Functions ---
def generate_verification_token(email):
    """Generate a time-sensitive email verification token"""
    return serializer.dumps(email, salt='email-verification')

def verify_token(token, expiration=3600):
    """Verify the email token (default: 1 hour expiration)"""
    try:
        email = serializer.loads(token, salt='email-verification', max_age=expiration)
        return email
    except (SignatureExpired, BadSignature):
        return None

def send_verification_email(user_email, username):
    """Send email verification link to user"""
    try:
        token = generate_verification_token(user_email)
        verify_url = url_for('verify_email', token=token, _external=True)

        msg = Message(
            subject='Verify Your Email - Voice Agent Platform',
            recipients=[user_email],
            html=render_template('emails/verify_email.html',
                               username=username,
                               verify_url=verify_url)
        )

        mail.send(msg)
        logger.info(f"Verification email sent to {user_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send verification email to {user_email}: {e}")
        return False

def send_approval_notification(user_email, username):
    """Send notification when admin approves the account"""
    try:
        msg = Message(
            subject='Account Approved - Voice Agent Platform',
            recipients=[user_email],
            html=render_template('emails/account_approved.html',
                               username=username,
                               login_url=url_for('login', _external=True))
        )

        mail.send(msg)
        logger.info(f"Approval notification sent to {user_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send approval notification to {user_email}: {e}")
        return False

# --- Helper Functions ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first', 'warning')
            return redirect(url_for('login'))
        user = User.query.get(session['user_id'])
        if not user or not user.is_admin:
            flash('Admin access required', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def approved_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = db.session.get(User, session['user_id'])
        if not user.is_approved and not user.is_admin:
            flash('Your account is pending admin approval', 'warning')
            return redirect(url_for('pending_approval'))
        return f(*args, **kwargs)
    return decorated_function

# --- Routes ---
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/homepage')
def homepage():
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'danger')
            return redirect(url_for('signup'))

        if User.query.filter_by(email=email).first():
            flash('Email already exists', 'danger')
            return redirect(url_for('signup'))

        hashed_password = generate_password_hash(password)
        new_user = User(
            username=username,
            email=email,
            password=hashed_password,
            is_approved=False,
            is_email_verified=False,
            minutes_balance=0
        )

        db.session.add(new_user)
        db.session.commit()

        # Send verification email
        if send_verification_email(email, username):
            flash('Account created! Please check your email to verify your account.', 'success')
        else:
            flash('Account created, but failed to send verification email. Please contact support.', 'warning')

        return redirect(url_for('login'))

    return render_template('auth/signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['is_admin'] = user.is_admin
            session['minutes_balance'] = user.minutes_balance
            flash(f'Welcome back, {user.username}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'danger')

    return render_template('auth/login.html')

@app.route('/verify-email/<token>')
def verify_email(token):
    """Verify user email address using the token"""
    email = verify_token(token)

    if not email:
        flash('The verification link is invalid or has expired.', 'danger')
        return redirect(url_for('login'))

    user = User.query.filter_by(email=email).first()

    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('login'))

    if user.is_email_verified:
        flash('Email already verified. You can log in now.', 'success')
        return redirect(url_for('login'))

    user.is_email_verified = True
    user.email_verified_at = datetime.now(timezone.utc)
    db.session.commit()

    flash('Email verified successfully! Please wait for admin approval to access your account.', 'success')
    return redirect(url_for('login'))

@app.route('/resend-verification', methods=['POST'])
def resend_verification():
    """Resend verification email"""
    email = request.form.get('email')
    user = User.query.filter_by(email=email).first()

    if not user:
        flash('Email not found.', 'danger')
        return redirect(url_for('login'))

    if user.is_email_verified:
        flash('Email is already verified.', 'success')
        return redirect(url_for('login'))

    if send_verification_email(user.email, user.username):
        flash('Verification email sent! Please check your inbox.', 'success')
    else:
        flash('Failed to send verification email. Please try again later.', 'danger')

    return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('login'))

@app.route('/pending-approval')
@login_required
def pending_approval():
    return render_template('auth/pending_approval.html')

@app.route('/dashboard')
@login_required
@approved_required
def dashboard():
    user = db.session.get(User, session['user_id'])

    if user.is_admin:
        return redirect(url_for('admin_dashboard'))

    agents = Agent.query.filter_by(user_id=user.id).all()
    recent_calls = CallLog.query.filter_by(user_id=user.id).order_by(CallLog.created_at.desc()).limit(10).all()
    total_calls = CallLog.query.filter_by(user_id=user.id).count()

    return render_template('user/user_dashboard.html', user=user, agents=agents, recent_calls=recent_calls, total_calls=total_calls, datetime=datetime)

@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    users = User.query.filter_by(is_admin=False).all()
    pending_users = User.query.filter_by(is_approved=False, is_admin=False).all()
    total_calls = CallLog.query.count()
    total_minutes = db.session.query(db.func.sum(CallLog.minutes_used)).scalar() or 0

    return render_template('admin/admin_dashboard.html',
                         users=users,
                         pending_users=pending_users,
                         total_calls=total_calls,
                         total_minutes=total_minutes)

@app.route('/admin/approve-user/<int:user_id>')
@login_required
@admin_required
def approve_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_approved = True
    user.minutes_balance = 500  # Give 500 free minutes
    user.subscription_plan = 'free'
    user.subscription_start_date = datetime.now(timezone.utc)  # Set subscription start date
    db.session.commit()

    # Send approval notification email
    send_approval_notification(user.email, user.username)

    flash(f'User {user.username} approved with 500 free minutes', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/add-minutes/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def add_minutes(user_id):
    user = User.query.get_or_404(user_id)
    minutes = int(request.form.get('minutes', 0))
    user.minutes_balance += minutes
    db.session.commit()
    flash(f'Added {minutes} minutes to {user.username}', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/trunk-management')
@login_required
@admin_required
def trunk_management():
    """View and manage SIP trunk configuration for all users"""
    users = User.query.filter_by(is_admin=False).order_by(User.username).all()
    return render_template('admin/admin_trunk_management.html', users=users)

@app.route('/admin/configure-trunk/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def configure_user_trunk(user_id):
    """Configure SIP trunk for a specific user"""
    user = User.query.get_or_404(user_id)

    if request.method == 'POST':
        outbound_trunk_id = request.form.get('outbound_trunk_id', '').strip()
        sip_notes = request.form.get('sip_notes', '').strip()

        # Update user trunk configuration
        user.outbound_trunk_id = outbound_trunk_id if outbound_trunk_id else None
        user.sip_configured = bool(outbound_trunk_id)
        user.sip_configured_at = datetime.now(timezone.utc) if outbound_trunk_id else None
        user.sip_notes = sip_notes if sip_notes else None

        db.session.commit()

        if outbound_trunk_id:
            flash(f'SIP trunk configured for {user.username}', 'success')
        else:
            flash(f'SIP trunk removed for {user.username}', 'success')

        return redirect(url_for('trunk_management'))

    return render_template('admin/admin_configure_trunk.html', user=user)

@app.route('/admin/remove-trunk/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def remove_user_trunk(user_id):
    """Remove SIP trunk configuration from a user"""
    user = User.query.get_or_404(user_id)

    user.outbound_trunk_id = None
    user.sip_configured = False
    user.sip_configured_at = None
    user.sip_notes = None

    db.session.commit()
    flash(f'SIP trunk removed from {user.username}', 'success')
    return redirect(url_for('trunk_management'))

@app.route('/admin/inbound-trunk-management')
@login_required
@admin_required
def inbound_trunk_management():
    """View and manage inbound SIP trunk configuration for inbound configurations"""
    # Get all inbound configurations from all users
    inbound_configs = InboundConfiguration.query.order_by(InboundConfiguration.created_at.desc()).all()
    return render_template('admin/admin_inbound_trunk_management.html', configs=inbound_configs)

@app.route('/admin/configure-inbound-trunk/<int:config_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def configure_inbound_trunk(config_id):
    """Configure inbound SIP trunk for a specific inbound configuration"""
    config = InboundConfiguration.query.get_or_404(config_id)

    if request.method == 'POST':
        inbound_trunk_id = request.form.get('inbound_trunk_id', '').strip()

        # Update configuration trunk
        config.trunk_id = inbound_trunk_id if inbound_trunk_id else None
        db.session.commit()

        if inbound_trunk_id:
            flash(f'Inbound trunk "{inbound_trunk_id}" configured for "{config.name}"', 'success')
        else:
            flash(f'Inbound trunk removed from "{config.name}"', 'success')

        return redirect(url_for('inbound_trunk_management'))

    return render_template('admin/admin_configure_inbound_trunk.html', config=config)

@app.route('/admin/remove-inbound-trunk/<int:config_id>', methods=['POST'])
@login_required
@admin_required
def remove_inbound_trunk(config_id):
    """Remove inbound SIP trunk from inbound configuration"""
    config = InboundConfiguration.query.get_or_404(config_id)

    config.trunk_id = None
    db.session.commit()

    flash(f'Inbound trunk removed from "{config.name}"', 'success')
    return redirect(url_for('inbound_trunk_management'))

@app.route('/agent/create', methods=['GET', 'POST'])
@login_required
@approved_required
def create_agent():
    # Redirect to new agents list page
    return redirect(url_for('agents_list'))

@app.route('/agents', methods=['GET'])
@login_required
@approved_required
def agents_list():
    """List all agents"""
    page = request.args.get('page', 1, type=int)
    per_page = 12  # 12 agents per page to match grid layout
    
    pagination = Agent.query.filter_by(user_id=session['user_id']).order_by(Agent.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    agents = pagination.items
    return render_template('agents/agents_list.html', agents=agents, pagination=pagination)

@app.route('/agent/new', methods=['GET', 'POST'])
@login_required
@approved_required
def new_agent_form():
    """Create new agent form"""
    # Voice ID to Name mapping
    voice_mapping = {
        'G1L6zhS0TTaBvSr18eUY': 'Fatima',
        '6XO1vwWJxHDXGcEu6pMV': 'Ayesha',
        'kgxi5e6hsB6HuAGpjbQ5': 'Hiba',
        'KjDucWgG5NYuMBznv52L': 'Zainab',
        'YdWLuz4rVsaG3kWAECFE': 'Ali'
    }

    if request.method == 'POST':
        name = request.form.get('name')
        prompt = clean_text(request.form.get('prompt'))
        greeting = clean_text(request.form.get('greeting', 'السلام عليكم ورحمة الله وبركاته، أهلاً وسهلاً فيك. أنا مساعدك الذكي، كيف أقدر أساعدك اليوم؟'))
        voice_id = request.form.get('voice_id', 'G1L6zhS0TTaBvSr18eUY')
        voice_name = voice_mapping.get(voice_id, 'Fatima')

        # Calculate next user-specific agent number
        max_agent = db.session.query(db.func.max(Agent.user_agent_number)).filter_by(user_id=session['user_id']).scalar()
        next_agent_number = (max_agent or 0) + 1

        new_agent = Agent(
            user_id=session['user_id'],
            user_agent_number=next_agent_number,
            name=name,
            prompt=prompt,
            greeting=greeting,
            voice_id=voice_id,
            voice_name=voice_name
        )

        db.session.add(new_agent)
        db.session.commit()

        flash(f'Agent "{name}" created successfully! You can now upload documents for the knowledge base.', 'success')
        return redirect(url_for('edit_agent_form', agent_id=new_agent.id))

    return render_template('agents/new_agent_form.html')

@app.route('/agent/<int:agent_id>/edit', methods=['GET', 'POST'])
@login_required
@approved_required
def edit_agent_form(agent_id):
    """Edit agent form"""
    agent = Agent.query.get_or_404(agent_id)

    # Check ownership
    if agent.user_id != session['user_id'] and not session.get('is_admin'):
        flash('Access denied', 'danger')
        return redirect(url_for('agents_list'))

    # Voice mapping
    voice_mapping = {
        'G1L6zhS0TTaBvSr18eUY': 'Fatima',
        '6XO1vwWJxHDXGcEu6pMV': 'Ayesha',
        'kgxi5e6hsB6HuAGpjbQ5': 'Hiba',
        'KjDucWgG5NYuMBznv52L': 'Zainab',
        'YdWLuz4rVsaG3kWAECFE': 'Ali'
    }

    if request.method == 'POST':
        # Update agent fields
        agent.name = request.form.get('name')
        agent.prompt = clean_text(request.form.get('prompt'))
        agent.greeting = clean_text(request.form.get('greeting', 'السلام عليكم ورحمة الله وبركاته، أهلاً وسهلاً فيك. أنا مساعدك الذكي، كيف أقدر أساعدك اليوم؟'))
        agent.voice_id = request.form.get('voice_id', 'G1L6zhS0TTaBvSr18eUY')
        agent.voice_name = voice_mapping.get(agent.voice_id, 'Fatima')

        db.session.commit()

        flash(f'Agent "{agent.name}" updated successfully!', 'success')
        return redirect(url_for('agents_list'))

    # Get knowledge base documents
    documents = KnowledgeBase.query.filter_by(agent_id=agent_id).order_by(KnowledgeBase.created_at.desc()).all()
    document_count = len(documents)

    return render_template('agents/new_agent_form.html', agent=agent, documents=documents, document_count=document_count)

@app.route('/agent/<int:agent_id>')
@login_required
@approved_required
def view_agent(agent_id):
    agent = Agent.query.get_or_404(agent_id)

    if agent.user_id != session['user_id'] and not session.get('is_admin'):
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))

    # Get call logs with pagination
    page = request.args.get('page', 1, type=int)
    per_page = 15  # Show 15 call logs per page
    
    call_logs_pagination = CallLog.query.filter_by(agent_id=agent_id).order_by(CallLog.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return render_template('agents/view_agent.html', agent=agent, call_logs=call_logs_pagination.items, pagination=call_logs_pagination)

@app.route('/agent/<int:agent_id>/delete', methods=['POST'])
@login_required
@approved_required
def delete_agent(agent_id):
    agent = Agent.query.get_or_404(agent_id)

    # Check ownership
    if agent.user_id != session['user_id'] and not session.get('is_admin'):
        flash('Access denied', 'danger')
        return redirect(url_for('agents_list'))

    agent_name = agent.name

    # Delete the agent (cascade will delete associated call logs)
    db.session.delete(agent)
    db.session.commit()

    flash(f'Agent "{agent_name}" deleted successfully!', 'success')
    return redirect(url_for('agents_list'))

def format_saudi_phone_number(phone_number: str) -> str:
    """
    Format phone numbers to E.164 format (WITH + sign: +966XXXXXXXXX)

    E.164 format required by Twilio and most SIP providers

    Examples:
        0115108724 -> +966115108724
        0512345678 -> +966512345678
        +966115108724 -> +966115108724
        966115108724 -> +966115108724
        +923067689694 -> +923067689694 (Pakistan number)
    """
    # Remove all spaces, dashes, parentheses
    cleaned = phone_number.strip().replace(' ', '').replace('-', '').replace('(', '').replace(')', '')

    # Already has + sign, just return it
    if cleaned.startswith('+'):
        return cleaned

    # Already has country code without + sign
    if cleaned.startswith('966') or cleaned.startswith('92') or cleaned.startswith('1'):
        return '+' + cleaned

    # Saudi local number starting with 0
    if cleaned.startswith('0'):
        return '+966' + cleaned[1:]  # Remove leading 0 and add +966

    # Assume it's a Saudi local number without 0 prefix
    return '+966' + cleaned

@app.route('/agent/<int:agent_id>/make-call', methods=['POST'])
@login_required
@approved_required
def make_call_route(agent_id):
    agent = db.session.get(Agent, agent_id)
    if not agent:
        return jsonify({'error': 'Agent not found'}), 404
    user = db.session.get(User, session['user_id'])

    if agent.user_id != session['user_id']:
        return jsonify({'error': 'Access denied'}), 403

    phone_number = request.form.get('phone_number')

    if not phone_number:
        return jsonify({'error': 'Phone number required'}), 400

    # Format phone number (without + sign)
    formatted_number = phone_number

    # Check if user has minutes
    if user.minutes_balance <= 0:
        return jsonify({'error': 'Insufficient minutes'}), 400


    print(f"user_outbound_trunk_id: {user.outbound_trunk_id}")
    try:
        # Get user's outbound trunk (with fallback to default)
        outbound_trunk_id = user.outbound_trunk_id if user.outbound_trunk_id else os.environ.get('SIP_OUTBOUND_TRUNK_ID')

        print(f"outbound_trunk_id: {outbound_trunk_id}")

        if not outbound_trunk_id:
            return jsonify({'error': 'No outbound trunk configured. Please contact administrator.'}), 400

        # Make the call with formatted number
        room_name = f"call-{agent_id}-{datetime.now(timezone.utc).timestamp()}"
        asyncio.run(make_livekit_call(formatted_number, room_name, agent.name, outbound_trunk_id))

        # Create call log
        call_log = CallLog(
            user_id=user.id,
            agent_id=agent_id,
            from_number=os.environ.get('SAUDI_PHONE_NUMBER', '966115108724'),
            to_number=phone_number,
            room_name=room_name,
            status='initiated'
        )

        db.session.add(call_log)
        db.session.commit()

        flash('Call initiated successfully!', 'success')
        return jsonify({'success': True, 'call_id': call_log.id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

async def make_livekit_call(phone_number, room_name, agent_name, outbound_trunk_id):
    """Create a dispatch and add a SIP participant to call the phone number"""
    lkapi = api.LiveKitAPI()

    # Create agent dispatch - agent_name should be "agent" as defined in agent.py
    dispatch = await lkapi.agent_dispatch.create_dispatch(
        api.CreateAgentDispatchRequest(
            agent_name="agent",  # This must match the agent name in your LiveKit setup
            room=room_name,
            metadata=phone_number
        )
    )

    # Wait for agent to connect before adding SIP participant (prevents race condition)
    await asyncio.sleep(2)

    print(f"outbound_trunk_id: {outbound_trunk_id}")
    # Create SIP participant to make the call
    sip_participant = await lkapi.sip.create_sip_participant(
        api.CreateSIPParticipantRequest(
            room_name=room_name,
            sip_trunk_id=outbound_trunk_id,
            sip_call_to=phone_number,
            participant_identity="phone_user",
        )
    )

    await lkapi.aclose()

@app.route('/web-call')
@login_required
@approved_required
def web_call():
    """Web call interface page"""
    user = db.session.get(User, session['user_id'])
    return render_template('calls/web_call.html', user=user)

@app.route('/subscription')
@login_required
@approved_required
def subscription():
    user = db.session.get(User, session['user_id'])
    return render_template('user/subscription.html', user=user, datetime=datetime)

@app.route('/custom-tools')
@login_required
@approved_required
def custom_tools():
    user = db.session.get(User, session['user_id'])
    return render_template('custom_tools.html', user=user)

@app.route('/call-logs')
@login_required
@approved_required
def call_logs():
    user = db.session.get(User, session['user_id'])

    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)

    # Limit per_page to reasonable values
    if per_page not in [10, 25, 50, 100]:
        per_page = 25

    # Paginate call logs
    pagination = CallLog.query.filter_by(user_id=user.id)\
        .order_by(CallLog.created_at.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)

    return render_template('calls/call_logs.html',
                         call_logs=pagination.items,
                         pagination=pagination,
                         per_page=per_page,
                         user=user)

@app.route('/call-log/<int:log_id>')
@login_required
@approved_required
def view_call_log(log_id):
    log = CallLog.query.get_or_404(log_id)

    if log.user_id != session['user_id'] and not session.get('is_admin'):
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))

    return render_template('calls/view_call_log.html', log=log)

@app.route('/api/demo-token', methods=['POST'])
def get_demo_token():
    """Generate a LiveKit token for demo voice agent session"""
    try:
        import secrets

        # Get LiveKit credentials from environment
        livekit_url = os.environ.get('LIVEKIT_URL')
        api_key = os.environ.get('LIVEKIT_API_KEY')
        api_secret = os.environ.get('LIVEKIT_API_SECRET')

        if not all([livekit_url, api_key, api_secret]):
            return jsonify({'error': 'LiveKit credentials not configured'}), 500

        # Generate unique room name for demo
        room_name = f"demo-{secrets.token_hex(8)}"
        participant_identity = f"demo-user-{secrets.token_hex(4)}"

        # Create token
        token = api.AccessToken(api_key, api_secret) \
            .with_identity(participant_identity) \
            .with_name("Demo User") \
            .with_grants(api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
            ))

        jwt_token = token.to_jwt()

        logger.info(f"🎫 Generated demo token for room: {room_name}")

        return jsonify({
            'token': jwt_token,
            'url': livekit_url,
            'room_name': room_name,
            'participant_identity': participant_identity
        })

    except Exception as e:
        logger.error(f"Error generating demo token: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/start-demo-agent', methods=['POST'])
def start_demo_agent():
    """Create agent dispatch for demo room"""
    try:
        data = request.json
        room_name = data.get('room_name')

        if not room_name:
            return jsonify({'error': 'room_name required'}), 400

        # Run async function to create dispatch
        async def create_demo_dispatch():
            lkapi = api.LiveKitAPI()

            # Create agent dispatch for the demo room
            dispatch = await lkapi.agent_dispatch.create_dispatch(
                api.CreateAgentDispatchRequest(
                    agent_name="agent-web",  # Use agent-web.py for web demos
                    room=room_name,
                    metadata="demo_session"
                )
            )

            await lkapi.aclose()
            return dispatch

        # Execute async function
        dispatch = asyncio.run(create_demo_dispatch())

        logger.info(f"🤖 Agent dispatched to demo room: {room_name}")

        return jsonify({
            'success': True,
            'dispatch_id': dispatch.id,
            'room_name': room_name
        })

    except Exception as e:
        logger.error(f"Error starting demo agent: {e}")
        return jsonify({'error': str(e)}), 500

# ==================== INBOUND AGENTS ====================

@app.route('/inbound')
@login_required
@approved_required
def inbound_agents():
    """List all inbound configurations for current user"""
    configs = InboundConfiguration.query.filter_by(
        user_id=session['user_id']
    ).order_by(InboundConfiguration.created_at.desc()).all()
    return render_template('agents/inbound_agents.html', configs=configs)


@app.route('/inbound/create', methods=['GET', 'POST'])
@login_required
@approved_required
def create_inbound_agent():
    """Create new inbound configuration by linking to existing agent"""
    # Get all agents to select from (no need to filter by call_type anymore)
    agents = Agent.query.filter_by(
        user_id=session['user_id']
    ).order_by(Agent.name).all()

    if request.method == 'POST':
        name = request.form.get('name')
        phone_number = request.form.get('phone_number', '').strip()
        agent_id = request.form.get('agent_id')

        # Validate agent exists
        selected_agent = Agent.query.filter_by(
            id=agent_id,
            user_id=session['user_id']
        ).first()

        if not selected_agent:
            flash('Selected agent not found', 'error')
            return render_template('agents/create_inbound_agent.html', agents=agents, form_data=request.form)

        # Validate phone number is provided
        if not phone_number:
            flash('Phone number is required', 'error')
            return render_template('agents/create_inbound_agent.html', agents=agents, form_data=request.form)

        # Check if phone number already exists
        existing_config = InboundConfiguration.query.filter_by(
            phone_number=phone_number
        ).first()

        if existing_config:
            flash(f'Phone number {phone_number} is already configured for "{existing_config.name}"', 'error')
            return render_template('agents/create_inbound_agent.html', agents=agents, form_data=request.form)

        # Create InboundConfiguration (links to existing agent, no duplication!)
        inbound_config = InboundConfiguration(
            user_id=session['user_id'],
            name=name,
            agent_id=agent_id,
            phone_number=phone_number,
            dispatch_rule_id='manual'
        )

        try:
            db.session.add(inbound_config)
            db.session.commit()

            flash(f'Inbound configuration "{name}" created successfully! Linked to agent "{selected_agent.name}"', 'success')
            return redirect(url_for('inbound_agents'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error creating inbound configuration: {str(e)}', 'error')
            logger.error(f"Inbound configuration creation error: {e}")

    return render_template('agents/create_inbound_agent.html', agents=agents)


@app.route('/inbound/<int:config_id>/edit', methods=['GET', 'POST'])
@login_required
@approved_required
def edit_inbound_agent(config_id):
    """Edit existing inbound configuration"""
    config = InboundConfiguration.query.filter_by(
        id=config_id,
        user_id=session['user_id']
    ).first_or_404()

    # Get all agents to select from
    agents = Agent.query.filter_by(
        user_id=session['user_id']
    ).order_by(Agent.name).all()

    if request.method == 'POST':
        name = request.form.get('name')
        phone_number = request.form.get('phone_number', '').strip()
        selected_agent_id = request.form.get('agent_id')

        # Validate agent exists
        selected_agent = Agent.query.filter_by(
            id=selected_agent_id,
            user_id=session['user_id']
        ).first()

        if not selected_agent:
            flash('Selected agent not found', 'error')
            return render_template('agents/edit_inbound_agent.html', config=config, agents=agents)

        # Validate phone number
        if not phone_number:
            flash('Phone number is required', 'error')
            return render_template('agents/edit_inbound_agent.html', config=config, agents=agents)

        # Check if phone number already exists (excluding current config)
        existing_config = InboundConfiguration.query.filter(
            InboundConfiguration.phone_number == phone_number,
            InboundConfiguration.id != config_id
        ).first()

        if existing_config:
            flash(f'Phone number {phone_number} is already used by "{existing_config.name}"', 'error')
            return render_template('agents/edit_inbound_agent.html', config=config, agents=agents)

        # Update configuration (just update the link, no duplication!)
        config.name = name
        config.phone_number = phone_number
        config.agent_id = selected_agent_id

        try:
            db.session.commit()
            flash(f'Inbound configuration "{config.name}" updated successfully! Now linked to "{selected_agent.name}"', 'success')
            return redirect(url_for('inbound_agents'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating configuration: {str(e)}', 'error')
            logger.error(f"Inbound configuration update error: {e}")

    return render_template('agents/edit_inbound_agent.html', config=config, agents=agents)


@app.route('/inbound/<int:config_id>/delete', methods=['POST'])
@login_required
@approved_required
def delete_inbound_agent(config_id):
    """Delete inbound configuration (agent remains for reuse)"""
    config = InboundConfiguration.query.filter_by(
        id=config_id,
        user_id=session['user_id']
    ).first_or_404()

    # Delete configuration only - the linked agent remains for reuse
    try:
        db.session.delete(config)
        db.session.commit()
        flash('Inbound configuration deleted successfully! The agent is still available.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting configuration: {str(e)}', 'error')
        logger.error(f"Inbound configuration deletion error: {e}")

    return redirect(url_for('inbound_agents'))


# --- Knowledge Base Routes ---
@app.route('/agents/<int:agent_id>/knowledge-base')
@login_required
@approved_required
def agent_knowledge_base(agent_id):
    """View and manage knowledge base for an agent"""
    agent = Agent.query.filter_by(
        id=agent_id,
        user_id=session['user_id']
    ).first_or_404()

    # Get all knowledge base documents
    documents = KnowledgeBase.query.filter_by(agent_id=agent_id).order_by(KnowledgeBase.created_at.desc()).all()

    # Calculate total size
    total_size = sum(doc.file_size or 0 for doc in documents)

    return render_template('agents/agent_knowledge_base.html',
                         agent=agent,
                         documents=documents,
                         total_size=total_size,
                         document_count=len(documents))


@app.route('/agents/<int:agent_id>/knowledge-base/upload', methods=['POST'])
@login_required
@approved_required
def upload_knowledge_base(agent_id):
    """Upload documents to knowledge base"""
    agent = Agent.query.filter_by(
        id=agent_id,
        user_id=session['user_id']
    ).first_or_404()

    if 'files' not in request.files:
        flash('No files selected', 'error')
        return redirect(url_for('edit_agent_form', agent_id=agent_id))

    files = request.files.getlist('files')

    if not files or files[0].filename == '':
        flash('No files selected', 'error')
        return redirect(url_for('edit_agent_form', agent_id=agent_id))

    from services.knowledge_base_service import kb_service
    from werkzeug.utils import secure_filename
    import tempfile

    uploaded_count = 0
    for file in files:
        if file and file.filename:
            try:
                # Save to temporary location
                filename = secure_filename(file.filename)
                with tempfile.NamedTemporaryFile(delete=False) as tmp:
                    file.save(tmp.name)
                    tmp_path = tmp.name

                # Add to knowledge base
                if kb_service.add_document(agent_id, tmp_path, filename):
                    # Add to database
                    kb_doc = KnowledgeBase(
                        agent_id=agent_id,
                        filename=filename,
                        file_path=str(kb_service.get_agent_docs_dir(agent_id) / filename),
                        file_type=filename.rsplit('.', 1)[1].lower() if '.' in filename else 'unknown',
                        file_size=os.path.getsize(tmp_path),
                        status='processing'
                    )
                    db.session.add(kb_doc)
                    uploaded_count += 1

                # Clean up temp file
                os.unlink(tmp_path)

            except Exception as e:
                logger.error(f"Error uploading file {filename}: {e}")
                flash(f'Error uploading {filename}: {str(e)}', 'error')

    if uploaded_count > 0:
        db.session.commit()

        # Build index in background
        try:
            if kb_service.build_index(agent_id):
                # Update status to ready
                KnowledgeBase.query.filter_by(agent_id=agent_id, status='processing').update({'status': 'ready'})
                db.session.commit()
                flash(f'{uploaded_count} document(s) uploaded and indexed successfully!', 'success')
            else:
                flash(f'{uploaded_count} document(s) uploaded but indexing failed', 'warning')
        except Exception as e:
            logger.error(f"Error building index: {e}")
            flash(f'{uploaded_count} document(s) uploaded but indexing failed: {str(e)}', 'warning')

    return redirect(url_for('edit_agent_form', agent_id=agent_id))


@app.route('/agents/<int:agent_id>/knowledge-base/<int:doc_id>/delete', methods=['POST'])
@login_required
@approved_required
def delete_knowledge_base_document(agent_id, doc_id):
    """Delete a knowledge base document"""
    agent = Agent.query.filter_by(
        id=agent_id,
        user_id=session['user_id']
    ).first_or_404()

    document = KnowledgeBase.query.filter_by(
        id=doc_id,
        agent_id=agent_id
    ).first_or_404()

    from services.knowledge_base_service import kb_service

    try:
        # Delete from file system
        kb_service.delete_document(agent_id, document.filename)

        # Delete from database
        db.session.delete(document)
        db.session.commit()

        # Update remaining documents status
        remaining_docs = KnowledgeBase.query.filter_by(agent_id=agent_id).all()
        if remaining_docs:
            KnowledgeBase.query.filter_by(agent_id=agent_id).update({'status': 'ready'})
            db.session.commit()

        flash(f'Document "{document.filename}" deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting document: {e}")
        flash(f'Error deleting document: {str(e)}', 'error')

    return redirect(url_for('edit_agent_form', agent_id=agent_id))


@app.route('/agents/<int:agent_id>/knowledge-base/rebuild', methods=['POST'])
@login_required
@approved_required
def rebuild_knowledge_base_index(agent_id):
    """Rebuild the knowledge base index"""
    agent = Agent.query.filter_by(
        id=agent_id,
        user_id=session['user_id']
    ).first_or_404()

    from services.knowledge_base_service import kb_service

    try:
        KnowledgeBase.query.filter_by(agent_id=agent_id).update({'status': 'processing'})
        db.session.commit()

        if kb_service.build_index(agent_id):
            KnowledgeBase.query.filter_by(agent_id=agent_id).update({'status': 'ready'})
            db.session.commit()
            flash('Knowledge base index rebuilt successfully!', 'success')
        else:
            flash('Failed to rebuild index - check if documents exist', 'error')
    except Exception as e:
        logger.error(f"Error rebuilding index: {e}")
        flash(f'Error rebuilding index: {str(e)}', 'error')

    return redirect(url_for('agent_knowledge_base', agent_id=agent_id))


# --- Tool Management Routes ---
@app.route('/tools', methods=['GET'])
@login_required
@approved_required
def tools_list():
    """List all tools for the current user"""
    tools = Tool.query.filter_by(user_id=session['user_id']).order_by(Tool.created_at.desc()).all()
    return render_template('tools/list.html', tools=tools)


@app.route('/tools/create', methods=['GET', 'POST'])
@login_required
@approved_required
def create_tool():
    """Create a new tool"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        tool_type = request.form.get('tool_type', '')

        # Validation
        if not name or not description or not tool_type:
            flash('Name, description, and tool type are required', 'error')
            return render_template('tools/create.html')

        if tool_type not in ['api_call', 'webhook', 'rpc']:
            flash('Invalid tool type', 'error')
            return render_template('tools/create.html')

        # Parse parameters (optional)
        parameters = {}
        parameters_str = request.form.get('parameters', '').strip()
        if parameters_str:
            try:
                parameters = json.loads(parameters_str)
            except json.JSONDecodeError:
                flash('Invalid JSON format for parameters', 'error')
                return render_template('tools/create.html')

        # Build config based on tool type
        config = {}
        if tool_type == 'api_call':
            config = {
                'url': request.form.get('api_url', '').strip(),
                'method': request.form.get('api_method', 'GET'),
                'headers': json.loads(request.form.get('api_headers', '{}')),
                'parameters': parameters
            }
            if not config['url']:
                flash('API URL is required for API call tools', 'error')
                return render_template('tools/create.html')

        elif tool_type == 'webhook':
            config = {
                'url': request.form.get('webhook_url', '').strip(),
                'headers': json.loads(request.form.get('webhook_headers', '{}')),
                'parameters': parameters
            }
            if not config['url']:
                flash('Webhook URL is required for webhook tools', 'error')
                return render_template('tools/create.html')

        elif tool_type == 'rpc':
            config = {
                'method': request.form.get('rpc_method', name),
                'timeout': float(request.form.get('rpc_timeout', 5.0)),
                'parameters': parameters
            }

        # Create tool
        tool = Tool(
            user_id=session['user_id'],
            name=name,
            description=description,
            tool_type=tool_type,
            config=json.dumps(config),
            is_active=True
        )

        db.session.add(tool)
        db.session.commit()

        flash(f'Tool "{name}" created successfully!', 'success')
        return redirect(url_for('tools_list'))

    return render_template('tools/create.html')


@app.route('/tools/<int:tool_id>/edit', methods=['GET', 'POST'])
@login_required
@approved_required
def edit_tool(tool_id):
    """Edit an existing tool"""
    tool = Tool.query.filter_by(id=tool_id, user_id=session['user_id']).first_or_404()

    if request.method == 'POST':
        tool.name = request.form.get('name', '').strip()
        tool.description = request.form.get('description', '').strip()
        tool.is_active = request.form.get('is_active') == 'on'

        # Parse parameters (optional)
        parameters = {}
        parameters_str = request.form.get('parameters', '').strip()
        if parameters_str:
            try:
                parameters = json.loads(parameters_str)
            except json.JSONDecodeError:
                flash('Invalid JSON format for parameters', 'error')
                config = json.loads(tool.config)
                return render_template('tools/edit.html', tool=tool, config=config)

        # Update config based on tool type
        config = json.loads(tool.config)
        if tool.tool_type == 'api_call':
            config['url'] = request.form.get('api_url', '').strip()
            config['method'] = request.form.get('api_method', 'GET')
            config['headers'] = json.loads(request.form.get('api_headers', '{}'))
            config['parameters'] = parameters
        elif tool.tool_type == 'webhook':
            config['url'] = request.form.get('webhook_url', '').strip()
            config['headers'] = json.loads(request.form.get('webhook_headers', '{}'))
            config['parameters'] = parameters
        elif tool.tool_type == 'rpc':
            config['method'] = request.form.get('rpc_method', tool.name)
            config['timeout'] = float(request.form.get('rpc_timeout', 5.0))
            config['parameters'] = parameters

        tool.config = json.dumps(config)
        tool.updated_at = datetime.now(timezone.utc)

        db.session.commit()
        flash(f'Tool "{tool.name}" updated successfully!', 'success')
        return redirect(url_for('tools_list'))

    # Parse config for template
    config = json.loads(tool.config)
    return render_template('tools/edit.html', tool=tool, config=config)


@app.route('/tools/<int:tool_id>/delete', methods=['POST'])
@login_required
@approved_required
def delete_tool(tool_id):
    """Delete a tool"""
    tool = Tool.query.filter_by(id=tool_id, user_id=session['user_id']).first_or_404()

    # Remove all agent associations
    AgentTool.query.filter_by(tool_id=tool_id).delete()

    db.session.delete(tool)
    db.session.commit()

    flash(f'Tool "{tool.name}" deleted successfully!', 'success')
    return redirect(url_for('tools_list'))


@app.route('/tools/<int:tool_id>/toggle', methods=['POST'])
@login_required
@approved_required
def toggle_tool(tool_id):
    """Toggle tool active status"""
    tool = Tool.query.filter_by(id=tool_id, user_id=session['user_id']).first_or_404()
    tool.is_active = not tool.is_active
    tool.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    status = "activated" if tool.is_active else "deactivated"
    flash(f'Tool "{tool.name}" {status}!', 'success')
    return redirect(url_for('tools_list'))


@app.route('/agents/<int:agent_id>/tools', methods=['GET', 'POST'])
@login_required
@approved_required
def agent_tools(agent_id):
    """Manage tools for a specific agent"""
    agent = Agent.query.filter_by(id=agent_id, user_id=session['user_id']).first_or_404()

    if request.method == 'POST':
        try:
            # Get selected tool IDs from form
            selected_tool_ids = request.form.getlist('tool_ids')
            logger.info(f"Received tool_ids from form: {selected_tool_ids}")

            selected_tool_ids = [int(tid) for tid in selected_tool_ids if tid]
            logger.info(f"Parsed tool_ids: {selected_tool_ids}")

            # Remove all existing associations
            deleted_count = AgentTool.query.filter_by(agent_id=agent_id).delete()
            logger.info(f"Deleted {deleted_count} existing tool associations")

            # Add new associations
            added_count = 0
            for tool_id in selected_tool_ids:
                # Verify tool belongs to user
                tool = Tool.query.filter_by(id=tool_id, user_id=session['user_id']).first()
                if tool:
                    agent_tool = AgentTool(agent_id=agent_id, tool_id=tool_id)
                    db.session.add(agent_tool)
                    added_count += 1
                    logger.info(f"Added tool {tool_id} ({tool.name}) to agent {agent_id}")
                else:
                    logger.warning(f"Tool {tool_id} not found or doesn't belong to user")

            db.session.commit()
            logger.info(f"Successfully committed {added_count} tool associations")
            flash(f'Tools updated for agent "{agent.name}"! ({added_count} tools assigned)', 'success')
            return redirect(url_for('edit_agent_form', agent_id=agent_id))

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating agent tools: {e}")
            import traceback
            logger.error(traceback.format_exc())
            flash(f'Error updating tools: {str(e)}', 'error')
            return redirect(url_for('agent_tools', agent_id=agent_id))

    # Get all user's tools
    all_tools = Tool.query.filter_by(user_id=session['user_id']).order_by(Tool.name).all()

    # Get currently assigned tools
    assigned_tool_ids = [at.tool_id for at in AgentTool.query.filter_by(agent_id=agent_id).all()]

    logger.info(f"Agent {agent_id} currently has {len(assigned_tool_ids)} tools assigned: {assigned_tool_ids}")
    logger.info(f"User has {len(all_tools)} tools available")

    return render_template('tools/agent_tools.html',
                         agent=agent,
                         all_tools=all_tools,
                         assigned_tool_ids=assigned_tool_ids)


# OLD CODE BELOW - keeping for reference but not used
@app.route('/inbound/<int:agent_id>/delete_OLD', methods=['POST'])
@login_required
@approved_required
def delete_inbound_agent_OLD(agent_id):
    """OLD: Delete inbound agent and its dispatch rule"""
    agent = Agent.query.filter_by(
        id=agent_id,
        user_id=session['user_id'],
        call_type='inbound'
    ).first_or_404()

    # Delete LiveKit dispatch rule
    if agent.dispatch_rule_id and agent.dispatch_rule_id != 'manual':
        try:
            async def delete_dispatch():
                lkapi = api.LiveKitAPI()
                await lkapi.sip.delete_sip_dispatch_rule(
                    api.DeleteSIPDispatchRuleRequest(
                        sip_dispatch_rule_id=agent.dispatch_rule_id
                    )
                )
                await lkapi.aclose()

            asyncio.run(delete_dispatch())
        except Exception as e:
            logger.error(f"Error deleting dispatch rule: {e}")

    db.session.delete(agent)
    db.session.commit()

    flash('Inbound agent deleted successfully!', 'success')
    return redirect(url_for('inbound_agents'))


@app.route('/inbound/calls')
@login_required
@approved_required
def inbound_call_logs():
    """View all inbound call logs"""
    page = request.args.get('page', 1, type=int)
    per_page = 20

    # Get agent IDs from InboundConfiguration for this user
    config_agent_ids = [c.agent_id for c in InboundConfiguration.query.filter_by(
        user_id=session['user_id']
    ).all()]

    # Get inbound call logs for those agents
    if config_agent_ids:
        pagination = CallLog.query.filter(
            CallLog.agent_id.in_(config_agent_ids),
            CallLog.call_type == 'inbound'
        ).order_by(CallLog.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
    else:
        pagination = CallLog.query.filter_by(id=0).paginate(page=1, per_page=per_page)

    return render_template('calls/inbound_call_logs.html',
                          pagination=pagination,
                          calls=pagination.items)


# ==================== OUTBOUND CAMPAIGNS ====================

@app.route('/outbound/campaigns')
@login_required
@approved_required
def campaigns():
    """List all campaigns with pagination"""
    page = request.args.get('page', 1, type=int)
    per_page = 12  # Show 12 campaigns per page
    
    # Get paginated campaigns
    campaigns_pagination = Campaign.query.options(joinedload(Campaign.agent)).filter_by(user_id=session['user_id']).order_by(Campaign.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    campaigns = campaigns_pagination.items

    # Add stats to each campaign
    for campaign in campaigns:
        total = len(campaign.contacts)
        completed = len([c for c in campaign.contacts if c.status == 'completed'])
        pending = len([c for c in campaign.contacts if c.status == 'pending'])
        failed = len([c for c in campaign.contacts if c.status == 'failed'])
        interested = len([c for c in campaign.contacts if c.status == 'completed' and c.interest_level == 'Interested'])
        not_interested = len([c for c in campaign.contacts if c.status == 'completed' and c.interest_level == 'Not Interested'])

        campaign.stats = {
            'total': total,
            'completed': completed,
            'pending': pending,
            'failed': failed,
            'interested': interested,
            'not_interested': not_interested,
            'progress': int((completed / total * 100)) if total > 0 else 0
        }

    return render_template('campaigns/campaigns.html', campaigns=campaigns, pagination=campaigns_pagination)


@app.route('/outbound/campaign/create', methods=['GET', 'POST'])
@login_required
@approved_required
def create_campaign():
    """Create new campaign"""
    if request.method == 'POST':
        name = request.form.get('name')
        agent_id = request.form.get('agent_id')
        description = clean_text(request.form.get('description', ''))
        call_window_start = request.form.get('call_window_start', '09:00')
        call_window_end = request.form.get('call_window_end', '18:00')
        concurrent_calls = int(request.form.get('concurrent_calls', 5))

        # Calculate next user-specific campaign number
        max_campaign = db.session.query(db.func.max(Campaign.user_campaign_number)).filter_by(user_id=session['user_id']).scalar()
        next_campaign_number = (max_campaign or 0) + 1

        campaign = Campaign(
            user_id=session['user_id'],
            user_campaign_number=next_campaign_number,
            agent_id=agent_id,
            name=name,
            description=description,
            call_window_start=call_window_start,
            call_window_end=call_window_end,
            concurrent_calls=concurrent_calls,
            status='draft'
        )

        try:
            db.session.add(campaign)
            db.session.commit()
            flash(f'Campaign "{name}" created successfully! Now upload contacts to start.', 'success')
            return redirect(url_for('view_campaign', campaign_id=campaign.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating campaign: {str(e)}', 'error')
            logger.error(f"Campaign creation error: {e}")

    # Get outbound agents only
    agents = Agent.query.filter_by(user_id=session['user_id'], call_type='outbound').all()
    return render_template('campaigns/create_campaign.html', agents=agents)


@app.route('/outbound/campaign/<int:campaign_id>/edit', methods=['GET', 'POST'])
@login_required
@approved_required
def edit_campaign(campaign_id):
    """Edit existing campaign"""
    # Get campaign and verify ownership
    campaign = Campaign.query.filter_by(id=campaign_id, user_id=session['user_id']).first_or_404()

    if request.method == 'POST':
        # Update campaign fields
        campaign.name = request.form.get('name')
        campaign.agent_id = request.form.get('agent_id')
        campaign.description = clean_text(request.form.get('description', ''))
        campaign.call_window_start = request.form.get('call_window_start', '09:00')
        campaign.call_window_end = request.form.get('call_window_end', '18:00')
        campaign.concurrent_calls = int(request.form.get('concurrent_calls', 5))

        try:
            db.session.commit()
            flash(f'Campaign "{campaign.name}" updated successfully!', 'success')
            return redirect(url_for('view_campaign', campaign_id=campaign.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating campaign: {str(e)}', 'error')
            logger.error(f"Campaign update error: {e}")

    # Get outbound agents for the dropdown
    agents = Agent.query.filter_by(user_id=session['user_id'], call_type='outbound').all()
    return render_template('campaigns/edit_campaign.html', campaign=campaign, agents=agents)


@app.route('/outbound/campaign/<int:campaign_id>')
@login_required
@approved_required
def view_campaign(campaign_id):
    """View campaign details and dashboard"""
    campaign = Campaign.query.options(joinedload(Campaign.agent)).filter_by(id=campaign_id, user_id=session['user_id']).first_or_404()

    # Calculate statistics
    total = len(campaign.contacts)
    completed = len([c for c in campaign.contacts if c.status == 'completed'])
    pending = len([c for c in campaign.contacts if c.status == 'pending'])
    calling = len([c for c in campaign.contacts if c.status == 'calling'])
    failed = len([c for c in campaign.contacts if c.status == 'failed'])
    no_answer = len([c for c in campaign.contacts if c.status == 'no_answer'])

    # Interest analysis (only for completed calls)
    interested = len([c for c in campaign.contacts if c.status == 'completed' and c.interest_level == 'Interested'])
    not_interested = len([c for c in campaign.contacts if c.status == 'completed' and c.interest_level == 'Not Interested'])

    # Calculate average duration
    completed_contacts = [c for c in campaign.contacts if c.status == 'completed' and c.duration > 0]
    avg_duration = sum(c.duration for c in completed_contacts) // len(completed_contacts) if completed_contacts else 0

    stats = {
        'total': total,
        'completed': completed,
        'pending': pending,
        'calling': calling,
        'failed': failed,
        'no_answer': no_answer,
        'interested': interested,
        'not_interested': not_interested,
        'avg_duration': avg_duration,
        'progress': int((completed / total * 100)) if total > 0 else 0
    }

    # Get recent calls with pagination
    contacts_page = request.args.get('contacts_page', 1, type=int)
    contacts_per_page = 10
    
    # Sort all contacts by last attempt or created date
    all_contacts = sorted(campaign.contacts, key=lambda c: c.last_attempt or c.created_at, reverse=True)
    
    # Calculate pagination
    total_contacts = len(all_contacts)
    start_idx = (contacts_page - 1) * contacts_per_page
    end_idx = start_idx + contacts_per_page
    recent_contacts = all_contacts[start_idx:end_idx]
    
    # Create pagination info
    contacts_pagination = {
        'page': contacts_page,
        'per_page': contacts_per_page,
        'total': total_contacts,
        'pages': math.ceil(total_contacts / contacts_per_page) if total_contacts > 0 else 1,
        'has_prev': contacts_page > 1,
        'has_next': contacts_page < math.ceil(total_contacts / contacts_per_page) if total_contacts > 0 else False,
        'prev_num': contacts_page - 1 if contacts_page > 1 else None,
        'next_num': contacts_page + 1 if contacts_page < math.ceil(total_contacts / contacts_per_page) else None
    }
    
    # Create mapping of room_name to call_log_id for quick lookup
    room_names = [c.room_name for c in recent_contacts if c.room_name]
    call_logs_map = {}
    if room_names:
        call_logs = CallLog.query.filter(CallLog.room_name.in_(room_names)).all()
        call_logs_map = {log.room_name: log.id for log in call_logs}

    return render_template('campaigns/view_campaign.html', campaign=campaign, stats=stats, recent_contacts=recent_contacts, call_logs_map=call_logs_map, contacts_pagination=contacts_pagination)


@app.route('/outbound/campaign/<int:campaign_id>/upload', methods=['POST'])
@login_required
@approved_required
def upload_contacts(campaign_id):
    """Upload CSV contacts to campaign"""
    campaign = Campaign.query.filter_by(id=campaign_id, user_id=session['user_id']).first_or_404()

    if 'file' not in request.files:
        flash('No file uploaded', 'error')
        return redirect(url_for('view_campaign', campaign_id=campaign_id))

    file = request.files['file']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('view_campaign', campaign_id=campaign_id))

    if not file.filename.endswith(('.csv', '.xlsx', '.xls')):
        flash('Only CSV and Excel files are supported', 'error')
        return redirect(url_for('view_campaign', campaign_id=campaign_id))

    try:
        import pandas as pd
        import io

        # Read file
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.StringIO(file.stream.read().decode('utf-8')))
        else:
            df = pd.read_excel(file)

        # Validate required column
        if 'phone_number' not in df.columns:
            flash('CSV must have a "phone_number" column', 'error')
            return redirect(url_for('view_campaign', campaign_id=campaign_id))

        # Add contacts
        added = 0
        for _, row in df.iterrows():
            phone_number = str(row['phone_number']).strip()
            name = str(row.get('name', '')) if pd.notna(row.get('name')) else ''

            # Skip if already exists
            existing = CampaignContact.query.filter_by(campaign_id=campaign_id, phone_number=phone_number).first()
            if existing:
                continue

            contact = CampaignContact(
                campaign_id=campaign_id,
                phone_number=phone_number,
                name=name
            )
            db.session.add(contact)
            added += 1

        db.session.commit()
        flash(f'Successfully uploaded {added} contacts!', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error uploading contacts: {str(e)}', 'error')
        logger.error(f"Contact upload error: {e}")

    return redirect(url_for('view_campaign', campaign_id=campaign_id))


@app.route('/outbound/campaign/<int:campaign_id>/add-contacts-manual', methods=['POST'])
@login_required
@approved_required
def add_contacts_manual(campaign_id):
    """Add contacts manually to campaign"""
    campaign = Campaign.query.filter_by(id=campaign_id, user_id=session['user_id']).first_or_404()

    contacts_text = request.form.get('contacts_text', '').strip()

    if not contacts_text:
        flash('Please enter at least one phone number', 'error')
        return redirect(url_for('view_campaign', campaign_id=campaign_id))

    try:
        # Parse contacts from text area
        lines = contacts_text.split('\n')
        added = 0
        skipped = 0

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check if line has comma (phone,name format)
            if ',' in line:
                parts = line.split(',', 1)
                phone_number = parts[0].strip()
                name = parts[1].strip() if len(parts) > 1 else ''
            else:
                phone_number = line.strip()
                name = ''

            # Skip if already exists
            existing = CampaignContact.query.filter_by(
                campaign_id=campaign_id,
                phone_number=phone_number
            ).first()

            if existing:
                skipped += 1
                continue

            # Create contact
            contact = CampaignContact(
                campaign_id=campaign_id,
                phone_number=phone_number,
                name=name
            )
            db.session.add(contact)
            added += 1

        db.session.commit()

        if added > 0:
            flash(f'Successfully added {added} contact(s)!', 'success')
        if skipped > 0:
            flash(f'{skipped} duplicate(s) skipped', 'info')

    except Exception as e:
        db.session.rollback()
        flash(f'Error adding contacts: {str(e)}', 'error')
        logger.error(f"Manual contact add error: {e}")

    return redirect(url_for('view_campaign', campaign_id=campaign_id))


@app.route('/outbound/campaign/<int:campaign_id>/start', methods=['POST'])
@login_required
@approved_required
def start_campaign(campaign_id):
    """Start campaign"""
    campaign = Campaign.query.filter_by(id=campaign_id, user_id=session['user_id']).first_or_404()

    if len(campaign.contacts) == 0:
        flash('Cannot start campaign with no contacts', 'error')
        return redirect(url_for('view_campaign', campaign_id=campaign_id))

    campaign.status = 'running'
    campaign.start_time = datetime.now(timezone.utc)
    db.session.commit()

    flash(f'Campaign "{campaign.name}" started!', 'success')
    return redirect(url_for('view_campaign', campaign_id=campaign_id))


@app.route('/outbound/campaign/<int:campaign_id>/pause', methods=['POST'])
@login_required
@approved_required
def pause_campaign(campaign_id):
    """Pause campaign"""
    campaign = Campaign.query.filter_by(id=campaign_id, user_id=session['user_id']).first_or_404()
    campaign.status = 'paused'
    db.session.commit()

    flash(f'Campaign "{campaign.name}" paused', 'success')
    return redirect(url_for('view_campaign', campaign_id=campaign_id))


@app.route('/outbound/campaign/<int:campaign_id>/stop', methods=['POST'])
@login_required
@approved_required
def stop_campaign(campaign_id):
    """Stop campaign"""
    campaign = Campaign.query.filter_by(id=campaign_id, user_id=session['user_id']).first_or_404()
    campaign.status = 'stopped'
    campaign.end_time = datetime.now(timezone.utc)
    db.session.commit()

    flash(f'Campaign "{campaign.name}" stopped', 'success')
    return redirect(url_for('view_campaign', campaign_id=campaign_id))


@app.route('/outbound/campaign/<int:campaign_id>/delete', methods=['POST'])
@login_required
@approved_required
def delete_campaign(campaign_id):
    """Delete campaign"""
    campaign = Campaign.query.filter_by(id=campaign_id, user_id=session['user_id']).first_or_404()

    try:
        db.session.delete(campaign)
        db.session.commit()
        flash(f'Campaign "{campaign.name}" deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting campaign: {str(e)}', 'error')
        logger.error(f"Campaign deletion error: {e}")

    return redirect(url_for('campaigns'))


@app.route('/outbound/campaign/<int:campaign_id>/export')
@login_required
@approved_required
def export_campaign(campaign_id):
    """Export campaign results as CSV"""
    campaign = Campaign.query.filter_by(id=campaign_id, user_id=session['user_id']).first_or_404()

    import csv
    import io
    from flask import make_response

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # Write headers
    writer.writerow(['Phone Number', 'Name', 'Status', 'Interest Level', 'Duration (seconds)', 'Attempts', 'Last Attempt'])

    # Write data
    for contact in campaign.contacts:
        writer.writerow([
            contact.phone_number,
            contact.name or '',
            contact.status,
            contact.interest_level or '',
            contact.duration,
            contact.attempts,
            contact.last_attempt.strftime('%Y-%m-%d %H:%M:%S') if contact.last_attempt else ''
        ])

    # Create response
    output.seek(0)
    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = f'attachment; filename=campaign_{campaign.id}_results.csv'
    response.headers['Content-Type'] = 'text/csv'

    return response


# --- Interest Analysis Helper ---
def analyze_sentiment(messages, agent_prompt=None):
    """
    Analyze the entire conversation to determine genuine user interest.
    This analyzes the full conversation context including what the agent was offering.

    Args:
        messages: List of conversation messages
        agent_prompt: The agent's instructions/prompt to understand what was being offered

    Returns: {
        'interest': 'Interested' or 'Not Interested',
        'confidence': 'High' or 'Medium' or 'Low'
    }
    """
    if not messages or len(messages) == 0:
        return {
            'interest': 'Not Interested',
            'confidence': 'Low',
            'reason': 'No conversation data'
        }

    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

        # Prepare full conversation for comprehensive analysis
        conversation_text = "\n".join([
            f"{msg['role'].capitalize()}: {msg['text']}"
            for msg in messages
        ])

        # Count messages for context
        user_messages = [msg for msg in messages if msg['role'] == 'user']
        agent_messages = [msg for msg in messages if msg['role'] == 'agent']

        # Include agent context if available
        agent_context = ""
        if agent_prompt:
            agent_context = f"""
AGENT'S INSTRUCTIONS/PURPOSE:
{agent_prompt}

This context helps you understand what the agent was offering/discussing.
"""

        prompt = f"""Analyze the ENTIRE conversation to determine if the user shows GENUINE INTEREST in what was being offered.

{agent_context}

DO NOT judge based solely on the customer's tone or politeness. Analyze the CONTENT and CONTEXT of the full conversation.

Full Conversation ({len(user_messages)} user messages, {len(agent_messages)} agent messages):
{conversation_text}

CRITICAL ANALYSIS CRITERIA - Evaluate the WHOLE conversation:

1. ENGAGEMENT LEVEL:
   - Does the user provide substantive responses? (not just "yes", "no", "ok")
   - Does the user answer the agent's questions with relevant details?
   - Is there meaningful back-and-forth dialogue?

2. INTEREST INDICATORS:
   - Does the user ask questions about the product/service/topic?
   - Does the user request more information, pricing, demos, or callbacks?
   - Does the user share their needs, problems, or use cases?
   - Does the user agree to next steps (meeting, call back, email, etc.)?
   - Does the user show curiosity or want to learn more?

3. CONVERSATION FLOW:
   - Is the user actively participating in the conversation?
   - Does the user contribute meaningfully to the discussion?
   - Does the conversation progress naturally with both parties engaged?

4. CLEAR DISINTEREST SIGNALS (Mark as NOT INTERESTED only if these are present):
   - Explicit rejection: "not interested", "no thanks", "don't call again"
   - Trying to end conversation quickly: "I'm busy", "gotta go", "not now", "wrong number"
   - Avoiding or ignoring questions repeatedly
   - Very brief dismissive responses throughout entire conversation
   - Asking to be removed from list

DECISION CRITERIA:
✅ INTERESTED = User shows engagement, asks questions, shares needs, wants follow-up, provides detailed responses, agrees to next steps
❌ NOT INTERESTED = Clear rejection, trying to end call quickly, dismissive throughout, explicit disinterest

IMPORTANT: Being polite but brief ≠ NOT INTERESTED
- If user is polite and answers questions, even if brief → lean toward INTERESTED
- If user provides any details about their situation → INTERESTED
- If user doesn't explicitly reject → analyze engagement level carefully
- Focus on CONTENT of what they say, not tone

Return ONLY valid JSON:
{{
    "interest": "Interested" or "Not Interested",
    "confidence": "High" or "Medium" or "Low",
    "reason": "Brief explanation of the decision based on conversation content",
    "key_indicators": {{
        "asked_questions": true/false,
        "requested_callback": true/false,
        "shared_needs": true/false,
        "agreed_next_steps": true/false,
        "provided_details": true/false,
        "explicit_rejection": true/false
    }},
    "conversation_quality": "engaging" or "neutral" or "dismissive"
}}"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert conversation analyst. Analyze the ENTIRE conversation objectively based on content and engagement patterns, not just tone or politeness. Focus on genuine interest indicators across the full dialogue."
                },
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.2  # Lower temperature for more consistent analysis
        )

        result = json.loads(response.choices[0].message.content)

        return {
            'interest': result.get('interest', 'Not Interested'),
            'confidence': result.get('confidence', 'Low'),
            'reason': result.get('reason', 'Analysis completed'),
            'conversation_quality': result.get('conversation_quality', 'neutral'),
            'key_indicators': result.get('key_indicators', {
                'asked_questions': False,
                'requested_callback': False,
                'shared_needs': False,
                'agreed_next_steps': False,
                'provided_details': False,
                'explicit_rejection': False
            }),
            'message_counts': {
                'user_messages': len(user_messages),
                'agent_messages': len(agent_messages)
            },
            'analyzed_at': datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error(f"Interest analysis error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            'interest': 'Not Interested',
            'confidence': 'Low',
            'reason': f'Analysis error: {str(e)}',
            'key_indicators': {
                'asked_questions': False,
                'requested_callback': False,
                'shared_needs': False,
                'agreed_next_steps': False,
                'provided_details': False,
                'explicit_rejection': False
            }
        }

@app.route('/webhook/call-ended', methods=['POST'])
def call_ended_webhook():
    """Webhook endpoint to receive call completion data from LiveKit"""
    try:
        data = request.json
        logger.info(f"📥 Webhook received: {data}")

        room_name = data.get('room_name')
        duration = data.get('duration', 0)
        transcription = data.get('transcription', '')
        metadata = data.get('metadata', {})
        message_count = data.get('message_count', 0)

        logger.info(f"Processing: {room_name}, {message_count} messages, {duration}s")

        # Check if this is a campaign call (format: campaign_{id}_contact_{id}_{timestamp})
        is_campaign_call = room_name.startswith('campaign_')

        if is_campaign_call:
            logger.info(f"📞 Detected campaign call: {room_name}")
            # Parse campaign and contact IDs
            try:
                parts = room_name.split('_')
                campaign_id = int(parts[1])
                contact_id = int(parts[3])

                # Update campaign contact
                contact = db.session.get(CampaignContact, contact_id)
                if contact:
                    contact.duration = duration
                    contact.transcription = transcription

                    # Determine call status - only mark completed if USER spoke
                    messages = metadata.get('messages', [])
                    user_messages = [msg for msg in messages if msg.get('role') == 'user']
                    sip_info = metadata.get('sip_info', {})
                    sip_call_status = sip_info.get('call_status', 'unknown')

                    logger.info(f"📞 SIP Status: {sip_call_status}, Total messages: {len(messages)}, User messages: {len(user_messages)}, Duration: {duration}s")

                    # Only mark as completed if USER actually spoke
                    if len(user_messages) > 0:
                        contact.status = 'completed'
                        logger.info(f"✅ Campaign call completed ({len(messages)} messages, {len(user_messages)} from user)")

                        # Analyze interest with agent context
                        logger.info(f"🔍 Analyzing customer interest...")
                        # Get agent prompt for context
                        campaign = Campaign.query.get(campaign_id)
                        agent_prompt = None
                        if campaign and campaign.agent_id:
                            agent = Agent.query.get(campaign.agent_id)
                            if agent:
                                agent_prompt = agent.prompt

                        sentiment_data = analyze_sentiment(messages, agent_prompt=agent_prompt)
                        contact.interest_level = sentiment_data.get('interest', 'Not Interested')
                        logger.info(f"✅ Interest: {contact.interest_level}")
                    elif len(messages) > 0 and len(user_messages) == 0:
                        # Agent spoke (greeting) but user didn't answer
                        contact.status = 'no_answer'
                        logger.info(f"📵 No answer (agent greeting sent but no user response)")
                    elif sip_call_status in ['dialing', 'ringing']:
                        contact.status = 'no_answer'
                        logger.info(f"📵 No answer (SIP: {sip_call_status})")
                    else:
                        contact.status = 'failed'
                        logger.info(f"❌ Call failed (SIP: {sip_call_status})")

                    db.session.commit()
                    logger.info(f"✅ Campaign contact updated: {contact_id}")

                    # ALSO CREATE CALL LOG ENTRY for campaign calls
                    campaign = Campaign.query.get(campaign_id)
                    if campaign:
                        # Get recording URL if available (sent directly from audio_recorder)
                        recording_url = data.get('recording_url')
                        if recording_url:
                            logger.info(f"✅ Campaign recording URL: {recording_url[:100]}...")

                        recording_id = None  # Not using LiveKit egress anymore

                        # Only charge if USER spoke (not just agent greeting)
                        call_log = CallLog(
                            user_id=campaign.user_id,
                            agent_id=campaign.agent_id,
                            from_number=sip_info.get('trunk_phone_number', 'campaign'),
                            to_number=sip_info.get('phone_number', contact.phone_number),
                            room_name=room_name,
                            duration_seconds=duration,
                            transcription=transcription,
                            transcription_data=json.dumps(metadata, ensure_ascii=False),
                            call_type='outbound',
                            status='completed' if len(user_messages) > 0 else 'no_answer',
                            minutes_used=math.ceil(duration / 60) if len(user_messages) > 0 else 0,
                            recording_url=recording_url,
                            recording_id=recording_id,
                            created_at=datetime.now(timezone.utc)
                        )

                        # Add sentiment analysis for campaign calls too with agent context (only if user spoke)
                        if messages and len(user_messages) > 0:
                            # Get agent prompt for context
                            agent_prompt = None
                            if campaign.agent_id:
                                agent = Agent.query.get(campaign.agent_id)
                                if agent:
                                    agent_prompt = agent.prompt

                            sentiment_data = analyze_sentiment(messages, agent_prompt=agent_prompt)
                            call_log.sentiment_summary = json.dumps(sentiment_data, ensure_ascii=False)
                        
                        db.session.add(call_log)
                        db.session.commit()
                        logger.info(f"✅ Campaign call log created: {call_log.id}")

                    return jsonify({
                        'success': True,
                        'message': f'Campaign call processed: {message_count} messages',
                        'contact_id': contact_id
                    }), 200
                else:
                    logger.error(f"❌ Campaign contact {contact_id} not found")
                    return jsonify({'error': 'Campaign contact not found'}), 404
            except (IndexError, ValueError) as e:
                logger.error(f"❌ Failed to parse campaign room name: {room_name}, error: {e}")
                return jsonify({'error': 'Invalid campaign room name'}), 400

        # Find call log by room name (for inbound calls)
        call_log = CallLog.query.filter_by(room_name=room_name).first()

        # If call log doesn't exist, create it (inbound call)
        if not call_log:
            logger.info(f"📞 Creating new inbound call log for: {room_name}")

            # Extract SIP info
            sip_info = metadata.get('sip_info', {})
            from_number = sip_info.get('phone_number', 'unknown')
            to_number = sip_info.get('trunk_phone_number', 'unknown')

            # Find inbound configuration by phone number called (to_number)
            inbound_config = InboundConfiguration.query.filter_by(phone_number=to_number).first()

            if inbound_config:
                # Get the linked agent
                agent = inbound_config.agent

                call_log = CallLog(
                    user_id=inbound_config.user_id,
                    agent_id=agent.id,
                    room_name=room_name,
                    from_number=from_number,
                    to_number=to_number,
                    call_type='inbound',
                    status='in_progress',
                    created_at=datetime.now(timezone.utc)
                )
                db.session.add(call_log)
                db.session.flush()  # Get the ID
                logger.info(f"✅ Created inbound call log (ID: {call_log.id}) for config: {inbound_config.name}, agent: {agent.name}")
            else:
                logger.error(f"❌ No inbound configuration found for phone number: {to_number}")
                return jsonify({'error': f'No inbound configuration for {to_number}'}), 404

        if call_log:
            # IMPORTANT: Save OLD minutes before updating (to prevent double-charging)
            old_minutes_used = call_log.minutes_used
            old_status = call_log.status

            call_log.duration_seconds = duration
            call_log.transcription = transcription
            call_log.transcription_data = json.dumps(metadata, ensure_ascii=False)  # Save full metadata

            # Determine call status - prioritize USER messages (not just agent greeting)
            messages = metadata.get('messages', [])
            user_messages = [msg for msg in messages if msg.get('role') == 'user']
            sip_info = metadata.get('sip_info', {})
            sip_call_status = sip_info.get('call_status', 'unknown')

            logger.info(f"📞 SIP Status: {sip_call_status}, Total messages: {len(messages)}, User messages: {len(user_messages)}, Duration: {duration}s")

            # Primary rule: Only charge if USER spoke (actual conversation happened)
            if len(user_messages) > 0:
                # User responded - call was completed and should be charged
                call_log.status = 'completed'
                call_log.minutes_used = math.ceil(duration / 60)
                logger.info(f"✅ Call completed ({len(messages)} messages, {len(user_messages)} from user, duration: {duration}s, minutes: {call_log.minutes_used})")

            # Secondary rule: Agent spoke (greeting) but user didn't respond
            elif len(messages) > 0 and len(user_messages) == 0:
                # Only agent greeting sent, user never answered - no charge
                call_log.status = 'no_answer'
                call_log.minutes_used = 0
                logger.info(f"📵 No answer (agent greeting sent but no user response, SIP: {sip_call_status})")

            # Tertiary rule: Check SIP status if no messages at all
            elif sip_call_status in ['dialing', 'ringing']:
                # Call was never answered - no charge
                call_log.status = 'no_answer'
                call_log.minutes_used = 0
                logger.info(f"📵 No answer (SIP: {sip_call_status}, no messages)")

            else:
                # No messages and no clear SIP status - technical failure
                call_log.status = 'failed'
                call_log.minutes_used = 0
                logger.info(f"❌ Call failed (no messages, SIP: {sip_call_status})")

            # Perform interest analysis on conversation with agent context (only if user spoke)
            messages = metadata.get('messages', [])
            user_messages = [msg for msg in messages if msg.get('role') == 'user']
            if messages and len(user_messages) > 0:
                logger.info(f"🔍 Analyzing customer interest for {len(messages)} messages...")
                # Get agent prompt for context
                agent_prompt = None
                if call_log.agent_id:
                    agent = Agent.query.get(call_log.agent_id)
                    if agent:
                        agent_prompt = agent.prompt

                sentiment_data = analyze_sentiment(messages, agent_prompt=agent_prompt)
                call_log.sentiment_summary = json.dumps(sentiment_data, ensure_ascii=False)
                logger.info(f"✅ Interest analysis complete: {sentiment_data.get('interest', 'Not Interested')}")
            else:
                logger.info("ℹ️  No messages to analyze for interest")
                call_log.sentiment_summary = json.dumps({
                    'interest': 'Not Interested',
                    'confidence': 'Low',
                    'key_indicators': {
                        'asked_questions': False,
                        'requested_info': False,
                        'positive_engagement': False,
                        'requested_callback': False
                    }
                }, ensure_ascii=False)

            # Save recording URL if available (sent directly from audio_recorder)
            recording_url = data.get('recording_url')
            if recording_url:
                call_log.recording_url = recording_url
                logger.info(f"✅ Recording URL saved: {recording_url[:100]}...")
            else:
                logger.debug("ℹ️  No recording URL in webhook payload")

            # Deduct minutes from user ONLY for completed calls
            # IMPORTANT: Only charge the DIFFERENCE to prevent double-charging on duplicate webhooks
            minutes_difference = call_log.minutes_used - old_minutes_used

            if minutes_difference != 0:
                user = db.session.get(User, call_log.user_id)
                if user:
                    # Adjust user balance by the difference (can be positive or negative)
                    user.minutes_balance -= minutes_difference
                    if user.minutes_balance < 0:
                        user.minutes_balance = 0
                    # Track total minutes used (add the difference)
                    user.minutes_used = (user.minutes_used or 0) + minutes_difference

                    if minutes_difference > 0:
                        logger.info(f"💰 Deducted {minutes_difference} minutes from user {user.username} (was {old_minutes_used}, now {call_log.minutes_used})")
                    else:
                        logger.info(f"💰 Refunded {-minutes_difference} minutes to user {user.username} (was {old_minutes_used}, now {call_log.minutes_used})")
            else:
                logger.info(f"💸 No minutes change (status: {call_log.status}, minutes: {call_log.minutes_used}, old: {old_minutes_used})")

            # Update agent last_used timestamp
            if call_log.agent_id:
                agent = db.session.get(Agent, call_log.agent_id)
                if agent:
                    agent.last_used = datetime.now(timezone.utc)

            db.session.commit()
            logger.info(f"✅ Call log updated: {room_name}")
            return jsonify({
                'success': True,
                'message': f'Call processed: {message_count} messages',
                'transcription_length': len(transcription)
            }), 200

        logger.warning(f"Call log not found: {room_name}")
        return jsonify({'error': 'Call log not found'}), 404

    except Exception as e:
        logger.error(f"Webhook error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

# --- Error Handlers ---
@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors with custom page"""
    logger.warning(f"404 Error: {request.url} - IP: {request.remote_addr}")
    return render_template('errors/404.html', current_year=datetime.now(timezone.utc).year), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors with generic page"""
    import uuid
    error_id = str(uuid.uuid4())[:8]
    logger.error(f"500 Error [{error_id}]: {error} - URL: {request.url} - IP: {request.remote_addr}")
    db.session.rollback()
    return render_template('errors/generic.html', 
                         error_code=500,
                         error_name="Internal Server Error",
                         error_description="Something went wrong on our end. Please try again later.",
                         error_id=error_id,
                         current_year=datetime.now(timezone.utc).year), 500

@app.errorhandler(403)
def forbidden_error(error):
    """Handle 403 errors with generic page"""
    logger.warning(f"403 Error: {request.url} - IP: {request.remote_addr}")
    return render_template('errors/generic.html',
                         error_code=403,
                         error_name="Access Forbidden",
                         error_description="You don't have permission to access this resource.",
                         current_year=datetime.now(timezone.utc).year), 403

@app.errorhandler(401)
def unauthorized_error(error):
    """Handle 401 errors with generic page"""
    logger.warning(f"401 Error: {request.url} - IP: {request.remote_addr}")
    return render_template('errors/generic.html',
                         error_code=401,
                         error_name="Unauthorized",
                         error_description="You need to log in to access this page.",
                         current_year=datetime.now(timezone.utc).year), 401

@app.errorhandler(429)
def ratelimit_error(error):
    """Handle 429 errors with generic page"""
    logger.warning(f"429 Error: {request.url} - IP: {request.remote_addr}")
    return render_template('errors/generic.html',
                         error_code=429,
                         error_name="Too Many Requests",
                         error_description="You're making too many requests. Please slow down.",
                         current_year=datetime.now(timezone.utc).year), 429

# --- Initialize Database ---
def init_db():
    with app.app_context():
        db.create_all()

        # Create default admin if not exists
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(
                username='admin',
                email='admin@example.com',
                password=generate_password_hash('admin123'),
                is_admin=True,
                is_approved=True,
                minutes_balance=999999
            )
            db.session.add(admin)
            db.session.commit()
            print("Default admin created: username='admin', password='admin123'")

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5002, host='0.0.0.0')