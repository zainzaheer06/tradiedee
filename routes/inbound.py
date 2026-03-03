"""
Inbound Agent Routes Blueprint
Handles inbound call configurations, linking phone numbers to agents
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from functools import wraps
from models import db, InboundConfiguration, Agent, CallLog
import logging

logger = logging.getLogger(__name__)

# Create blueprint
inbound_bp = Blueprint('inbound', __name__)

# ==================== DECORATORS ====================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first', 'warning')
            return redirect(url_for('core.login'))
        return f(*args, **kwargs)
    return decorated_function

def approved_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from models import User
        user = db.session.get(User, session['user_id'])
        if not user.is_approved and not user.is_admin:
            flash('Your account is pending admin approval', 'warning')
            return redirect(url_for('core.pending_approval'))
        return f(*args, **kwargs)
    return decorated_function

# ==================== INBOUND AGENT ROUTES ====================

@inbound_bp.route('/')
@login_required
@approved_required
def inbound_agents():
    """List all inbound configurations for current user"""
    configs = InboundConfiguration.query.filter_by(
        user_id=session['user_id']
    ).order_by(InboundConfiguration.created_at.desc()).all()
    return render_template('agents/inbound_agents.html', configs=configs)


@inbound_bp.route('/create', methods=['GET', 'POST'])
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
            return redirect(url_for('inbound.inbound_agents'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error creating inbound configuration: {str(e)}', 'error')
            logger.error(f"Inbound configuration creation error: {e}")

    return render_template('agents/create_inbound_agent.html', agents=agents)


@inbound_bp.route('/<int:config_id>/edit', methods=['GET', 'POST'])
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
            return redirect(url_for('inbound.inbound_agents'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating configuration: {str(e)}', 'error')
            logger.error(f"Inbound configuration update error: {e}")

    return render_template('agents/edit_inbound_agent.html', config=config, agents=agents)


@inbound_bp.route('/<int:config_id>/delete', methods=['POST'])
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

    return redirect(url_for('inbound.inbound_agents'))


@inbound_bp.route('/calls')
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
