"""
WhatsApp Agent Management Routes Blueprint
Handles CRUD + deploy/activate/deactivate for WhatsApp AI agents.
Fully standalone — no modifications needed to existing routes.

Each WhatsApp agent:
  1. Links to an existing Agent (prompt, temperature, tools)
  2. Adds WhatsApp API config (url, key) OR Meta official API credentials
  3. Adds WhatsApp-specific system prompt
  4. Auto-generates an n8n workflow via the n8n REST API
"""
import logging
import uuid
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify

from models import db, Agent, WhatsAppAgent, AgentTool, Tool, SAUDI_TZ
from utils.decorators import login_required, approved_required
from services.n8n_service import n8n_service

logger = logging.getLogger(__name__)

whatsapp_bp = Blueprint('whatsapp', __name__)

# Default WhatsApp system prompt template
DEFAULT_WA_SYSTEM_PROMPT = """You are a WhatsApp AI assistant. Follow these rules:
- Keep responses short (2-3 sentences max) — this is a chat, not an essay
- Respond in the SAME language the customer uses
- No emojis unless the customer uses them first
- Be conversational and natural, like texting a colleague
- Ask one question at a time
- If you don't know something, say so honestly and offer to connect with a human"""


# ==================== LIST PAGE ====================

@whatsapp_bp.route('/', methods=['GET'])
@login_required
@approved_required
def whatsapp_agents_list():
    """List all WhatsApp agents for the current user"""
    page = request.args.get('page', 1, type=int)
    per_page = 12

    query = WhatsAppAgent.query.filter_by(user_id=session['user_id'])
    pagination = query.order_by(WhatsAppAgent.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return render_template('whatsapp/whatsapp_agents.html',
                           agents=pagination.items,
                           pagination=pagination)


# ==================== CREATE ====================

@whatsapp_bp.route('/new', methods=['GET', 'POST'])
@login_required
@approved_required
def new_whatsapp_agent():
    """Create a new WhatsApp agent"""
    if request.method == 'GET':
        # Get user's agents for the dropdown
        agents = Agent.query.filter_by(user_id=session['user_id']).order_by(Agent.name).all()
        return render_template('whatsapp/new_whatsapp_agent.html',
                               agents=agents,
                               default_wa_prompt=DEFAULT_WA_SYSTEM_PROMPT)

    # POST — create the agent
    try:
        agent_id = request.form.get('agent_id', type=int)
        name = request.form.get('name', '').strip()
        whatsapp_provider = request.form.get('whatsapp_provider', 'whapi').strip()
        whatsapp_system_prompt = request.form.get('whatsapp_system_prompt', '').strip()
        send_text_endpoint = request.form.get('send_text_endpoint', '').strip() or None
        send_voice_endpoint = request.form.get('send_voice_endpoint', '').strip() or None
        enable_voice_response = request.form.get('enable_voice_response') == 'on'
        enable_image_analysis = request.form.get('enable_image_analysis') == 'on'
        enable_document_analysis = request.form.get('enable_document_analysis') == 'on'
        memory_window = request.form.get('memory_window', 10, type=int)

        # Validation
        if not name:
            flash('Name is required.', 'error')
            return redirect(url_for('whatsapp.new_whatsapp_agent'))

        if not agent_id:
            flash('Please select an agent.', 'error')
            return redirect(url_for('whatsapp.new_whatsapp_agent'))

        # Provider-specific field extraction
        if whatsapp_provider == 'meta':
            # Meta Official API fields
            meta_phone_number_id = request.form.get('meta_phone_number_id', '').strip()
            meta_business_account_id = request.form.get('meta_business_account_id', '').strip()
            meta_access_token = request.form.get('meta_access_token', '').strip()
            whatsapp_phone_number = request.form.get('meta_phone_number', '').strip()

            if not meta_phone_number_id:
                flash('Phone Number ID is required for Meta provider.', 'error')
                return redirect(url_for('whatsapp.new_whatsapp_agent'))
            if not meta_business_account_id:
                flash('Business Account ID is required for Meta provider.', 'error')
                return redirect(url_for('whatsapp.new_whatsapp_agent'))
            if not meta_access_token:
                flash('API Key (Access Token) is required for Meta provider.', 'error')
                return redirect(url_for('whatsapp.new_whatsapp_agent'))

            # Auto-construct the Graph API URL from Phone Number ID
            whatsapp_api_url = f"https://graph.facebook.com/v21.0/{meta_phone_number_id}"
            whatsapp_api_key = meta_access_token  # Store access token in the generic key field too for n8n compatibility
            meta_verify_token = f"nevox_{uuid.uuid4().hex[:16]}"  # Auto-generate verify token
        else:
            # Generic provider fields
            whatsapp_api_url = request.form.get('whatsapp_api_url', '').strip().rstrip('/')
            whatsapp_api_key = request.form.get('whatsapp_api_key', '').strip()
            whatsapp_phone_number = request.form.get('whatsapp_phone_number', '').strip()
            meta_phone_number_id = None
            meta_business_account_id = None
            meta_access_token = None
            meta_verify_token = None

            if not whatsapp_api_url:
                flash('WhatsApp API URL is required.', 'error')
                return redirect(url_for('whatsapp.new_whatsapp_agent'))

            if not whatsapp_api_key:
                flash('WhatsApp API Key is required.', 'error')
                return redirect(url_for('whatsapp.new_whatsapp_agent'))

        # Verify agent belongs to user
        agent = Agent.query.filter_by(id=agent_id, user_id=session['user_id']).first()
        if not agent:
            flash('Invalid agent selected.', 'error')
            return redirect(url_for('whatsapp.new_whatsapp_agent'))

        # Clamp memory window
        memory_window = max(1, min(50, memory_window))

        wa_agent = WhatsAppAgent(
            user_id=session['user_id'],
            agent_id=agent_id,
            name=name,
            whatsapp_provider=whatsapp_provider,
            whatsapp_api_url=whatsapp_api_url,
            whatsapp_api_key=whatsapp_api_key,
            whatsapp_phone_number=whatsapp_phone_number,
            whatsapp_system_prompt=whatsapp_system_prompt or DEFAULT_WA_SYSTEM_PROMPT,
            send_text_endpoint=send_text_endpoint,
            send_voice_endpoint=send_voice_endpoint,
            enable_voice_response=enable_voice_response,
            enable_image_analysis=enable_image_analysis,
            enable_document_analysis=enable_document_analysis,
            memory_window=memory_window,
            meta_phone_number_id=meta_phone_number_id,
            meta_business_account_id=meta_business_account_id,
            meta_access_token=meta_access_token,
            meta_verify_token=meta_verify_token,
            status='draft'
        )

        db.session.add(wa_agent)
        db.session.commit()

        flash(f'WhatsApp agent "{name}" created. Deploy it to start receiving messages.', 'success')
        return redirect(url_for('whatsapp.view_whatsapp_agent', agent_id=wa_agent.id))

    except Exception as e:
        db.session.rollback()
        logger.exception(f"Error creating WhatsApp agent: {e}")
        flash(f'Error creating agent: {str(e)}', 'error')
        return redirect(url_for('whatsapp.new_whatsapp_agent'))


# ==================== VIEW ====================

@whatsapp_bp.route('/<int:agent_id>', methods=['GET'])
@login_required
@approved_required
def view_whatsapp_agent(agent_id):
    """View WhatsApp agent details"""
    wa_agent = WhatsAppAgent.query.filter_by(
        id=agent_id, user_id=session['user_id']
    ).first_or_404()

    # Get linked tools for display
    tools = []
    if wa_agent.agent:
        agent_tools = AgentTool.query.filter_by(agent_id=wa_agent.agent_id).all()
        for at in agent_tools:
            tool = Tool.query.get(at.tool_id)
            if tool and tool.is_active:
                tools.append({
                    'name': tool.name,
                    'type': tool.tool_type,
                    'supported': tool.tool_type in ('api_call', 'webhook')
                })

    # Build webhook URL for display
    webhook_url = None
    if wa_agent.webhook_path:
        webhook_url = f"https://automation.nevoxai.com/webhook/{wa_agent.webhook_path}"

    return render_template('whatsapp/view_whatsapp_agent.html',
                           wa_agent=wa_agent,
                           tools=tools,
                           webhook_url=webhook_url)


# ==================== EDIT ====================

@whatsapp_bp.route('/<int:agent_id>/edit', methods=['GET', 'POST'])
@login_required
@approved_required
def edit_whatsapp_agent(agent_id):
    """Edit WhatsApp agent configuration"""
    wa_agent = WhatsAppAgent.query.filter_by(
        id=agent_id, user_id=session['user_id']
    ).first_or_404()

    if request.method == 'GET':
        agents = Agent.query.filter_by(user_id=session['user_id']).order_by(Agent.name).all()
        return render_template('whatsapp/edit_whatsapp_agent.html',
                               wa_agent=wa_agent,
                               agents=agents)

    # POST — update
    try:
        wa_agent.name = request.form.get('name', wa_agent.name).strip()
        wa_agent.agent_id = request.form.get('agent_id', wa_agent.agent_id, type=int)
        wa_agent.whatsapp_provider = request.form.get('whatsapp_provider', wa_agent.whatsapp_provider or 'whapi').strip()
        wa_agent.whatsapp_system_prompt = request.form.get('whatsapp_system_prompt', '').strip()
        wa_agent.send_text_endpoint = request.form.get('send_text_endpoint', '').strip() or None
        wa_agent.send_voice_endpoint = request.form.get('send_voice_endpoint', '').strip() or None
        wa_agent.enable_voice_response = request.form.get('enable_voice_response') == 'on'
        wa_agent.enable_image_analysis = request.form.get('enable_image_analysis') == 'on'
        wa_agent.enable_document_analysis = request.form.get('enable_document_analysis') == 'on'
        wa_agent.memory_window = max(1, min(50, request.form.get('memory_window', 10, type=int)))

        if wa_agent.whatsapp_provider == 'meta':
            # Meta-specific fields
            wa_agent.meta_phone_number_id = request.form.get('meta_phone_number_id', '').strip()
            wa_agent.meta_business_account_id = request.form.get('meta_business_account_id', '').strip()
            meta_access_token = request.form.get('meta_access_token', '').strip()
            if meta_access_token:
                wa_agent.meta_access_token = meta_access_token
                wa_agent.whatsapp_api_key = meta_access_token  # Keep in sync for n8n

            wa_agent.whatsapp_phone_number = request.form.get('meta_phone_number', '').strip()

            # Auto-construct Graph API URL
            if wa_agent.meta_phone_number_id:
                wa_agent.whatsapp_api_url = f"https://graph.facebook.com/v21.0/{wa_agent.meta_phone_number_id}"

            # Generate verify token if not set
            if not wa_agent.meta_verify_token:
                wa_agent.meta_verify_token = f"nevox_{uuid.uuid4().hex[:16]}"

            if not wa_agent.meta_phone_number_id:
                flash('Phone Number ID is required for Meta provider.', 'error')
                return redirect(url_for('whatsapp.edit_whatsapp_agent', agent_id=agent_id))
            if not wa_agent.meta_business_account_id:
                flash('Business Account ID is required for Meta provider.', 'error')
                return redirect(url_for('whatsapp.edit_whatsapp_agent', agent_id=agent_id))
        else:
            # Generic provider fields
            wa_agent.whatsapp_api_url = request.form.get('whatsapp_api_url', wa_agent.whatsapp_api_url or '').strip().rstrip('/')
            wa_agent.whatsapp_api_key = request.form.get('whatsapp_api_key', wa_agent.whatsapp_api_key or '').strip()
            wa_agent.whatsapp_phone_number = request.form.get('whatsapp_phone_number', '').strip()

        # Verify agent belongs to user
        agent = Agent.query.filter_by(id=wa_agent.agent_id, user_id=session['user_id']).first()
        if not agent:
            flash('Invalid agent selected.', 'error')
            return redirect(url_for('whatsapp.edit_whatsapp_agent', agent_id=agent_id))

        db.session.commit()

        flash('WhatsApp agent updated. Redeploy to apply changes to the workflow.', 'success')
        return redirect(url_for('whatsapp.view_whatsapp_agent', agent_id=agent_id))

    except Exception as e:
        db.session.rollback()
        logger.exception(f"Error updating WhatsApp agent: {e}")
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('whatsapp.edit_whatsapp_agent', agent_id=agent_id))


# ==================== DEPLOY ====================

@whatsapp_bp.route('/<int:agent_id>/deploy', methods=['POST'])
@login_required
@approved_required
def deploy_whatsapp_agent(agent_id):
    """Deploy (create or update) the n8n workflow for this WhatsApp agent"""
    wa_agent = WhatsAppAgent.query.filter_by(
        id=agent_id, user_id=session['user_id']
    ).first_or_404()

    try:
        wa_agent.status = 'deploying'
        wa_agent.error_message = None
        db.session.commit()

        if wa_agent.n8n_workflow_id:
            # Update existing workflow
            result = n8n_service.update_workflow(wa_agent.n8n_workflow_id, wa_agent)
            if result['success']:
                # Also activate it
                activate_result = n8n_service.activate_workflow(wa_agent.n8n_workflow_id)
                if activate_result['success']:
                    wa_agent.status = 'active'
                    wa_agent.is_active = True
                    wa_agent.n8n_workflow_active = True
                else:
                    wa_agent.status = 'error'
                    wa_agent.error_message = f"Workflow updated but activation failed: {activate_result.get('error', '')}"
            else:
                wa_agent.status = 'error'
                wa_agent.error_message = result.get('error', 'Unknown error')
        else:
            # Create new workflow
            result = n8n_service.create_workflow(wa_agent)
            if result['success']:
                wa_agent.n8n_workflow_id = result['workflow_id']
                wa_agent.webhook_path = result['webhook_path']

                # Activate it
                activate_result = n8n_service.activate_workflow(wa_agent.n8n_workflow_id)
                if activate_result['success']:
                    wa_agent.status = 'active'
                    wa_agent.is_active = True
                    wa_agent.n8n_workflow_active = True
                else:
                    wa_agent.status = 'error'
                    wa_agent.error_message = f"Workflow created but activation failed: {activate_result.get('error', '')}"
            else:
                wa_agent.status = 'error'
                wa_agent.error_message = result.get('error', 'Unknown error')

        db.session.commit()

        if wa_agent.status == 'active':
            flash('WhatsApp agent deployed and activated successfully!', 'success')
        else:
            flash(f'Deployment issue: {wa_agent.error_message}', 'error')

    except Exception as e:
        db.session.rollback()
        logger.exception(f"Error deploying WhatsApp agent: {e}")
        wa_agent.status = 'error'
        wa_agent.error_message = str(e)
        db.session.commit()
        flash(f'Deployment error: {str(e)}', 'error')

    return redirect(url_for('whatsapp.view_whatsapp_agent', agent_id=agent_id))


# ==================== ACTIVATE / DEACTIVATE ====================

@whatsapp_bp.route('/<int:agent_id>/activate', methods=['POST'])
@login_required
@approved_required
def activate_whatsapp_agent(agent_id):
    """Activate the n8n workflow"""
    wa_agent = WhatsAppAgent.query.filter_by(
        id=agent_id, user_id=session['user_id']
    ).first_or_404()

    if not wa_agent.n8n_workflow_id:
        flash('Deploy the agent first before activating.', 'error')
        return redirect(url_for('whatsapp.view_whatsapp_agent', agent_id=agent_id))

    result = n8n_service.activate_workflow(wa_agent.n8n_workflow_id)
    if result['success']:
        wa_agent.status = 'active'
        wa_agent.is_active = True
        wa_agent.n8n_workflow_active = True
        db.session.commit()
        flash('WhatsApp agent activated.', 'success')
    else:
        flash(f'Activation failed: {result.get("error", "")}', 'error')

    return redirect(url_for('whatsapp.view_whatsapp_agent', agent_id=agent_id))


@whatsapp_bp.route('/<int:agent_id>/deactivate', methods=['POST'])
@login_required
@approved_required
def deactivate_whatsapp_agent(agent_id):
    """Deactivate the n8n workflow"""
    wa_agent = WhatsAppAgent.query.filter_by(
        id=agent_id, user_id=session['user_id']
    ).first_or_404()

    if not wa_agent.n8n_workflow_id:
        flash('No workflow to deactivate.', 'error')
        return redirect(url_for('whatsapp.view_whatsapp_agent', agent_id=agent_id))

    result = n8n_service.deactivate_workflow(wa_agent.n8n_workflow_id)
    if result['success']:
        wa_agent.status = 'paused'
        wa_agent.is_active = False
        wa_agent.n8n_workflow_active = False
        db.session.commit()
        flash('WhatsApp agent paused.', 'success')
    else:
        flash(f'Deactivation failed: {result.get("error", "")}', 'error')

    return redirect(url_for('whatsapp.view_whatsapp_agent', agent_id=agent_id))


# ==================== DELETE ====================

@whatsapp_bp.route('/<int:agent_id>/delete', methods=['POST'])
@login_required
@approved_required
def delete_whatsapp_agent(agent_id):
    """Delete WhatsApp agent and its n8n workflow"""
    wa_agent = WhatsAppAgent.query.filter_by(
        id=agent_id, user_id=session['user_id']
    ).first_or_404()

    try:
        # Delete from n8n first
        if wa_agent.n8n_workflow_id:
            n8n_result = n8n_service.delete_workflow(wa_agent.n8n_workflow_id)
            if not n8n_result['success']:
                logger.warning(f"Failed to delete n8n workflow {wa_agent.n8n_workflow_id}: {n8n_result.get('error')}")
                # Continue with DB deletion anyway

        name = wa_agent.name
        db.session.delete(wa_agent)
        db.session.commit()

        flash(f'WhatsApp agent "{name}" deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.exception(f"Error deleting WhatsApp agent: {e}")
        flash(f'Error: {str(e)}', 'error')

    return redirect(url_for('whatsapp.whatsapp_agents_list'))


# ==================== API: Get Agent Prompt (for AJAX preview) ====================

@whatsapp_bp.route('/api/agent-prompt/<int:agent_id>', methods=['GET'])
@login_required
@approved_required
def get_agent_prompt(agent_id):
    """Return agent prompt and tools for the create form preview"""
    agent = Agent.query.filter_by(id=agent_id, user_id=session['user_id']).first()
    if not agent:
        return jsonify({'error': 'Agent not found'}), 404

    # Get tools
    tools = []
    agent_tools = AgentTool.query.filter_by(agent_id=agent.id).all()
    for at in agent_tools:
        tool = Tool.query.get(at.tool_id)
        if tool and tool.is_active:
            tools.append({
                'name': tool.name,
                'type': tool.tool_type,
                'description': tool.description,
                'supported': tool.tool_type in ('api_call', 'webhook')
            })

    return jsonify({
        'prompt': agent.prompt,
        'temperature': agent.temperature,
        'voice_name': agent.voice_name,
        'tools': tools
    })


# ==================== API: Check n8n Connection ====================

@whatsapp_bp.route('/api/test-n8n', methods=['GET'])
@login_required
@approved_required
def test_n8n_connection():
    """Test the n8n API connection"""
    result = n8n_service.test_connection()
    return jsonify(result)


# ==================== META WEBHOOK VERIFICATION ====================

@whatsapp_bp.route('/webhook/meta/<int:agent_id>', methods=['GET'])
def meta_webhook_verify(agent_id):
    """
    Meta WhatsApp webhook verification (challenge-response).
    Meta sends a GET request with hub.mode, hub.verify_token, hub.challenge.
    We must respond with hub.challenge if the verify_token matches.
    """
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    if not mode or not token or not challenge:
        return 'Missing parameters', 400

    if mode != 'subscribe':
        return 'Invalid mode', 403

    # Find the WhatsApp agent by ID
    wa_agent = WhatsAppAgent.query.filter_by(id=agent_id, whatsapp_provider='meta').first()
    if not wa_agent:
        logger.warning(f"Meta webhook verify: agent {agent_id} not found or not Meta provider")
        return 'Agent not found', 404

    if token != wa_agent.meta_verify_token:
        logger.warning(f"Meta webhook verify: token mismatch for agent {agent_id}")
        return 'Invalid verify token', 403

    # Mark verified
    wa_agent.meta_webhook_verified = True
    db.session.commit()
    logger.info(f"Meta webhook verified for WhatsApp agent {agent_id} ({wa_agent.name})")

    # Return the challenge as plain text (required by Meta)
    return challenge, 200


@whatsapp_bp.route('/webhook/meta/<int:agent_id>', methods=['POST'])
def meta_webhook_receive(agent_id):
    """
    Receive incoming messages from Meta WhatsApp Cloud API.
    Meta sends webhook events as POST with JSON payload.
    This endpoint acknowledges receipt and can forward to n8n or process directly.
    """
    wa_agent = WhatsAppAgent.query.filter_by(id=agent_id, whatsapp_provider='meta').first()
    if not wa_agent:
        return jsonify({'error': 'Agent not found'}), 404

    try:
        payload = request.get_json(silent=True)
        if not payload:
            return jsonify({'status': 'ok'}), 200

        logger.info(f"Meta webhook received for agent {agent_id}: {payload.get('object', 'unknown')}")

        # Extract messages from the Meta webhook payload
        if payload.get('object') == 'whatsapp_business_account':
            for entry in payload.get('entry', []):
                for change in entry.get('changes', []):
                    value = change.get('value', {})
                    messages = value.get('messages', [])

                    if messages and wa_agent.n8n_workflow_id and wa_agent.webhook_path:
                        # Forward the entire payload to the n8n webhook for processing
                        import requests as http_requests
                        n8n_webhook_url = f"https://automation.nevoxai.com/webhook/{wa_agent.webhook_path}"
                        try:
                            http_requests.post(
                                n8n_webhook_url,
                                json=payload,
                                headers={'Content-Type': 'application/json'},
                                timeout=10
                            )
                        except Exception as fwd_err:
                            logger.error(f"Failed to forward Meta webhook to n8n: {fwd_err}")

        # Always return 200 to Meta (they'll retry on non-200)
        return jsonify({'status': 'ok'}), 200

    except Exception as e:
        logger.exception(f"Error processing Meta webhook for agent {agent_id}: {e}")
        return jsonify({'status': 'ok'}), 200  # Still return 200 to prevent Meta retries
