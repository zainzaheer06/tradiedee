"""
Agent Management Routes Blueprint
Handles all agent-related operations including CRUD, calls, knowledge base, and tools

REDIS CACHING:
- Invalidates agent config cache when agent is edited
- Cascade invalidates campaign metadata for all campaigns using the agent
"""
import os
import asyncio
import logging
import tempfile
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from livekit import api
from werkzeug.utils import secure_filename

from models import db, Agent, User, CallLog, KnowledgeBase, Tool, AgentTool, SAUDI_TZ
from utils.decorators import login_required, approved_required
from utils.helpers import clean_text
from services.knowledge_base_service import kb_service

# Redis caching service for cache invalidation
from services.redis_service import redis_service

logger = logging.getLogger(__name__)

# Create blueprint
agents_bp = Blueprint('agents', __name__)


# ==================== AGENT LIST & CREATE ====================

@agents_bp.route('/create', methods=['GET', 'POST'])
@login_required
@approved_required
def create_agent():
    """Redirect to new agents list page"""
    return redirect(url_for('agents.agents_list'))


@agents_bp.route('/', methods=['GET'])
@login_required
@approved_required
def agents_list():
    """List all agents with search functionality"""
    page = request.args.get('page', 1, type=int)
    per_page = 12  # 12 agents per page to match grid layout
    search_query = request.args.get('search', '').strip()

    # Base query for user's agents
    query = Agent.query.filter_by(user_id=session['user_id'])

    # Apply search filter if provided
    if search_query:
        query = query.filter(
            db.or_(
                Agent.name.ilike(f'%{search_query}%'),
                Agent.prompt.ilike(f'%{search_query}%'),
                Agent.voice_name.ilike(f'%{search_query}%')
            )
        )

    # Order and paginate
    pagination = query.order_by(Agent.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    agents = pagination.items
    return render_template('agents/agents_list.html', agents=agents, pagination=pagination, search_query=search_query)


@agents_bp.route('/new', methods=['GET', 'POST'])
@login_required
@approved_required
def new_agent_form():
    """Create new agent form"""
    # Generic Voice ID to ElevenLabs Voice ID mapping (hides ElevenLabs IDs from frontend)
    generic_to_elevenlabs_mapping = {
        'voice_1': 'G1L6zhS0TTaBvSr18eUY',  # Fatima
        'voice_2': '6XO1vwWJxHDXGcEu6pMV',  # Ayesha
        'voice_3': 'zJBKdaTfvV4Cs3Q3Uqj8',  # Rabia
        'voice_4': 'kgxi5e6hsB6HuAGpjbQ5',  # Hiba
        'voice_5': 'KjDucWgG5NYuMBznv52L',  # Zainab
        'voice_6': 'YdWLuz4rVsaG3kWAECFE'   # Ali
    }

    # Voice ID to Name mapping
    voice_mapping = {
        'G1L6zhS0TTaBvSr18eUY': 'Fatima',
        '6XO1vwWJxHDXGcEu6pMV': 'Ayesha',
        'zJBKdaTfvV4Cs3Q3Uqj8': 'Rabia',
        'kgxi5e6hsB6HuAGpjbQ5': 'Hiba',
        'KjDucWgG5NYuMBznv52L': 'Zainab',
        'YdWLuz4rVsaG3kWAECFE': 'Ali'
    }

    if request.method == 'POST':
        name = request.form.get('name')
        prompt = clean_text(request.form.get('prompt'))

        # Validate prompt is not empty
        if not prompt:
            flash('Error: Agent prompt cannot be empty. Please create a prompt using the Prompt Builder tab.', 'danger')
            return render_template('agents/new_agent_form.html')

        greeting = clean_text(request.form.get('greeting', 'Welcome! I am your AI assistant. How can I help you today?'))


        
        # Get generic voice ID from form and map to actual ElevenLabs voice ID
        generic_voice_id = request.form.get('voice_id', 'voice_1')
        voice_id = generic_to_elevenlabs_mapping.get(generic_voice_id, 'G1L6zhS0TTaBvSr18eUY')
        voice_name = voice_mapping.get(voice_id, 'Fatima')

        #voice_id = request.form.get('voice_id', 'G1L6zhS0TTaBvSr18eUY')
        #voice_name = voice_mapping.get(voice_id, 'Fatima')

        # Calculate next user-specific agent number
        max_agent = db.session.query(db.func.max(Agent.user_agent_number)).filter_by(user_id=session['user_id']).scalar()
        next_agent_number = (max_agent or 0) + 1

        temperature = float(request.form.get('temperature', 0.4))
        # Update VAD mode
        vad_mode = request.form.get('vad_mode', 'dynamic')


        new_agent = Agent(
            user_id=session['user_id'],
            user_agent_number=next_agent_number,
            name=name,
            prompt=prompt,
            greeting=greeting,
            voice_id=voice_id,
            voice_name=voice_name,
            temperature=temperature,
            vad_mode=vad_mode
        )

        db.session.add(new_agent)
        db.session.commit()

        flash(f'Agent "{name}" created successfully! You can now upload documents for the knowledge base.', 'success')
        return redirect(url_for('agents.edit_agent_form', agent_id=new_agent.id))

    return render_template('agents/new_agent_form.html')


# ==================== AGENT VIEW & EDIT ====================

@agents_bp.route('/<int:agent_id>')
@login_required
@approved_required
def view_agent(agent_id):
    """View agent details and call logs"""
    agent = Agent.query.get_or_404(agent_id)

    if agent.user_id != session['user_id'] and not session.get('is_admin'):
        flash('Access denied', 'danger')
        return redirect(url_for('core.dashboard'))

    # Get call logs with pagination
    page = request.args.get('page', 1, type=int)
    per_page = 15  # Show 15 call logs per page

    call_logs_pagination = CallLog.query.filter_by(agent_id=agent_id).order_by(CallLog.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return render_template('agents/view_agent.html', agent=agent, call_logs=call_logs_pagination.items, pagination=call_logs_pagination)

'''
@agents_bp.route('/<int:agent_id>/edit', methods=['GET', 'POST'])
@login_required
@approved_required
def edit_agent_form(agent_id):
    """Edit agent form"""
    agent = Agent.query.get_or_404(agent_id)

    # Check ownership
    if agent.user_id != session['user_id'] and not session.get('is_admin'):
        flash('Access denied', 'danger')
        return redirect(url_for('agents.agents_list'))

    # Generic Voice ID to ElevenLabs Voice ID mapping (hides ElevenLabs IDs from frontend)
    generic_to_elevenlabs_mapping = {
        'voice_1': 'G1L6zhS0TTaBvSr18eUY',  # Fatima
        'voice_2': '6XO1vwWJxHDXGcEu6pMV',  # Ayesha
        'voice_3': 'zJBKdaTfvV4Cs3Q3Uqj8',  # Rabia
        'voice_4': 'kgxi5e6hsB6HuAGpjbQ5',  # Hiba
        'voice_5': 'KjDucWgG5NYuMBznv52L',  # Zainab
        'voice_6': 'YdWLuz4rVsaG3kWAECFE'   # Ali
    }


    # Voice mapping
    voice_mapping = {
        'G1L6zhS0TTaBvSr18eUY': 'Fatima',
        '6XO1vwWJxHDXGcEu6pMV': 'Ayesha',
        'zJBKdaTfvV4Cs3Q3Uqj8': 'Rabia',
        'kgxi5e6hsB6HuAGpjbQ5': 'Hiba',
        'KjDucWgG5NYuMBznv52L': 'Zainab',
        'YdWLuz4rVsaG3kWAECFE': 'Ali'
    }

    if request.method == 'POST':
        # Update agent fields
        agent.name = request.form.get('name')

        # Validate and clean prompt
        prompt_value = clean_text(request.form.get('prompt'))
        if not prompt_value:
            flash('Error: Agent prompt cannot be empty. Please create a prompt using the Prompt Builder tab.', 'danger')
            documents = KnowledgeBase.query.filter_by(agent_id=agent_id).order_by(KnowledgeBase.created_at.desc()).all()
            document_count = len(documents)
            return render_template('agents/new_agent_form.html', agent=agent, documents=documents, document_count=document_count)

        agent.prompt = prompt_value
        agent.greeting = clean_text(request.form.get('greeting', 'Welcome! I am your AI assistant. How can I help you today?'))
        #agent.voice_id = request.form.get('voice_id', 'G1L6zhS0TTaBvSr18eUY')
        #agent.voice_name = voice_mapping.get(agent.voice_id, 'Fatima')

        # Get generic voice ID from form and map to actual ElevenLabs voice ID
        generic_voice_id = request.form.get('voice_id', 'voice_1')
        agent.voice_id = generic_to_elevenlabs_mapping.get(generic_voice_id, 'G1L6zhS0TTaBvSr18eUY')
        agent.voice_name = voice_mapping.get(agent.voice_id, 'Fatima')
        agent.temperature = float(request.form.get('temperature', 0.4))

        # Update workflow assignment
        workflow_id = request.form.get('workflow_id')
        if workflow_id == '' or workflow_id == 'none':
            agent.workflow_id = None
        elif workflow_id:
            agent.workflow_id = int(workflow_id)

        db.session.commit()

        # ⚡ CRITICAL: Invalidate Redis cache after agent update
        logger.info(f"🗑️ Invalidating Redis cache for agent {agent_id}")
        redis_service.invalidate_agent_config(agent_id)

        # ⚡ CASCADE INVALIDATION: Invalidate all campaigns using this agent
        # When agent config changes, campaign metadata must be refreshed
        from models import Campaign
        campaigns_using_agent = Campaign.query.filter_by(agent_id=agent_id).all()

        if campaigns_using_agent:
            logger.info(f"🗑️ Invalidating {len(campaigns_using_agent)} campaign(s) using agent {agent_id}")
            for campaign in campaigns_using_agent:
                redis_service.invalidate_campaign_metadata(campaign.id)

            flash(f'Agent "{agent.name}" updated successfully! {len(campaigns_using_agent)} campaign(s) refreshed.', 'success')
        else:
            flash(f'Agent "{agent.name}" updated successfully!', 'success')

        return redirect(url_for('agents.edit_agent_form', agent_id=agent_id))

    # Get knowledge base documents
    documents = KnowledgeBase.query.filter_by(agent_id=agent_id).order_by(KnowledgeBase.created_at.desc()).all()
    document_count = len(documents)

    # Get assigned tools
    from models import Tool, AgentTool
    assigned_tool_ids = [at.tool_id for at in AgentTool.query.filter_by(agent_id=agent_id).all()]
    assigned_tools = Tool.query.filter(Tool.id.in_(assigned_tool_ids)).all() if assigned_tool_ids else []

    # Get available workflows for this user
    from models import Workflow
    workflows = Workflow.query.filter_by(user_id=session['user_id'], is_active=True).all()


    return render_template('agents/new_agent_form.html',
                         agent=agent,
                         documents=documents,
                         document_count=document_count,
                         assigned_tools=assigned_tools,
                         workflows=workflows,
                         elevenlabs_to_generic=elevenlabs_to_generic_mapping)
'''


@agents_bp.route('/<int:agent_id>/edit', methods=['GET', 'POST'])
@login_required
@approved_required
def edit_agent_form(agent_id):
    """Edit agent form"""
    agent = Agent.query.get_or_404(agent_id)

    # Check ownership
    if agent.user_id != session['user_id'] and not session.get('is_admin'):
        flash('Access denied', 'danger')
        return redirect(url_for('agents.agents_list'))

    # Generic Voice ID to ElevenLabs Voice ID mapping (hides ElevenLabs IDs from frontend)
    generic_to_elevenlabs_mapping = {
        'voice_1': 'G1L6zhS0TTaBvSr18eUY',  # Fatima
        'voice_2': '6XO1vwWJxHDXGcEu6pMV',  # Ayesha
        'voice_3': 'zJBKdaTfvV4Cs3Q3Uqj8',  # Rabia
        'voice_4': 'kgxi5e6hsB6HuAGpjbQ5',  # Hiba
        'voice_5': 'KjDucWgG5NYuMBznv52L',  # Zainab
        'voice_6': 'YdWLuz4rVsaG3kWAECFE'   # Ali
    }

    # Voice mapping
    voice_mapping = {
        'G1L6zhS0TTaBvSr18eUY': 'Fatima',
        '6XO1vwWJxHDXGcEu6pMV': 'Ayesha',
        'zJBKdaTfvV4Cs3Q3Uqj8': 'Rabia',
        'kgxi5e6hsB6HuAGpjbQ5': 'Hiba',
        'KjDucWgG5NYuMBznv52L': 'Zainab',
        'YdWLuz4rVsaG3kWAECFE': 'Ali'
    }

    if request.method == 'POST':
        # Update agent fields
        agent.name = request.form.get('name')

        # Validate and clean prompt
        prompt_value = clean_text(request.form.get('prompt'))
        if not prompt_value:
            flash('Error: Agent prompt cannot be empty. Please create a prompt using the Prompt Builder tab.', 'danger')
            documents = KnowledgeBase.query.filter_by(agent_id=agent_id).order_by(KnowledgeBase.created_at.desc()).all()
            document_count = len(documents)
            return render_template('agents/new_agent_form.html', agent=agent, documents=documents, document_count=document_count)

        agent.prompt = prompt_value
        agent.greeting = clean_text(request.form.get('greeting', 'Welcome! I am your AI assistant. How can I help you today?'))

        # Get generic voice ID from form and map to actual ElevenLabs voice ID
        generic_voice_id = request.form.get('voice_id', 'voice_1')
        agent.voice_id = generic_to_elevenlabs_mapping.get(generic_voice_id, 'G1L6zhS0TTaBvSr18eUY')
        agent.voice_name = voice_mapping.get(agent.voice_id, 'Fatima')

        # Update temperature (LLM creativity control)
        agent.temperature = float(request.form.get('temperature', agent.temperature or 0.4))

        # Update VAD mode
        agent.vad_mode = request.form.get('vad_mode', 'dynamic')


        # Update workflow assignment
        workflow_id = request.form.get('workflow_id')
        if workflow_id == '' or workflow_id == 'none':
            agent.workflow_id = None
        elif workflow_id:
            agent.workflow_id = int(workflow_id)

        db.session.commit()

        # ⚡ CRITICAL: Invalidate Redis cache after agent update
        logger.info(f"🗑️ Invalidating Redis cache for agent {agent_id}")
        redis_service.invalidate_agent_config(agent_id)

        # ⚡ CASCADE INVALIDATION: Invalidate all campaigns using this agent
        # When agent config changes, campaign metadata must be refreshed
        from models import Campaign
        campaigns_using_agent = Campaign.query.filter_by(agent_id=agent_id).all()

        if campaigns_using_agent:
            logger.info(f"🗑️ Invalidating {len(campaigns_using_agent)} campaign(s) using agent {agent_id}")
            for campaign in campaigns_using_agent:
                redis_service.invalidate_campaign_metadata(campaign.id)

            flash(f'Agent "{agent.name}" updated successfully! {len(campaigns_using_agent)} campaign(s) refreshed.', 'success')
        else:
            flash(f'Agent "{agent.name}" updated successfully!', 'success')

        return redirect(url_for('agents.edit_agent_form', agent_id=agent_id))

    # Get knowledge base documents
    documents = KnowledgeBase.query.filter_by(agent_id=agent_id).order_by(KnowledgeBase.created_at.desc()).all()
    document_count = len(documents)

    # Get assigned tools
    from models import Tool, AgentTool
    assigned_tool_ids = [at.tool_id for at in AgentTool.query.filter_by(agent_id=agent_id).all()]
    assigned_tools = Tool.query.filter(Tool.id.in_(assigned_tool_ids)).all() if assigned_tool_ids else []

    # Get available workflows for this user
    from models import Workflow
    workflows = Workflow.query.filter_by(user_id=session['user_id'], is_active=True).all()

    # Create reverse mapping for template (ElevenLabs ID -> Generic ID)
    elevenlabs_to_generic_mapping = {v: k for k, v in generic_to_elevenlabs_mapping.items()}

    return render_template('agents/new_agent_form.html',
                         agent=agent,
                         documents=documents,
                         document_count=document_count,
                         assigned_tools=assigned_tools,
                         workflows=workflows,
                         elevenlabs_to_generic=elevenlabs_to_generic_mapping)





# ==================== AGENT DELETE ====================

@agents_bp.route('/<int:agent_id>/delete', methods=['POST'])
@login_required
@approved_required
def delete_agent(agent_id):
    """Delete an agent"""
    agent = Agent.query.get_or_404(agent_id)

    # Check ownership
    if agent.user_id != session['user_id'] and not session.get('is_admin'):
        flash('Access denied', 'danger')
        return redirect(url_for('agents.agents_list'))

    agent_name = agent.name

    # ⚡ STEP 1: Invalidate agent config cache
    logger.info(f"🗑️ Invalidating cache for deleted agent {agent_id}")
    redis_service.invalidate_agent_config(agent_id)

    # ⚡ STEP 2: CASCADE - Invalidate all campaigns using this agent
    from models import Campaign
    campaigns = Campaign.query.filter_by(agent_id=agent_id).all()
    if campaigns:
        logger.info(f"🗑️ Invalidating {len(campaigns)} campaign(s) that used agent {agent_id}")
        for campaign in campaigns:
            redis_service.invalidate_campaign_metadata(campaign.id)

    # STEP 3: Delete the agent (cascade will delete associated call logs)
    db.session.delete(agent)
    db.session.commit()

    flash(f'Agent "{agent_name}" deleted successfully!', 'success')
    return redirect(url_for('agents.agents_list'))


# ==================== MAKE CALL ====================

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


@agents_bp.route('/<int:agent_id>/make-call', methods=['POST'])
@login_required
@approved_required
def make_call_route(agent_id):
    """Initiate an outbound call using the agent"""
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
        #room_name = f"call-{agent_id}-{datetime.now(SAUDI_TZ).timestamp()}"
        room_name = f"call-{agent_id}-{user.username}-{phone_number[-4:]}-{datetime.now(SAUDI_TZ).timestamp()}"
        asyncio.run(make_livekit_call(formatted_number, room_name, agent.name, outbound_trunk_id))

        # Create call log
        call_log = CallLog(
            user_id=user.id,
            agent_id=agent_id,
            #from_number=os.environ.get('SAUDI_PHONE_NUMBER', '966115108724'),
            from_number=user.outbound_phone_number or os.environ.get('SAUDI_PHONE_NUMBER', '966115108724'),
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


# ==================== KNOWLEDGE BASE MANAGEMENT ====================

@agents_bp.route('/<int:agent_id>/knowledge-base')
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

@agents_bp.route('/<int:agent_id>/knowledge-base/upload', methods=['POST'])
@login_required
@approved_required
def upload_knowledge_base(agent_id):
    """Upload documents to knowledge base"""
    logger.info("=" * 80)
    logger.info(f"[UPLOAD START] Agent ID: {agent_id}")
    logger.info(f"[UPLOAD] Request method: {request.method}")
    logger.info(f"[UPLOAD] Content-Type: {request.content_type}")
    logger.info(f"[UPLOAD] Content-Length: {request.content_length}")
    logger.info(f"[UPLOAD] Files in request: {list(request.files.keys())}")
    logger.info(f"[UPLOAD] Form data: {list(request.form.keys())}")
    
    agent = Agent.query.filter_by(
        id=agent_id,
        user_id=session['user_id']
    ).first_or_404()
    
    logger.info(f"[UPLOAD] Agent found: {agent.name}")

    if 'files' not in request.files:
        logger.error("[UPLOAD] 'files' key not in request.files")
        logger.error(f"[UPLOAD] Available keys: {list(request.files.keys())}")
        flash('No files selected', 'error')
        return redirect(url_for('agents.edit_agent_form', agent_id=agent_id))

    files = request.files.getlist('files')
    logger.info(f"[UPLOAD] Received {len(files)} files")
    
    for i, f in enumerate(files):
        logger.info(f"[UPLOAD] File {i+1}: {f.filename} ({f.content_length} bytes)")

    if not files or files[0].filename == '':
        logger.error("[UPLOAD] Empty file list or no filename")
        flash('No files selected', 'error')
        return redirect(url_for('agents.edit_agent_form', agent_id=agent_id))

    uploaded_count = 0
    errors = []
    
    # Create temp directory
    temp_upload_dir = os.path.join(tempfile.gettempdir(), 'kb_uploads')
    logger.info(f"[UPLOAD] Temp directory: {temp_upload_dir}")
    
    try:
        os.makedirs(temp_upload_dir, mode=0o777, exist_ok=True)
        logger.info(f"[UPLOAD] Temp directory ready (exists: {os.path.exists(temp_upload_dir)})")
    except Exception as e:
        logger.error(f"[UPLOAD] Failed to create temp directory: {e}", exc_info=True)
        flash(f'Server error: Could not create upload directory', 'error')
        return redirect(url_for('agents.edit_agent_form', agent_id=agent_id))

    for file in files:
        if file and file.filename:
            try:
                filename = secure_filename(file.filename)
                logger.info(f"[UPLOAD] Processing: {filename}")
                
                tmp_path = os.path.join(temp_upload_dir, f"{agent_id}_{filename}")
                logger.info(f"[UPLOAD] Saving to: {tmp_path}")
                
                # Save file
                file.save(tmp_path)
                file_size = os.path.getsize(tmp_path)
                logger.info(f"[UPLOAD] Saved successfully: {file_size} bytes")
                
                # Validate size
                max_size = 50 * 1024 * 1024
                if file_size > max_size:
                    os.unlink(tmp_path)
                    errors.append(f'{filename}: File too large (max 50MB)')
                    logger.warning(f"[UPLOAD] File too large: {filename}")
                    continue
                
                if file_size == 0:
                    os.unlink(tmp_path)
                    errors.append(f'{filename}: File is empty')
                    logger.warning(f"[UPLOAD] File is empty: {filename}")
                    continue

                # Add to KB
                logger.info(f"[UPLOAD] Adding to KB service...")
                if kb_service.add_document(agent_id, tmp_path, filename):
                    kb_doc = KnowledgeBase(
                        agent_id=agent_id,
                        filename=filename,
                        file_path=str(kb_service.get_agent_docs_dir(agent_id) / filename),
                        file_type=filename.rsplit('.', 1)[1].lower() if '.' in filename else 'unknown',
                        file_size=file_size,
                        status='processing'
                    )
                    db.session.add(kb_doc)
                    uploaded_count += 1
                    logger.info(f"[UPLOAD] ✓ Added to KB: {filename}")
                else:
                    errors.append(f'{filename}: Failed to add to knowledge base')
                    logger.error(f"[UPLOAD] ✗ Failed to add: {filename}")

                # Cleanup
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                    logger.info(f"[UPLOAD] Cleaned up temp file")

            except Exception as e:
                logger.error(f"[UPLOAD] Error processing {filename}: {e}", exc_info=True)
                errors.append(f'{filename}: {str(e)}')

    # Commit
    if uploaded_count > 0:
        try:
            db.session.commit()
            logger.info(f"[UPLOAD] ✓ Committed {uploaded_count} documents")

            # Build index
            logger.info(f"[UPLOAD] Building index...")
            if kb_service.build_index(agent_id):
                KnowledgeBase.query.filter_by(
                    agent_id=agent_id, 
                    status='processing'
                ).update({'status': 'ready'})
                db.session.commit()
                
                flash(f'✓ {uploaded_count} document(s) uploaded and indexed!', 'success')
                logger.info(f"[UPLOAD] ✓ Index built successfully")
            else:
                flash(f'⚠ {uploaded_count} uploaded but indexing failed', 'warning')
                logger.error(f"[UPLOAD] ✗ Index build failed")

        except Exception as e:
            db.session.rollback()
            logger.error(f"[UPLOAD] Error during commit: {e}", exc_info=True)
            flash(f'Error: {str(e)}', 'error')
    
    if errors:
        for error in errors:
            flash(f'⚠ {error}', 'warning')
    
    logger.info(f"[UPLOAD END] Uploaded: {uploaded_count}, Errors: {len(errors)}")
    logger.info("=" * 80)

    return redirect(url_for('agents.edit_agent_form', agent_id=agent_id))

@agents_bp.route('/<int:agent_id>/knowledge-base/<int:doc_id>/delete', methods=['POST'])
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

    return redirect(url_for('agents.edit_agent_form', agent_id=agent_id))


@agents_bp.route('/<int:agent_id>/knowledge-base/rebuild', methods=['POST'])
@login_required
@approved_required
def rebuild_knowledge_base_index(agent_id):
    """Rebuild the knowledge base index"""
    agent = Agent.query.filter_by(
        id=agent_id,
        user_id=session['user_id']
    ).first_or_404()

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

    return redirect(url_for('agents.agent_knowledge_base', agent_id=agent_id))


# ==================== AGENT TOOLS MANAGEMENT ====================

@agents_bp.route('/<int:agent_id>/tools', methods=['GET', 'POST'])
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
            return redirect(url_for('agents.edit_agent_form', agent_id=agent_id))

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating agent tools: {e}")
            import traceback
            logger.error(traceback.format_exc())
            flash(f'Error updating tools: {str(e)}', 'error')
            return redirect(url_for('agents.agent_tools', agent_id=agent_id))

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
