"""
Jobs Management Routes - Phase 1 Feature
Handles job creation, status updates, and job tracking
"""

import logging
from flask import Blueprint, request, jsonify, render_template, session, redirect, url_for
from datetime import datetime, timedelta
from functools import wraps

from models import db, Job, Business, EmergencyEscalationLog, SMSLog, User, CallLog, Customer
from utils.decorators import login_required

logger = logging.getLogger(__name__)

jobs_bp = Blueprint('jobs', __name__, url_prefix='/jobs')


def require_business(f):
    """Decorator to check if user has business configured"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            return redirect(url_for('core.login'))

        business = Business.query.filter_by(user_id=user_id).first()
        if not business:
            return redirect(url_for('business_setup.setup'))

        return f(*args, business=business, **kwargs)

    return decorated_function


# ============================================================================
# JOB DASHBOARD
# ============================================================================

@jobs_bp.route('/', methods=['GET'])
@login_required
@require_business
def job_dashboard(business):
    """Main jobs dashboard"""
    try:
        # Get jobs for this business
        today = datetime.now()
        date_filter = request.args.get('date', 'all')
        status_filter = request.args.get('status', 'all')

        query = Job.query.filter_by(business_id=business.id)

        # Apply date filter only when explicitly selected
        if date_filter and date_filter != 'all':
            target_date = datetime.strptime(date_filter, '%Y-%m-%d')
            query = query.filter(
                db.or_(
                    # Jobs scheduled for this date
                    db.and_(
                        Job.scheduled_datetime >= target_date,
                        Job.scheduled_datetime < target_date + timedelta(days=1)
                    ),
                    # Jobs created on this date (regardless of schedule)
                    db.and_(
                        Job.created_at >= target_date,
                        Job.created_at < target_date + timedelta(days=1)
                    ),
                    # Unscheduled jobs always show
                    Job.scheduled_datetime.is_(None)
                )
            )

        if status_filter and status_filter != 'all':
            query = query.filter_by(status=status_filter)

        jobs = query.order_by(Job.created_at.desc()).all()

        # Calculate statistics
        stats = {
            'total_today': len(jobs),
            'emergencies': len([j for j in jobs if j.is_emergency]),
            'completed': len([j for j in jobs if j.status == 'completed']),
            'pending': len([j for j in jobs if j.status in ['new', 'scheduled']]),
        }

        return render_template(
            'jobs/dashboard.html',
            jobs=jobs,
            business=business,
            stats=stats,
            date_filter=date_filter,
            status_filter=status_filter
        )

    except Exception as e:
        logger.error(f"Error loading job dashboard: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# CREATE JOB (from AI call)
# ============================================================================

@jobs_bp.route('/create', methods=['POST'])
def create_job():
    """
    Create job from AI call data
    Called by the voice agent after capturing customer info
    """
    try:
        data = request.json
        business_id = data.get('business_id')

        # Verify business exists
        business = Business.query.get(business_id)
        if not business:
            return jsonify({'error': 'Business not found'}), 404

        # Find or create customer record
        customer_id = None
        phone = (data.get('customer_phone') or '').strip()
        if phone:
            customer = Customer.query.filter_by(business_id=business_id, phone=phone).first()
            if not customer:
                customer = Customer(
                    business_id=business_id,
                    name=data.get('customer_name'),
                    phone=phone,
                    email=data.get('customer_email'),
                    address=data.get('customer_address'),
                    suburb=data.get('customer_suburb'),
                    postcode=data.get('customer_postcode'),
                )
                db.session.add(customer)
                db.session.flush()
            customer_id = customer.id

        # Create job
        job = Job(
            business_id=business_id,
            customer_id=customer_id,
            customer_name=data.get('customer_name', ''),
            customer_phone=data.get('customer_phone', ''),
            customer_email=data.get('customer_email'),
            customer_address=data.get('customer_address', ''),
            customer_suburb=data.get('customer_suburb', ''),
            customer_postcode=data.get('customer_postcode', ''),
            job_type=data.get('job_type', ''),
            description=data.get('description', ''),
            urgency=data.get('urgency', 'normal'),
            is_emergency=data.get('is_emergency', False),
            emergency_keywords_detected=data.get('emergency_keywords'),
            scheduled_datetime=datetime.fromisoformat(data['scheduled_datetime']) if data.get('scheduled_datetime') else None,
            call_transcript=data.get('call_transcript'),
            call_summary=data.get('call_summary'),
            recording_url=data.get('recording_url'),
            address_validated=data.get('address_validated', False),
            address_coordinates=data.get('address_coordinates'),
        )

        db.session.add(job)
        db.session.commit()

        logger.info(f"Job created: #{job.id} for {job.customer_name}")

        return jsonify({
            'status': 'success',
            'job_id': job.id,
            'message': 'Job created successfully'
        }), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating job: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# VIEW JOB DETAILS
# ============================================================================

@jobs_bp.route('/<int:job_id>', methods=['GET'])
@login_required
@require_business
def view_job(job_id, business):
    """View detailed job information"""
    try:
        job = Job.query.filter_by(id=job_id, business_id=business.id).first()
        if not job:
            return jsonify({'error': 'Job not found'}), 404

        # Get related emergency logs
        emergency_logs = EmergencyEscalationLog.query.filter_by(job_id=job_id).all()

        # Get related SMS
        sms_logs = SMSLog.query.filter_by(job_id=job_id).all()

        return render_template(
            'jobs/detail.html',
            job=job,
            business=business,
            emergency_logs=emergency_logs,
            sms_logs=sms_logs
        )

    except Exception as e:
        logger.error(f"Error viewing job: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# UPDATE JOB STATUS
# ============================================================================

@jobs_bp.route('/<int:job_id>/status', methods=['PUT'])
@login_required
@require_business
def update_job_status(job_id, business):
    """Update job status"""
    try:
        data = request.json
        job = Job.query.filter_by(id=job_id, business_id=business.id).first()
        if not job:
            return jsonify({'error': 'Job not found'}), 404

        old_status = job.status
        new_status = data.get('status')

        # Validate status transition
        valid_statuses = ['new', 'scheduled', 'assigned', 'on_the_way', 'in_progress', 'completed', 'invoiced']
        if new_status not in valid_statuses:
            return jsonify({'error': f'Invalid status: {new_status}'}), 400

        job.status = new_status
        job.completion_notes = data.get('notes', job.completion_notes)

        if new_status == 'completed':
            job.actual_duration_minutes = data.get('duration_minutes')

        db.session.commit()

        logger.info(f"Job #{job_id} status updated: {old_status} → {new_status}")

        return jsonify({
            'status': 'success',
            'job_id': job_id,
            'new_status': new_status
        })

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating job status: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# SCHEDULE / CALENDAR VIEW
# ============================================================================

@jobs_bp.route('/schedule', methods=['GET'])
@login_required
@require_business
def job_schedule(business):
    """Weekly calendar view of scheduled jobs"""
    try:
        # Parse week offset from query param (?week=0 is current, 1 is next, -1 is previous)
        week_offset = int(request.args.get('week', 0))

        today = datetime.now().date()
        # Monday of current week
        monday = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
        sunday = monday + timedelta(days=6)

        week_start = datetime.combine(monday, datetime.min.time())
        week_end = datetime.combine(sunday, datetime.max.time())

        jobs = Job.query.filter(
            Job.business_id == business.id,
            Job.scheduled_datetime.isnot(None),
            Job.scheduled_datetime >= week_start,
            Job.scheduled_datetime <= week_end,
        ).order_by(Job.scheduled_datetime.asc()).all()

        # Also get unscheduled jobs (new jobs without a date)
        unscheduled = Job.query.filter(
            Job.business_id == business.id,
            Job.scheduled_datetime.is_(None),
            Job.status.in_(['new', 'scheduled']),
        ).order_by(Job.created_at.desc()).all()

        # Group jobs by day of week (0=Monday .. 6=Sunday)
        days = []
        for i in range(7):
            day_date = monday + timedelta(days=i)
            day_jobs = [j for j in jobs if j.scheduled_datetime.date() == day_date]
            days.append({
                'date': day_date,
                'name': day_date.strftime('%A'),
                'short': day_date.strftime('%a'),
                'display': day_date.strftime('%b %d'),
                'is_today': day_date == today,
                'jobs': day_jobs,
            })

        return render_template(
            'jobs/schedule.html',
            business=business,
            days=days,
            week_offset=week_offset,
            monday=monday,
            sunday=sunday,
            unscheduled=unscheduled,
            total_scheduled=len(jobs),
        )

    except Exception as e:
        logger.error(f"Error loading schedule: {str(e)}")
        return render_template('jobs/schedule.html', business=business, days=[], week_offset=0,
                               monday=datetime.now().date(), sunday=datetime.now().date(),
                               unscheduled=[], total_scheduled=0)


# ============================================================================
# API: Get Jobs for Calendar/Schedule
# ============================================================================

@jobs_bp.route('/api/scheduled', methods=['GET'])
@login_required
@require_business
def get_scheduled_jobs(business):
    """Get scheduled jobs for calendar view"""
    try:
        days_ahead = int(request.args.get('days', 30))

        jobs = Job.query.filter(
            Job.business_id == business.id,
            Job.scheduled_datetime.isnot(None),
            Job.scheduled_datetime >= datetime.now(),
            Job.scheduled_datetime <= datetime.now() + timedelta(days=days_ahead)
        ).all()

        return jsonify({
            'status': 'success',
            'count': len(jobs),
            'jobs': [
                {
                    'id': j.id,
                    'customer': j.customer_name,
                    'phone': j.customer_phone,
                    'datetime': j.scheduled_datetime.isoformat(),
                    'job_type': j.job_type,
                    'is_emergency': j.is_emergency,
                    'status': j.status,
                }
                for j in jobs
            ]
        })

    except Exception as e:
        logger.error(f"Error fetching scheduled jobs: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# API: Get Job Statistics
# ============================================================================

@jobs_bp.route('/api/stats', methods=['GET'])
@login_required
@require_business
def get_job_stats(business):
    """Get job statistics for dashboard"""
    try:
        today = datetime.now().date()

        total_jobs = Job.query.filter_by(business_id=business.id).count()
        today_jobs = Job.query.filter(
            Job.business_id == business.id,
            Job.created_at >= datetime.combine(today, datetime.min.time()),
            Job.created_at < datetime.combine(today, datetime.max.time())
        ).count()

        completed = Job.query.filter_by(business_id=business.id, status='completed').count()
        emergencies = Job.query.filter_by(business_id=business.id, is_emergency=True).count()
        pending = Job.query.filter(
            Job.business_id == business.id,
            Job.status.in_(['new', 'scheduled'])
        ).count()

        return jsonify({
            'status': 'success',
            'total_jobs': total_jobs,
            'today_jobs': today_jobs,
            'completed': completed,
            'emergencies': emergencies,
            'pending': pending,
        })

    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}")
        return jsonify({'error': str(e)}), 500
