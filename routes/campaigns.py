"""
Campaign Management Routes Blueprint
Handles all outbound campaign-related operations including CRUD, contact management, and campaign control

REDIS CACHING:
- Invalidates campaign metadata cache when campaign is edited, started, paused, stopped, or deleted
- Prevents stale cache when campaign status changes
"""
import os
import math
import csv
import io
import logging
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, make_response
from sqlalchemy.orm import joinedload

from models import db, Campaign, CampaignContact, Agent, CallLog, SAUDI_TZ
from utils.decorators import login_required, approved_required
from utils.helpers import clean_text

# Redis caching service for cache invalidation
from services.redis_service import redis_service

logger = logging.getLogger(__name__)

# Create blueprint
campaigns_bp = Blueprint('campaigns', __name__)


# ==================== CAMPAIGN LIST ====================

@campaigns_bp.route('/campaigns')
@login_required
@approved_required
def campaigns():
    """List all campaigns with pagination, search, and filters"""
    page = request.args.get('page', 1, type=int)
    per_page = 12  # Show 12 campaigns per page
    search_query = request.args.get('search', '').strip()
    status_filter = request.args.get('status', '').strip()

    # Base query for user's campaigns
    query = Campaign.query.options(joinedload(Campaign.agent)).filter_by(user_id=session['user_id'])

    # Apply search filter if provided
    if search_query:
        query = query.filter(
            db.or_(
                Campaign.name.ilike(f'%{search_query}%'),
                Campaign.description.ilike(f'%{search_query}%')
            )
        )

    # Apply status filter if provided
    if status_filter:
        query = query.filter(Campaign.status == status_filter)

    # Get paginated campaigns
    campaigns_pagination = query.order_by(Campaign.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    campaigns = campaigns_pagination.items

    # Add stats to each campaign
    for campaign in campaigns:
        total = len(campaign.contacts)
        completed = len([c for c in campaign.contacts if c.status == 'completed'])
        pending = len([c for c in campaign.contacts if c.status == 'pending'])
        failed = len([c for c in campaign.contacts if c.status == 'failed'])
        no_answer = len([c for c in campaign.contacts if c.status == 'no_answer'])
        interested = len([c for c in campaign.contacts if c.status == 'completed' and c.interest_level == 'Interested'])
        not_interested = len([c for c in campaign.contacts if c.status == 'completed' and c.interest_level == 'Not Interested'])

        # Progress = all processed contacts (completed + failed + no_answer)
        processed = completed + failed + no_answer

        campaign.stats = {
            'total': total,
            'completed': completed,
            'pending': pending,
            'failed': failed,
            'no_answer': no_answer,
            'interested': interested,
            'not_interested': not_interested,
            'processed': processed,
            'progress': int((processed / total * 100)) if total > 0 else 0
        }

    return render_template('campaigns/campaigns.html', campaigns=campaigns, pagination=campaigns_pagination, search_query=search_query, status_filter=status_filter)


# ==================== CREATE CAMPAIGN ====================

@campaigns_bp.route('/campaign/create', methods=['GET', 'POST'])
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
            return redirect(url_for('campaigns.view_campaign', campaign_id=campaign.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating campaign: {str(e)}', 'error')
            logger.error(f"Campaign creation error: {e}")

    # Get outbound agents only
    agents = Agent.query.filter_by(user_id=session['user_id'], call_type='outbound').all()
    return render_template('campaigns/create_campaign.html', agents=agents)


# ==================== EDIT CAMPAIGN ====================

@campaigns_bp.route('/campaign/<int:campaign_id>/edit', methods=['GET', 'POST'])
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

            # ⚡ CRITICAL: Invalidate Redis cache after campaign update
            logger.info(f"🗑️ Invalidating Redis cache for campaign {campaign_id}")
            redis_service.invalidate_campaign_metadata(campaign_id)

            flash(f'Campaign "{campaign.name}" updated successfully!', 'success')
            return redirect(url_for('campaigns.view_campaign', campaign_id=campaign.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating campaign: {str(e)}', 'error')
            logger.error(f"Campaign update error: {e}")

    # Get outbound agents for the dropdown
    agents = Agent.query.filter_by(user_id=session['user_id'], call_type='outbound').all()
    return render_template('campaigns/edit_campaign.html', campaign=campaign, agents=agents)


# ==================== VIEW CAMPAIGN ====================

@campaigns_bp.route('/campaign/<int:campaign_id>')
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

    # Progress = all processed contacts (completed + failed + no_answer + calling)
    processed = completed + failed + no_answer + calling

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
        'processed': processed,
        'progress': int((processed / total * 100)) if total > 0 else 0
    }

    # Get recent calls with pagination
    contacts_page = request.args.get('contacts_page', 1, type=int)
    contacts_per_page = 10

    # Sort all contacts by last attempt or created date (normalize timezone-aware vs naive datetimes)
    def get_sort_key(contact):
        dt = contact.last_attempt or contact.created_at
        # Normalize timezone-aware datetimes to naive for comparison
        if dt and hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
            return dt.replace(tzinfo=None)
        return dt

    all_contacts = sorted(campaign.contacts, key=get_sort_key, reverse=True)

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


# ==================== DELETE CAMPAIGN ====================

@campaigns_bp.route('/campaign/<int:campaign_id>/delete', methods=['POST'])
@login_required
@approved_required
def delete_campaign(campaign_id):
    """Delete campaign"""
    campaign = Campaign.query.filter_by(id=campaign_id, user_id=session['user_id']).first_or_404()

    try:
        # ⚡ Invalidate cache BEFORE deleting campaign
        logger.info(f"🗑️ Invalidating cache for deleted campaign {campaign_id}")
        redis_service.invalidate_campaign_metadata(campaign_id)

        db.session.delete(campaign)
        db.session.commit()
        flash(f'Campaign "{campaign.name}" deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting campaign: {str(e)}', 'error')
        logger.error(f"Campaign deletion error: {e}")

    return redirect(url_for('campaigns.campaigns'))


# ==================== UPLOAD CONTACTS ====================

@campaigns_bp.route('/campaign/<int:campaign_id>/upload', methods=['POST'])
@login_required
@approved_required
def upload_contacts(campaign_id):
    """Upload CSV contacts to campaign"""
    campaign = Campaign.query.filter_by(id=campaign_id, user_id=session['user_id']).first_or_404()

    if 'file' not in request.files:
        flash('No file uploaded', 'error')
        return redirect(url_for('campaigns.view_campaign', campaign_id=campaign_id))

    file = request.files['file']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('campaigns.view_campaign', campaign_id=campaign_id))

    if not file.filename.endswith(('.csv', '.xlsx', '.xls')):
        flash('Only CSV and Excel files are supported', 'error')
        return redirect(url_for('campaigns.view_campaign', campaign_id=campaign_id))

    try:
        import pandas as pd

        # Read file
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.StringIO(file.stream.read().decode('utf-8')))
        else:
            df = pd.read_excel(file)

        # Validate required column
        if 'phone_number' not in df.columns:
            flash('CSV must have a "phone_number" column', 'error')
            return redirect(url_for('campaigns.view_campaign', campaign_id=campaign_id))

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

    return redirect(url_for('campaigns.view_campaign', campaign_id=campaign_id))


# ==================== ADD CONTACTS MANUALLY ====================

@campaigns_bp.route('/campaign/<int:campaign_id>/add-contacts-manual', methods=['POST'])
@login_required
@approved_required
def add_contacts_manual(campaign_id):
    """Add contacts manually to campaign"""
    campaign = Campaign.query.filter_by(id=campaign_id, user_id=session['user_id']).first_or_404()

    contacts_text = request.form.get('contacts_text', '').strip()

    if not contacts_text:
        flash('Please enter at least one phone number', 'error')
        return redirect(url_for('campaigns.view_campaign', campaign_id=campaign_id))

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

    return redirect(url_for('campaigns.view_campaign', campaign_id=campaign_id))


# ==================== START CAMPAIGN ====================

@campaigns_bp.route('/campaign/<int:campaign_id>/start', methods=['POST'])
@login_required
@approved_required
def start_campaign(campaign_id):
    """Start campaign"""
    campaign = Campaign.query.filter_by(id=campaign_id, user_id=session['user_id']).first_or_404()

    if len(campaign.contacts) == 0:
        flash('Cannot start campaign with no contacts', 'error')
        return redirect(url_for('campaigns.view_campaign', campaign_id=campaign_id))

    campaign.status = 'running'
    campaign.start_time = datetime.now(SAUDI_TZ).replace(tzinfo=None)
    db.session.commit()

    # ⚡ Invalidate cache after campaign status change
    logger.info(f"🗑️ Invalidating cache for started campaign {campaign_id}")
    redis_service.invalidate_campaign_metadata(campaign_id)

    flash(f'Campaign "{campaign.name}" started!', 'success')
    return redirect(url_for('campaigns.view_campaign', campaign_id=campaign_id))


# ==================== PAUSE CAMPAIGN ====================

@campaigns_bp.route('/campaign/<int:campaign_id>/pause', methods=['POST'])
@login_required
@approved_required
def pause_campaign(campaign_id):
    """Pause campaign"""
    campaign = Campaign.query.filter_by(id=campaign_id, user_id=session['user_id']).first_or_404()
    campaign.status = 'paused'
    db.session.commit()

    # ⚡ Invalidate cache after campaign status change
    logger.info(f"🗑️ Invalidating cache for paused campaign {campaign_id}")
    redis_service.invalidate_campaign_metadata(campaign_id)

    flash(f'Campaign "{campaign.name}" paused', 'success')
    return redirect(url_for('campaigns.view_campaign', campaign_id=campaign_id))


# ==================== STOP CAMPAIGN ====================

@campaigns_bp.route('/campaign/<int:campaign_id>/stop', methods=['POST'])
@login_required
@approved_required
def stop_campaign(campaign_id):
    """Stop campaign"""
    campaign = Campaign.query.filter_by(id=campaign_id, user_id=session['user_id']).first_or_404()
    campaign.status = 'stopped'
    campaign.end_time = datetime.now(SAUDI_TZ).replace(tzinfo=None)
    db.session.commit()

    # ⚡ Invalidate cache after campaign status change
    logger.info(f"🗑️ Invalidating cache for stopped campaign {campaign_id}")
    redis_service.invalidate_campaign_metadata(campaign_id)

    flash(f'Campaign "{campaign.name}" stopped', 'success')
    return redirect(url_for('campaigns.view_campaign', campaign_id=campaign_id))


# ==================== EXPORT CAMPAIGN ====================

@campaigns_bp.route('/campaign/<int:campaign_id>/export')
@login_required
@approved_required
def export_campaign(campaign_id):
    """Export campaign results as CSV"""
    campaign = Campaign.query.filter_by(id=campaign_id, user_id=session['user_id']).first_or_404()

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
