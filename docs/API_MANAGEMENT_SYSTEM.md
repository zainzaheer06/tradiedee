# API Management System - Complete Implementation Guide

## Table of Contents
1. [Problem Statement](#problem-statement)
2. [Solution Overview](#solution-overview)
3. [Architecture](#architecture)
4. [Database Changes](#database-changes)
5. [Implementation Files](#implementation-files)
6. [API Endpoints Reference](#api-endpoints-reference)
7. [Integration Guide](#integration-guide)
8. [Step-by-Step Implementation](#step-by-step-implementation)

---

## Problem Statement

### Business Requirements

The NevoxAI platform needs to support external integrations for automated calling workflows:

1. **Intelligent Appointment Management**
   - Automated booking, confirmation calls, smart reminders, and one-click rescheduling

2. **No-Show Recovery System**
   - Real-time missed appointment detection with AI-initiated follow-up calls

3. **Advanced Analytics Dashboard**
   - Real-time performance metrics, engagement analytics, and call outcome reporting

4. **Mass Communication Campaigns**
   - Bulk calling for health awareness, clinic announcements, and targeted patient outreach

### Technical Challenges

| Challenge | Description |
|-----------|-------------|
| **External Trigger** | n8n/external systems need to trigger calls programmatically |
| **Authentication** | Secure API access without sharing user credentials |
| **Context Injection** | Pass business data (patient info, appointment details) to AI agent |
| **Unified Tracking** | Track API-triggered calls alongside UI/Campaign calls |
| **Rate Limiting** | Prevent abuse and control API usage per user |

### Current System Limitations

```
CURRENT STATE:
├── UI Call: User clicks button → Pre-call webhook → Call
├── Inbound Call: Phone rings → Dispatch webhook → Call
├── Campaign Call: Worker picks contact → Call
│
└── MISSING: External API → ??? → Call
```

**Key Question:** How does n8n trigger a call and inject context without a pre-call webhook?

---

## Solution Overview

### Core Insight

The existing `make_livekit_call()` function already accepts a `webhook_context` parameter that gets passed to the AI agent via room metadata. For API-triggered calls, we simply pass the context **from the API request** instead of from a webhook.

### Solution Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      UNIFIED CALL CONTEXT SYSTEM                             │
└─────────────────────────────────────────────────────────────────────────────┘

                         ALL CALLS USE SAME CONTEXT STRUCTURE
                                        │
            ┌───────────────────────────┼───────────────────────────┐
            │                           │                           │
            ▼                           ▼                           ▼
     ┌─────────────┐            ┌─────────────┐            ┌─────────────┐
     │   UI Call   │            │  API Call   │            │  Campaign   │
     │             │            │             │            │    Call     │
     │ Pre-call WH │            │ Context in  │            │ Context from│
     │ fetches data│            │ API request │            │ Contact DB  │
     └──────┬──────┘            └──────┬──────┘            └──────┬──────┘
            │                          │                          │
            └──────────────────────────┼──────────────────────────┘
                                       │
                                       ▼
                    ┌─────────────────────────────────────┐
                    │         CALL SERVICE                 │
                    │   (Unified call initiation)          │
                    └─────────────────────────────────────┘
                                       │
                                       ▼
                    ┌─────────────────────────────────────┐
                    │       room_metadata (JSON)           │
                    │  Contains: source, call_type,        │
                    │  agent_id, context (business data)   │
                    └─────────────────────────────────────┘
                                       │
                                       ▼
                    ┌─────────────────────────────────────┐
                    │         LIVEKIT AGENT               │
                    │   Reads context from metadata       │
                    │   Same code path for ALL sources    │
                    └─────────────────────────────────────┘
```

### Key Components

| Component | Purpose |
|-----------|---------|
| **User.api_key** | Per-user API key for authentication |
| **CallService** | Unified call initiation for all sources |
| **APIService** | API key generation, validation |
| **RateLimiterService** | Per-user rate limiting |
| **APICallLog** | Track API-triggered calls with context |
| **External API Routes** | `/api/v1/...` endpoints |
| **API Settings UI** | User interface to manage API keys |

---

## Architecture

### System Flow Diagram

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
┌───────────────────────┐
│  1. Validate API Key  │ ──► api_service.validate_api_key()
│     Get User          │     Returns User or 401 Unauthorized
└───────────────────────┘
        │
        ▼
┌───────────────────────┐
│  2. Check Rate Limit  │ ──► rate_limiter.is_allowed(user_id)
│                       │     Returns (allowed, remaining) or 429
└───────────────────────┘
        │
        ▼
┌───────────────────────┐
│  3. Validate Agent    │ ──► Agent.query.filter_by(id, user_id)
│     Ownership         │     Returns Agent or 404
└───────────────────────┘
        │
        ▼
┌───────────────────────┐
│  4. Create CallLog    │ ──► Standard call tracking
│     Create APICallLog │     API-specific tracking with context
└───────────────────────┘
        │
        ▼
┌───────────────────────┐
│  5. Build Context     │ ──► {
│                       │       "source": "api",
│                       │       "call_type": "noshow_recovery",
│                       │       "context": { patient data }
│                       │     }
└───────────────────────┘
        │
        ▼
┌───────────────────────┐
│  6. LiveKit Call      │ ──► make_livekit_call() with context
│     Room + SIP        │     Context passed via room_metadata
└───────────────────────┘
        │
        ▼
┌───────────────────────┐
│  7. Return Response   │ ──► {
│                       │       "success": true,
│                       │       "call_id": 1234,
│                       │       "room_name": "...",
│                       │       "status": "initiated"
│                       │     }
└───────────────────────┘
        │
        ▼
    AI Agent reads context from room_metadata
    and conducts the call with full patient information
```

### File Structure

```
nevoxai-project/
│
├── models.py                              # Updated - User.api_key + APICallLog
│
├── services/
│   ├── __init__.py
│   ├── api_service.py                    # NEW - API key management
│   ├── call_service.py                   # NEW - Unified call initiation
│   └── rate_limiter_service.py           # NEW - Per-user rate limiting
│
├── routes/
│   ├── external_api.py                   # NEW - /api/v1/... endpoints
│   └── api_settings.py                   # NEW - UI for API key management
│
├── templates/
│   └── settings/
│       └── api_management.html           # NEW - UI template
│
└── migrations/
    └── add_api_management.py             # NEW - Database migration
```

---

## Database Changes

### User Model Additions

Add the following fields to the `User` model in `models.py`:

```python
# API Management System Fields
api_key = db.Column(db.String(64), unique=True, nullable=True, index=True)
api_key_created_at = db.Column(db.DateTime, nullable=True)
api_rate_limit = db.Column(db.Integer, default=100)  # calls per hour
```

### New Model: APICallLog

Add this new model to track API-triggered calls:

```python
class APICallLog(db.Model):
    """
    Track calls initiated via external API
    Links to main CallLog but stores API-specific metadata
    """
    __tablename__ = 'api_call_log'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    call_log_id = db.Column(db.Integer, db.ForeignKey('call_log.id'), nullable=True)

    # API Request Info
    call_type = db.Column(db.String(50))  # noshow_recovery, reminder, confirmation, etc.
    request_context = db.Column(db.Text)  # JSON - original context sent by API client

    # Response tracking
    status = db.Column(db.String(20), default='initiated')  # initiated, completed, failed
    error_message = db.Column(db.Text, nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))
    completed_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    user = db.relationship('User', backref='api_call_logs')
    call_log = db.relationship('CallLog', backref='api_call_record')

    def __repr__(self):
        return f'<APICallLog {self.id} type={self.call_type}>'
```

### Migration Script

Create file: `migrations/add_api_management.py`

```python
"""
Migration: Add API Management System
- Adds api_key fields to User model
- Creates APICallLog table

Run: python migrations/add_api_management.py
"""
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models import db


def upgrade():
    """Add API management fields and tables"""
    with app.app_context():
        # Add columns to User table
        try:
            db.session.execute(db.text('''
                ALTER TABLE user ADD COLUMN api_key VARCHAR(64) UNIQUE;
            '''))
            print("✅ Added api_key column to user table")
        except Exception as e:
            print(f"⚠️ api_key column may already exist: {e}")

        try:
            db.session.execute(db.text('''
                ALTER TABLE user ADD COLUMN api_key_created_at DATETIME;
            '''))
            print("✅ Added api_key_created_at column to user table")
        except Exception as e:
            print(f"⚠️ api_key_created_at column may already exist: {e}")

        try:
            db.session.execute(db.text('''
                ALTER TABLE user ADD COLUMN api_rate_limit INTEGER DEFAULT 100;
            '''))
            print("✅ Added api_rate_limit column to user table")
        except Exception as e:
            print(f"⚠️ api_rate_limit column may already exist: {e}")

        # Create APICallLog table
        try:
            db.session.execute(db.text('''
                CREATE TABLE IF NOT EXISTS api_call_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    call_log_id INTEGER,
                    call_type VARCHAR(50),
                    request_context TEXT,
                    status VARCHAR(20) DEFAULT 'initiated',
                    error_message TEXT,
                    created_at DATETIME,
                    completed_at DATETIME,
                    FOREIGN KEY (user_id) REFERENCES user(id),
                    FOREIGN KEY (call_log_id) REFERENCES call_log(id)
                );
            '''))
            print("✅ Created api_call_log table")
        except Exception as e:
            print(f"⚠️ api_call_log table may already exist: {e}")

        # Create index on api_key for fast lookups
        try:
            db.session.execute(db.text('''
                CREATE INDEX IF NOT EXISTS idx_user_api_key ON user(api_key);
            '''))
            print("✅ Created index on user.api_key")
        except Exception as e:
            print(f"⚠️ Index may already exist: {e}")

        db.session.commit()
        print("\n✅ Migration completed successfully!")


def downgrade():
    """Remove API management fields and tables"""
    with app.app_context():
        # SQLite doesn't support DROP COLUMN easily, so we skip for now
        try:
            db.session.execute(db.text('DROP TABLE IF EXISTS api_call_log;'))
            print("✅ Dropped api_call_log table")
        except Exception as e:
            print(f"⚠️ Error dropping table: {e}")

        db.session.commit()
        print("\n✅ Downgrade completed!")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='API Management Migration')
    parser.add_argument('--downgrade', action='store_true', help='Rollback migration')
    args = parser.parse_args()

    if args.downgrade:
        downgrade()
    else:
        upgrade()
```

---

## Implementation Files

### 1. services/api_service.py

```python
"""
API Service - API Key Management
Handles generation, validation, and management of user API keys
"""
import secrets
import logging
from datetime import datetime
from typing import Optional

from models import db, User, SAUDI_TZ

logger = logging.getLogger(__name__)


class APIService:
    """
    API Key Management Service

    Handles:
    - Generating secure API keys
    - Validating API keys
    - Revoking/regenerating keys
    - Key masking for display
    """

    KEY_PREFIX = "nvx_sk_"  # NevoXAI Secret Key
    KEY_LENGTH = 32  # 32 hex characters = 128 bits of entropy

    def generate_api_key(self, user_id: int) -> str:
        """
        Generate a new API key for a user

        Args:
            user_id: The user ID to generate key for

        Returns:
            The generated API key (shown only once)

        Raises:
            ValueError: If user not found
        """
        user = db.session.get(User, user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")

        # Generate cryptographically secure random key
        random_part = secrets.token_hex(self.KEY_LENGTH // 2)
        api_key = f"{self.KEY_PREFIX}{random_part}"

        # Store in database
        user.api_key = api_key
        user.api_key_created_at = datetime.now(SAUDI_TZ).replace(tzinfo=None)
        db.session.commit()

        logger.info(f"Generated API key for user {user_id}")
        return api_key

    def validate_api_key(self, api_key: str) -> Optional[User]:
        """
        Validate an API key and return the associated user

        Args:
            api_key: The API key to validate

        Returns:
            User object if valid, None otherwise
        """
        if not api_key:
            return None

        # Check prefix
        if not api_key.startswith(self.KEY_PREFIX):
            logger.warning(f"Invalid API key prefix: {api_key[:10]}...")
            return None

        # Look up user
        user = User.query.filter_by(api_key=api_key).first()

        if user:
            logger.debug(f"API key validated for user {user.id}")
        else:
            logger.warning(f"API key not found: {api_key[:15]}...")

        return user

    def revoke_api_key(self, user_id: int) -> bool:
        """
        Revoke a user's API key

        Args:
            user_id: The user ID whose key to revoke

        Returns:
            True if revoked, False if user not found
        """
        user = db.session.get(User, user_id)
        if not user:
            return False

        user.api_key = None
        user.api_key_created_at = None
        db.session.commit()

        logger.info(f"Revoked API key for user {user_id}")
        return True

    def regenerate_api_key(self, user_id: int) -> str:
        """
        Regenerate API key (revoke old + generate new)

        Args:
            user_id: The user ID

        Returns:
            The new API key
        """
        self.revoke_api_key(user_id)
        return self.generate_api_key(user_id)

    def get_masked_key(self, user_id: int) -> Optional[str]:
        """
        Get masked API key for display
        Shows first 10 chars and last 4 chars

        Args:
            user_id: The user ID

        Returns:
            Masked key like "nvx_sk_abc...xyz" or None
        """
        user = db.session.get(User, user_id)
        if not user or not user.api_key:
            return None

        key = user.api_key
        # Show: nvx_sk_abc...wxyz (prefix + 3 chars ... last 4 chars)
        return f"{key[:13]}...{key[-4:]}"

    def has_api_key(self, user_id: int) -> bool:
        """Check if user has an API key"""
        user = db.session.get(User, user_id)
        return bool(user and user.api_key)


# Global singleton instance
api_service = APIService()
```

### 2. services/call_service.py

```python
"""
Call Service - Unified Call Initiation
Handles call initiation for ALL sources: UI, API, Campaign

This is the CORE service that ensures consistent call handling
and context injection regardless of how the call was triggered.
"""
import os
import json
import asyncio
import logging
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, Dict, Any

from livekit import api

from models import db, User, Agent, CallLog, Workflow, APICallLog, SAUDI_TZ

logger = logging.getLogger(__name__)


@dataclass
class CallResult:
    """Result of a call initiation attempt"""
    success: bool
    call_id: Optional[int] = None
    room_name: Optional[str] = None
    status: str = 'unknown'
    error: Optional[str] = None


class CallService:
    """
    Unified Call Initiation Service

    Provides a single entry point for initiating calls from:
    - UI (web interface)
    - API (external integrations like n8n)
    - Campaigns (bulk calling)

    All calls flow through the same path, ensuring:
    - Consistent CallLog creation
    - Unified context injection to AI agent
    - Proper tracking and analytics
    """

    # Supported call types for categorization
    CALL_TYPES = [
        'outbound',                # Generic outbound call
        'noshow_recovery',         # Follow up on missed appointment
        'appointment_reminder',    # Reminder before appointment
        'appointment_confirmation', # Confirm upcoming appointment
        'campaign',                # Bulk campaign call
        'custom'                   # Custom/other
    ]

    def initiate_call(
        self,
        user: User,
        agent: Agent,
        phone_number: str,
        context: Dict[str, Any] = None,
        source: str = 'ui',
        call_type: str = 'outbound'
    ) -> CallResult:
        """
        Initiate an outbound call with unified context handling

        This method is the single entry point for all call initiation.
        It handles context injection differently based on source:

        - source='ui': May fetch additional context from pre-call webhook
        - source='api': Uses context as-is (provided by API caller)
        - source='campaign': Uses context from campaign contact data

        Args:
            user: User initiating the call (for billing/tracking)
            agent: Agent to use for the call
            phone_number: Phone number to call (E.164 format recommended)
            context: Business context (patient info, appointment details, etc.)
            source: Call source - 'ui', 'api', or 'campaign'
            call_type: Type of call for categorization/analytics

        Returns:
            CallResult with call_id, room_name, status, or error
        """
        # Validate user has minutes
        if user.minutes_balance <= 0:
            logger.warning(f"User {user.id} has insufficient minutes")
            return CallResult(success=False, error='Insufficient minutes balance')

        # Get outbound trunk
        outbound_trunk_id = self._get_trunk_id(user)
        if not outbound_trunk_id:
            logger.error(f"No outbound trunk configured for user {user.id}")
            return CallResult(success=False, error='No outbound trunk configured')

        # Validate call type
        if call_type not in self.CALL_TYPES:
            call_type = 'custom'

        # Build unified call context
        call_context = self._build_call_context(
            agent=agent,
            phone_number=phone_number,
            context=context,
            source=source,
            call_type=call_type
        )

        # For UI calls, optionally fetch pre-call data
        if source == 'ui' and agent.workflow_id:
            webhook_data = self._fetch_pre_call_data_if_enabled(agent, phone_number)
            if webhook_data:
                call_context["context"].update(webhook_data)
                logger.info(f"Merged pre-call webhook data for agent {agent.id}")

        # Generate unique room name
        room_name = f"{call_type}-{agent.id}-{int(datetime.now().timestamp())}"

        try:
            # Create CallLog record
            call_log = CallLog(
                user_id=user.id,
                agent_id=agent.id,
                from_number=os.environ.get('SAUDI_PHONE_NUMBER', ''),
                to_number=phone_number,
                room_name=room_name,
                status='initiated',
                call_type='outbound'
            )
            db.session.add(call_log)
            db.session.flush()  # Get ID without full commit

            # Add call_id to context (agent can reference this)
            call_context["call_id"] = call_log.id

            # For API calls, create APICallLog for tracking
            if source == 'api':
                api_call_log = APICallLog(
                    user_id=user.id,
                    call_log_id=call_log.id,
                    call_type=call_type,
                    request_context=json.dumps(context or {}, ensure_ascii=False),
                    status='initiated'
                )
                db.session.add(api_call_log)

            # Initiate LiveKit call with full context
            asyncio.run(self._make_livekit_call(
                phone_number=phone_number,
                room_name=room_name,
                agent_name=agent.name,
                outbound_trunk_id=outbound_trunk_id,
                agent_id=agent.id,
                call_context=call_context
            ))

            # Commit all database changes
            db.session.commit()

            logger.info(
                f"Call initiated successfully | "
                f"room={room_name} | source={source} | type={call_type} | "
                f"agent={agent.id} | user={user.id}"
            )

            return CallResult(
                success=True,
                call_id=call_log.id,
                room_name=room_name,
                status='initiated'
            )

        except Exception as e:
            db.session.rollback()
            logger.error(f"Call initiation failed: {e}", exc_info=True)
            return CallResult(success=False, error=str(e))

    def _build_call_context(
        self,
        agent: Agent,
        phone_number: str,
        context: Dict[str, Any],
        source: str,
        call_type: str
    ) -> Dict[str, Any]:
        """
        Build unified call context structure

        This context is passed to the AI agent via room metadata.
        The agent reads this to understand the call purpose and access
        business data (patient info, appointment details, etc.)
        """
        return {
            "source": source,           # 'ui', 'api', 'campaign'
            "call_type": call_type,     # 'noshow_recovery', etc.
            "agent_id": agent.id,
            "agent_name": agent.name,
            "phone_number": phone_number,
            "initiated_at": datetime.now(SAUDI_TZ).isoformat(),
            "context": context or {}    # Business data from API/webhook
        }

    def _get_trunk_id(self, user: User) -> Optional[str]:
        """Get outbound trunk ID for user"""
        return user.outbound_trunk_id or os.environ.get('SIP_OUTBOUND_TRUNK_ID')

    def _fetch_pre_call_data_if_enabled(
        self,
        agent: Agent,
        phone_number: str
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch pre-call data from webhook if enabled for agent's workflow

        This is used for UI calls to enrich context with CRM data.
        API calls skip this (they provide their own context).
        """
        if not agent.workflow_id:
            return None

        workflow = db.session.get(Workflow, agent.workflow_id)
        if not workflow or not workflow.pre_call_enabled or not workflow.is_active:
            return None

        webhook_url = workflow.pre_call_webhook_url or workflow.webhook_url
        if not webhook_url:
            return None

        # Import here to avoid circular imports
        from services.webhook_service_async import fetch_pre_call_data_sync

        try:
            return fetch_pre_call_data_sync(
                workflow_url=webhook_url,
                api_key=workflow.api_key,
                call_context={
                    'event_type': 'pre_call',
                    'agent_name': agent.name,
                    'agent_id': agent.id,
                    'phone_number': phone_number,
                    'call_type': 'outbound_ui'
                },
                timeout=workflow.pre_call_timeout or 3
            )
        except Exception as e:
            logger.warning(f"Pre-call webhook failed for agent {agent.id}: {e}")
            return None

    async def _make_livekit_call(
        self,
        phone_number: str,
        room_name: str,
        agent_name: str,
        outbound_trunk_id: str,
        agent_id: int,
        call_context: Dict[str, Any]
    ):
        """
        Create LiveKit room and SIP participant

        The call_context is passed via room_metadata, which the
        AI agent reads when the call connects.
        """
        lkapi = api.LiveKitAPI()

        # Prepare room metadata with full context
        room_metadata = json.dumps({
            "type": call_context.get("call_type", "outbound"),
            "agent_id": agent_id,
            "phone_number": phone_number,
            "webhook_context": call_context.get("context"),  # Business data
            "source": call_context.get("source"),
            "call_id": call_context.get("call_id")
        }, ensure_ascii=False)

        # Create agent dispatch
        await lkapi.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name="agent",
                room=room_name,
                metadata=room_metadata
            )
        )

        # Wait for agent to be ready
        await asyncio.sleep(2)

        # Create SIP participant to dial out
        await lkapi.sip.create_sip_participant(
            api.CreateSIPParticipantRequest(
                room_name=room_name,
                sip_trunk_id=outbound_trunk_id,
                sip_call_to=phone_number,
                participant_identity="phone_user",
                participant_metadata=room_metadata
            )
        )

        await lkapi.aclose()
        logger.debug(f"LiveKit call created: {room_name}")

    # ==================== STATUS METHODS ====================

    def get_call_status(self, call_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Get call status and basic details

        Args:
            call_id: The call log ID
            user_id: User ID (for authorization check)

        Returns:
            Dict with call status or None if not found
        """
        call_log = CallLog.query.filter_by(id=call_id, user_id=user_id).first()
        if not call_log:
            return None

        return {
            "call_id": call_log.id,
            "status": call_log.status,
            "duration_seconds": call_log.duration_seconds,
            "to_number": call_log.to_number,
            "agent_id": call_log.agent_id,
            "room_name": call_log.room_name,
            "created_at": call_log.created_at.isoformat() if call_log.created_at else None
        }

    def get_call_transcript(self, call_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Get call transcript and analysis

        Args:
            call_id: The call log ID
            user_id: User ID (for authorization check)

        Returns:
            Dict with transcript data or None if not found
        """
        call_log = CallLog.query.filter_by(id=call_id, user_id=user_id).first()
        if not call_log:
            return None

        # Parse JSON fields safely
        transcription_data = None
        sentiment_summary = None

        try:
            if call_log.transcription_data:
                transcription_data = json.loads(call_log.transcription_data)
        except json.JSONDecodeError:
            pass

        try:
            if call_log.sentiment_summary:
                sentiment_summary = json.loads(call_log.sentiment_summary)
        except json.JSONDecodeError:
            pass

        return {
            "call_id": call_log.id,
            "transcription": call_log.transcription,
            "transcription_data": transcription_data,
            "sentiment_summary": sentiment_summary,
            "duration_seconds": call_log.duration_seconds,
            "recording_url": call_log.recording_url
        }


# Global singleton instance
call_service = CallService()
```

### 3. services/rate_limiter_service.py

```python
"""
Rate Limiter Service - Per-User API Rate Limiting
In-memory sliding window rate limiter
"""
import time
import logging
from collections import defaultdict
from threading import Lock
from typing import Tuple, Dict, Any

logger = logging.getLogger(__name__)


class RateLimiterService:
    """
    In-memory rate limiter for API calls

    Uses a sliding window algorithm to track calls per user.
    Thread-safe for concurrent access.

    Note: In a multi-process/multi-server setup, consider using
    Redis for distributed rate limiting.
    """

    def __init__(self):
        self._calls: Dict[int, list] = defaultdict(list)  # user_id -> [timestamps]
        self._lock = Lock()

    def is_allowed(
        self,
        user_id: int,
        limit: int = 100,
        window_seconds: int = 3600
    ) -> Tuple[bool, int]:
        """
        Check if user is within rate limit

        Args:
            user_id: User ID to check
            limit: Maximum calls allowed per window (default: 100)
            window_seconds: Window size in seconds (default: 3600 = 1 hour)

        Returns:
            Tuple of (is_allowed, remaining_calls)
        """
        now = time.time()
        window_start = now - window_seconds

        with self._lock:
            # Remove expired entries
            self._calls[user_id] = [
                ts for ts in self._calls[user_id]
                if ts > window_start
            ]

            current_count = len(self._calls[user_id])
            remaining = max(0, limit - current_count)
            allowed = current_count < limit

            if not allowed:
                logger.warning(
                    f"Rate limit exceeded for user {user_id}: "
                    f"{current_count}/{limit} calls in window"
                )

            return allowed, remaining

    def record_call(self, user_id: int):
        """
        Record a call for rate limiting

        Args:
            user_id: User ID making the call
        """
        with self._lock:
            self._calls[user_id].append(time.time())

    def get_usage(self, user_id: int, window_seconds: int = 3600) -> Dict[str, Any]:
        """
        Get usage statistics for a user

        Args:
            user_id: User ID
            window_seconds: Window to check (default: 1 hour)

        Returns:
            Dict with usage stats
        """
        now = time.time()
        window_start = now - window_seconds

        with self._lock:
            recent_calls = [
                ts for ts in self._calls[user_id]
                if ts > window_start
            ]

            return {
                "user_id": user_id,
                "calls_in_window": len(recent_calls),
                "window_seconds": window_seconds,
                "oldest_call": min(recent_calls) if recent_calls else None,
                "newest_call": max(recent_calls) if recent_calls else None
            }

    def reset_user(self, user_id: int):
        """
        Reset rate limit for a user (admin function)

        Args:
            user_id: User ID to reset
        """
        with self._lock:
            self._calls[user_id] = []
            logger.info(f"Rate limit reset for user {user_id}")


# Global singleton instance
rate_limiter = RateLimiterService()
```

### 4. routes/external_api.py

```python
"""
External API Routes
/api/v1/... endpoints for n8n and external integrations

This blueprint provides RESTful API endpoints for external systems
to interact with NevoxAI programmatically.
"""
import logging
from functools import wraps
from flask import Blueprint, request, jsonify

from models import db, Agent, Campaign
from services.api_service import api_service
from services.call_service import call_service, CallService
from services.rate_limiter_service import rate_limiter

logger = logging.getLogger(__name__)

# Create blueprint with /api/v1 prefix
external_api_bp = Blueprint('external_api', __name__, url_prefix='/api/v1')


# ==================== AUTHENTICATION DECORATOR ====================

def require_api_key(f):
    """
    Decorator to require API key authentication

    Validates X-API-Key header and checks rate limits.
    On success, adds 'api_user' and 'rate_limit_remaining' to request.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # Get API key from header
        api_key = request.headers.get('X-API-Key')

        if not api_key:
            return jsonify({
                'success': False,
                'error': 'API key required. Provide X-API-Key header.',
                'code': 'MISSING_API_KEY'
            }), 401

        # Validate API key
        user = api_service.validate_api_key(api_key)
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
        allowed, remaining = rate_limiter.is_allowed(
            user.id,
            limit=user.api_rate_limit or 100
        )

        if not allowed:
            return jsonify({
                'success': False,
                'error': 'Rate limit exceeded. Try again later.',
                'code': 'RATE_LIMIT_EXCEEDED',
                'retry_after_seconds': 3600
            }), 429

        # Add user to request context
        request.api_user = user
        request.rate_limit_remaining = remaining

        return f(*args, **kwargs)
    return decorated


# ==================== CALL ENDPOINTS ====================

@external_api_bp.route('/call/initiate', methods=['POST'])
@require_api_key
def initiate_call():
    """
    Initiate an outbound call

    This is the primary endpoint for triggering calls from external systems
    like n8n workflows.

    Request:
        POST /api/v1/call/initiate
        Headers:
            X-API-Key: nvx_sk_...
            Content-Type: application/json
        Body:
            {
                "agent_id": 5,
                "phone": "+966512345678",
                "call_type": "noshow_recovery",  // optional
                "context": {                      // optional - passed to AI
                    "patient_name": "Ahmed",
                    "missed_appointment": {
                        "date": "2026-01-29",
                        "time": "10:00",
                        "doctor": "Dr. Fatima"
                    }
                }
            }

    Response (success):
        {
            "success": true,
            "call_id": 1234,
            "room_name": "noshow_recovery-5-1706621234",
            "status": "initiated",
            "rate_limit_remaining": 95
        }

    Response (error):
        {
            "success": false,
            "error": "Error message",
            "code": "ERROR_CODE"
        }
    """
    user = request.api_user
    data = request.get_json()

    # Validate request body
    if not data:
        return jsonify({
            'success': False,
            'error': 'Request body required',
            'code': 'MISSING_BODY'
        }), 400

    # Extract and validate required fields
    agent_id = data.get('agent_id')
    phone = data.get('phone')
    call_type = data.get('call_type', 'custom')
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

    # Validate call_type
    if call_type not in CallService.CALL_TYPES:
        return jsonify({
            'success': False,
            'error': f'Invalid call_type. Must be one of: {CallService.CALL_TYPES}',
            'code': 'INVALID_CALL_TYPE'
        }), 400

    # Verify agent exists and belongs to user
    agent = Agent.query.filter_by(id=agent_id, user_id=user.id).first()
    if not agent:
        return jsonify({
            'success': False,
            'error': 'Agent not found or access denied',
            'code': 'AGENT_NOT_FOUND'
        }), 404

    # Initiate the call
    result = call_service.initiate_call(
        user=user,
        agent=agent,
        phone_number=phone,
        context=context,
        source='api',
        call_type=call_type
    )

    # Record call for rate limiting (even if failed, counts toward limit)
    rate_limiter.record_call(user.id)

    if result.success:
        logger.info(f"API call initiated: user={user.id} agent={agent_id} call_id={result.call_id}")
        return jsonify({
            'success': True,
            'call_id': result.call_id,
            'room_name': result.room_name,
            'status': result.status,
            'rate_limit_remaining': request.rate_limit_remaining - 1
        }), 200
    else:
        logger.warning(f"API call failed: user={user.id} error={result.error}")
        return jsonify({
            'success': False,
            'error': result.error,
            'code': 'CALL_FAILED'
        }), 400


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
            "created_at": "2026-01-29T10:30:00"
        }
    """
    user = request.api_user

    status = call_service.get_call_status(call_id, user.id)
    if not status:
        return jsonify({
            'success': False,
            'error': 'Call not found',
            'code': 'CALL_NOT_FOUND'
        }), 404

    return jsonify({
        'success': True,
        **status
    }), 200


@external_api_bp.route('/call/<int:call_id>/transcript', methods=['GET'])
@require_api_key
def get_call_transcript(call_id):
    """
    Get call transcript and analysis

    Request:
        GET /api/v1/call/1234/transcript
        Headers:
            X-API-Key: nvx_sk_...

    Response:
        {
            "success": true,
            "call_id": 1234,
            "transcription": "Full conversation text...",
            "transcription_data": {...},
            "sentiment_summary": {...},
            "duration_seconds": 145,
            "recording_url": "https://..."
        }
    """
    user = request.api_user

    transcript = call_service.get_call_transcript(call_id, user.id)
    if not transcript:
        return jsonify({
            'success': False,
            'error': 'Call not found',
            'code': 'CALL_NOT_FOUND'
        }), 404

    return jsonify({
        'success': True,
        **transcript
    }), 200


# ==================== CAMPAIGN ENDPOINTS ====================

@external_api_bp.route('/campaign/<int:campaign_id>/start', methods=['POST'])
@require_api_key
def start_campaign_api(campaign_id):
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
            "status": "running",
            "contacts_count": 150
        }
    """
    from datetime import datetime
    from models import SAUDI_TZ
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
            'code': 'CAMPAIGN_ALREADY_RUNNING'
        }), 400

    if len(campaign.contacts) == 0:
        return jsonify({
            'success': False,
            'error': 'Campaign has no contacts',
            'code': 'CAMPAIGN_NO_CONTACTS'
        }), 400

    # Start the campaign
    campaign.status = 'running'
    campaign.start_time = datetime.now(SAUDI_TZ).replace(tzinfo=None)
    db.session.commit()

    # Invalidate cache
    redis_service.invalidate_campaign_metadata(campaign_id)

    logger.info(f"Campaign {campaign_id} started via API by user {user.id}")

    return jsonify({
        'success': True,
        'campaign_id': campaign.id,
        'name': campaign.name,
        'status': 'running',
        'contacts_count': len(campaign.contacts)
    }), 200


@external_api_bp.route('/campaign/<int:campaign_id>/pause', methods=['POST'])
@require_api_key
def pause_campaign_api(campaign_id):
    """Pause a running campaign"""
    from services.redis_service import redis_service

    user = request.api_user
    campaign = Campaign.query.filter_by(id=campaign_id, user_id=user.id).first()

    if not campaign:
        return jsonify({
            'success': False,
            'error': 'Campaign not found'
        }), 404

    if campaign.status != 'running':
        return jsonify({
            'success': False,
            'error': 'Campaign is not running'
        }), 400

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
def get_campaign_status_api(campaign_id):
    """
    Get campaign status and progress

    Request:
        GET /api/v1/campaign/123/status
        Headers:
            X-API-Key: nvx_sk_...

    Response:
        {
            "success": true,
            "campaign_id": 123,
            "name": "Q1 Outreach",
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
        return jsonify({
            'success': False,
            'error': 'Campaign not found',
            'code': 'CAMPAIGN_NOT_FOUND'
        }), 404

    # Calculate progress
    total = len(campaign.contacts)
    completed = len([c for c in campaign.contacts if c.status == 'completed'])
    pending = len([c for c in campaign.contacts if c.status == 'pending'])
    failed = len([c for c in campaign.contacts if c.status == 'failed'])
    no_answer = len([c for c in campaign.contacts if c.status == 'no_answer'])

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


# ==================== UTILITY ENDPOINTS ====================

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
    agents = Agent.query.filter_by(user_id=user.id).order_by(Agent.created_at.desc()).all()

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
            "remaining": 85
        }
    """
    user = request.api_user
    usage = rate_limiter.get_usage(user.id)

    return jsonify({
        'success': True,
        'rate_limit': user.api_rate_limit or 100,
        'calls_this_hour': usage['calls_in_window'],
        'remaining': (user.api_rate_limit or 100) - usage['calls_in_window'],
        'window_seconds': usage['window_seconds']
    }), 200


@external_api_bp.route('/health', methods=['GET'])
def health():
    """
    Health check endpoint (no authentication required)

    Response:
        {
            "status": "healthy",
            "service": "NevoxAI External API",
            "version": "1.0"
        }
    """
    from datetime import datetime
    from models import SAUDI_TZ

    return jsonify({
        'status': 'healthy',
        'service': 'NevoxAI External API',
        'version': '1.0',
        'timestamp': datetime.now(SAUDI_TZ).isoformat()
    }), 200
```

### 5. routes/api_settings.py

```python
"""
API Settings Routes
UI for managing API keys and viewing usage
"""
import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify

from models import db, User, APICallLog
from services.api_service import api_service
from services.rate_limiter_service import rate_limiter
from utils.decorators import login_required, approved_required

logger = logging.getLogger(__name__)

# Create blueprint
api_settings_bp = Blueprint('api_settings', __name__, url_prefix='/settings/api')


@api_settings_bp.route('/')
@login_required
@approved_required
def api_settings():
    """
    API Management Settings Page

    Shows:
    - Current API key (masked)
    - Key generation/regeneration buttons
    - Usage statistics
    - Recent API calls
    """
    user = db.session.get(User, session['user_id'])

    # Get masked API key for display
    masked_key = api_service.get_masked_key(user.id)

    # Check if we have a newly generated key to show (one-time display)
    new_api_key = session.pop('new_api_key', None)

    # Get usage stats
    usage = rate_limiter.get_usage(user.id)

    # Get recent API calls
    recent_calls = APICallLog.query.filter_by(user_id=user.id)\
        .order_by(APICallLog.created_at.desc())\
        .limit(20)\
        .all()

    return render_template('settings/api_management.html',
        user=user,
        masked_key=masked_key,
        new_api_key=new_api_key,  # Shown only once after generation
        has_api_key=bool(user.api_key),
        api_key_created_at=user.api_key_created_at,
        rate_limit=user.api_rate_limit or 100,
        usage=usage,
        recent_calls=recent_calls
    )


@api_settings_bp.route('/generate', methods=['POST'])
@login_required
@approved_required
def generate_api_key():
    """Generate a new API key"""
    user_id = session['user_id']
    user = db.session.get(User, user_id)

    # Check if user already has a key
    if user.api_key:
        flash('You already have an API key. Use "Regenerate" to create a new one.', 'warning')
        return redirect(url_for('api_settings.api_settings'))

    try:
        new_key = api_service.generate_api_key(user_id)

        # Store in session to show once
        session['new_api_key'] = new_key

        flash('API key generated successfully! Copy it now - it will only be shown once.', 'success')
        logger.info(f"API key generated for user {user_id}")

    except Exception as e:
        logger.error(f"Error generating API key for user {user_id}: {e}")
        flash('Error generating API key. Please try again.', 'error')

    return redirect(url_for('api_settings.api_settings'))


@api_settings_bp.route('/regenerate', methods=['POST'])
@login_required
@approved_required
def regenerate_api_key():
    """Regenerate API key (revokes old key)"""
    user_id = session['user_id']

    try:
        new_key = api_service.regenerate_api_key(user_id)

        # Store in session to show once
        session['new_api_key'] = new_key

        flash('API key regenerated! Your old key has been revoked. Copy the new key now.', 'success')
        logger.info(f"API key regenerated for user {user_id}")

    except Exception as e:
        logger.error(f"Error regenerating API key for user {user_id}: {e}")
        flash('Error regenerating API key. Please try again.', 'error')

    return redirect(url_for('api_settings.api_settings'))


@api_settings_bp.route('/revoke', methods=['POST'])
@login_required
@approved_required
def revoke_api_key():
    """Revoke API key"""
    user_id = session['user_id']

    if api_service.revoke_api_key(user_id):
        flash('API key revoked successfully. Any integrations using this key will stop working.', 'success')
        logger.info(f"API key revoked for user {user_id}")
    else:
        flash('Error revoking API key.', 'error')

    return redirect(url_for('api_settings.api_settings'))


@api_settings_bp.route('/usage/json')
@login_required
@approved_required
def get_usage_json():
    """Get usage stats as JSON (for AJAX refresh)"""
    user_id = session['user_id']
    user = db.session.get(User, user_id)
    usage = rate_limiter.get_usage(user_id)

    return jsonify({
        'rate_limit': user.api_rate_limit or 100,
        'calls_this_hour': usage['calls_in_window'],
        'remaining': (user.api_rate_limit or 100) - usage['calls_in_window']
    })
```

### 6. templates/settings/api_management.html

```html
{% extends "base.html" %}

{% block title %}API Management - NevoxAI{% endblock %}

{% block content %}
<div class="container-fluid py-4">
    <div class="row">
        <div class="col-12">
            <h2 class="mb-4">
                <i class="fas fa-key me-2"></i>API Management
            </h2>
        </div>
    </div>

    <!-- API Key Section -->
    <div class="row mb-4">
        <div class="col-lg-8">
            <div class="card">
                <div class="card-header">
                    <h5 class="mb-0">
                        <i class="fas fa-shield-alt me-2"></i>API Key
                    </h5>
                </div>
                <div class="card-body">
                    {% if new_api_key %}
                    <!-- Show newly generated key (one time only) -->
                    <div class="alert alert-success">
                        <h6 class="alert-heading">
                            <i class="fas fa-check-circle me-2"></i>Your New API Key
                        </h6>
                        <p class="mb-2">Copy this key now. It will only be shown once!</p>
                        <div class="input-group mb-3">
                            <input type="text" class="form-control font-monospace"
                                   id="newApiKey" value="{{ new_api_key }}" readonly>
                            <button class="btn btn-outline-primary" type="button"
                                    onclick="copyApiKey()">
                                <i class="fas fa-copy"></i> Copy
                            </button>
                        </div>
                        <small class="text-muted">
                            Store this key securely. You won't be able to see it again.
                        </small>
                    </div>
                    {% endif %}

                    {% if has_api_key %}
                    <div class="mb-4">
                        <label class="form-label text-muted">Current API Key</label>
                        <div class="input-group">
                            <input type="text" class="form-control font-monospace"
                                   value="{{ masked_key }}" readonly>
                            <span class="input-group-text">
                                <i class="fas fa-lock"></i>
                            </span>
                        </div>
                        <small class="text-muted">
                            Created: {{ api_key_created_at.strftime('%Y-%m-%d %H:%M') if api_key_created_at else 'Unknown' }}
                        </small>
                    </div>

                    <div class="d-flex gap-2">
                        <form action="{{ url_for('api_settings.regenerate_api_key') }}" method="POST"
                              onsubmit="return confirm('This will revoke your current key. Any integrations using it will stop working. Continue?')">
                            <button type="submit" class="btn btn-warning">
                                <i class="fas fa-sync-alt me-1"></i>Regenerate Key
                            </button>
                        </form>
                        <form action="{{ url_for('api_settings.revoke_api_key') }}" method="POST"
                              onsubmit="return confirm('This will permanently revoke your API key. Continue?')">
                            <button type="submit" class="btn btn-danger">
                                <i class="fas fa-trash me-1"></i>Revoke Key
                            </button>
                        </form>
                    </div>
                    {% else %}
                    <div class="text-center py-4">
                        <i class="fas fa-key fa-3x text-muted mb-3"></i>
                        <p class="text-muted mb-3">No API key generated yet</p>
                        <form action="{{ url_for('api_settings.generate_api_key') }}" method="POST">
                            <button type="submit" class="btn btn-primary btn-lg">
                                <i class="fas fa-plus me-2"></i>Generate API Key
                            </button>
                        </form>
                    </div>
                    {% endif %}
                </div>
            </div>
        </div>

        <!-- Usage Stats -->
        <div class="col-lg-4">
            <div class="card">
                <div class="card-header">
                    <h5 class="mb-0">
                        <i class="fas fa-chart-bar me-2"></i>Usage (This Hour)
                    </h5>
                </div>
                <div class="card-body">
                    <div class="d-flex justify-content-between mb-2">
                        <span>API Calls</span>
                        <strong>{{ usage.calls_in_window }} / {{ rate_limit }}</strong>
                    </div>
                    <div class="progress mb-3" style="height: 10px;">
                        {% set usage_percent = (usage.calls_in_window / rate_limit * 100) | int %}
                        <div class="progress-bar {% if usage_percent > 80 %}bg-danger{% elif usage_percent > 50 %}bg-warning{% else %}bg-success{% endif %}"
                             style="width: {{ usage_percent }}%"></div>
                    </div>
                    <small class="text-muted">
                        {{ rate_limit - usage.calls_in_window }} calls remaining
                    </small>
                </div>
            </div>
        </div>
    </div>

    <!-- API Documentation -->
    <div class="row mb-4">
        <div class="col-12">
            <div class="card">
                <div class="card-header">
                    <h5 class="mb-0">
                        <i class="fas fa-book me-2"></i>Quick Start Guide
                    </h5>
                </div>
                <div class="card-body">
                    <h6>Base URL</h6>
                    <pre class="bg-dark text-light p-3 rounded"><code>{{ request.host_url }}api/v1</code></pre>

                    <h6>Authentication</h6>
                    <p>Include your API key in the <code>X-API-Key</code> header:</p>
                    <pre class="bg-dark text-light p-3 rounded"><code>X-API-Key: nvx_sk_your_api_key_here</code></pre>

                    <h6>Example: Initiate a Call</h6>
                    <pre class="bg-dark text-light p-3 rounded"><code>POST /api/v1/call/initiate
Content-Type: application/json
X-API-Key: nvx_sk_your_api_key_here

{
  "agent_id": 5,
  "phone": "+966512345678",
  "call_type": "noshow_recovery",
  "context": {
    "patient_name": "Ahmed",
    "missed_appointment": {
      "date": "2026-01-29",
      "time": "10:00"
    }
  }
}</code></pre>

                    <h6>Available Endpoints</h6>
                    <table class="table table-sm">
                        <thead>
                            <tr>
                                <th>Method</th>
                                <th>Endpoint</th>
                                <th>Description</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr>
                                <td><span class="badge bg-success">POST</span></td>
                                <td><code>/call/initiate</code></td>
                                <td>Trigger an outbound call</td>
                            </tr>
                            <tr>
                                <td><span class="badge bg-primary">GET</span></td>
                                <td><code>/call/{id}/status</code></td>
                                <td>Get call status</td>
                            </tr>
                            <tr>
                                <td><span class="badge bg-primary">GET</span></td>
                                <td><code>/call/{id}/transcript</code></td>
                                <td>Get call transcript</td>
                            </tr>
                            <tr>
                                <td><span class="badge bg-success">POST</span></td>
                                <td><code>/campaign/{id}/start</code></td>
                                <td>Start a campaign</td>
                            </tr>
                            <tr>
                                <td><span class="badge bg-primary">GET</span></td>
                                <td><code>/campaign/{id}/status</code></td>
                                <td>Get campaign progress</td>
                            </tr>
                            <tr>
                                <td><span class="badge bg-primary">GET</span></td>
                                <td><code>/agents</code></td>
                                <td>List your agents</td>
                            </tr>
                            <tr>
                                <td><span class="badge bg-primary">GET</span></td>
                                <td><code>/usage</code></td>
                                <td>Get API usage stats</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <!-- Recent API Calls -->
    <div class="row">
        <div class="col-12">
            <div class="card">
                <div class="card-header">
                    <h5 class="mb-0">
                        <i class="fas fa-history me-2"></i>Recent API Calls
                    </h5>
                </div>
                <div class="card-body">
                    {% if recent_calls %}
                    <div class="table-responsive">
                        <table class="table table-hover">
                            <thead>
                                <tr>
                                    <th>Time</th>
                                    <th>Call Type</th>
                                    <th>Status</th>
                                    <th>Call ID</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for call in recent_calls %}
                                <tr>
                                    <td>{{ call.created_at.strftime('%Y-%m-%d %H:%M:%S') }}</td>
                                    <td>
                                        <span class="badge bg-info">{{ call.call_type or 'custom' }}</span>
                                    </td>
                                    <td>
                                        {% if call.status == 'completed' %}
                                        <span class="badge bg-success">Completed</span>
                                        {% elif call.status == 'initiated' %}
                                        <span class="badge bg-primary">Initiated</span>
                                        {% elif call.status == 'failed' %}
                                        <span class="badge bg-danger">Failed</span>
                                        {% else %}
                                        <span class="badge bg-secondary">{{ call.status }}</span>
                                        {% endif %}
                                    </td>
                                    <td>
                                        {% if call.call_log_id %}
                                        <a href="{{ url_for('core.call_details', call_id=call.call_log_id) }}">
                                            #{{ call.call_log_id }}
                                        </a>
                                        {% else %}
                                        -
                                        {% endif %}
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                    {% else %}
                    <div class="text-center py-4 text-muted">
                        <i class="fas fa-inbox fa-2x mb-2"></i>
                        <p>No API calls yet</p>
                    </div>
                    {% endif %}
                </div>
            </div>
        </div>
    </div>
</div>

<script>
function copyApiKey() {
    const input = document.getElementById('newApiKey');
    input.select();
    document.execCommand('copy');

    // Show feedback
    const btn = event.target.closest('button');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-check"></i> Copied!';
    btn.classList.remove('btn-outline-primary');
    btn.classList.add('btn-success');

    setTimeout(() => {
        btn.innerHTML = originalText;
        btn.classList.remove('btn-success');
        btn.classList.add('btn-outline-primary');
    }, 2000);
}
</script>
{% endblock %}
```

---

## API Endpoints Reference

### Authentication

All API endpoints (except `/health`) require authentication via the `X-API-Key` header.

```
X-API-Key: nvx_sk_your_api_key_here
```

### Endpoints Summary

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/call/initiate` | Initiate an outbound call |
| `GET` | `/api/v1/call/{id}/status` | Get call status |
| `GET` | `/api/v1/call/{id}/transcript` | Get call transcript |
| `POST` | `/api/v1/campaign/{id}/start` | Start a campaign |
| `POST` | `/api/v1/campaign/{id}/pause` | Pause a campaign |
| `GET` | `/api/v1/campaign/{id}/status` | Get campaign status |
| `GET` | `/api/v1/agents` | List user's agents |
| `GET` | `/api/v1/campaigns` | List user's campaigns |
| `GET` | `/api/v1/usage` | Get API usage stats |
| `GET` | `/api/v1/health` | Health check (no auth) |

### Call Types

| Type | Description |
|------|-------------|
| `outbound` | Generic outbound call |
| `noshow_recovery` | Follow up on missed appointment |
| `appointment_reminder` | Reminder before appointment |
| `appointment_confirmation` | Confirm upcoming appointment |
| `campaign` | Bulk campaign call |
| `custom` | Custom/other |

### Error Codes

| Code | Description |
|------|-------------|
| `MISSING_API_KEY` | X-API-Key header not provided |
| `INVALID_API_KEY` | API key is invalid or revoked |
| `RATE_LIMIT_EXCEEDED` | Too many requests |
| `AGENT_NOT_FOUND` | Agent doesn't exist or access denied |
| `CALL_NOT_FOUND` | Call doesn't exist or access denied |
| `CAMPAIGN_NOT_FOUND` | Campaign doesn't exist or access denied |
| `CALL_FAILED` | Call initiation failed |

---

## Integration Guide

### n8n Integration Example

#### No-Show Recovery Workflow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Webhook    │     │  Get Patient│     │  Call API   │     │  Handle     │
│  Trigger    │────►│  Details    │────►│  Initiate   │────►│  Response   │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
```

**n8n HTTP Request Node Configuration:**

```json
{
  "method": "POST",
  "url": "https://your-domain.com/api/v1/call/initiate",
  "headers": {
    "X-API-Key": "nvx_sk_your_api_key",
    "Content-Type": "application/json"
  },
  "body": {
    "agent_id": 5,
    "phone": "{{ $json.patient_phone }}",
    "call_type": "noshow_recovery",
    "context": {
      "patient_name": "{{ $json.patient_name }}",
      "missed_appointment": {
        "date": "{{ $json.appointment_date }}",
        "time": "{{ $json.appointment_time }}",
        "doctor": "{{ $json.doctor_name }}"
      }
    }
  }
}
```

### Polling for Call Completion

After initiating a call, poll the status endpoint:

```javascript
// n8n Function Node
const callId = $json.call_id;
const maxAttempts = 30;  // 5 minutes with 10s intervals
let attempts = 0;

while (attempts < maxAttempts) {
  const response = await $http.get({
    url: `https://your-domain.com/api/v1/call/${callId}/status`,
    headers: { 'X-API-Key': 'nvx_sk_your_api_key' }
  });

  if (response.status === 'completed' || response.status === 'failed') {
    return response;
  }

  await new Promise(resolve => setTimeout(resolve, 10000));  // Wait 10s
  attempts++;
}
```

---

## Step-by-Step Implementation

### Step 1: Update models.py

Add the new fields to User model and the APICallLog model:

```python
# In models.py, add to User class:
api_key = db.Column(db.String(64), unique=True, nullable=True, index=True)
api_key_created_at = db.Column(db.DateTime, nullable=True)
api_rate_limit = db.Column(db.Integer, default=100)

# Add the APICallLog class (see full code above)
```

### Step 2: Run Migration

```bash
cd nevoxai-project
python migrations/add_api_management.py
```

### Step 3: Create Service Files

Create the following files in `services/`:
- `api_service.py`
- `call_service.py`
- `rate_limiter_service.py`

### Step 4: Create Route Files

Create the following files in `routes/`:
- `external_api.py`
- `api_settings.py`

### Step 5: Create Template

Create `templates/settings/api_management.html`

### Step 6: Register Blueprints

In your `app.py` or main application file:

```python
from routes.external_api import external_api_bp
from routes.api_settings import api_settings_bp

app.register_blueprint(external_api_bp)
app.register_blueprint(api_settings_bp)
```

### Step 7: Add Navigation Link

Add link to API settings in your navigation:

```html
<a href="{{ url_for('api_settings.api_settings') }}" class="nav-link">
    <i class="fas fa-key"></i> API Management
</a>
```

### Step 8: Test the Integration

1. Generate an API key from the UI
2. Test with curl:

```bash
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

## Security Best Practices

1. **Key Storage**: Never log full API keys. Always mask in logs and UI.

2. **HTTPS Only**: Ensure API endpoints are only accessible via HTTPS.

3. **Rate Limiting**: Default 100 calls/hour prevents abuse.

4. **Key Rotation**: Users should regenerate keys periodically.

5. **Scope Limitation**: Keys only access the user's own resources.

6. **Audit Trail**: APICallLog tracks all API-initiated calls.

---

## Troubleshooting

### "Invalid API key" Error

- Check key is correctly copied (no extra spaces)
- Verify key hasn't been revoked
- Ensure using correct header: `X-API-Key`

### "Rate limit exceeded" Error

- Wait for the rate limit window to reset (1 hour)
- Contact admin to increase limit if needed

### Call Not Initiating

- Verify agent_id exists and belongs to user
- Check user has sufficient minutes balance
- Verify outbound trunk is configured

### Context Not Reaching Agent

- Ensure context is valid JSON
- Check agent is reading from `room.metadata` or `participant.metadata`
- Verify `webhook_context` field in metadata

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-01-30 | Initial implementation |

---

## Support

For issues or questions:
- GitHub: https://github.com/your-repo/issues
- Email: support@nevoxai.com
