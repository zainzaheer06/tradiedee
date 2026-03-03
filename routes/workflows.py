"""
Workflow Management Routes Blueprint
Handles n8n workflow integration with API key authentication

REDIS CACHING:
- Invalidates workflow config cache when workflow is updated or API key is regenerated
"""
import logging
import asyncio
from datetime import datetime
from urllib.parse import urlparse
from flask import Blueprint, request, jsonify, session, render_template

from models import db, Workflow, Agent, WebhookLog, SAUDI_TZ
from utils.decorators import login_required, approved_required
from services.webhook_service import webhook_service


# =============================================================================
# SSRF PROTECTION - WEBHOOK URL VALIDATION
# =============================================================================
# WHY: Prevents Server-Side Request Forgery (SSRF) attacks
# ATTACK: Attacker sets webhook_url to "http://169.254.169.254" to steal AWS credentials
#         or "http://localhost:5432" to probe internal database

ALLOWED_WEBHOOK_DOMAINS = {
    'workflows.nevoxai.com',
    'nevoxai.com',
}

def is_safe_webhook_url(url: str) -> tuple[bool, str]:
    """
    Validate webhook URL to prevent SSRF attacks.

    Returns: (is_safe, error_message)
    """
    try:
        parsed = urlparse(url)

        # Must be HTTPS - prevents MITM attacks on webhook data
        if parsed.scheme != 'https':
            return False, "Webhook URL must use HTTPS"

        if not parsed.hostname:
            return False, "Invalid URL - no hostname"

        hostname = parsed.hostname.lower()

        # Must be from allowed domains only
        is_allowed = any(
            hostname == domain or hostname.endswith('.' + domain)
            for domain in ALLOWED_WEBHOOK_DOMAINS
        )

        if not is_allowed:
            return False, f"Domain not allowed. Use: {', '.join(ALLOWED_WEBHOOK_DOMAINS)}"

        return True, ""

    except Exception as e:
        return False, f"Invalid URL: {str(e)}"

# Redis caching service for cache invalidation
from services.redis_service import redis_service

logger = logging.getLogger(__name__)

# Create blueprint
workflows_bp = Blueprint('workflows', __name__)


# ==================== HTML PAGES ====================

@workflows_bp.route('/workflows', methods=['GET'])
@login_required
@approved_required
def workflows_page():
    """Render workflows management page"""
    return render_template('workflows/workflows.html')


# ==================== API ENDPOINTS ====================

@workflows_bp.route('/api/workflows', methods=['GET'])
@login_required
@approved_required
def get_workflows():
    """Get all workflows for the current user"""
    try:
        workflows = Workflow.query.filter_by(user_id=session['user_id']).order_by(Workflow.created_at.desc()).all()

        return jsonify([{
            'id': w.id,
            'name': w.name,
            'description': w.description,
            'webhook_url': w.webhook_url,
            'api_key': w.api_key,  # Show API key so user can copy it
            'is_active': w.is_active,
            'pre_call_enabled': w.pre_call_enabled,
            'post_call_enabled': w.post_call_enabled,
            'pre_call_timeout': w.pre_call_timeout,
            'stats': {
                'total_calls': w.total_calls,
                'successful_calls': w.successful_calls,
                'failed_calls': w.failed_calls,
                'success_rate': round((w.successful_calls / w.total_calls * 100) if w.total_calls > 0 else 0, 1),
                'last_triggered': w.last_triggered_at.isoformat() if w.last_triggered_at else None
            },
            'agents_using': len(w.agents),
            'created_at': w.created_at.isoformat(),
            'updated_at': w.updated_at.isoformat() if w.updated_at else None
        } for w in workflows]), 200

    except Exception as e:
        logger.error(f"Error fetching workflows: {e}")
        return jsonify({'error': str(e)}), 500


@workflows_bp.route('/api/workflows', methods=['POST'])
@login_required
@approved_required
def create_workflow():
    """Create a new workflow"""
    try:
        data = request.json

        # Validation
        if not data.get('name'):
            return jsonify({'error': 'Workflow name is required'}), 400

        if not data.get('webhook_url'):
            return jsonify({'error': 'Webhook URL is required'}), 400

        # Validate URL format and prevent SSRF
        webhook_url = data['webhook_url'].strip()
        is_safe, error_msg = is_safe_webhook_url(webhook_url)
        if not is_safe:
            return jsonify({'error': error_msg}), 400

        # Generate secure API key
        api_key = webhook_service.generate_api_key()

        workflow = Workflow(
            user_id=session['user_id'],
            name=data['name'].strip(),
            description=data.get('description', '').strip(),
            webhook_url=webhook_url,
            api_key=api_key,
            is_active=True,
            pre_call_enabled=data.get('pre_call_enabled', False),
            post_call_enabled=data.get('post_call_enabled', True),
            pre_call_timeout=data.get('pre_call_timeout', 3)
        )

        db.session.add(workflow)
        db.session.commit()

        logger.info(f"Created workflow: {workflow.name} (ID: {workflow.id})")

        return jsonify({
            'success': True,
            'message': 'Workflow created successfully',
            'workflow': {
                'id': workflow.id,
                'name': workflow.name,
                'description': workflow.description,
                'webhook_url': workflow.webhook_url,
                'api_key': workflow.api_key,
                'is_active': workflow.is_active,
                'created_at': workflow.created_at.isoformat()
            }
        }), 201

    except Exception as e:
        logger.error(f"Error creating workflow: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ==================== UPDATE & DELETE WORKFLOWS ====================

@workflows_bp.route('/api/workflows/<int:workflow_id>', methods=['PUT'])
@login_required
@approved_required
def update_workflow(workflow_id):
    """Update an existing workflow"""
    try:
        workflow = Workflow.query.filter_by(
            id=workflow_id,
            user_id=session['user_id']
        ).first()

        if not workflow:
            return jsonify({'error': 'Workflow not found'}), 404

        data = request.json

        # Update fields if provided
        if 'name' in data:
            workflow.name = data['name'].strip()

        if 'description' in data:
            workflow.description = data['description'].strip()

        if 'webhook_url' in data:
            webhook_url = data['webhook_url'].strip()
            is_safe, error_msg = is_safe_webhook_url(webhook_url)
            if not is_safe:
                return jsonify({'error': error_msg}), 400
            workflow.webhook_url = webhook_url

        if 'is_active' in data:
            workflow.is_active = data['is_active']

                # Update webhook settings
        if 'pre_call_enabled' in data:
            workflow.pre_call_enabled = data['pre_call_enabled']

        if 'post_call_enabled' in data:
            workflow.post_call_enabled = data['post_call_enabled']

        if 'pre_call_timeout' in data:
            workflow.pre_call_timeout = data['pre_call_timeout']    

        workflow.updated_at = datetime.now(SAUDI_TZ).replace(tzinfo=None)
        db.session.commit()

        # ⚡ CRITICAL: Invalidate Redis cache after workflow update
        logger.info(f"🗑️ Invalidating Redis cache for workflow {workflow_id}")
        redis_service.invalidate_workflow(workflow_id)

        logger.info(f"Updated workflow: {workflow.name} (ID: {workflow.id})")

        return jsonify({
            'success': True,
            'message': 'Workflow updated successfully'
        }), 200

    except Exception as e:
        logger.error(f"Error updating workflow: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@workflows_bp.route('/api/workflows/<int:workflow_id>', methods=['DELETE'])
@login_required
@approved_required
def delete_workflow(workflow_id):
    """Delete a workflow"""
    try:
        workflow = Workflow.query.filter_by(
            id=workflow_id,
            user_id=session['user_id']
        ).first()

        if not workflow:
            return jsonify({'error': 'Workflow not found'}), 404

        # Check if any agents are using this workflow
        if workflow.agents:
            return jsonify({
                'error': f'Cannot delete workflow. {len(workflow.agents)} agent(s) are using it. Please remove the workflow from these agents first.'
            }), 400

        workflow_name = workflow.name
        db.session.delete(workflow)
        db.session.commit()

        logger.info(f"Deleted workflow: {workflow_name} (ID: {workflow_id})")

        return jsonify({
            'success': True,
            'message': 'Workflow deleted successfully'
        }), 200

    except Exception as e:
        logger.error(f"Error deleting workflow: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ==================== API KEY MANAGEMENT ====================

@workflows_bp.route('/api/workflows/<int:workflow_id>/regenerate-key', methods=['POST'])
@login_required
@approved_required
def regenerate_api_key(workflow_id):
    """Regenerate API key for a workflow"""
    try:
        workflow = Workflow.query.filter_by(
            id=workflow_id,
            user_id=session['user_id']
        ).first()

        if not workflow:
            return jsonify({'error': 'Workflow not found'}), 404

        # Generate new API key
        old_key = workflow.api_key[:10] + '...'
        workflow.api_key = webhook_service.generate_api_key()
        workflow.updated_at = datetime.now(SAUDI_TZ).replace(tzinfo=None)
        db.session.commit()

        # ⚡ CRITICAL: Invalidate Redis cache after API key regeneration
        logger.info(f"🗑️ Invalidating Redis cache for workflow {workflow_id} (API key changed)")
        redis_service.invalidate_workflow(workflow_id)

        logger.info(f"Regenerated API key for workflow: {workflow.name} (ID: {workflow.id})")

        return jsonify({
            'success': True,
            'message': 'API key regenerated successfully. Update your n8n webhook configuration with the new key.',
            'api_key': workflow.api_key
        }), 200

    except Exception as e:
        logger.error(f"Error regenerating API key: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ==================== WEBHOOK LOGS ====================

@workflows_bp.route('/api/workflows/<int:workflow_id>/logs', methods=['GET'])
@login_required
@approved_required
def get_workflow_logs(workflow_id):
    """Get webhook logs for debugging"""
    try:
        workflow = Workflow.query.filter_by(
            id=workflow_id,
            user_id=session['user_id']
        ).first()

        if not workflow:
            return jsonify({'error': 'Workflow not found'}), 404

        page = request.args.get('page', 1, type=int)
        per_page = 50

        logs_query = WebhookLog.query.filter_by(workflow_id=workflow_id)\
            .order_by(WebhookLog.created_at.desc())

        logs_pagination = logs_query.paginate(page=page, per_page=per_page, error_out=False)

        return jsonify({
            'logs': [{
                'id': log.id,
                'status': log.status,
                'http_status': log.http_status,
                'call_log_id': log.call_log_id,
                'error_message': log.error_message,
                'retry_count': log.retry_count,
                'created_at': log.created_at.isoformat(),
                # Include first 500 chars of payload for debugging
                'payload_preview': log.request_payload[:500] if log.request_payload else None
            } for log in logs_pagination.items],
            'pagination': {
                'total': logs_pagination.total,
                'pages': logs_pagination.pages,
                'current_page': page,
                'per_page': per_page,
                'has_next': logs_pagination.has_next,
                'has_prev': logs_pagination.has_prev
            }
        }), 200

    except Exception as e:
        logger.error(f"Error fetching workflow logs: {e}")
        return jsonify({'error': str(e)}), 500


# ==================== TEST WEBHOOK ====================

@workflows_bp.route('/api/workflows/<int:workflow_id>/test', methods=['POST'])
@login_required
@approved_required
def test_workflow(workflow_id):
    """Send a test webhook to verify configuration"""
    try:
        workflow = Workflow.query.filter_by(
            id=workflow_id,
            user_id=session['user_id']
        ).first()

        if not workflow:
            return jsonify({'error': 'Workflow not found'}), 404

        # Sample test data
        test_data = {
            'event_type': 'test_webhook',
            'message': 'This is a test webhook from Nevox AI',
            'timestamp': datetime.now(SAUDI_TZ).isoformat(),
            'workflow_id': workflow.id,
            'workflow_name': workflow.name,
            'test': True
        }

        # Send webhook synchronously for immediate feedback
        import requests
        import json
        import hmac
        import hashlib

        payload_str = json.dumps(test_data, ensure_ascii=False)
        signature = webhook_service.generate_signature(payload_str, workflow.api_key)

        headers = {
            'Content-Type': 'application/json; charset=utf-8',
            'X-Nevox-API-Key': workflow.api_key,
            'X-Nevox-Signature': signature,
            'X-Nevox-Timestamp': datetime.now().isoformat(),
            'User-Agent': 'Nevox-Webhook/1.0'
        }

        try:
            response = requests.post(
                workflow.webhook_url,
                json=test_data,
                headers=headers,
                timeout=10
            )

            success = response.status_code == 200

            # Log the test
            webhook_log = WebhookLog(
                workflow_id=workflow.id,
                status='success' if success else 'failed',
                http_status=response.status_code,
                request_payload=payload_str[:5000],
                response_body=response.text[:1000]
            )
            db.session.add(webhook_log)
            db.session.commit()

            logger.info(f"Test webhook sent to {workflow.name}: HTTP {response.status_code}")

            return jsonify({
                'success': success,
                'message': 'Test webhook sent successfully' if success else f'Test webhook failed with status {response.status_code}',
                'http_status': response.status_code,
                'response': response.text[:500]  # First 500 chars of response
            }), 200

        except requests.exceptions.Timeout:
            webhook_log = WebhookLog(
                workflow_id=workflow.id,
                status='failed',
                request_payload=payload_str[:5000],
                error_message='Request timeout after 10 seconds'
            )
            db.session.add(webhook_log)
            db.session.commit()

            return jsonify({
                'success': False,
                'message': 'Test webhook timed out after 10 seconds',
                'error': 'Timeout'
            }), 200

        except Exception as e:
            webhook_log = WebhookLog(
                workflow_id=workflow.id,
                status='failed',
                request_payload=payload_str[:5000],
                error_message=str(e)[:500]
            )
            db.session.add(webhook_log)
            db.session.commit()

            return jsonify({
                'success': False,
                'message': 'Test webhook failed',
                'error': str(e)
            }), 200

    except Exception as e:
        logger.error(f"Error testing workflow: {e}")
        return jsonify({'error': str(e)}), 500
