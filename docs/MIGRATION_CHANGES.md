# SQLAlchemy ORM Migration - Line-by-Line Changes

This document shows every change made during the migration from raw `sqlite3` to SQLAlchemy ORM.

---

## Table of Contents

1. [database.py (NEW FILE)](#1-databasepy-new-file)
2. [agent_api_flow_transcriptions.py](#2-agent_api_flow_transcriptionspy)
3. [services/campaign_worker.py](#3-servicescampaign_workerpy)
4. [services/tool_service.py](#4-servicestool_servicepy)
5. [server-code/agent-inbound.py](#5-server-codeagent-inboundpy)

---

## 1. database.py (NEW FILE)

**Location:** `nevoxai-project/database.py`

**Purpose:** Unified database access layer for scripts running outside Flask context.

### BEFORE: File did not exist

### AFTER: Complete new file

```python
"""
database.py - Standalone Database Module for Nevox AI Voice Agents

Works outside Flask context (agent scripts, workers, background jobs).
Optimized for voice call latency and concurrent access.

Usage:
    from database import get_session, get_readonly_session
    from models import Agent

    # For read operations (SELECT)
    with get_readonly_session() as session:
        agent = session.query(Agent).filter_by(id=1).first()
        if agent:
            return {'id': agent.id, 'name': agent.name}  # Always return dicts!

    # For write operations (INSERT/UPDATE/DELETE)
    with get_session() as session:
        agent = Agent(name="New", user_id=1, prompt="...")
        session.add(agent)
        # Auto-commits on exit
"""

import os
import logging
from contextlib import contextmanager
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import QueuePool, StaticPool
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# =============================================================================
# DATABASE URL - Change THIS ONE LINE for PostgreSQL later
# =============================================================================
DATABASE_URL = os.environ.get(
    'DATABASE_URL',
    'sqlite:///instance/voice_agent.db'
)

IS_SQLITE = DATABASE_URL.startswith('sqlite')
IS_POSTGRES = DATABASE_URL.startswith('postgresql')

logger.info(f"Database: {'SQLite' if IS_SQLITE else 'PostgreSQL'}")


# =============================================================================
# ENGINE CONFIGURATION (Optimized for Voice Applications)
# =============================================================================
def _create_engine():
    """Create engine with settings optimized for voice call latency"""

    if IS_SQLITE:
        # SQLite: Use StaticPool to eliminate "database is locked" errors
        return create_engine(
            DATABASE_URL,
            connect_args={'check_same_thread': False},
            poolclass=StaticPool,
            echo=False,
        )
    else:
        # PostgreSQL: Tuned for voice call latency
        # - Lower pool_size (base connections are expensive)
        # - Higher max_overflow (overflow is cheap, blocking is expensive)
        # - Short pool_timeout (fail fast, don't hang voice calls)
        return create_engine(
            DATABASE_URL,
            poolclass=QueuePool,
            pool_size=10,             # Base connections (reduced from 20)
            max_overflow=40,          # Extra during peak (increased from 30)
            pool_timeout=10,          # Fail fast for voice (reduced from 30)
            pool_recycle=1800,        # Recycle every 30 min
            pool_pre_ping=True,       # Verify connection before use
            echo=False,
        )


engine = _create_engine()


# =============================================================================
# SQLITE OPTIMIZATIONS (WAL Mode + Foreign Keys)
# =============================================================================
if IS_SQLITE:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        """Enable foreign keys and WAL mode for better concurrency"""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging
        cursor.close()


# =============================================================================
# SESSION FACTORY
# =============================================================================
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False  # Prevent DetachedInstanceError
)

ScopedSession = scoped_session(SessionLocal)


# =============================================================================
# CONTEXT MANAGERS
# =============================================================================
@contextmanager
def get_session():
    """
    Context manager for database sessions (read/write).
    Auto-commits on success, auto-rollback on failure.

    IMPORTANT: Always return dicts, not model objects!
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        session.close()


@contextmanager
def get_readonly_session():
    """
    Context manager for read-only queries.
    More efficient (no commit). Use for SELECT operations.
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# =============================================================================
# CONNECTION HEALTH CHECK (Critical for Voice Agents)
# =============================================================================
def check_connection() -> bool:
    """
    Verify database connection before accepting voice calls.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================
def get_engine():
    """Get SQLAlchemy engine for advanced operations"""
    return engine


def init_db():
    """Create all tables from models.py"""
    from models import db
    db.metadata.create_all(engine)
    logger.info("Database tables initialized")


def get_table_names():
    """Get list of all table names"""
    from sqlalchemy import inspect
    return inspect(engine).get_table_names()


def table_exists(table_name: str) -> bool:
    """Check if a table exists"""
    return table_name in get_table_names()
```

---

## 2. agent_api_flow_transcriptions.py

**Location:** `nevoxai-project/agent_api_flow_transcriptions.py`

### Change 1: Import Statements (Lines 1-21)

#### BEFORE:
```python
import asyncio
import logging
import os
import time
import json
import sqlite3  # <-- RAW SQLITE3
import aiohttp
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

from types import SimpleNamespace
from typing import AsyncIterable
import re

# Redis caching service (40x speedup!)
from services.redis_service import redis_service
```

#### AFTER:
```python
import asyncio
import logging
import os
import time
import json
import aiohttp
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

from types import SimpleNamespace
from typing import AsyncIterable
import re

# Redis caching service (40x speedup!)
from services.redis_service import redis_service

# SQLAlchemy ORM database access (replaces sqlite3)
from database import get_readonly_session, check_connection
from models import Agent as AgentModel  # Renamed to avoid conflict with livekit.agents.Agent
```

**Changes:**
- Removed: `import sqlite3`
- Added: `from database import get_readonly_session, check_connection`
- Added: `from models import Agent as AgentModel` (renamed to avoid conflict with `livekit.agents.Agent`)

---

### Change 2: get_agent_config() Function (Lines 94-153)

#### BEFORE:
```python
def get_agent_config(agent_id: int, use_cache=True):
    """
    Fetch agent configuration with Redis caching.
    """
    # Redis cache check
    if use_cache:
        cached_config = redis_service.get_agent_config(agent_id)
        if cached_config:
            logger.debug(f"✅ Redis cache HIT: agent {agent_id}")
            return cached_config

    logger.debug(f"❌ Redis cache MISS: agent {agent_id} - loading from DB")

    try:
        # OLD: Raw sqlite3 connection
        db_path = os.path.join(os.path.dirname(__file__), 'instance', 'voice_agent.db')
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Raw SQL query with ? placeholder
            cursor.execute("""
                SELECT id, name, prompt, greeting, voice_id, voice_name, temperature, vad_mode
                FROM agent WHERE id = ?
            """, (agent_id,))

            row = cursor.fetchone()

        if row:
            config = {
                'id': row['id'],
                'name': row['name'],
                'prompt': row['prompt'],
                'greeting': row['greeting'] or 'Default greeting...',
                'voice_id': row['voice_id'],
                'voice_name': row['voice_name'],
                'temperature': row['temperature'] or 0.4,
                'vad_mode': row['vad_mode'] or 'dynamic'
            }

            redis_service.cache_agent_config(agent_id, config, ttl=3600)
            return config
        else:
            return None

    except Exception as e:
        logger.error(f"Database error: {e}")
        return None
```

#### AFTER:
```python
def get_agent_config(agent_id: int, use_cache=True) -> dict | None:
    """
    Fetch agent configuration with Redis caching.
    Uses SQLAlchemy ORM for database-agnostic queries.

    PERFORMANCE IMPROVEMENT:
    - Redis cache: ~0.5ms (40x faster than DB!)
    - Database queries reduced by 95%

    Args:
        agent_id: Agent ID to fetch
        use_cache: Whether to use Redis cache (default: True)

    Returns:
        dict: Agent configuration or None if not found
    """
    # STEP 1: Try Redis cache first (FAST! ~0.5ms)
    if use_cache:
        cached_config = redis_service.get_agent_config(agent_id)
        if cached_config:
            logger.debug(f"Redis cache HIT: agent {agent_id}")
            return cached_config

    # STEP 2: Cache miss - load from database using SQLAlchemy ORM
    logger.debug(f"Redis cache MISS: agent {agent_id} - loading from DB")

    try:
        # NEW: Use get_readonly_session for SELECT queries (more efficient)
        with get_readonly_session() as session:
            agent = session.query(AgentModel).filter_by(id=agent_id).first()

            if agent:
                # Convert to dict INSIDE session (critical to avoid DetachedInstanceError!)
                config = {
                    'id': agent.id,
                    'name': agent.name,
                    'prompt': agent.prompt,
                    'greeting': agent.greeting or 'السلام عليكم ورحمة الله وبركاته...',
                    'voice_id': agent.voice_id,
                    'voice_name': agent.voice_name,
                    'temperature': agent.temperature if agent.temperature else 0.4,
                    'vad_mode': agent.vad_mode if agent.vad_mode else 'dynamic'
                }

                # STEP 3: Cache it in Redis for next time (TTL: 1 hour)
                redis_service.cache_agent_config(agent_id, config, ttl=3600)

                logger.info(f"Loaded agent config from database: {config['name']}")
                return config  # Return dict, not model object!
            else:
                logger.warning(f"Agent {agent_id} not found in database")
                return None

    except Exception as e:
        logger.error(f"Database error fetching agent config: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None
```

**Changes:**
- Removed: `sqlite3.connect(db_path)`
- Removed: `conn.row_factory = sqlite3.Row`
- Removed: `cursor.execute("SELECT ... WHERE id = ?", (agent_id,))`
- Added: `with get_readonly_session() as session:`
- Added: `agent = session.query(AgentModel).filter_by(id=agent_id).first()`
- Changed: Access via `agent.name` instead of `row['name']`
- Added: Type hint `-> dict | None`
- **IMPORTANT**: Used `AgentModel` alias to avoid conflict with `livekit.agents.Agent`

---

## 3. services/campaign_worker.py

**Location:** `nevoxai-project/services/campaign_worker.py`

### Change 1: Import Statements (Lines 1-28)

#### BEFORE:
```python
"""
Campaign Worker - Processes outbound campaigns and makes calls
"""
import os
import time
import logging
import asyncio
import sqlite3  # <-- RAW SQLITE3
from datetime import datetime
from dotenv import load_dotenv
from livekit import api

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from services.redis_service import redis_service
from models import SAUDI_TZ

load_dotenv()

# Database path
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance', 'voice_agent.db')
```

#### AFTER:
```python
"""
Campaign Worker - Processes outbound campaigns and makes calls
Runs continuously in the background, monitoring active campaigns

PERFORMANCE OPTIMIZATIONS:
- Redis caching for agent configs (40x speedup!)
- Redis caching for user trunk IDs (30x speedup!)
- Reduced database queries by 95%
- SQLAlchemy ORM for database-agnostic queries (SQLite/PostgreSQL)
"""
import os
import time
import logging
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from livekit import api

# Redis caching service for performance optimization
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from services.redis_service import redis_service
from models import SAUDI_TZ, Campaign, CampaignContact, Agent, User, Workflow

# SQLAlchemy ORM database access (replaces sqlite3)
from database import get_session, get_readonly_session, check_connection

load_dotenv()
```

**Changes:**
- Removed: `import sqlite3`
- Removed: `DB_PATH = os.path.join(...)`
- Added: `from models import SAUDI_TZ, Campaign, CampaignContact, Agent, User, Workflow`
- Added: `from database import get_session, get_readonly_session, check_connection`

---

### Change 2: CampaignWorker.__init__() (Lines 44-52)

#### BEFORE:
```python
class CampaignWorker:
    def __init__(self):
        self.active_calls = {}
        self.lkapi = None

    def get_db_connection(self):
        """Get database connection with row factory"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
```

#### AFTER:
```python
class CampaignWorker:
    def __init__(self):
        self.active_calls = {}  # Track active calls per campaign
        self.lkapi = None

        # Verify database connection at startup
        if not check_connection():
            raise RuntimeError("Database connection failed - campaign worker cannot start")
        logger.info("Database connection verified")
```

**Changes:**
- Removed: `get_db_connection()` method entirely
- Added: Database connection health check at startup

---

### Change 3: get_running_campaigns() (Lines 100-117)

#### BEFORE:
```python
def get_running_campaigns(self):
    """Get all campaigns that are currently running"""
    conn = self.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM campaign WHERE status = 'running'")
    campaigns = cursor.fetchall()
    conn.close()

    return [dict(c) for c in campaigns]
```

#### AFTER:
```python
def get_running_campaigns(self) -> list[dict]:
    """Get all campaigns that are currently running"""
    with get_readonly_session() as session:
        campaigns = session.query(Campaign).filter_by(status='running').all()
        # Convert to list of dicts (critical to avoid DetachedInstanceError!)
        return [
            {
                'id': c.id,
                'user_id': c.user_id,
                'agent_id': c.agent_id,
                'name': c.name,
                'status': c.status,
                'concurrent_calls': c.concurrent_calls,
                'call_window_start': c.call_window_start,
                'call_window_end': c.call_window_end,
            }
            for c in campaigns
        ]
```

**Changes:**
- Removed: `conn = self.get_db_connection()`
- Removed: `cursor.execute("SELECT * FROM campaign WHERE status = 'running'")`
- Added: `with get_readonly_session() as session:`
- Added: `session.query(Campaign).filter_by(status='running').all()`
- Added: Explicit dict conversion with all needed fields

---

### Change 4: cleanup_finished_calls() (Lines 119-146)

#### BEFORE:
```python
def cleanup_finished_calls(self, campaign_id):
    """Remove finished calls from active_calls tracking"""
    if campaign_id not in self.active_calls or not self.active_calls[campaign_id]:
        return

    conn = self.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM campaign_contact WHERE campaign_id = ? AND status = 'calling'",
        (campaign_id,)
    )
    active_contact_ids = {row['id'] for row in cursor.fetchall()}
    conn.close()

    # Filter out finished calls
    initial_count = len(self.active_calls[campaign_id])
    self.active_calls[campaign_id] = [
        call for call in self.active_calls[campaign_id]
        if call['contact_id'] in active_contact_ids
    ]
    # ... rest of logging
```

#### AFTER:
```python
def cleanup_finished_calls(self, campaign_id):
    """
    Remove finished calls from active_calls tracking.
    A call is finished if its status is NOT 'calling' in the database.
    """
    if campaign_id not in self.active_calls or not self.active_calls[campaign_id]:
        return

    # Get contact IDs that are still in 'calling' status
    with get_readonly_session() as session:
        active_contacts = session.query(CampaignContact.id).filter_by(
            campaign_id=campaign_id,
            status='calling'
        ).all()
        active_contact_ids = {c.id for c in active_contacts}

    # Filter out finished calls from tracking
    initial_count = len(self.active_calls[campaign_id])
    self.active_calls[campaign_id] = [
        call for call in self.active_calls[campaign_id]
        if call['contact_id'] in active_contact_ids
    ]
    # ... rest of logging
```

**Changes:**
- Removed: `conn = self.get_db_connection()` and `cursor.execute(...)`
- Added: `with get_readonly_session() as session:`
- Added: `session.query(CampaignContact.id).filter_by(...).all()`

---

### Change 5: check_campaign_completion() (Lines 148-176)

#### BEFORE:
```python
def check_campaign_completion(self, campaign_id) -> bool:
    """Check if a campaign should be marked as completed"""
    self.cleanup_finished_calls(campaign_id)

    # Count pending contacts
    conn = self.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) as count FROM campaign_contact WHERE campaign_id = ? AND status = 'pending'",
        (campaign_id,)
    )
    pending_count = cursor.fetchone()['count']
    conn.close()

    active_count = len(self.active_calls.get(campaign_id, []))

    if pending_count == 0 and active_count == 0:
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE campaign SET status = 'completed', end_time = ? WHERE id = ? AND status = 'running'",
            (saudi_now_naive(), campaign_id)
        )
        conn.commit()
        conn.close()
        return True

    return False
```

#### AFTER:
```python
def check_campaign_completion(self, campaign_id) -> bool:
    """Check if a campaign should be marked as completed (regardless of call window)"""
    # First, cleanup finished calls to get accurate count
    self.cleanup_finished_calls(campaign_id)

    # Count pending contacts
    with get_readonly_session() as session:
        pending_count = session.query(CampaignContact).filter_by(
            campaign_id=campaign_id,
            status='pending'
        ).count()

    # Check if there are any active calls for this campaign
    active_count = len(self.active_calls.get(campaign_id, []))

    # If no pending contacts and no active calls, mark as completed
    if pending_count == 0 and active_count == 0:
        with get_session() as session:
            campaign = session.query(Campaign).filter_by(
                id=campaign_id,
                status='running'
            ).first()
            if campaign:
                campaign.status = 'completed'
                campaign.end_time = saudi_now_naive()
                logger.info(f"Campaign {campaign_id} marked as completed (no pending contacts)")
                return True

    return False
```

**Changes:**
- Removed: All `cursor.execute()` calls with raw SQL
- Added: `session.query(CampaignContact).filter_by(...).count()`
- Added: `session.query(Campaign).filter_by(...).first()` for update
- Changed: Direct attribute assignment `campaign.status = 'completed'`

---

### Change 6: get_pending_contacts() (Lines 178-198)

#### BEFORE:
```python
def get_pending_contacts(self, campaign_id, limit=1):
    """Get pending contacts for a campaign"""
    conn = self.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM campaign_contact
        WHERE campaign_id = ? AND status = 'pending'
        ORDER BY created_at ASC
        LIMIT ?
    """, (campaign_id, limit))
    contacts = cursor.fetchall()
    conn.close()
    return [dict(c) for c in contacts]
```

#### AFTER:
```python
def get_pending_contacts(self, campaign_id, limit=1) -> list[dict]:
    """Get pending contacts for a campaign"""
    with get_readonly_session() as session:
        contacts = session.query(CampaignContact).filter_by(
            campaign_id=campaign_id,
            status='pending'
        ).order_by(CampaignContact.created_at.asc()).limit(limit).all()

        # Convert to list of dicts (critical!)
        return [
            {
                'id': c.id,
                'campaign_id': c.campaign_id,
                'phone_number': c.phone_number,
                'name': c.name,
                'status': c.status,
                'attempts': c.attempts or 0,
                'created_at': c.created_at,
            }
            for c in contacts
        ]
```

**Changes:**
- Removed: Raw SQL `SELECT * FROM campaign_contact WHERE ...`
- Added: `session.query(CampaignContact).filter_by(...).order_by(...).limit(...).all()`
- Added: Explicit dict conversion

---

### Change 7: get_agent_config() (Lines 200-235)

#### BEFORE:
```python
def get_agent_config(self, agent_id):
    """Get agent configuration"""
    # Redis cache check
    cached_config = redis_service.get_agent_config(agent_id)
    if cached_config:
        return cached_config

    conn = self.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM agent WHERE id = ?", (agent_id,))
    agent_row = cursor.fetchone()
    conn.close()

    if agent_row:
        agent_dict = {
            'id': agent_row['id'],
            'name': agent_row['name'],
            'prompt': agent_row['prompt'],
            'greeting': agent_row['greeting'],
            'voice_id': agent_row['voice_id'],
            'voice_name': agent_row['voice_name']
        }
        redis_service.cache_agent_config(agent_id, agent_dict, ttl=3600)
        return agent_dict

    return None
```

#### AFTER:
```python
def get_agent_config(self, agent_id) -> dict | None:
    """
    Get agent configuration with Redis caching

    PERFORMANCE: Redis cache gives 40x speedup (~0.5ms vs ~20ms)
    """
    # STEP 1: Try Redis cache first (FAST! ~0.5ms)
    cached_config = redis_service.get_agent_config(agent_id)

    if cached_config:
        logger.debug(f"Redis cache HIT: agent {agent_id}")
        return cached_config

    # STEP 2: Cache miss - load from database using SQLAlchemy ORM
    logger.debug(f"Redis cache MISS: agent {agent_id} - loading from DB")

    with get_readonly_session() as session:
        agent = session.query(Agent).filter_by(id=agent_id).first()

        if agent:
            # Convert to dict INSIDE session (critical!)
            agent_dict = {
                'id': agent.id,
                'name': agent.name,
                'prompt': agent.prompt,
                'greeting': agent.greeting,
                'voice_id': agent.voice_id,
                'voice_name': agent.voice_name
            }

            # STEP 3: Cache it in Redis for next time (TTL: 1 hour)
            redis_service.cache_agent_config(agent_id, agent_dict, ttl=3600)

            return agent_dict

    return None
```

**Changes:**
- Removed: `cursor.execute("SELECT * FROM agent WHERE id = ?", (agent_id,))`
- Added: `session.query(Agent).filter_by(id=agent_id).first()`
- Changed: Access via `agent.name` instead of `agent_row['name']`

---

### Change 8: update_contact_status() (Lines 237-249)

#### BEFORE:
```python
def update_contact_status(self, contact_id, status, **kwargs):
    """Update contact status"""
    conn = self.get_db_connection()
    cursor = conn.cursor()

    update_fields = [f"{key} = ?" for key in kwargs.keys()]
    update_values = list(kwargs.values())

    sql = f"""
        UPDATE campaign_contact
        SET status = ?, last_attempt = ?, {', '.join(update_fields) if update_fields else ''}
        WHERE id = ?
    """

    timestamp = saudi_now_naive()
    params = [status, timestamp] + update_values + [contact_id]

    # Remove empty update fields
    if not update_fields:
        sql = """
            UPDATE campaign_contact
            SET status = ?, last_attempt = ?
            WHERE id = ?
        """
        params = [status, timestamp, contact_id]

    cursor.execute(sql, params)
    conn.commit()
    conn.close()
```

#### AFTER:
```python
def update_contact_status(self, contact_id, status, **kwargs):
    """Update contact status using SQLAlchemy ORM"""
    with get_session() as session:
        contact = session.query(CampaignContact).filter_by(id=contact_id).first()
        if contact:
            contact.status = status
            contact.last_attempt = saudi_now_naive()

            # Apply any additional field updates
            for key, value in kwargs.items():
                if hasattr(contact, key):
                    setattr(contact, key, value)
            # Auto-commits on exit
```

**Changes:**
- Removed: All raw SQL `UPDATE` statement building
- Added: `session.query(CampaignContact).filter_by(id=contact_id).first()`
- Changed: Direct attribute assignment `contact.status = status`
- Changed: Dynamic field updates via `setattr()`

---

### Change 9: make_call() - Workflow Query (Lines 287-303)

#### BEFORE:
```python
# Check if agent has workflow with pre-call webhook enabled
conn = self.get_db_connection()
cursor = conn.cursor()

cursor.execute("""
    SELECT w.pre_call_enabled, w.pre_call_webhook_url, w.webhook_url,
           w.api_key, w.pre_call_timeout
    FROM agent a
    JOIN workflow w ON a.workflow_id = w.id
    WHERE a.id = ? AND w.pre_call_enabled = 1 AND w.is_active = 1
""", (agent['id'],))

workflow_row = cursor.fetchone()
conn.close()

if workflow_row:
    webhook_url = workflow_row['pre_call_webhook_url'] or workflow_row['webhook_url']
    api_key = workflow_row['api_key']
    timeout = workflow_row['pre_call_timeout'] or 3
```

#### AFTER:
```python
# Check if agent has workflow with pre-call webhook enabled (SQLAlchemy ORM)
workflow_data = None
with get_readonly_session() as session:
    agent_obj = session.query(Agent).filter_by(id=agent['id']).first()
    if agent_obj and agent_obj.workflow_id:
        workflow = session.query(Workflow).filter_by(
            id=agent_obj.workflow_id,
            pre_call_enabled=True,
            is_active=True
        ).first()
        if workflow:
            workflow_data = {
                'pre_call_webhook_url': workflow.pre_call_webhook_url,
                'webhook_url': workflow.webhook_url,
                'api_key': workflow.api_key,
                'pre_call_timeout': workflow.pre_call_timeout
            }

if workflow_data:
    webhook_url = workflow_data['pre_call_webhook_url'] or workflow_data['webhook_url']
    api_key = workflow_data['api_key']
    timeout = workflow_data['pre_call_timeout'] or 3
```

**Changes:**
- Removed: Raw SQL JOIN query
- Added: Two separate ORM queries (Agent, then Workflow)
- Changed: Access via model attributes instead of row dict

---

### Change 10: process_campaign() - User Trunk Query (Lines 454-464)

#### BEFORE:
```python
if not outbound_trunk_id:
    # Cache MISS - load from database
    logger.debug(f"Redis cache MISS: user {campaign['user_id']} trunk - loading from DB")

    conn = self.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT outbound_trunk_id FROM user WHERE id = ?", (campaign['user_id'],))
    user_row = cursor.fetchone()
    conn.close()

    outbound_trunk_id = user_row['outbound_trunk_id'] if user_row and user_row['outbound_trunk_id'] else DEFAULT_OUTBOUND_TRUNK_ID
```

#### AFTER:
```python
if not outbound_trunk_id:
    # Cache MISS - load from database using SQLAlchemy ORM
    logger.debug(f"Redis cache MISS: user {campaign['user_id']} trunk - loading from DB")

    with get_readonly_session() as session:
        user = session.query(User).filter_by(id=campaign['user_id']).first()
        outbound_trunk_id = user.outbound_trunk_id if user and user.outbound_trunk_id else DEFAULT_OUTBOUND_TRUNK_ID
```

**Changes:**
- Removed: `cursor.execute("SELECT outbound_trunk_id FROM user WHERE id = ?", ...)`
- Added: `session.query(User).filter_by(id=...).first()`
- Changed: Access via `user.outbound_trunk_id`

---

### Change 11: run() - Log Message (Line 489)

#### BEFORE:
```python
async def run(self):
    """Main worker loop"""
    logger.info("=" * 60)
    logger.info("Campaign Worker Started")
    logger.info("=" * 60)
    logger.info(f"Database: {DB_PATH}")  # <-- Referenced removed variable
```

#### AFTER:
```python
async def run(self):
    """Main worker loop"""
    logger.info("=" * 60)
    logger.info("Campaign Worker Started")
    logger.info("=" * 60)
    logger.info(f"Database: SQLAlchemy ORM (SQLite/PostgreSQL)")
```

**Changes:**
- Changed: `{DB_PATH}` to `SQLAlchemy ORM (SQLite/PostgreSQL)`

---

## 4. services/tool_service.py

**Location:** `nevoxai-project/services/tool_service.py`

### Change 1: Import Statements (Lines 1-29)

#### BEFORE:
```python
"""
Tool Service - Dynamically load and execute custom tools for voice agents
"""

import json
import logging
import sqlite3  # <-- RAW SQLITE3
import os
import time
import aiohttp
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from livekit.agents import function_tool, RunContext, get_job_context

logger = logging.getLogger("tool_service")
```

#### AFTER:
```python
"""
Tool Service - Dynamically load and execute custom tools for voice agents

This service:
1. Loads tools from database
2. Creates function_tool instances at runtime
3. Executes different tool types (API call, webhook, RPC)
4. CACHES tools for instant performance (Option 4)
5. PRE-WARMS cache at startup
"""

import json
import logging
import os
import sys
import time
import aiohttp
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from livekit.agents import function_tool, RunContext, get_job_context

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# SQLAlchemy ORM database access (replaces sqlite3)
from database import get_readonly_session, check_connection
from models import Agent, Tool, AgentTool

logger = logging.getLogger("tool_service")
```

**Changes:**
- Removed: `import sqlite3`
- Added: `import sys`
- Added: `sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))`
- Added: `from database import get_readonly_session, check_connection`
- Added: `from models import Agent, Tool, AgentTool`

---

### Change 2: ToolService.__init__() (Lines 32-44)

#### BEFORE:
```python
class ToolService:
    """Service for managing and executing custom tools"""

    def __init__(self):
        self.db_path = self._get_db_path()
        # Tool cache for instant performance
        self._tool_cache = {}
        self._cache_ttl = 300  # 5 minutes
        logger.info(f"ToolService initialized with database: {self.db_path}")

    def _get_db_path(self) -> str:
        """Get the database path"""
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance', 'voice_agent.db')
        if not os.path.exists(db_path):
            db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'voice_agent.db')
        return db_path
```

#### AFTER:
```python
class ToolService:
    """Service for managing and executing custom tools"""

    def __init__(self):
        # Tool cache for instant performance
        self._tool_cache = {}
        self._cache_ttl = 300  # 5 minutes

        # Verify database connection
        if not check_connection():
            logger.warning("Database connection check failed at ToolService init")
        else:
            logger.info("ToolService initialized with SQLAlchemy ORM")
```

**Changes:**
- Removed: `self.db_path = self._get_db_path()`
- Removed: `_get_db_path()` method entirely
- Added: Database connection health check

---

### Change 3: preload_all_agents() (Lines 46-98)

#### BEFORE:
```python
def preload_all_agents(self):
    """Pre-warm tool cache at startup"""
    logger.info("=" * 60)
    logger.info("PRE-WARMING TOOL CACHE FOR ALL AGENTS")
    logger.info("=" * 60)

    start_time = time.time()

    try:
        if not os.path.exists(self.db_path):
            logger.warning("Database not found - skipping pre-warming")
            return

        # Get all agent IDs
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM agent ORDER BY id")
        agents = cursor.fetchall()
        conn.close()

        if not agents:
            logger.warning("No agents found in database")
            return

        # ... rest of method
```

#### AFTER:
```python
def preload_all_agents(self):
    """
    Pre-warm tool cache at startup for instant call performance.
    This method should be called once when the worker starts.
    Uses SQLAlchemy ORM for database-agnostic queries.
    """
    logger.info("=" * 60)
    logger.info("PRE-WARMING TOOL CACHE FOR ALL AGENTS")
    logger.info("=" * 60)

    start_time = time.time()

    try:
        # Get all agents using SQLAlchemy ORM
        with get_readonly_session() as session:
            agent_rows = session.query(Agent.id, Agent.name).order_by(Agent.id).all()
            # Convert to list of tuples (critical - access inside session!)
            agents = [(a.id, a.name) for a in agent_rows]

        if not agents:
            logger.warning("No agents found in database")
            return

        # ... rest of method unchanged
```

**Changes:**
- Removed: `if not os.path.exists(self.db_path)` check
- Removed: `sqlite3.connect(self.db_path)` and cursor operations
- Added: `with get_readonly_session() as session:`
- Added: `session.query(Agent.id, Agent.name).order_by(Agent.id).all()`
- Added: List comprehension to extract tuples inside session

---

### Change 4: get_agent_tools() (Lines 100-135)

#### BEFORE:
```python
def get_agent_tools(self, agent_id: int) -> List[Dict[str, Any]]:
    """Retrieve all active tools for a specific agent"""
    try:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Query to get all tools linked to this agent
        cursor.execute("""
            SELECT t.*
            FROM tool t
            INNER JOIN agent_tool at ON t.id = at.tool_id
            WHERE at.agent_id = ? AND t.is_active = 1
            ORDER BY t.created_at ASC
        """, (agent_id,))

        rows = cursor.fetchall()
        conn.close()

        tools = []
        for row in rows:
            tool = {
                'id': row['id'],
                'name': row['name'],
                'description': row['description'],
                'tool_type': row['tool_type'],
                'config': json.loads(row['config']) if row['config'] else {}
            }
            tools.append(tool)

        logger.debug(f"Loaded {len(tools)} tool configs for agent {agent_id}")
        return tools

    except sqlite3.Error as e:
        logger.error(f"Database error loading tools: {e}")
        return []
    except Exception as e:
        logger.error(f"Error loading tools: {e}")
        return []
```

#### AFTER:
```python
def get_agent_tools(self, agent_id: int) -> List[Dict[str, Any]]:
    """
    Retrieve all active tools for a specific agent using SQLAlchemy ORM.

    Args:
        agent_id: The agent ID

    Returns:
        List of tool dictionaries
    """
    try:
        with get_readonly_session() as session:
            # Query to get all active tools linked to this agent
            tool_rows = session.query(Tool).join(AgentTool).filter(
                AgentTool.agent_id == agent_id,
                Tool.is_active == True
            ).order_by(Tool.created_at.asc()).all()

            # Convert to list of dicts (critical - access inside session!)
            tools = []
            for t in tool_rows:
                tool = {
                    'id': t.id,
                    'name': t.name,
                    'description': t.description,
                    'tool_type': t.tool_type,
                    'config': json.loads(t.config) if t.config else {}
                }
                tools.append(tool)

        logger.debug(f"Loaded {len(tools)} tool configs for agent {agent_id}")
        return tools

    except Exception as e:
        logger.error(f"Error loading tools: {e}")
        return []
```

**Changes:**
- Removed: `sqlite3.connect(self.db_path)` and cursor operations
- Removed: Raw SQL JOIN query
- Added: `with get_readonly_session() as session:`
- Added: `session.query(Tool).join(AgentTool).filter(...).order_by(...).all()`
- Changed: Access via `t.name` instead of `row['name']`
- Removed: `sqlite3.Error` exception handling (now just `Exception`)

---

## 5. server-code/agent-inbound.py

**Location:** `nevoxai-project/server-code/agent-inbound.py`

This file runs on the production server and handles inbound voice calls.

### Change 1: Import Statements (Lines 1-17)

#### BEFORE:
```python
import asyncio
import logging
import os
import time
import json
import aiohttp
import sqlite3  # <-- RAW SQLITE3
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

from typing import AsyncIterable
import re
import time

# Saudi Arabia Timezone (UTC+3)
SAUDI_TZ = timezone(timedelta(hours=3))
from livekit import api, rtc
```

#### AFTER:
```python
import asyncio
import logging
import os
import time
import json
import aiohttp
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

from typing import AsyncIterable
import re
import time

# SQLAlchemy ORM database access (replaces sqlite3)
from database import get_readonly_session, check_connection
from models import Agent as AgentModel, InboundConfiguration

# Saudi Arabia Timezone (UTC+3)
SAUDI_TZ = timezone(timedelta(hours=3))
from livekit import api, rtc
```

**Changes:**
- Removed: `import sqlite3`
- Added: `from database import get_readonly_session, check_connection`
- Added: `from models import Agent as AgentModel, InboundConfiguration`
- **IMPORTANT**: Used `AgentModel` alias to avoid conflict with `livekit.agents.Agent`

---

### Change 2: get_agent_config() Function (Lines 98-160)

#### BEFORE:
```python
def get_agent_config(agent_id: int, use_cache=True):
    """Fetch agent configuration from database with caching"""
    # Check cache first
    if use_cache and agent_id in _agent_config_cache:
        # ... cache check ...

    try:
        db_path = os.path.join(os.path.dirname(__file__), 'instance', 'voice_agent.db')
        if not os.path.exists(db_path):
            db_path = os.path.join(os.path.dirname(__file__), 'voice_agent.db')

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, name, prompt, greeting, voice_id, voice_name, temperature, vad_mode
            FROM agent WHERE id = ?
        """, (agent_id,))

        row = cursor.fetchone()
        conn.close()

        if row:
            config = {
                'id': row['id'],
                'name': row['name'],
                # ...
            }
```

#### AFTER:
```python
def get_agent_config(agent_id: int, use_cache=True) -> dict | None:
    """
    Fetch agent configuration from database with caching.
    Uses SQLAlchemy ORM for database-agnostic queries.
    """
    # Check cache first
    if use_cache and agent_id in _agent_config_cache:
        # ... cache check (unchanged) ...

    try:
        # Use SQLAlchemy ORM instead of raw sqlite3
        with get_readonly_session() as session:
            agent = session.query(AgentModel).filter_by(id=agent_id).first()

            if agent:
                # Convert to dict INSIDE session (critical!)
                config = {
                    'id': agent.id,
                    'name': agent.name,
                    'prompt': agent.prompt,
                    'greeting': agent.greeting if agent.greeting else 'Default greeting...',
                    'voice_id': agent.voice_id,
                    'voice_name': agent.voice_name,
                    'temperature': agent.temperature if agent.temperature else 0.4,
                    'vad_mode': agent.vad_mode if agent.vad_mode else 'dynamic'
                }
                # ... cache result (unchanged) ...
```

**Changes:**
- Removed: `db_path` detection and `os.path.exists()` checks
- Removed: `sqlite3.connect()` and cursor operations
- Added: `with get_readonly_session() as session:`
- Added: `session.query(AgentModel).filter_by(id=agent_id).first()`

---

### Change 3: get_inbound_agent_by_number() Function (Lines 163-246)

#### BEFORE:
```python
def get_inbound_agent_by_number(to_number):
    """Fetch inbound configuration by phone number"""
    try:
        db_path = os.path.join(...)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT ic.id as config_id, ic.name as config_name, ic.phone_number,
                   a.id as agent_id, a.name as agent_name, a.prompt, ...
            FROM inbound_configuration ic
            INNER JOIN agent a ON ic.agent_id = a.id
            ORDER BY ic.created_at DESC
        """)

        rows = cursor.fetchall()
        conn.close()
        # ... match phone number logic ...
```

#### AFTER:
```python
def get_inbound_agent_by_number(to_number) -> dict | None:
    """
    Fetch inbound configuration by phone number.
    Uses SQLAlchemy ORM for database-agnostic queries.
    """
    try:
        clean_to_number = to_number.replace('+', '').replace('-', '').replace(' ', '') if to_number else ''

        with get_readonly_session() as session:
            # Query InboundConfiguration with relationship to Agent
            configs = session.query(InboundConfiguration).join(AgentModel).order_by(
                InboundConfiguration.created_at.desc()
            ).all()

            # Convert to list of dicts INSIDE session (critical!)
            rows = []
            for ic in configs:
                rows.append({
                    'config_id': ic.id,
                    'config_name': ic.name,
                    'phone_number': ic.phone_number,
                    'agent_id': ic.agent.id,
                    'agent_name': ic.agent.name,
                    'prompt': ic.agent.prompt,
                    # ... other fields via relationship ...
                })
        # ... match phone number logic (unchanged) ...
```

**Changes:**
- Removed: Raw SQL JOIN query
- Added: `session.query(InboundConfiguration).join(AgentModel)...`
- Added: Access related Agent via `ic.agent.name` relationship
- Changed: Convert to dicts inside session before returning

---

## Summary of All Changes

| File | Lines Changed | Key Changes |
|------|---------------|-------------|
| `database.py` | NEW (207 lines) | Created unified database access layer |
| `agent_api_flow_transcriptions.py` | ~60 lines | Replaced sqlite3 with ORM in get_agent_config() |
| `services/campaign_worker.py` | ~150 lines | Replaced all sqlite3 calls (11 locations) |
| `services/tool_service.py` | ~80 lines | Replaced sqlite3 in __init__, preload_all_agents(), get_agent_tools() |
| `server-code/agent-inbound.py` | ~100 lines | Replaced sqlite3 in get_agent_config(), get_inbound_agent_by_number() |

### Pattern Applied Everywhere

**BEFORE (sqlite3):**
```python
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()
cursor.execute("SELECT * FROM table WHERE id = ?", (id,))
row = cursor.fetchone()
conn.close()
result = row['column_name']
```

**AFTER (SQLAlchemy ORM):**
```python
with get_readonly_session() as session:
    obj = session.query(Model).filter_by(id=id).first()
    if obj:
        result = {
            'column_name': obj.column_name,
            # ... other fields
        }
```

### Critical Rule Applied

Every function that queries the database now:
1. Uses context manager (`with get_session()` or `with get_readonly_session()`)
2. Converts model objects to dicts **inside** the session
3. Returns dicts, never model objects

---

## 6. server-code/campaign_worker.py

**Location:** `nevoxai-project/server-code/campaign_worker.py`

This file runs on the production server and handles outbound campaign calls.

### Change 1: Import Statements (Lines 1-39)

#### BEFORE:
```python
"""
Campaign Worker - Processes outbound campaigns and makes calls
Runs continuously in the background, monitoring active campaigns

PERFORMANCE OPTIMIZATIONS:
- Redis caching for agent configs (40x speedup!)
- Redis caching for user trunk IDs (30x speedup!)
- Reduced database queries by 95%
"""
import os
import time
import logging
import asyncio
import sqlite3  # <-- RAW SQLITE3
from datetime import datetime
from dotenv import load_dotenv
from livekit import api

# Redis caching service for performance optimization
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from services.redis_service import redis_service
from models import SAUDI_TZ

load_dotenv()

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("campaign-worker")

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance', 'voice_agent.db')
DEFAULT_OUTBOUND_TRUNK_ID = os.getenv("SIP_OUTBOUND_TRUNK_ID")
CHECK_INTERVAL = 10
```

#### AFTER:
```python
"""
Campaign Worker - Processes outbound campaigns and makes calls
Runs continuously in the background, monitoring active campaigns

PERFORMANCE OPTIMIZATIONS:
- Redis caching for agent configs (40x speedup!)
- Redis caching for user trunk IDs (30x speedup!)
- Reduced database queries by 95%
- SQLAlchemy ORM for database-agnostic queries (SQLite/PostgreSQL)
"""
import os
import time
import logging
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from livekit import api

# Add parent directory to path for imports
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# SQLAlchemy ORM database access (replaces sqlite3)
from database import get_session, get_readonly_session, check_connection
from models import Campaign, CampaignContact, Agent, User, SAUDI_TZ

# Redis caching service for performance optimization
from services.redis_service import redis_service

load_dotenv()

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("campaign-worker")

DEFAULT_OUTBOUND_TRUNK_ID = os.getenv("SIP_OUTBOUND_TRUNK_ID")
CHECK_INTERVAL = 10
```

**Changes:**
- Removed: `import sqlite3`
- Removed: `DB_PATH = os.path.join(...)`
- Added: `from database import get_session, get_readonly_session, check_connection`
- Added: `from models import Campaign, CampaignContact, Agent, User, SAUDI_TZ`
- Added: SQLAlchemy ORM note in docstring

---

### Change 2: CampaignWorker Class - Removed get_db_connection() (Lines 46-57)

#### BEFORE:
```python
class CampaignWorker:
    def __init__(self):
        self.active_calls = {}
        self.lkapi = None

    def get_db_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
```

#### AFTER:
```python
class CampaignWorker:
    def __init__(self):
        self.active_calls = {}  # Track active calls per campaign
        self.lkapi = None
```

**Changes:**
- Removed: `get_db_connection()` method entirely
- Database connections now handled by `get_session()` / `get_readonly_session()` context managers

---

### Change 3: get_running_campaigns() (Lines 60-75)

#### BEFORE:
```python
def get_running_campaigns(self):
    """Get all campaigns that are currently running"""
    conn = self.get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM campaign
        WHERE status = 'running'
    """)

    campaigns = cursor.fetchall()
    conn.close()

    return campaigns
```

#### AFTER:
```python
def get_running_campaigns(self):
    """Get all campaigns that are currently running (SQLAlchemy ORM)"""
    with get_readonly_session() as session:
        campaigns = session.query(Campaign).filter_by(status='running').all()
        # Convert to list of dicts to avoid DetachedInstanceError
        return [
            {
                'id': c.id,
                'user_id': c.user_id,
                'agent_id': c.agent_id,
                'name': c.name,
                'status': c.status,
                'concurrent_calls': c.concurrent_calls,
                'call_window_start': c.call_window_start,
                'call_window_end': c.call_window_end,
            }
            for c in campaigns
        ]
```

**Changes:**
- Removed: `conn = self.get_db_connection()` and raw SQL
- Added: `with get_readonly_session() as session:`
- Added: `session.query(Campaign).filter_by(status='running').all()`
- Added: Explicit dict conversion with all needed fields

---

### Change 4: cleanup_finished_calls() (Lines 77-107)

#### BEFORE:
```python
def cleanup_finished_calls(self, campaign_id):
    """Remove finished calls from active_calls tracking."""
    if campaign_id not in self.active_calls or not self.active_calls[campaign_id]:
        return

    conn = self.get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id FROM campaign_contact
        WHERE campaign_id = ? AND status = 'calling'
    """, (campaign_id,))

    active_contact_ids = {row['id'] for row in cursor.fetchall()}
    conn.close()

    # Filter out finished calls from tracking
    # ... rest of method
```

#### AFTER:
```python
def cleanup_finished_calls(self, campaign_id):
    """Remove finished calls from active_calls tracking (SQLAlchemy ORM)."""
    if campaign_id not in self.active_calls or not self.active_calls[campaign_id]:
        return

    with get_readonly_session() as session:
        # Get contact IDs that are still in 'calling' status
        contacts = session.query(CampaignContact.id).filter_by(
            campaign_id=campaign_id,
            status='calling'
        ).all()
        active_contact_ids = {c.id for c in contacts}

    # Filter out finished calls from tracking
    # ... rest of method unchanged
```

**Changes:**
- Removed: `conn = self.get_db_connection()` and raw SQL
- Added: `with get_readonly_session() as session:`
- Added: `session.query(CampaignContact.id).filter_by(...).all()`

---

### Change 5: check_campaign_completion() (Lines 108-143)

#### BEFORE:
```python
def check_campaign_completion(self, campaign_id):
    """Check if a campaign should be marked as completed"""
    self.cleanup_finished_calls(campaign_id)

    conn = self.get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*) as count FROM campaign_contact
        WHERE campaign_id = ? AND status = 'pending'
    """, (campaign_id,))

    pending_count = cursor.fetchone()['count']
    active_count = len(self.active_calls.get(campaign_id, []))

    if pending_count == 0 and active_count == 0:
        cursor.execute("""
            UPDATE campaign
            SET status = 'completed', end_time = ?
            WHERE id = ? AND status = 'running'
        """, (saudi_now_naive(), campaign_id))
        conn.commit()

        if cursor.rowcount > 0:
            logger.info(f"Campaign {campaign_id} marked as completed")
            conn.close()
            return True

    conn.close()
    return False
```

#### AFTER:
```python
def check_campaign_completion(self, campaign_id):
    """Check if a campaign should be marked as completed (SQLAlchemy ORM)"""
    self.cleanup_finished_calls(campaign_id)

    with get_readonly_session() as session:
        pending_count = session.query(CampaignContact).filter_by(
            campaign_id=campaign_id,
            status='pending'
        ).count()

    active_count = len(self.active_calls.get(campaign_id, []))

    if pending_count == 0 and active_count == 0:
        with get_session() as session:
            campaign = session.query(Campaign).filter_by(
                id=campaign_id,
                status='running'
            ).first()

            if campaign:
                campaign.status = 'completed'
                campaign.end_time = saudi_now_naive()
                logger.info(f"Campaign {campaign_id} marked as completed")
                return True

    return False
```

**Changes:**
- Removed: Raw SQL COUNT and UPDATE queries
- Added: `session.query(CampaignContact).filter_by(...).count()`
- Added: `session.query(Campaign).filter_by(...).first()` for update
- Changed: Direct attribute assignment `campaign.status = 'completed'`

---

### Change 6: get_pending_contacts() (Lines 144-160)

#### BEFORE:
```python
def get_pending_contacts(self, campaign_id, limit=1):
    """Get pending contacts for a campaign"""
    conn = self.get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM campaign_contact
        WHERE campaign_id = ? AND status = 'pending'
        ORDER BY created_at ASC
        LIMIT ?
    """, (campaign_id, limit))

    contacts = cursor.fetchall()
    conn.close()

    return contacts
```

#### AFTER:
```python
def get_pending_contacts(self, campaign_id, limit=1):
    """Get pending contacts for a campaign (SQLAlchemy ORM)"""
    with get_readonly_session() as session:
        contacts = session.query(CampaignContact).filter_by(
            campaign_id=campaign_id,
            status='pending'
        ).order_by(CampaignContact.created_at.asc()).limit(limit).all()

        # Convert to list of dicts to avoid DetachedInstanceError
        return [
            {
                'id': c.id,
                'campaign_id': c.campaign_id,
                'phone_number': c.phone_number,
                'name': c.name,
                'status': c.status,
                'attempts': c.attempts or 0,
                'created_at': c.created_at,
            }
            for c in contacts
        ]
```

**Changes:**
- Removed: Raw SQL SELECT with LIMIT
- Added: `session.query(CampaignContact).filter_by(...).order_by(...).limit(...).all()`
- Added: Explicit dict conversion

---

### Change 7: get_agent_config() (Lines 161-210)

#### BEFORE:
```python
def get_agent_config(self, agent_id):
    """Get agent configuration with Redis caching"""
    cached_config = redis_service.get_agent_config(agent_id)

    if cached_config:
        logger.debug(f"Redis cache HIT: agent {agent_id}")
        return cached_config

    logger.debug(f"Redis cache MISS: agent {agent_id} - loading from DB")

    conn = self.get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, name, prompt, greeting, voice_id, voice_name
        FROM agent
        WHERE id = ?
    """, (agent_id,))

    agent = cursor.fetchone()
    conn.close()

    if agent:
        agent_dict = {
            'id': agent['id'],
            'name': agent['name'],
            'prompt': agent['prompt'],
            'greeting': agent['greeting'],
            'voice_id': agent['voice_id'],
            'voice_name': agent['voice_name']
        }

        redis_service.cache_agent_config(agent_id, agent_dict, ttl=3600)
        return agent_dict

    return None
```

#### AFTER:
```python
def get_agent_config(self, agent_id):
    """Get agent configuration with Redis caching (SQLAlchemy ORM)"""
    cached_config = redis_service.get_agent_config(agent_id)

    if cached_config:
        logger.debug(f"Redis cache HIT: agent {agent_id}")
        return cached_config

    logger.debug(f"Redis cache MISS: agent {agent_id} - loading from DB")

    with get_readonly_session() as session:
        agent = session.query(Agent).filter_by(id=agent_id).first()

        if agent:
            agent_dict = {
                'id': agent.id,
                'name': agent.name,
                'prompt': agent.prompt,
                'greeting': agent.greeting,
                'voice_id': agent.voice_id,
                'voice_name': agent.voice_name
            }

            redis_service.cache_agent_config(agent_id, agent_dict, ttl=3600)
            return agent_dict

    return None
```

**Changes:**
- Removed: `conn = self.get_db_connection()` and raw SQL
- Added: `with get_readonly_session() as session:`
- Added: `session.query(Agent).filter_by(id=agent_id).first()`
- Changed: Access via `agent.name` instead of `agent['name']`

---

### Change 8: update_contact_status() (Lines 211-240)

#### BEFORE:
```python
def update_contact_status(self, contact_id, status, **kwargs):
    """Update contact status"""
    conn = self.get_db_connection()
    cursor = conn.cursor()

    update_fields = [f"{key} = ?" for key in kwargs.keys()]
    update_values = list(kwargs.values())

    sql = f"""
        UPDATE campaign_contact
        SET status = ?, last_attempt = ?, {', '.join(update_fields) if update_fields else ''}
        WHERE id = ?
    """

    timestamp = saudi_now_naive()
    params = [status, timestamp] + update_values + [contact_id]

    if not update_fields:
        sql = """
            UPDATE campaign_contact
            SET status = ?, last_attempt = ?
            WHERE id = ?
        """
        params = [status, timestamp, contact_id]

    cursor.execute(sql, params)
    conn.commit()
    conn.close()
```

#### AFTER:
```python
def update_contact_status(self, contact_id, status, **kwargs):
    """Update contact status (SQLAlchemy ORM)"""
    timestamp = saudi_now_naive()

    with get_session() as session:
        contact = session.query(CampaignContact).filter_by(id=contact_id).first()

        if contact:
            contact.status = status
            contact.last_attempt = timestamp

            # Update any additional fields passed in kwargs
            for key, value in kwargs.items():
                if hasattr(contact, key):
                    setattr(contact, key, value)
            # Commits automatically on context manager exit
```

**Changes:**
- Removed: All raw SQL UPDATE statement building
- Added: `with get_session() as session:`
- Added: `session.query(CampaignContact).filter_by(id=contact_id).first()`
- Changed: Direct attribute assignment `contact.status = status`
- Changed: Dynamic field updates via `setattr()`

---

### Change 9: process_campaign() - User Trunk Query (Lines 334-351)

#### BEFORE:
```python
# Get user's outbound trunk ID with Redis caching
outbound_trunk_id = redis_service.get_user_trunk(campaign['user_id'])

if not outbound_trunk_id:
    logger.debug(f"Redis cache MISS: user {campaign['user_id']} trunk - loading from DB")

    conn = self.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT outbound_trunk_id FROM user WHERE id = ?", (campaign['user_id'],))
    user_row = cursor.fetchone()
    conn.close()

    outbound_trunk_id = user_row['outbound_trunk_id'] if user_row and user_row['outbound_trunk_id'] else DEFAULT_OUTBOUND_TRUNK_ID

    if outbound_trunk_id:
        redis_service.cache_user_trunk(campaign['user_id'], outbound_trunk_id, ttl=3600)
else:
    logger.debug(f"Redis cache HIT: user {campaign['user_id']} trunk")
```

#### AFTER:
```python
# Get user's outbound trunk ID with Redis caching
outbound_trunk_id = redis_service.get_user_trunk(campaign['user_id'])

if not outbound_trunk_id:
    logger.debug(f"Redis cache MISS: user {campaign['user_id']} trunk - loading from DB")

    with get_readonly_session() as session:
        user = session.query(User).filter_by(id=campaign['user_id']).first()
        outbound_trunk_id = user.outbound_trunk_id if user and user.outbound_trunk_id else DEFAULT_OUTBOUND_TRUNK_ID

    if outbound_trunk_id:
        redis_service.cache_user_trunk(campaign['user_id'], outbound_trunk_id, ttl=3600)
else:
    logger.debug(f"Redis cache HIT: user {campaign['user_id']} trunk")
```

**Changes:**
- Removed: `conn = self.get_db_connection()` and raw SQL
- Added: `with get_readonly_session() as session:`
- Added: `session.query(User).filter_by(id=...).first()`
- Changed: Access via `user.outbound_trunk_id`

---

### Change 10: run() - Startup Logging (Lines 364-379)

#### BEFORE:
```python
async def run(self):
    """Main worker loop"""
    logger.info("=" * 60)
    logger.info("Campaign Worker Started")
    logger.info("=" * 60)
    logger.info(f"Database: {DB_PATH}")
    logger.info(f"Check Interval: {CHECK_INTERVAL}s")
    logger.info(f"Default Outbound Trunk: {DEFAULT_OUTBOUND_TRUNK_ID}")
    logger.info(f"Mode: Per-user trunk routing (with fallback to default)")
    logger.info("=" * 60)

    if not DEFAULT_OUTBOUND_TRUNK_ID:
        logger.warning("SIP_OUTBOUND_TRUNK_ID not set in .env")
```

#### AFTER:
```python
async def run(self):
    """Main worker loop"""
    logger.info("=" * 60)
    logger.info("Campaign Worker Started (SQLAlchemy ORM)")
    logger.info("=" * 60)
    logger.info(f"Database: SQLAlchemy ORM (SQLite/PostgreSQL)")
    logger.info(f"Check Interval: {CHECK_INTERVAL}s")
    logger.info(f"Default Outbound Trunk: {DEFAULT_OUTBOUND_TRUNK_ID}")
    logger.info(f"Mode: Per-user trunk routing (with fallback to default)")
    logger.info("=" * 60)

    # Verify database connection on startup
    if not check_connection():
        logger.error("Database connection failed! Check DATABASE_URL")
        return

    if not DEFAULT_OUTBOUND_TRUNK_ID:
        logger.warning("SIP_OUTBOUND_TRUNK_ID not set in .env")
```

**Changes:**
- Changed: `{DB_PATH}` to `SQLAlchemy ORM (SQLite/PostgreSQL)`
- Added: Database connection health check at startup with `check_connection()`
- Added: Early return if database connection fails

---

## Updated Summary of All Changes

| File | Lines Changed | Key Changes |
|------|---------------|-------------|
| `database.py` | NEW (207 lines) | Created unified database access layer |
| `agent_api_flow_transcriptions.py` | ~60 lines | Replaced sqlite3 with ORM in get_agent_config() |
| `services/campaign_worker.py` | ~150 lines | Replaced all sqlite3 calls (11 locations) |
| `services/tool_service.py` | ~80 lines | Replaced sqlite3 in __init__, preload_all_agents(), get_agent_tools() |
| `server-code/agent-inbound.py` | ~100 lines | Replaced sqlite3 in get_agent_config(), get_inbound_agent_by_number() |
| `server-code/campaign_worker.py` | ~120 lines | Replaced all sqlite3 calls (8 methods) |
