"""
Phase 1 Main Routes
Home page, testing dashboard, and Phase 1 overview
"""

import logging
from datetime import datetime
from flask import Blueprint, render_template, session, request, jsonify, redirect, url_for
from models import db, User, Business

logger = logging.getLogger(__name__)

phase1_bp = Blueprint('phase1', __name__)


@phase1_bp.route('/', methods=['GET'])
def home():
    """Phase 1 home page"""
    try:
        current_user = None
        user_business = None

        user_id = session.get('user_id')
        if user_id:
            current_user = User.query.get(user_id)
            if current_user:
                user_business = Business.query.filter_by(user_id=user_id).first()

        return render_template(
            'phase1_home.html',
            current_user=current_user,
            user_business=user_business
        )

    except Exception as e:
        logger.error(f"Error loading home page: {str(e)}")
        return render_template('phase1_home.html', error=str(e)), 500


@phase1_bp.route('/test', methods=['GET'])
def test_dashboard():
    """Phase 1 testing dashboard - requires login"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return redirect(url_for('core.login'))

        return render_template('phase1_test.html')

    except Exception as e:
        logger.error(f"Error loading test dashboard: {str(e)}")
        return render_template('phase1_test.html', error=str(e)), 500


@phase1_bp.route('/demo', methods=['GET'])
def demo_testing():
    """Public demo testing dashboard - no login required"""
    try:
        return render_template('phase1_test.html')

    except Exception as e:
        logger.error(f"Error loading demo dashboard: {str(e)}")
        return render_template('phase1_test.html', error=str(e)), 500


@phase1_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for Phase 1"""
    try:
        # Check database
        business_count = Business.query.count()

        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'businesses': business_count,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@phase1_bp.route('/api/status', methods=['GET'])
def phase1_status():
    """Get Phase 1 system status"""
    try:
        stats = {
            'total_businesses': Business.query.count(),
            'total_jobs': 0,  # Will count from Job model when needed
            'features': {
                'scheduling': True,
                'emergency_escalation': True,
                'address_validation': True,
                'sms_automation': True,
                'customer_history': True
            }
        }

        return jsonify({
            'status': 'success',
            'system': stats
        })

    except Exception as e:
        logger.error(f"Error getting status: {str(e)}")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@phase1_bp.route('/calls', methods=['GET'])
def calls_dashboard():
    """CallTradie voice calls management dashboard"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return redirect(url_for('core.login'))

        return render_template('calls_dashboard.html')

    except Exception as e:
        logger.error(f"Error loading calls dashboard: {str(e)}")
        return render_template('calls_dashboard.html', error=str(e)), 500
