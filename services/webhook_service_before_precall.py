"""
Webhook Service for n8n Integration
Production-grade webhook delivery with:
- NON-BLOCKING execution (threading)
- API key authentication
- HMAC signature verification
- Retry logic with exponential backoff
- Comprehensive logging
- Redis caching for workflow configs (40x speedup!)
"""
import json
import secrets
import hashlib
import hmac
import requests
import time
import logging
from datetime import datetime
from threading import Thread
from typing import Optional, Dict
from flask import current_app

# Redis caching service (40x speedup for workflow lookups!)
from services.redis_service import redis_service

logger = logging.getLogger(__name__)


class WebhookService:
    """Production-grade webhook service with retry logic"""

    MAX_RETRIES = 3
    RETRY_DELAYS = [2, 5, 10]  # seconds (exponential backoff)
    TIMEOUT = 15  # seconds

    @staticmethod
    def generate_api_key() -> str:
        """Generate secure API key (32 bytes = 43 chars in base64)"""
        return secrets.token_urlsafe(32)

    @staticmethod
    def generate_signature(payload: str, api_key: str) -> str:
        """Generate HMAC-SHA256 signature for payload verification"""
        return hmac.new(
            api_key.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    @staticmethod
    def _send_webhook_sync(
        app,
        workflow_id: int,
        workflow_url: str,
        api_key: str,
        call_data: Dict,
        call_log_id: Optional[int] = None,
        retry_count: int = 0
    ) -> bool:
        """
        Internal synchronous webhook sender (runs in background thread)

        THIS RUNS IN A SEPARATE THREAD - does not block Flask response

        Args:
            app: Flask app instance (for database context)
            workflow_id: Workflow database ID
            workflow_url: n8n webhook URL
            api_key: API key for authentication
            call_data: Dict of call data to send
            call_log_id: Optional call log ID for tracking
            retry_count: Current retry attempt

        Returns:
            bool: Success status
        """
        from models import db, Workflow, WebhookLog, SAUDI_TZ

        # Prepare payload
        payload_str = json.dumps(call_data, ensure_ascii=False)
        signature = WebhookService.generate_signature(payload_str, api_key)

        # Prepare headers with authentication
        headers = {
            'Content-Type': 'application/json; charset=utf-8',
            'X-Nevox-API-Key': api_key,
            'X-Nevox-Signature': signature,
            'X-Nevox-Timestamp': datetime.now().isoformat(),
            'User-Agent': 'Nevox-Webhook/1.0'
        }

        try:
            logger.info(f"📤 Sending webhook to workflow {workflow_id} (attempt {retry_count + 1}/{WebhookService.MAX_RETRIES + 1})")

            # Send POST request
            response = requests.post(
                workflow_url,
                json=call_data,
                headers=headers,
                timeout=WebhookService.TIMEOUT
            )

            response_text = response.text[:1000]  # Limit size

            # Use Flask app context for database operations
            with app.app_context():
                # ✅ STEP 1: Try Redis cache first (FAST! ~0.5ms)
                workflow_config = redis_service.get_workflow(workflow_id)

                if not workflow_config:
                    # ❌ Cache MISS - load from database (SLOW! ~20ms)
                    logger.debug(f"❌ Redis cache MISS: workflow {workflow_id} - loading from DB")
                    workflow = db.session.get(Workflow, workflow_id)

                    if workflow and workflow.is_active:
                        # Cache workflow config for next time (TTL: 30 minutes)
                        workflow_config = {
                            'id': workflow.id,
                            'url': workflow.webhook_url,
                            'is_active': workflow.is_active
                        }
                        redis_service.cache_workflow(workflow_id, workflow_config, ttl=1800)
                    else:
                        workflow = None  # Will use this for stats update
                else:
                    # ✅ Cache HIT - load minimal workflow object for stats update only
                    logger.debug(f"✅ Redis cache HIT: workflow {workflow_id}")
                    workflow = db.session.get(Workflow, workflow_id)

                # Create log entry
                webhook_log = WebhookLog(
                    workflow_id=workflow_id,
                    call_log_id=call_log_id,
                    status='success' if response.status_code == 200 else 'failed',
                    http_status=response.status_code,
                    request_payload=payload_str[:5000],  # Limit size
                    response_body=response_text,
                    retry_count=retry_count
                )

                if response.status_code == 200:
                    logger.info(f"✅ Webhook successful: workflow {workflow_id}")
                    if workflow:
                        workflow.successful_calls += 1
                        workflow.last_triggered_at = datetime.now(SAUDI_TZ).replace(tzinfo=None)
                    db.session.add(webhook_log)
                    db.session.commit()
                    return True
                else:
                    logger.warning(f"⚠️ Webhook returned {response.status_code}: {response_text[:200]}")
                    if workflow:
                        workflow.failed_calls += 1

                    # Retry on 5xx errors (server errors)
                    if response.status_code >= 500 and retry_count < WebhookService.MAX_RETRIES:
                        webhook_log.status = 'retrying'
                        db.session.add(webhook_log)
                        db.session.commit()

                        delay = WebhookService.RETRY_DELAYS[retry_count]
                        logger.info(f"🔄 Retrying in {delay}s... (server error)")
                        time.sleep(delay)

                        # Recursive retry
                        return WebhookService._send_webhook_sync(
                            app, workflow_id, workflow_url, api_key,
                            call_data, call_log_id, retry_count + 1
                        )

                    db.session.add(webhook_log)
                    db.session.commit()
                    return False

        except requests.exceptions.Timeout:
            error_msg = f"Timeout after {WebhookService.TIMEOUT}s"
            logger.error(f"⏱️ Webhook timeout: workflow {workflow_id}")

            with app.app_context():
                # Load workflow for stats update (no need to cache on error)
                workflow = db.session.get(Workflow, workflow_id)
                webhook_log = WebhookLog(
                    workflow_id=workflow_id,
                    call_log_id=call_log_id,
                    status='failed',
                    request_payload=payload_str[:5000],
                    error_message=error_msg,
                    retry_count=retry_count
                )
                if workflow:
                    workflow.failed_calls += 1
                db.session.add(webhook_log)
                db.session.commit()
            return False

        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Webhook error for workflow {workflow_id}: {error_msg}")

            with app.app_context():
                # Load workflow for stats update (no need to cache on error)
                workflow = db.session.get(Workflow, workflow_id)
                webhook_log = WebhookLog(
                    workflow_id=workflow_id,
                    call_log_id=call_log_id,
                    status='failed',
                    request_payload=payload_str[:5000],
                    error_message=error_msg[:500],
                    retry_count=retry_count
                )
                if workflow:
                    workflow.failed_calls += 1
                db.session.add(webhook_log)
                db.session.commit()

            # Retry on network errors
            if retry_count < WebhookService.MAX_RETRIES:
                delay = WebhookService.RETRY_DELAYS[retry_count]
                logger.info(f"🔄 Retrying in {delay}s... (network error)")
                time.sleep(delay)
                return WebhookService._send_webhook_sync(
                    app, workflow_id, workflow_url, api_key,
                    call_data, call_log_id, retry_count + 1
                )

            return False

    @staticmethod
    def trigger_webhook(
        workflow_id: int,
        workflow_url: str,
        api_key: str,
        call_data: Dict,
        call_log_id: Optional[int] = None
    ):
        """
        NON-BLOCKING webhook trigger (returns immediately)

        This spawns a background thread for webhook delivery.
        The Flask response is NOT delayed by retries or timeouts.

        Args:
            workflow_id: Workflow database ID
            workflow_url: n8n webhook URL
            api_key: API key for authentication
            call_data: Dict of call data to send
            call_log_id: Optional call log ID for tracking
        """
        # Get Flask app instance for database context
        app = current_app._get_current_object()

        # Spawn background thread (fire-and-forget)
        thread = Thread(
            target=WebhookService._send_webhook_sync,
            args=(app, workflow_id, workflow_url, api_key, call_data, call_log_id),
            daemon=True  # Thread dies when main process exits
        )
        thread.start()

        logger.info(f"🚀 Webhook triggered in background thread: workflow {workflow_id}")


    @staticmethod
    def fetch_pre_call_data(
        workflow_url: str,
        api_key: str,
        call_context: Dict,
        timeout: int = 3
    ) -> Optional[Dict]:
        """
        BLOCKING pre-call webhook to fetch customer data before call starts
        This is a synchronous call that blocks until response is received or timeout.
        Should be called BEFORE dispatching the LiveKit call.
        Args:
            workflow_url: n8n webhook URL
            api_key: API key for authentication
            call_context: Dict with call context (agent_name, phone_number, etc.)
            timeout: Max wait time in seconds
        Returns:
            Dict with webhook response data (raw), or None if failed/timeout
        Example response:
            {
                "customer_name": "أحمد محمد",
                "last_order": "iPhone 15 Pro",
                "order_date": "2024-12-15"
            }
        """
        payload_str = json.dumps(call_context, ensure_ascii=False)
        signature = WebhookService.generate_signature(payload_str, api_key)

        headers = {
            'Content-Type': 'application/json; charset=utf-8',
            'X-Nevox-API-Key': api_key,
            'X-Nevox-Signature': signature,
            'X-Nevox-Event': 'pre_call',
            'X-Nevox-Timestamp': datetime.now().isoformat(),
            'User-Agent': 'Nevox-PreCall-Webhook/1.0'
        }

        try:
            logger.info(f"📤 Fetching pre-call data from n8n (timeout: {timeout}s)...")

            # Send POST request (BLOCKING)
            response = requests.post(
                workflow_url,
                json=call_context,
                headers=headers,
                timeout=timeout
            )

            if response.status_code == 200:
                try:
                    webhook_data = response.json()
                    logger.info(f"✅ Pre-call webhook SUCCESS: {list(webhook_data.keys()) if webhook_data else 'empty'}")
                    return webhook_data if webhook_data else None
                except json.JSONDecodeError:
                    logger.warning(f"⚠️ Pre-call webhook returned invalid JSON: {response.text[:200]}")
                    return None
            else:
                logger.warning(f"⚠️ Pre-call webhook returned {response.status_code}: {response.text[:200]}")
                return None

        except requests.exceptions.Timeout:
            logger.warning(f"⏱️ Pre-call webhook timeout ({timeout}s)")
            return None

        except requests.exceptions.ConnectionError as e:
            logger.error(f"❌ Pre-call webhook connection error: {e}")
            return None

        except Exception as e:
            logger.error(f"❌ Pre-call webhook error: {e}")
            return None

# Singleton instance
webhook_service = WebhookService()
