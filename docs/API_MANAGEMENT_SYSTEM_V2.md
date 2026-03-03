# API Management System V2 - Simplified Implementation

## Overview

This document describes a **simplified** API Management System that enables external integrations (n8n, custom apps) to trigger outbound calls programmatically.

**Key Principle:** Reuse existing code, minimize complexity.

---

## Table of Contents

1. [Problem & Solution](#problem--solution)
2. [Architecture](#architecture)
3. [Implementation](#implementation)
4. [API Reference](#api-reference)
5. [n8n Integration Guide](#n8n-integration-guide)
6. [Step-by-Step Setup](#step-by-step-setup)

---

## Problem & Solution

### Business Need

External systems (n8n workflows) need to trigger calls for:
- **No-Show Recovery** - Call patients who missed appointments
- **Appointment Reminders** - Automated reminder calls
- **Appointment Confirmations** - Confirm bookings
- **Custom Outreach** - Any automated calling scenario

### Solution Approach

| Approach | Description |
|----------|-------------|
| ❌ **Over-engineered** | Create new CallService, duplicate functions, complex abstractions |
| ✅ **Simplified** | Reuse existing `make_livekit_call()`, add thin API layer |

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Reuse `make_livekit_call()`** | Already works, accepts `webhook_context` |
| **ThreadPoolExecutor** | Non-blocking - Flask responds immediately |
| **User-level API key** | Simple auth, one key per user |
| **Redis rate limiting** | Works with multiple workers |
| **Minimal new code** | ~200 lines vs ~1000 lines |

---

## Architecture

### System Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           API CALL FLOW                                      │
└─────────────────────────────────────────────────────────────────────────────┘

n8n / External System
        │
        │  POST /api/v1/call/initiate
        │  Headers: X-API-Key: nvx_sk_abc123...
        │  Body: {
        │    "agent_id": 5,
        │    "phone": "+966512345678",
        │    "call_type": "noshow_recovery",
        │    "context": {
        │      "patient_name": "Ahmed",
        │      "missed_date": "2026-01-29"
        │    }
        │  }
        │
        ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                         YOUR FLASK BACKEND                                 │
├───────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  ┌─────────────────┐                                                      │
│  │ 1. Validate     │ → User.query.filter_by(api_key=key)                  │
│  │    API Key      │   Returns User or 401                                │
│  └────────┬────────┘                                                      │
│           │                                                               │
│           ▼                                                               │
│  ┌─────────────────┐                                                      │
│  │ 2. Check Rate   │ → Redis: INCR api_rate:{user_id}                     │
│  │    Limit        │   Returns (allowed, remaining) or 429                │
│  └────────┬────────┘                                                      │
│           │                                                               │
│           ▼                                                               │
│  ┌─────────────────┐                                                      │
│  │ 3. Verify Agent │ → Agent.query.filter_by(id, user_id)                 │
│  │    Ownership    │   Returns Agent or 404                               │
│  └────────┬────────┘                                                      │
│           │                                                               │
│           ▼                                                               │
│  ┌─────────────────┐                                                      │
│  │ 4. Create       │ → CallLog(status='initiated')                        │
│  │    CallLog      │   Tracks the call                                    │
│  └────────┬────────┘                                                      │
│           │                                                               │
│           ▼                                                               │
│  ┌─────────────────┐     ┌──────────────────────────────────────────┐    │
│  │ 5. Submit to    │────▶│  Background Thread (ThreadPoolExecutor)  │    │
│  │    ThreadPool   │     │                                          │    │
│  └────────┬────────┘     │  asyncio.run(make_livekit_call(          │    │
│           │              │      phone, room_name, agent_name,        │    │
│           │              │      trunk_id, agent_id,                  │    │
│           │              │      webhook_context={...}  ◀── CONTEXT   │    │
│           │              │  ))                                       │    │
│           │              │                                          │    │
│           │              │  ┌────────────────────────────────────┐  │    │
│           │              │  │ EXISTING make_livekit_call():      │  │    │
│           │              │  │ - Creates room with metadata       │  │    │
│           │              │  │ - Dispatches agent                 │  │    │
│           │              │  │ - Creates SIP participant          │  │    │
│           │              │  │ - Context in room_metadata         │  │    │
│           │              │  └────────────────────────────────────┘  │    │
│           │              └──────────────────────────────────────────┘    │
│           │                                                               │
│           ▼                                                               │
│  ┌─────────────────┐                                                      │
│  │ 6. Return       │ → {"success": true, "call_id": 123}                  │
│  │    Immediately  │   Response time: <100ms                              │
│  └─────────────────┘                                                      │
│                                                                           │
└───────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                         LIVEKIT + AI AGENT                                 │
├───────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  Agent reads context from room.metadata:                                  │
│  {                                                                        │
│    "type": "noshow_recovery",                                             │
│    "agent_id": 5,                                                         │
│    "webhook_context": {                                                   │
│      "source": "api",                                                     │
│      "call_type": "noshow_recovery",                                      │
│      "patient_name": "Ahmed",                                             │
│      "missed_date": "2026-01-29"                                          │
│    }                                                                      │
│  }                                                                        │
│                                                                           │
│  AI Agent conducts call with full context!                                │
│                                                                           │
└───────────────────────────────────────────────────────────────────────────┘
```

### File Structure

```
nevoxai-project/
│
├── models.py                    # Add: api_key, api_key_created_at
│
├── services/
│   └── api_rate_limiter.py     # NEW: Redis-based rate limiting
│
├── routes/
│   ├── agents.py               # EXISTING: make_livekit_call() - NO CHANGES
│   ├── external_api.py         # NEW: /api/v1/... endpoints
│   └── api_settings.py         # NEW: UI for API key management
│
├── templates/
│   └── settings/
│       └── api_keys.html       # NEW: API key management UI
│
└── migrations/
    └── add_api_key_to_user.py  # NEW: Database migration
```

### What We Reuse (No Changes Needed)

| Component | Location | Why Reuse |
|-----------|----------|-----------|
| `make_livekit_call()` | routes/agents.py:447 | Already handles context via `webhook_context` |
| `format_saudi_phone_number()` | routes/agents.py:309 | Phone formatting |
| `redis_service` | services/redis_service.py | Already configured |
| `CallLog` model | models.py | Standard call tracking |

---

## Implementation

### 1. Database Changes

#### models.py - Add to User class

```python
class User(db.Model):
    # ... existing fields ...

    # API Management (ADD THESE)
    api_key = db.Column(db.String(64), unique=True, nullable=True, index=True)
    api_key_created_at = db.Column(db.DateTime, nullable=True)
    api_rate_limit = db.Column(db.Integer, default=100)  # calls per hour
```

#### Migration Script

Create file: `migrations/add_api_key_to_user.py`

```python
"""
Migration: Add API key fields to User model
Run: python migrations/add_api_key_to_user.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models import db

def upgrade():
    with app.app_context():
        # Add api_key column
        try:
            db.session.execute(db.text(
                'ALTER TABLE user ADD COLUMN api_key VARCHAR(64) UNIQUE'
            ))
            print("✅ Added api_key column")
        except Exception as e:
            print(f"⚠️ api_key may exist: {e}")

        # Add api_key_created_at column
        try:
            db.session.execute(db.text(
                'ALTER TABLE user ADD COLUMN api_key_created_at DATETIME'
            ))
            print("✅ Added api_key_created_at column")
        except Exception as e:
            print(f"⚠️ api_key_created_at may exist: {e}")

        # Add api_rate_limit column
        try:
            db.session.execute(db.text(
                'ALTER TABLE user ADD COLUMN api_rate_limit INTEGER DEFAULT 100'
            ))
            print("✅ Added api_rate_limit column")
        except Exception as e:
            print(f"⚠️ api_rate_limit may exist: {e}")

        # Create index for fast lookups
        try:
            db.session.execute(db.text(
                'CREATE INDEX IF NOT EXISTS idx_user_api_key ON user(api_key)'
            ))
            print("✅ Created index on api_key")
        except Exception as e:
            print(f"⚠️ Index may exist: {e}")

        db.session.commit()
        print("\n✅ Migration complete!")

def downgrade():
    print("SQLite doesn't support DROP COLUMN easily. Manual cleanup required.")

if __name__ == '__main__':
    upgrade()
```

---

### 2. Rate Limiter Service (Redis-based)

Create file: `services/api_rate_limiter.py`

```python
"""
API Rate Limiter - Redis-based for multi-worker support
"""
import logging
from typing import Tuple

logger = logging.getLogger(__name__)


class APIRateLimiter:
    """
    Redis-based rate limiter for API calls

    Why Redis instead of in-memory?
    - Works with multiple Flask workers (Gunicorn)
    - Survives process restarts
    - Accurate rate limiting across all instances
    """

    def __init__(self):
        self.redis = None
        self._init_redis()

    def _init_redis(self):
        """Initialize Redis connection"""
        try:
            from services.redis_service import redis_service
            self.redis = redis_service.redis_client
            logger.info("✅ API Rate Limiter connected to Redis")
        except Exception as e:
            logger.warning(f"⚠️ Redis not available, rate limiting disabled: {e}")
            self.redis = None

    def is_allowed(self, user_id: int, limit: int = 100, window_seconds: int = 3600) -> Tuple[bool, int]:
        """
        Check if user is within rate limit

        Args:
            user_id: User ID to check
            limit: Max calls per window (default: 100)
            window_seconds: Window size (default: 3600 = 1 hour)

        Returns:
            Tuple of (is_allowed, remaining_calls)
        """
        if not self.redis:
            # Redis unavailable - allow but log warning
            logger.warning("Rate limiting disabled (no Redis)")
            return True, limit

        key = f"api_rate:{user_id}"

        try:
            # Get current count
            current = self.redis.get(key)
            current = int(current) if current else 0

            if current >= limit:
                logger.warning(f"Rate limit exceeded for user {user_id}: {current}/{limit}")
                return False, 0

            # Increment counter with expiry
            pipe = self.redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, window_seconds)
            pipe.execute()

            remaining = limit - current - 1
            return True, remaining

        except Exception as e:
            logger.error(f"Rate limiter error: {e}")
            return True, limit  # Allow on error

    def get_usage(self, user_id: int) -> dict:
        """Get current usage stats for a user"""
        if not self.redis:
            return {"calls_used": 0, "error": "Redis unavailable"}

        key = f"api_rate:{user_id}"

        try:
            current = self.redis.get(key)
            ttl = self.redis.ttl(key)

            return {
                "calls_used": int(current) if current else 0,
                "ttl_seconds": ttl if ttl > 0 else 3600
            }
        except Exception as e:
            return {"calls_used": 0, "error": str(e)}

    def reset(self, user_id: int) -> bool:
        """Reset rate limit for a user (admin function)"""
        if not self.redis:
            return False

        key = f"api_rate:{user_id}"
        try:
            self.redis.delete(key)
            logger.info(f"Rate limit reset for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to reset rate limit: {e}")
            return False


# Global instance
api_rate_limiter = APIRateLimiter()
```

---

### 3. External API Routes

Create file: `routes/external_api.py`

```python
"""
External API Routes - /api/v1/...
Enables external systems (n8n) to trigger calls programmatically

Key Design:
- Reuses existing make_livekit_call() - no code duplication
- ThreadPoolExecutor for non-blocking execution
- Redis-based rate limiting
"""
import os
import time
import secrets
import logging
import asyncio
from datetime import datetime
from functools import wraps
from concurrent.futures import ThreadPoolExecutor

from flask import Blueprint, request, jsonify

from models import db, User, Agent, CallLog, Campaign, SAUDI_TZ
from services.api_rate_limiter import api_rate_limiter

# Import EXISTING functions - no duplication!
from routes.agents import make_livekit_call, format_saudi_phone_number

logger = logging.getLogger(__name__)

# Blueprint
external_api_bp = Blueprint('external_api', __name__, url_prefix='/api/v1')

# Thread pool for non-blocking call execution
# This prevents Flask from blocking while waiting for LiveKit
call_executor = ThreadPoolExecutor(max_workers=20, thread_name_prefix='api_call_')


# ============================================================================
#                           AUTHENTICATION
# ============================================================================

def require_api_key(f):
    """
    Decorator: Validate API key and check rate limit

    On success, adds to request:
    - request.api_user: User object
    - request.rate_limit_remaining: Remaining calls
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # Get API key from header
        api_key = request.headers.get('X-API-Key')

        if not api_key:
            return jsonify({
                'success': False,
                'error': 'API key required. Include X-API-Key header.',
                'code': 'MISSING_API_KEY'
            }), 401

        # Validate key format
        if not api_key.startswith('nvx_sk_'):
            return jsonify({
                'success': False,
                'error': 'Invalid API key format',
                'code': 'INVALID_KEY_FORMAT'
            }), 401

        # Find user by API key
        user = User.query.filter_by(api_key=api_key).first()

        if not user:
            logger.warning(f"Invalid API key attempt: {api_key[:15]}...")
            return jsonify({
                'success': False,
                'error': 'Invalid API key',
                'code': 'INVALID_API_KEY'
            }), 401

        # Check user is approved
        if not user.is_approved:
            return jsonify({
                'success': False,
                'error': 'Account not approved',
                'code': 'ACCOUNT_NOT_APPROVED'
            }), 403

        # Check rate limit
        limit = user.api_rate_limit or 100
        allowed, remaining = api_rate_limiter.is_allowed(user.id, limit=limit)

        if not allowed:
            return jsonify({
                'success': False,
                'error': f'Rate limit exceeded. Max {limit} calls per hour.',
                'code': 'RATE_LIMIT_EXCEEDED',
                'retry_after_seconds': 3600
            }), 429

        # Attach to request
        request.api_user = user
        request.rate_limit_remaining = remaining

        return f(*args, **kwargs)

    return decorated


# ============================================================================
#                           CALL ENDPOINTS
# ============================================================================

@external_api_bp.route('/call/initiate', methods=['POST'])
@require_api_key
def initiate_call():
    """
    Initiate an outbound call

    This is the PRIMARY endpoint for triggering calls from n8n or external systems.

    Request:
        POST /api/v1/call/initiate
        Headers:
            X-API-Key: nvx_sk_your_key_here
            Content-Type: application/json
        Body:
            {
                "agent_id": 5,                      // Required: Your agent ID
                "phone": "+966512345678",           // Required: Phone to call
                "call_type": "noshow_recovery",     // Optional: For categorization
                "context": {                        // Optional: Passed to AI agent
                    "patient_name": "Ahmed",
                    "missed_appointment": {
                        "date": "2026-01-29",
                        "time": "10:00",
                        "doctor": "Dr. Fatima"
                    }
                }
            }

    Response (Success - 200):
        {
            "success": true,
            "call_id": 1234,
            "room_name": "noshow_recovery-5-1706621234",
            "status": "initiated",
            "rate_limit_remaining": 95
        }

    Response (Error - 4xx):
        {
            "success": false,
            "error": "Error description",
            "code": "ERROR_CODE"
        }

    Call Types:
        - outbound: Generic outbound call
        - noshow_recovery: Follow up on missed appointment
        - appointment_reminder: Reminder before appointment
        - appointment_confirmation: Confirm booking
        - campaign: Bulk campaign call
        - custom: Any other type

    Context:
        The 'context' object is passed directly to the AI agent via room metadata.
        The agent can access this data to personalize the conversation.

        Example: For no-show recovery, include patient name and missed appointment
        details so the AI can say "Hi Ahmed, I'm calling about your missed
        appointment on January 29th..."
    """
    user = request.api_user
    data = request.get_json()

    # ========== VALIDATION ==========

    if not data:
        return jsonify({
            'success': False,
            'error': 'Request body required',
            'code': 'MISSING_BODY'
        }), 400

    agent_id = data.get('agent_id')
    phone = data.get('phone')
    call_type = data.get('call_type', 'api_outbound')
    context = data.get('context', {})

    if not agent_id:
        return jsonify({
            'success': False,
            'error': 'agent_id is required',
            'code': 'MISSING_AGENT_ID'
        }), 400

    if not phone:
        return jsonify({
            'success': False,
            'error': 'phone is required',
            'code': 'MISSING_PHONE'
        }), 400

    # Validate agent belongs to user
    agent = Agent.query.filter_by(id=agent_id, user_id=user.id).first()
    if not agent:
        return jsonify({
            'success': False,
            'error': 'Agent not found or access denied',
            'code': 'AGENT_NOT_FOUND'
        }), 404

    # Check minutes balance
    if user.minutes_balance <= 0:
        return jsonify({
            'success': False,
            'error': 'Insufficient minutes balance',
            'code': 'INSUFFICIENT_MINUTES'
        }), 400

    # Get outbound trunk
    outbound_trunk_id = user.outbound_trunk_id or os.environ.get('SIP_OUTBOUND_TRUNK_ID')
    if not outbound_trunk_id:
        return jsonify({
            'success': False,
            'error': 'No outbound trunk configured',
            'code': 'NO_TRUNK'
        }), 400

    # ========== PREPARE CALL ==========

    # Format phone number
    try:
        formatted_phone = format_saudi_phone_number(phone)
    except Exception:
        formatted_phone = phone  # Use as-is if formatting fails

    # Generate unique room name
    timestamp = int(datetime.now().timestamp())
    room_name = f"{call_type}-{agent_id}-{timestamp}"

    # Build webhook_context (passed to AI agent via room metadata)
    webhook_context = {
        "source": "api",
        "call_type": call_type,
        "initiated_at": datetime.now(SAUDI_TZ).isoformat(),
        "api_user_id": user.id,
        **context  # Merge user-provided context (patient_name, etc.)
    }

    # ========== INITIATE CALL ==========

    try:
        # Create CallLog record FIRST (so we have call_id)
        call_log = CallLog(
            user_id=user.id,
            agent_id=agent_id,
            from_number=os.environ.get('SAUDI_PHONE_NUMBER', ''),
            to_number=formatted_phone,
            room_name=room_name,
            status='initiated',
            call_type='outbound'
        )
        db.session.add(call_log)
        db.session.flush()  # Get ID without full commit

        # Add call_id to context (agent can reference this)
        webhook_context['call_id'] = call_log.id

        # ✅ SUBMIT TO THREAD POOL (Non-blocking!)
        # This returns immediately - Flask doesn't wait for LiveKit
        call_executor.submit(
            _execute_call,
            formatted_phone,
            room_name,
            agent.name,
            outbound_trunk_id,
            agent_id,
            webhook_context
        )

        # Commit database changes
        db.session.commit()

        logger.info(
            f"✅ API call initiated | "
            f"call_id={call_log.id} | room={room_name} | "
            f"user={user.id} | agent={agent_id} | type={call_type}"
        )

        return jsonify({
            'success': True,
            'call_id': call_log.id,
            'room_name': room_name,
            'status': 'initiated',
            'rate_limit_remaining': request.rate_limit_remaining
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ API call failed: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e),
            'code': 'CALL_FAILED'
        }), 500


def _execute_call(phone, room_name, agent_name, trunk_id, agent_id, context):
    """
    Execute call in background thread

    This runs in ThreadPoolExecutor, separate from Flask request thread.
    Uses the EXISTING make_livekit_call() function - no code duplication!
    """
    try:
        asyncio.run(
            make_livekit_call(
                phone_number=phone,
                room_name=room_name,
                agent_name=agent_name,
                outbound_trunk_id=trunk_id,
                agent_id=agent_id,
                webhook_context=context  # ✅ Context passed to agent!
            )
        )
        logger.info(f"✅ Call executed: {room_name}")
    except Exception as e:
        logger.error(f"❌ Call execution failed: {room_name} - {e}")
        # Could update CallLog.status = 'failed' here if needed


@external_api_bp.route('/call/<int:call_id>/status', methods=['GET'])
@require_api_key
def get_call_status(call_id):
    """
    Get call status and details

    Request:
        GET /api/v1/call/1234/status
        Headers:
            X-API-Key: nvx_sk_...

    Response:
        {
            "success": true,
            "call_id": 1234,
            "status": "completed",
            "duration_seconds": 145,
            "to_number": "+966512345678",
            "agent_id": 5,
            "room_name": "noshow_recovery-5-1706621234",
            "created_at": "2026-01-29T10:30:00"
        }

    Status Values:
        - initiated: Call request received, connecting
        - completed: Call finished successfully
        - failed: Call failed to connect
        - no_answer: Phone not answered
    """
    user = request.api_user

    call_log = CallLog.query.filter_by(id=call_id, user_id=user.id).first()

    if not call_log:
        return jsonify({
            'success': False,
            'error': 'Call not found',
            'code': 'CALL_NOT_FOUND'
        }), 404

    return jsonify({
        'success': True,
        'call_id': call_log.id,
        'status': call_log.status,
        'duration_seconds': call_log.duration_seconds or 0,
        'to_number': call_log.to_number,
        'agent_id': call_log.agent_id,
        'room_name': call_log.room_name,
        'created_at': call_log.created_at.isoformat() if call_log.created_at else None
    }), 200


@external_api_bp.route('/call/<int:call_id>/transcript', methods=['GET'])
@require_api_key
def get_call_transcript(call_id):
    """
    Get call transcript and recording

    Request:
        GET /api/v1/call/1234/transcript
        Headers:
            X-API-Key: nvx_sk_...

    Response:
        {
            "success": true,
            "call_id": 1234,
            "transcription": "Agent: السلام عليكم...\nUser: وعليكم السلام...",
            "duration_seconds": 145,
            "recording_url": "https://..."
        }

    Note: Transcript is available after call completes.
    """
    user = request.api_user

    call_log = CallLog.query.filter_by(id=call_id, user_id=user.id).first()

    if not call_log:
        return jsonify({
            'success': False,
            'error': 'Call not found',
            'code': 'CALL_NOT_FOUND'
        }), 404

    return jsonify({
        'success': True,
        'call_id': call_log.id,
        'status': call_log.status,
        'transcription': call_log.transcription or '',
        'duration_seconds': call_log.duration_seconds or 0,
        'recording_url': call_log.recording_url
    }), 200


# ============================================================================
#                           CAMPAIGN ENDPOINTS
# ============================================================================

@external_api_bp.route('/campaign/<int:campaign_id>/start', methods=['POST'])
@require_api_key
def start_campaign(campaign_id):
    """
    Start a campaign via API

    Request:
        POST /api/v1/campaign/123/start
        Headers:
            X-API-Key: nvx_sk_...

    Response:
        {
            "success": true,
            "campaign_id": 123,
            "name": "January Outreach",
            "status": "running",
            "contacts_count": 150
        }
    """
    from services.redis_service import redis_service

    user = request.api_user

    campaign = Campaign.query.filter_by(id=campaign_id, user_id=user.id).first()

    if not campaign:
        return jsonify({
            'success': False,
            'error': 'Campaign not found',
            'code': 'CAMPAIGN_NOT_FOUND'
        }), 404

    if campaign.status == 'running':
        return jsonify({
            'success': False,
            'error': 'Campaign is already running',
            'code': 'ALREADY_RUNNING'
        }), 400

    if len(campaign.contacts) == 0:
        return jsonify({
            'success': False,
            'error': 'Campaign has no contacts',
            'code': 'NO_CONTACTS'
        }), 400

    # Start campaign
    campaign.status = 'running'
    campaign.start_time = datetime.now(SAUDI_TZ).replace(tzinfo=None)
    db.session.commit()

    # Invalidate cache
    redis_service.invalidate_campaign_metadata(campaign_id)

    logger.info(f"✅ Campaign {campaign_id} started via API by user {user.id}")

    return jsonify({
        'success': True,
        'campaign_id': campaign.id,
        'name': campaign.name,
        'status': 'running',
        'contacts_count': len(campaign.contacts)
    }), 200


@external_api_bp.route('/campaign/<int:campaign_id>/pause', methods=['POST'])
@require_api_key
def pause_campaign(campaign_id):
    """Pause a running campaign"""
    from services.redis_service import redis_service

    user = request.api_user
    campaign = Campaign.query.filter_by(id=campaign_id, user_id=user.id).first()

    if not campaign:
        return jsonify({'success': False, 'error': 'Campaign not found'}), 404

    if campaign.status != 'running':
        return jsonify({'success': False, 'error': 'Campaign is not running'}), 400

    campaign.status = 'paused'
    db.session.commit()
    redis_service.invalidate_campaign_metadata(campaign_id)

    return jsonify({
        'success': True,
        'campaign_id': campaign.id,
        'status': 'paused'
    }), 200


@external_api_bp.route('/campaign/<int:campaign_id>/status', methods=['GET'])
@require_api_key
def get_campaign_status(campaign_id):
    """
    Get campaign status and progress

    Response:
        {
            "success": true,
            "campaign_id": 123,
            "name": "January Outreach",
            "status": "running",
            "progress": {
                "total": 150,
                "completed": 45,
                "pending": 100,
                "failed": 5,
                "percentage": 30
            }
        }
    """
    user = request.api_user
    campaign = Campaign.query.filter_by(id=campaign_id, user_id=user.id).first()

    if not campaign:
        return jsonify({'success': False, 'error': 'Campaign not found'}), 404

    # Calculate progress
    contacts = campaign.contacts
    total = len(contacts)
    completed = len([c for c in contacts if c.status == 'completed'])
    pending = len([c for c in contacts if c.status == 'pending'])
    failed = len([c for c in contacts if c.status == 'failed'])
    no_answer = len([c for c in contacts if c.status == 'no_answer'])

    return jsonify({
        'success': True,
        'campaign_id': campaign.id,
        'name': campaign.name,
        'status': campaign.status,
        'progress': {
            'total': total,
            'completed': completed,
            'pending': pending,
            'failed': failed,
            'no_answer': no_answer,
            'percentage': int((completed / total * 100)) if total > 0 else 0
        }
    }), 200


# ============================================================================
#                           UTILITY ENDPOINTS
# ============================================================================

@external_api_bp.route('/agents', methods=['GET'])
@require_api_key
def list_agents():
    """
    List all agents for the authenticated user

    Response:
        {
            "success": true,
            "agents": [
                {"id": 1, "name": "Sales Agent", "call_type": "outbound"},
                {"id": 2, "name": "Support Agent", "call_type": "inbound"}
            ]
        }
    """
    user = request.api_user
    agents = Agent.query.filter_by(user_id=user.id).order_by(Agent.name).all()

    return jsonify({
        'success': True,
        'agents': [{
            'id': a.id,
            'name': a.name,
            'call_type': a.call_type,
            'voice_name': a.voice_name
        } for a in agents]
    }), 200


@external_api_bp.route('/campaigns', methods=['GET'])
@require_api_key
def list_campaigns():
    """List all campaigns for the authenticated user"""
    user = request.api_user
    campaigns = Campaign.query.filter_by(user_id=user.id).order_by(Campaign.created_at.desc()).all()

    return jsonify({
        'success': True,
        'campaigns': [{
            'id': c.id,
            'name': c.name,
            'status': c.status,
            'contacts_count': len(c.contacts)
        } for c in campaigns]
    }), 200


@external_api_bp.route('/usage', methods=['GET'])
@require_api_key
def get_usage():
    """
    Get API usage statistics

    Response:
        {
            "success": true,
            "rate_limit": 100,
            "calls_this_hour": 15,
            "remaining": 85,
            "minutes_balance": 500
        }
    """
    user = request.api_user
    usage = api_rate_limiter.get_usage(user.id)
    limit = user.api_rate_limit or 100

    return jsonify({
        'success': True,
        'rate_limit': limit,
        'calls_this_hour': usage.get('calls_used', 0),
        'remaining': limit - usage.get('calls_used', 0),
        'minutes_balance': user.minutes_balance
    }), 200


@external_api_bp.route('/health', methods=['GET'])
def health():
    """
    Health check endpoint (no authentication required)

    Use this to verify the API is running.
    """
    return jsonify({
        'status': 'healthy',
        'service': 'NevoxAI External API',
        'version': '2.0',
        'timestamp': datetime.now(SAUDI_TZ).isoformat()
    }), 200
```

---

### 4. API Settings Routes (UI)

Create file: `routes/api_settings.py`

```python
"""
API Settings Routes - UI for managing API keys
"""
import secrets
import logging
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, session, jsonify

from models import db, User, SAUDI_TZ
from services.api_rate_limiter import api_rate_limiter
from utils.decorators import login_required, approved_required

logger = logging.getLogger(__name__)

api_settings_bp = Blueprint('api_settings', __name__, url_prefix='/settings/api')


@api_settings_bp.route('/')
@login_required
@approved_required
def api_settings():
    """API Key Management Page"""
    user = db.session.get(User, session['user_id'])

    # Get masked key for display
    masked_key = None
    if user.api_key:
        masked_key = f"{user.api_key[:13]}...{user.api_key[-4:]}"

    # Check for newly generated key (show once)
    new_key = session.pop('new_api_key', None)

    # Get usage stats
    usage = api_rate_limiter.get_usage(user.id)

    return render_template('settings/api_keys.html',
        user=user,
        masked_key=masked_key,
        new_api_key=new_key,
        has_key=bool(user.api_key),
        key_created_at=user.api_key_created_at,
        rate_limit=user.api_rate_limit or 100,
        usage=usage
    )


@api_settings_bp.route('/generate', methods=['POST'])
@login_required
@approved_required
def generate_key():
    """Generate new API key"""
    user = db.session.get(User, session['user_id'])

    if user.api_key:
        flash('You already have an API key. Regenerate to create a new one.', 'warning')
        return redirect(url_for('api_settings.api_settings'))

    # Generate secure key
    api_key = f"nvx_sk_{secrets.token_hex(24)}"

    user.api_key = api_key
    user.api_key_created_at = datetime.now(SAUDI_TZ).replace(tzinfo=None)
    db.session.commit()

    # Store in session to show once
    session['new_api_key'] = api_key

    logger.info(f"API key generated for user {user.id}")
    flash('API key generated! Copy it now - it will only be shown once.', 'success')

    return redirect(url_for('api_settings.api_settings'))


@api_settings_bp.route('/regenerate', methods=['POST'])
@login_required
@approved_required
def regenerate_key():
    """Regenerate API key (revokes old one)"""
    user = db.session.get(User, session['user_id'])

    # Generate new key
    api_key = f"nvx_sk_{secrets.token_hex(24)}"

    user.api_key = api_key
    user.api_key_created_at = datetime.now(SAUDI_TZ).replace(tzinfo=None)
    db.session.commit()

    # Reset rate limit
    api_rate_limiter.reset(user.id)

    # Store in session to show once
    session['new_api_key'] = api_key

    logger.info(f"API key regenerated for user {user.id}")
    flash('API key regenerated! Your old key has been revoked.', 'success')

    return redirect(url_for('api_settings.api_settings'))


@api_settings_bp.route('/revoke', methods=['POST'])
@login_required
@approved_required
def revoke_key():
    """Revoke API key"""
    user = db.session.get(User, session['user_id'])

    user.api_key = None
    user.api_key_created_at = None
    db.session.commit()

    logger.info(f"API key revoked for user {user.id}")
    flash('API key revoked. Any integrations using it will stop working.', 'success')

    return redirect(url_for('api_settings.api_settings'))
```

---

### 5. API Settings Template (UI)

Create file: `templates/settings/api_keys.html`

```html
{% extends "base.html" %}

{% block title %}API Keys - NevoxAI{% endblock %}

{% block content %}
<div class="container-fluid py-4">
    <div class="row">
        <div class="col-12">
            <h2 class="mb-4">
                <i class="fas fa-key me-2"></i>API Management
            </h2>
        </div>
    </div>

    <div class="row">
        <!-- API Key Card -->
        <div class="col-lg-8">
            <div class="card mb-4">
                <div class="card-header">
                    <h5 class="mb-0"><i class="fas fa-shield-alt me-2"></i>Your API Key</h5>
                </div>
                <div class="card-body">

                    {% if new_api_key %}
                    <!-- Show newly generated key (ONE TIME ONLY) -->
                    <div class="alert alert-success">
                        <h6 class="alert-heading">
                            <i class="fas fa-check-circle me-2"></i>Your New API Key
                        </h6>
                        <p class="mb-2">Copy this key now. It will only be shown once!</p>
                        <div class="input-group mb-3">
                            <input type="text" class="form-control font-monospace bg-light"
                                   id="newApiKey" value="{{ new_api_key }}" readonly>
                            <button class="btn btn-primary" type="button" onclick="copyKey()">
                                <i class="fas fa-copy me-1"></i>Copy
                            </button>
                        </div>
                        <small class="text-muted">
                            <i class="fas fa-exclamation-triangle me-1"></i>
                            Store this key securely. You won't be able to see it again.
                        </small>
                    </div>
                    {% endif %}

                    {% if has_key %}
                    <div class="mb-4">
                        <label class="form-label text-muted small">Current API Key</label>
                        <div class="input-group">
                            <input type="text" class="form-control font-monospace"
                                   value="{{ masked_key }}" readonly>
                            <span class="input-group-text"><i class="fas fa-lock"></i></span>
                        </div>
                        <small class="text-muted">
                            Created: {{ key_created_at.strftime('%Y-%m-%d %H:%M') if key_created_at else 'Unknown' }}
                        </small>
                    </div>

                    <div class="d-flex gap-2">
                        <form action="{{ url_for('api_settings.regenerate_key') }}" method="POST"
                              onsubmit="return confirm('This will revoke your current key. Continue?')">
                            <button type="submit" class="btn btn-warning">
                                <i class="fas fa-sync-alt me-1"></i>Regenerate
                            </button>
                        </form>
                        <form action="{{ url_for('api_settings.revoke_key') }}" method="POST"
                              onsubmit="return confirm('Revoke your API key? Integrations will stop working.')">
                            <button type="submit" class="btn btn-outline-danger">
                                <i class="fas fa-trash me-1"></i>Revoke
                            </button>
                        </form>
                    </div>

                    {% else %}
                    <div class="text-center py-5">
                        <i class="fas fa-key fa-4x text-muted mb-3"></i>
                        <p class="text-muted mb-4">No API key generated yet</p>
                        <form action="{{ url_for('api_settings.generate_key') }}" method="POST">
                            <button type="submit" class="btn btn-primary btn-lg">
                                <i class="fas fa-plus me-2"></i>Generate API Key
                            </button>
                        </form>
                    </div>
                    {% endif %}
                </div>
            </div>

            <!-- Quick Start Guide -->
            <div class="card">
                <div class="card-header">
                    <h5 class="mb-0"><i class="fas fa-book me-2"></i>Quick Start</h5>
                </div>
                <div class="card-body">
                    <h6>Base URL</h6>
                    <pre class="bg-dark text-light p-3 rounded"><code>{{ request.host_url }}api/v1</code></pre>

                    <h6>Authentication</h6>
                    <p>Include your API key in the <code>X-API-Key</code> header:</p>
                    <pre class="bg-dark text-light p-3 rounded"><code>X-API-Key: nvx_sk_your_key_here</code></pre>

                    <h6>Example: Initiate a Call</h6>
                    <pre class="bg-dark text-light p-3 rounded"><code>curl -X POST {{ request.host_url }}api/v1/call/initiate \
  -H "X-API-Key: nvx_sk_your_key" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": 5,
    "phone": "+966512345678",
    "call_type": "noshow_recovery",
    "context": {
      "patient_name": "Ahmed",
      "missed_date": "2026-01-29"
    }
  }'</code></pre>

                    <h6 class="mt-4">Available Endpoints</h6>
                    <table class="table table-sm">
                        <thead>
                            <tr><th>Method</th><th>Endpoint</th><th>Description</th></tr>
                        </thead>
                        <tbody>
                            <tr>
                                <td><span class="badge bg-success">POST</span></td>
                                <td><code>/call/initiate</code></td>
                                <td>Trigger outbound call</td>
                            </tr>
                            <tr>
                                <td><span class="badge bg-primary">GET</span></td>
                                <td><code>/call/{id}/status</code></td>
                                <td>Get call status</td>
                            </tr>
                            <tr>
                                <td><span class="badge bg-primary">GET</span></td>
                                <td><code>/call/{id}/transcript</code></td>
                                <td>Get transcript</td>
                            </tr>
                            <tr>
                                <td><span class="badge bg-success">POST</span></td>
                                <td><code>/campaign/{id}/start</code></td>
                                <td>Start campaign</td>
                            </tr>
                            <tr>
                                <td><span class="badge bg-primary">GET</span></td>
                                <td><code>/campaign/{id}/status</code></td>
                                <td>Campaign progress</td>
                            </tr>
                            <tr>
                                <td><span class="badge bg-primary">GET</span></td>
                                <td><code>/agents</code></td>
                                <td>List your agents</td>
                            </tr>
                            <tr>
                                <td><span class="badge bg-primary">GET</span></td>
                                <td><code>/usage</code></td>
                                <td>API usage stats</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- Usage Stats -->
        <div class="col-lg-4">
            <div class="card mb-4">
                <div class="card-header">
                    <h5 class="mb-0"><i class="fas fa-chart-bar me-2"></i>Usage</h5>
                </div>
                <div class="card-body">
                    <div class="d-flex justify-content-between mb-2">
                        <span>API Calls (This Hour)</span>
                        <strong>{{ usage.get('calls_used', 0) }} / {{ rate_limit }}</strong>
                    </div>
                    {% set pct = ((usage.get('calls_used', 0) / rate_limit) * 100)|int %}
                    <div class="progress mb-3" style="height: 10px;">
                        <div class="progress-bar {% if pct > 80 %}bg-danger{% elif pct > 50 %}bg-warning{% else %}bg-success{% endif %}"
                             style="width: {{ pct }}%"></div>
                    </div>
                    <small class="text-muted">
                        {{ rate_limit - usage.get('calls_used', 0) }} calls remaining
                    </small>
                </div>
            </div>

            <div class="card">
                <div class="card-header">
                    <h5 class="mb-0"><i class="fas fa-info-circle me-2"></i>Tips</h5>
                </div>
                <div class="card-body">
                    <ul class="list-unstyled mb-0">
                        <li class="mb-2">
                            <i class="fas fa-check text-success me-2"></i>
                            Keep your API key secret
                        </li>
                        <li class="mb-2">
                            <i class="fas fa-check text-success me-2"></i>
                            Regenerate if compromised
                        </li>
                        <li class="mb-2">
                            <i class="fas fa-check text-success me-2"></i>
                            Rate limit: {{ rate_limit }} calls/hour
                        </li>
                        <li>
                            <i class="fas fa-check text-success me-2"></i>
                            Use context to personalize calls
                        </li>
                    </ul>
                </div>
            </div>
        </div>
    </div>
</div>

<script>
function copyKey() {
    const input = document.getElementById('newApiKey');
    input.select();
    document.execCommand('copy');

    const btn = event.target.closest('button');
    const original = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-check me-1"></i>Copied!';
    btn.classList.replace('btn-primary', 'btn-success');

    setTimeout(() => {
        btn.innerHTML = original;
        btn.classList.replace('btn-success', 'btn-primary');
    }, 2000);
}
</script>
{% endblock %}
```

---

## API Reference

### Authentication

All endpoints (except `/health`) require the `X-API-Key` header:

```
X-API-Key: nvx_sk_your_api_key_here
```

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/call/initiate` | Trigger outbound call |
| `GET` | `/api/v1/call/{id}/status` | Get call status |
| `GET` | `/api/v1/call/{id}/transcript` | Get transcript |
| `POST` | `/api/v1/campaign/{id}/start` | Start campaign |
| `POST` | `/api/v1/campaign/{id}/pause` | Pause campaign |
| `GET` | `/api/v1/campaign/{id}/status` | Campaign progress |
| `GET` | `/api/v1/agents` | List agents |
| `GET` | `/api/v1/campaigns` | List campaigns |
| `GET` | `/api/v1/usage` | API usage stats |
| `GET` | `/api/v1/health` | Health check |

### Call Types

| Type | Use Case |
|------|----------|
| `outbound` | Generic outbound call |
| `noshow_recovery` | Follow up on missed appointment |
| `appointment_reminder` | Reminder before appointment |
| `appointment_confirmation` | Confirm booking |
| `campaign` | Bulk campaign |
| `custom` | Any other |

### Error Codes

| Code | HTTP | Description |
|------|------|-------------|
| `MISSING_API_KEY` | 401 | No X-API-Key header |
| `INVALID_API_KEY` | 401 | Key not found |
| `RATE_LIMIT_EXCEEDED` | 429 | Too many requests |
| `AGENT_NOT_FOUND` | 404 | Agent doesn't exist |
| `CALL_NOT_FOUND` | 404 | Call doesn't exist |
| `INSUFFICIENT_MINUTES` | 400 | No minutes balance |
| `CALL_FAILED` | 500 | Call initiation failed |

---

## n8n Integration Guide

### No-Show Recovery Workflow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Webhook    │     │  HTTP       │     │  Wait       │     │  HTTP       │
│  Trigger    │────▶│  Request    │────▶│  (Poll)     │────▶│  Request    │
│  (from CRM) │     │  /call/init │     │             │     │  /status    │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
```

### n8n HTTP Request Node Configuration

**Initiate Call:**

```json
{
  "method": "POST",
  "url": "https://your-domain.com/api/v1/call/initiate",
  "authentication": "genericCredentialType",
  "genericAuthType": "httpHeaderAuth",
  "httpHeaderAuth": {
    "name": "X-API-Key",
    "value": "nvx_sk_your_key"
  },
  "sendBody": true,
  "bodyContentType": "json",
  "jsonBody": {
    "agent_id": "={{ $json.agent_id }}",
    "phone": "={{ $json.patient_phone }}",
    "call_type": "noshow_recovery",
    "context": {
      "patient_name": "={{ $json.patient_name }}",
      "missed_appointment": {
        "date": "={{ $json.appointment_date }}",
        "time": "={{ $json.appointment_time }}",
        "doctor": "={{ $json.doctor_name }}"
      }
    }
  }
}
```

**Check Status (Polling):**

```json
{
  "method": "GET",
  "url": "https://your-domain.com/api/v1/call/{{ $json.call_id }}/status",
  "authentication": "genericCredentialType",
  "genericAuthType": "httpHeaderAuth",
  "httpHeaderAuth": {
    "name": "X-API-Key",
    "value": "nvx_sk_your_key"
  }
}
```

### Polling Loop in n8n

Use the **Loop Over Items** or **Wait** node to poll until call completes:

```javascript
// n8n Code Node - Check if call is complete
const status = $json.status;

if (status === 'completed' || status === 'failed') {
  return { done: true, status };
}

// Not done - wait and retry
return { done: false };
```

---

## Step-by-Step Setup

### Step 1: Run Migration

```bash
cd nevoxai-project
python migrations/add_api_key_to_user.py
```

### Step 2: Create Files

Create these files in your project:
- `services/api_rate_limiter.py`
- `routes/external_api.py`
- `routes/api_settings.py`
- `templates/settings/api_keys.html`

### Step 3: Register Blueprints

In your `app.py`:

```python
from routes.external_api import external_api_bp
from routes.api_settings import api_settings_bp

app.register_blueprint(external_api_bp)
app.register_blueprint(api_settings_bp)
```

### Step 4: Add Navigation Link

In your sidebar/navigation template:

```html
<a href="{{ url_for('api_settings.api_settings') }}" class="nav-link">
    <i class="fas fa-key"></i>
    <span>API Keys</span>
</a>
```

### Step 5: Test the API

```bash
# 1. Generate API key from UI

# 2. Test health endpoint
curl https://your-domain.com/api/v1/health

# 3. Test call initiation
curl -X POST https://your-domain.com/api/v1/call/initiate \
  -H "X-API-Key: nvx_sk_your_key" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": 5,
    "phone": "+966512345678",
    "call_type": "noshow_recovery",
    "context": {
      "patient_name": "Ahmed"
    }
  }'
```

---

## Summary

### Files to Create

| File | Lines | Purpose |
|------|-------|---------|
| `migrations/add_api_key_to_user.py` | ~50 | Database migration |
| `services/api_rate_limiter.py` | ~80 | Redis rate limiting |
| `routes/external_api.py` | ~400 | API endpoints |
| `routes/api_settings.py` | ~80 | UI routes |
| `templates/settings/api_keys.html` | ~180 | UI template |
| **Total** | **~790** | |

### Files Modified

| File | Change |
|------|--------|
| `models.py` | Add 3 fields to User |
| `app.py` | Register 2 blueprints |

### Key Features

| Feature | Implementation |
|---------|----------------|
| **Reuses existing code** | `make_livekit_call()` from agents.py |
| **Non-blocking** | ThreadPoolExecutor |
| **Rate limiting** | Redis-based (multi-worker safe) |
| **Context injection** | Via `webhook_context` parameter |
| **Simple auth** | User-level API key |

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 2.0 | 2026-01-30 | Simplified implementation, reuses existing code |

---

## Support

For issues:
- GitHub: https://github.com/your-repo/issues
- Email: support@nevoxai.com
