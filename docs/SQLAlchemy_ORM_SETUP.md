# SQLAlchemy ORM Setup Documentation

## Overview

This document explains how to migrate the NevoxAI voice agent platform from mixed database access (Flask-SQLAlchemy + raw sqlite3) to a unified SQLAlchemy ORM approach that works with both SQLite and PostgreSQL.

### Key Benefits
- **Database Agnostic**: Same code runs on SQLite (now) and PostgreSQL (later)
- **Easy Migration**: Switch databases by changing ONE line (DATABASE_URL)
- **No Raw SQL**: ORM handles SQL syntax differences automatically
- **Connection Pooling**: Better handling of concurrent voice calls

---

## Table of Contents

1. [Key Concepts](#key-concepts)
2. [Current Architecture](#current-architecture)
3. [Target Architecture](#target-architecture)
4. [Why database.py?](#why-databasepy)
5. [The database.py Module](#the-databasepy-module)
6. [Migration Guide](#migration-guide)
7. [Usage Examples](#usage-examples)
8. [Schema Changes (Adding Columns/Tables)](#schema-changes)
9. [Switching to PostgreSQL](#switching-to-postgresql)
10. [Troubleshooting](#troubleshooting)

---

## Key Concepts

### What Changes, What Stays Same

| File | Purpose | Needs Changes? |
|------|---------|----------------|
| `models.py` | Defines tables & columns | **NO** - already complete |
| `database.py` | Connection for standalone scripts | **NEW** - create this |
| `routes/*.py` | Flask routes (use db.session) | **NO** - keep as-is |
| `agent scripts` | Voice agent code (uses sqlite3) | **YES** - use database.py |
| `.env` | Database URL | **YES** - add DATABASE_URL |

### Two Ways to Access Database

| Context | Method | Used By |
|---------|--------|---------|
| Inside Flask | `db.session` (Flask-SQLAlchemy) | Routes, web app |
| Outside Flask | `database.py` (standalone) | Agent scripts, workers |

```
INSIDE FLASK (routes/*.py)          OUTSIDE FLASK (agent scripts)
--------------------------          -----------------------------
from models import db, Agent        from database import get_session
                                    from models import Agent

agent = Agent.query.get(1)          with get_session() as session:
db.session.add(agent)                   agent = session.query(Agent).get(1)
db.session.commit()                     session.add(agent)
                                        # auto-commits on exit
```

**Important**: `database.py` replaces `sqlite3`, NOT `db.session`!

---

---

## Why database.py?

### The Problem

Your agent scripts (`agent_api_flow_transcriptions.py`, `campaign_worker.py`) run **outside Flask**. They can't use `db.session` because there's no Flask app context.

### Current Workaround (Bad)

```python
# agent_api_flow_transcriptions.py - CURRENT CODE
import sqlite3

db_path = 'instance/voice_agent.db'
conn = sqlite3.connect(db_path)  # Direct SQLite connection
cursor = conn.cursor()
cursor.execute("SELECT * FROM agent WHERE id = ?", (id,))  # Raw SQL
```

**Problems with this approach:**
1. SQLite uses `?` placeholders, PostgreSQL uses `%s` - code breaks when switching
2. No connection pooling - creates new connection every time
3. Database locking issues with concurrent calls
4. Duplicates logic already in models.py

### Solution: database.py

```python
# agent_api_flow_transcriptions.py - NEW CODE
from database import get_session
from models import Agent

with get_session() as session:
    agent = session.query(Agent).get(id)  # Uses existing model!
```

**Benefits:**
1. Same code works with SQLite AND PostgreSQL
2. Connection pooling built-in
3. No locking issues
4. Reuses existing models - no duplication

### When to Use What

| Situation | Use |
|-----------|-----|
| Writing Flask routes | `db.session` (Flask-SQLAlchemy) |
| Writing agent scripts | `database.py` (standalone) |
| Writing background workers | `database.py` (standalone) |
| Writing migration scripts | `database.py` (standalone) |

---

## Critical Rule: Always Return Dicts, Not Model Objects

**This is where most SQLAlchemy migrations fail!**

Model objects become invalid after the session closes. This causes `DetachedInstanceError`.

### WRONG (causes error):
```python
def get_agent(id):
    with get_session() as session:
        return session.query(Agent).get(id)  # Object returned outside session!

# Later in code:
agent = get_agent(1)
print(agent.name)  # DetachedInstanceError!
```

### CORRECT (return dict):
```python
def get_agent(id) -> dict | None:
    with get_readonly_session() as session:
        agent = session.query(Agent).filter_by(id=id).first()
        if agent:
            return {
                'id': agent.id,
                'name': agent.name,
                'prompt': agent.prompt,
                # ... all fields you need
            }
        return None

# Later in code:
agent = get_agent(1)
print(agent['name'])  # Works!
```

### Rule of Thumb
- **Inside session**: Use model objects freely
- **Returning from function**: Convert to dict first
- **Storing for later**: Always use dict

---

## Specialist Recommendations for Voice Applications

### Pool Settings Comparison

| Setting | Default | Voice-Optimized | Reason |
|---------|---------|-----------------|--------|
| pool_size | 20 | 10-15 | Base connections are expensive |
| max_overflow | 30 | 40-50 | Overflow is cheap, blocking is expensive |
| pool_timeout | 30 | 10 | Fail fast, don't hang voice calls |

### SQLite Optimizations

| Feature | Purpose |
|---------|---------|
| `StaticPool` | Single connection, eliminates "database is locked" |
| `PRAGMA journal_mode=WAL` | Write-Ahead Logging for better concurrency |
| `PRAGMA foreign_keys=ON` | Enforce referential integrity |

### Connection Health Check

Always verify database before accepting calls:
```python
# At agent startup
if not check_connection():
    raise RuntimeError('Database unavailable - agent cannot start')
```

---

## Current Architecture

### The Problem: Mixed Database Access

The codebase currently uses **two different database access patterns**:

| Component | Access Method | Location |
|-----------|---------------|----------|
| Flask routes | Flask-SQLAlchemy ORM | `routes/*.py` |
| Agent scripts | Raw `sqlite3` | `agent_api_flow_transcriptions.py` |
| Campaign worker | Raw `sqlite3` | `services/campaign_worker.py` |
| Tool service | Raw `sqlite3` | `services/tool_service.py` |

### Why This Is Problematic

1. **Database locking** - SQLite file-level locks cause issues with concurrent voice calls
2. **Code duplication** - Same queries written in two different styles
3. **Migration difficulty** - Raw SQL uses `?` placeholders, PostgreSQL uses `%s`
4. **No connection pooling** - Each sqlite3.connect() creates new connection

---

## Target Architecture

### Unified SQLAlchemy ORM

After migration, ALL components will use SQLAlchemy ORM through a shared `database.py` module:

```
+-------------------------------------------------------------+
|                      database.py                            |
|  +-----------------------------------------------------+   |
|  |  SQLAlchemy Engine (with connection pooling)        |   |
|  |  - Works with SQLite (now)                          |   |
|  |  - Works with PostgreSQL (later)                    |   |
|  +-----------------------------------------------------+   |
+-------------------------------------------------------------+
           |                    |                    |
           v                    v                    v
    +----------+        +--------------+      +------------+
    |  Flask   |        | Agent Script |      |  Campaign  |
    |  Routes  |        |  (LiveKit)   |      |   Worker   |
    +----------+        +--------------+      +------------+
```

---

## The database.py Module

### Complete Implementation

Create this file at `nevoxai-project/database.py`:

```python
"""
database.py - Standalone Database Module for Nevox AI Voice Agents

Works outside Flask context (agent scripts, workers, background jobs).
Optimized for voice call latency and concurrent access.

Usage:
    from database import get_session
    from models import Agent

    with get_session() as session:
        agent = session.query(Agent).filter_by(id=1).first()
        if agent:
            return {'id': agent.id, 'name': agent.name}  # Always return dicts!
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

    WRONG (causes DetachedInstanceError):
        with get_session() as session:
            return session.query(Agent).get(id)  # Object returned outside session!

    CORRECT:
        with get_session() as session:
            agent = session.query(Agent).get(id)
            if agent:
                return {'id': agent.id, 'name': agent.name}
            return None
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

    Usage at agent startup:
        if not check_connection():
            raise RuntimeError('Database unavailable - agent cannot start')
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

## Migration Guide

### Step 1: Create database.py

Copy the module above to `nevoxai-project/database.py`.

### Step 2: Update agent_api_flow_transcriptions.py

**Before (lines 7, 94-168):**
```python
import sqlite3

def get_agent_config(agent_id: int, use_cache=True):
    # Redis cache check...

    db_path = os.path.join(os.path.dirname(__file__), 'instance', 'voice_agent.db')
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, prompt, greeting, voice_id, voice_name, temperature, vad_mode
            FROM agent WHERE id = ?
        """, (agent_id,))
        row = cursor.fetchone()

    if row:
        config = {
            'id': row['id'],
            'name': row['name'],
            # ...
        }
```

**After:**
```python
# Remove: import sqlite3
from database import get_readonly_session  # Use readonly for SELECT queries
from models import Agent

def get_agent_config(agent_id: int, use_cache=True) -> dict | None:
    """
    Fetch agent configuration with Redis caching.
    Now uses SQLAlchemy ORM instead of raw sqlite3.

    IMPORTANT: Returns dict, not model object (prevents DetachedInstanceError)
    """
    # Redis cache check (unchanged)
    if use_cache:
        cached_config = redis_service.get_agent_config(agent_id)
        if cached_config:
            logger.debug(f"Redis cache HIT: agent {agent_id}")
            return cached_config

    logger.debug(f"Redis cache MISS: agent {agent_id} - loading from DB")

    try:
        # Use get_readonly_session for SELECT queries (more efficient)
        with get_readonly_session() as session:
            agent = session.query(Agent).filter_by(id=agent_id).first()

            if agent:
                # Convert to dict INSIDE session (critical!)
                config = {
                    'id': agent.id,
                    'name': agent.name,
                    'prompt': agent.prompt,
                    'greeting': agent.greeting or 'Default greeting...',
                    'voice_id': agent.voice_id,
                    'voice_name': agent.voice_name,
                    'temperature': agent.temperature or 0.4,
                    'vad_mode': agent.vad_mode or 'dynamic'
                }

                # Cache in Redis
                redis_service.cache_agent_config(agent_id, config, ttl=3600)
                logger.info(f"Loaded agent config: {config['name']}")
                return config  # Return dict, not model object!
            else:
                logger.warning(f"Agent {agent_id} not found")
                return None

    except Exception as e:
        logger.error(f"Database error: {e}")
        return None
```

### Step 3: Update services/campaign_worker.py

**Before:**
```python
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance', 'voice_agent.db')

class CampaignWorker:
    def get_db_connection(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def get_running_campaigns(self):
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM campaign WHERE status = 'running'")
        campaigns = cursor.fetchall()
        conn.close()
        return campaigns
```

**After:**
```python
# Remove: import sqlite3, DB_PATH
from database import get_session
from models import Campaign, CampaignContact, Agent, User, Workflow

class CampaignWorker:
    # Remove get_db_connection method

    def get_running_campaigns(self):
        """Get all campaigns with 'running' status"""
        with get_session() as session:
            campaigns = session.query(Campaign).filter_by(status='running').all()
            # Convert to list of dicts if needed for compatibility
            return [
                {
                    'id': c.id,
                    'user_id': c.user_id,
                    'agent_id': c.agent_id,
                    'name': c.name,
                    'concurrent_calls': c.concurrent_calls,
                    'call_window_start': c.call_window_start,
                    'call_window_end': c.call_window_end,
                }
                for c in campaigns
            ]

    def get_pending_contacts(self, campaign_id: int, limit: int = 10):
        """Get pending contacts for a campaign"""
        with get_session() as session:
            contacts = session.query(CampaignContact).filter_by(
                campaign_id=campaign_id,
                status='pending'
            ).limit(limit).all()
            return contacts

    def update_contact_status(self, contact_id: int, status: str, **kwargs):
        """Update a contact's status"""
        with get_session() as session:
            contact = session.query(CampaignContact).get(contact_id)
            if contact:
                contact.status = status
                for key, value in kwargs.items():
                    if hasattr(contact, key):
                        setattr(contact, key, value)

    def mark_campaign_completed(self, campaign_id: int):
        """Mark a campaign as completed"""
        with get_session() as session:
            campaign = session.query(Campaign).get(campaign_id)
            if campaign:
                campaign.status = 'completed'
                campaign.end_time = datetime.now(SAUDI_TZ)

    def get_agent_config(self, agent_id: int):
        """Get agent configuration for calls"""
        with get_session() as session:
            agent = session.query(Agent).get(agent_id)
            if agent:
                return {
                    'id': agent.id,
                    'name': agent.name,
                    'prompt': agent.prompt,
                    'greeting': agent.greeting,
                    'voice_id': agent.voice_id,
                    'voice_name': agent.voice_name,
                }
        return None

    def get_user_trunk_id(self, user_id: int):
        """Get user's SIP trunk ID"""
        with get_session() as session:
            user = session.query(User).get(user_id)
            if user:
                return user.outbound_trunk_id
        return None
```

### Step 4: Update services/tool_service.py

**Before:**
```python
import sqlite3

class ToolService:
    def __init__(self):
        self.db_path = self._get_db_path()

    def _get_db_path(self):
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance', 'voice_agent.db')
        if not os.path.exists(db_path):
            db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'voice_agent.db')
        return db_path

    def get_agent_tools(self, agent_id: int):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.* FROM tool t
            JOIN agent_tool at ON t.id = at.tool_id
            WHERE at.agent_id = ? AND t.is_active = 1
        """, (agent_id,))
        tools = cursor.fetchall()
        conn.close()
        return tools
```

**After:**
```python
# Remove: import sqlite3
from database import get_session
from models import Tool, AgentTool

class ToolService:
    def __init__(self):
        # Remove db_path - not needed with ORM
        self._tool_cache = {}

    # Remove _get_db_path method

    def get_agent_tools(self, agent_id: int):
        """Get all active tools assigned to an agent"""
        with get_session() as session:
            tools = session.query(Tool).join(AgentTool).filter(
                AgentTool.agent_id == agent_id,
                Tool.is_active == True
            ).all()

            return [
                {
                    'id': tool.id,
                    'name': tool.name,
                    'description': tool.description,
                    'tool_type': tool.tool_type,
                    'config': tool.config,
                }
                for tool in tools
            ]

    def preload_all_agents(self):
        """Preload tools for all agents into cache"""
        with get_session() as session:
            # Get all unique agent IDs that have tools
            agent_ids = session.query(AgentTool.agent_id).distinct().all()

            for (agent_id,) in agent_ids:
                tools = self.get_agent_tools(agent_id)
                self._tool_cache[agent_id] = tools

        logger.info(f"Preloaded tools for {len(self._tool_cache)} agents")
```

---

## Usage Examples

### Basic Queries

```python
from database import get_session
from models import User, Agent, CallLog

# Get single record by ID
with get_session() as session:
    user = session.query(User).get(1)
    print(user.username)

# Get single record by filter
with get_session() as session:
    user = session.query(User).filter_by(email="test@example.com").first()

# Get all records
with get_session() as session:
    agents = session.query(Agent).filter_by(user_id=1).all()
    for agent in agents:
        print(agent.name)

# Get with ordering
with get_session() as session:
    logs = session.query(CallLog).order_by(CallLog.created_at.desc()).limit(10).all()

# Count records
with get_session() as session:
    count = session.query(Agent).filter_by(user_id=1).count()
```

### Creating Records

```python
from database import get_session
from models import Agent

with get_session() as session:
    agent = Agent(
        user_id=1,
        name="New Agent",
        prompt="You are a helpful assistant",
        greeting="Hello!",
        voice_id="abc123"
    )
    session.add(agent)
    # Commits automatically when exiting the context manager

# Get the ID after creation
with get_session() as session:
    agent = Agent(name="Test", user_id=1, prompt="Test")
    session.add(agent)
    session.flush()  # Generates the ID
    print(f"New agent ID: {agent.id}")
```

### Updating Records

```python
from database import get_session
from models import Agent

with get_session() as session:
    agent = session.query(Agent).get(1)
    if agent:
        agent.name = "Updated Name"
        agent.prompt = "New prompt"
        # Commits automatically
```

### Deleting Records

```python
from database import get_session
from models import Agent

with get_session() as session:
    agent = session.query(Agent).get(1)
    if agent:
        session.delete(agent)
        # Commits automatically
```

### Complex Queries

```python
from database import get_session
from models import Agent, CallLog, User
from sqlalchemy import func, and_, or_

# Join query
with get_session() as session:
    results = session.query(Agent, User).join(User).filter(
        User.is_active == True
    ).all()

# Aggregate functions
with get_session() as session:
    total_minutes = session.query(func.sum(CallLog.duration_seconds)).filter(
        CallLog.user_id == 1
    ).scalar()

# Complex filters
with get_session() as session:
    agents = session.query(Agent).filter(
        and_(
            Agent.user_id == 1,
            or_(
                Agent.call_type == 'inbound',
                Agent.call_type == 'outbound'
            )
        )
    ).all()
```

### Working with Relationships

```python
from database import get_session
from models import Campaign, CampaignContact

# Access related objects
with get_session() as session:
    campaign = session.query(Campaign).get(1)

    # Access agent through relationship
    print(f"Agent: {campaign.agent.name}")

    # Access user through relationship
    print(f"User: {campaign.user.username}")

    # Access contacts through relationship
    for contact in campaign.contacts:
        print(f"Contact: {contact.phone_number}")
```

---

---

## Schema Changes

### Do I Need to Edit database.py When Adding Columns?

**NO!** `database.py` and `models.py` have different purposes:

| File | Purpose | Edit When |
|------|---------|-----------|
| `models.py` | Defines table structure (columns, types) | Adding/removing columns or tables |
| `database.py` | Provides database connection | Almost never (only for connection settings) |

Think of it like:
- `models.py` = Blueprint of a house (rooms, doors, windows)
- `database.py` = The road to reach the house (address, directions)

**Changing the house layout doesn't change the road!**

### How to Add a New Column

```python
# 1. Edit models.py ONLY
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80))
    phone = db.Column(db.String(20))  # <-- ADD NEW COLUMN

# 2. Run migration (if using Flask-Migrate)
flask db migrate -m "Add phone to User"
flask db upgrade

# 3. database.py - NO CHANGES NEEDED!
```

### How to Add a New Table

```python
# 1. Edit models.py ONLY
class NewTable(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))

# 2. Run migration
flask db migrate -m "Add NewTable"
flask db upgrade

# 3. database.py - NO CHANGES NEEDED!
```

### Setting Up Flask-Migrate (Recommended)

```bash
pip install Flask-Migrate
```

Add to `app.py`:
```python
from flask_migrate import Migrate
migrate = Migrate(app, db)
```

Initialize once:
```bash
flask db init
```

From now on, any model change:
```bash
flask db migrate -m "Description"
flask db upgrade
```

---

## Switching to PostgreSQL (Alibaba Cloud)

### Overview

After SQLAlchemy ORM migration is complete, switching to PostgreSQL requires **NO CODE CHANGES** - just configuration!

```
+------------------+
|   Your Code      |  <-- Same code, no changes
+------------------+
         |
         v
+------------------+
|   SQLAlchemy     |  <-- Translates automatically
+------------------+
         |
    +----+----+
    |         |
    v         v
+-------+  +----------+
|SQLite |  |PostgreSQL|
+-------+  +----------+
   NOW       LATER
```

---

### Quick Checklist: What You Need to Do

| Step | Task | Files to Change | Time |
|------|------|-----------------|------|
| 1 | Install PostgreSQL driver | `requirements.txt` | 1 min |
| 2 | Create PostgreSQL database on Alibaba Cloud | Alibaba Console | 10 min |
| 3 | Update DATABASE_URL in .env | `.env` | 30 sec |
| 4 | Create tables | Run script | 1 min |
| 5 | Migrate data (optional) | Run script | 5 min |
| 6 | **Test & Deploy** | - | - |

**Total code changes: ZERO!** Only `.env` configuration changes.

---

### Step 1: Install PostgreSQL Driver

Add to `requirements.txt`:
```
psycopg2-binary==2.9.9
```

Then install:
```bash
pip install psycopg2-binary
```

---

### Step 2: Create PostgreSQL Database on Alibaba Cloud

#### Option A: Alibaba Cloud RDS for PostgreSQL (Recommended)
1. Go to Alibaba Cloud Console → RDS
2. Create PostgreSQL instance
3. Configure:
   - Region: Choose closest to your server
   - DB Engine: PostgreSQL 14+
   - Instance Type: Start with 1 Core / 2GB RAM
   - Storage: 20GB (expandable)
4. Create database and user:

```sql
-- Run in Alibaba Cloud DMS or psql
CREATE DATABASE nevoxai_db;
CREATE USER nevoxai_user WITH PASSWORD 'your_secure_password_here';
GRANT ALL PRIVILEGES ON DATABASE nevoxai_db TO nevoxai_user;

-- Also grant schema permissions
\c nevoxai_db
GRANT ALL ON SCHEMA public TO nevoxai_user;
```

#### Option B: Self-hosted PostgreSQL on ECS
```bash
# On your Alibaba ECS instance
sudo apt update
sudo apt install postgresql postgresql-contrib

sudo -u postgres psql
CREATE DATABASE nevoxai_db;
CREATE USER nevoxai_user WITH PASSWORD 'your_secure_password_here';
GRANT ALL PRIVILEGES ON DATABASE nevoxai_db TO nevoxai_user;
\q
```

---

### Step 3: Update .env File (THE ONLY FILE CHANGE!)

**Before (SQLite):**
```env
# DATABASE_URL=sqlite:///instance/voice_agent.db
# Or if not set, database.py uses this default
```

**After (PostgreSQL on Alibaba Cloud RDS):**
```env
DATABASE_URL=postgresql://nevoxai_user:your_password@rm-xxxxx.pg.rds.aliyuncs.com:5432/nevoxai_db
```

**After (Self-hosted PostgreSQL):**
```env
DATABASE_URL=postgresql://nevoxai_user:your_password@localhost:5432/nevoxai_db
```

**Format breakdown:**
```
postgresql://USERNAME:PASSWORD@HOST:PORT/DATABASE_NAME
```

---

### Step 4: Create Tables

**Option A: Using Flask-Migrate (if set up):**
```bash
flask db upgrade
```

**Option B: Using database.py directly:**
```python
# Run this once
from database import init_db
init_db()  # Creates all 11 tables from models.py
print("Tables created!")
```

**Option C: Quick script:**
```bash
# Create file: scripts/init_postgres.py
python -c "from database import init_db; init_db(); print('Done!')"
```

---

### Step 5: Migrate Existing Data (Optional)

If you have existing data in SQLite that you want to keep:

```python
# scripts/migrate_sqlite_to_postgres.py
"""
Migrate data from SQLite to PostgreSQL
Run AFTER setting DATABASE_URL to PostgreSQL
"""
import sqlite3
import os
from database import get_session
from models import User, Agent, Campaign, CampaignContact, CallLog, Tool, AgentTool, Workflow, InboundConfiguration, KnowledgeBase

# Path to your SQLite database
SQLITE_PATH = 'instance/voice_agent.db'

def migrate_table(sqlite_cursor, model_class, table_name):
    """Migrate a single table"""
    print(f"Migrating {table_name}...")

    sqlite_cursor.execute(f"SELECT * FROM {table_name}")
    rows = sqlite_cursor.fetchall()
    columns = [description[0] for description in sqlite_cursor.description]

    with get_session() as session:
        for row in rows:
            data = dict(zip(columns, row))
            obj = model_class(**data)
            session.merge(obj)  # merge handles existing IDs

    print(f"  ✅ Migrated {len(rows)} rows from {table_name}")

def main():
    if not os.path.exists(SQLITE_PATH):
        print(f"❌ SQLite database not found at {SQLITE_PATH}")
        return

    # Connect to SQLite
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row
    cursor = sqlite_conn.cursor()

    # Migrate in order (respect foreign keys)
    migrations = [
        (User, 'user'),
        (Agent, 'agent'),
        (Campaign, 'campaign'),
        (CampaignContact, 'campaign_contact'),
        (CallLog, 'call_log'),
        (Tool, 'tool'),
        (AgentTool, 'agent_tool'),
        (Workflow, 'workflow'),
        (InboundConfiguration, 'inbound_configuration'),
        (KnowledgeBase, 'knowledge_base'),
    ]

    for model_class, table_name in migrations:
        try:
            migrate_table(cursor, model_class, table_name)
        except Exception as e:
            print(f"  ⚠️ Error migrating {table_name}: {e}")

    sqlite_conn.close()
    print("\n✅ Migration complete!")

if __name__ == "__main__":
    main()
```

Run migration:
```bash
python scripts/migrate_sqlite_to_postgres.py
```

---

### Step 6: Verify Everything Works

```python
# scripts/test_postgres_connection.py
from database import check_connection, get_readonly_session
from models import User, Agent

print("Testing PostgreSQL connection...")

if check_connection():
    print("✅ Database connection successful!")

    with get_readonly_session() as session:
        user_count = session.query(User).count()
        agent_count = session.query(Agent).count()
        print(f"   Users: {user_count}")
        print(f"   Agents: {agent_count}")
else:
    print("❌ Database connection failed!")
```

---

### What Changes for PostgreSQL?

| Component | Changes Needed? | Details |
|-----------|-----------------|---------|
| `models.py` | **NO** | Same models work with both databases |
| `database.py` | **NO** | Auto-detects PostgreSQL from URL |
| `routes/*.py` | **NO** | Flask-SQLAlchemy unchanged |
| `agent scripts` | **NO** | All use SQLAlchemy ORM now |
| `.env` | **YES** | Only change DATABASE_URL |
| `requirements.txt` | **YES** | Add psycopg2-binary |

---

### PostgreSQL-Specific Configuration (Already in database.py)

The `database.py` module automatically applies PostgreSQL-optimized settings:

```python
# From database.py - already configured!
if IS_POSTGRES:
    engine = create_engine(
        DATABASE_URL,
        poolclass=QueuePool,
        pool_size=10,         # Base connections for voice calls
        max_overflow=40,      # Handle concurrent call spikes
        pool_timeout=10,      # Fail fast for voice (don't block)
        pool_recycle=1800,    # Recycle every 30 min
        pool_pre_ping=True,   # Verify connection health
    )
```

---

### Alibaba Cloud RDS Tips

1. **Whitelist your server IP** in RDS security settings
2. **Enable SSL** for production (add `?sslmode=require` to URL)
3. **Set up automated backups** in RDS console
4. **Monitor connection pool** - increase if you see timeouts

**SSL Connection Example:**
```env
DATABASE_URL=postgresql://user:pass@host:5432/db?sslmode=require
```

---

### Rollback Plan

If something goes wrong, switch back to SQLite instantly:

```env
# Just change back to SQLite
DATABASE_URL=sqlite:///instance/voice_agent.db
```

Restart your services and you're back on SQLite!

---

### Troubleshooting PostgreSQL

#### "Connection refused"
- Check Alibaba Cloud security groups
- Verify IP is whitelisted in RDS
- Confirm port 5432 is open

#### "Authentication failed"
- Double-check username/password in .env
- Verify user has permissions on database

#### "Database does not exist"
```sql
CREATE DATABASE nevoxai_db;
```

#### "Permission denied for schema public"
```sql
GRANT ALL ON SCHEMA public TO nevoxai_user;
```

---

---

## Troubleshooting

### "database is locked" (SQLite)

This happens with concurrent access. The `database.py` module uses `StaticPool` to prevent this. If you still see it:

1. Ensure all code uses `database.py`, not direct `sqlite3.connect()`
2. Use context managers (`with get_session()`) to ensure connections close
3. Consider switching to PostgreSQL for production

### DetachedInstanceError

This happens when accessing model attributes after the session closes:

```python
# Wrong
with get_session() as session:
    agent = session.query(Agent).get(1)
print(agent.name)  # Error! Session closed

# Correct - option 1: access inside session
with get_session() as session:
    agent = session.query(Agent).get(1)
    name = agent.name
print(name)  # Works

# Correct - option 2: convert to dict
with get_session() as session:
    agent = session.query(Agent).get(1)
    agent_dict = {
        'id': agent.id,
        'name': agent.name
    }
print(agent_dict['name'])  # Works
```

### Connection Pool Exhausted (PostgreSQL)

If you see "QueuePool limit reached":

1. Ensure all sessions are properly closed (use context managers)
2. Increase pool size in `database.py`:
   ```python
   'pool_size': 30,      # Increase from 20
   'max_overflow': 50,   # Increase from 30
   ```

### Models Not Found

If `from models import Agent` fails:

1. Ensure `models.py` is in the same directory as `database.py`
2. Or update the import path:
   ```python
   import sys
   sys.path.insert(0, '/path/to/nevoxai-project')
   from models import Agent
   ```

---

## Summary

| Before | After |
|--------|-------|
| `import sqlite3` | `from database import get_session` |
| `sqlite3.connect(path)` | `with get_session() as session:` |
| `cursor.execute("SELECT ... WHERE id = ?", (id,))` | `session.query(Model).get(id)` |
| `cursor.fetchone()` | `.first()` |
| `cursor.fetchall()` | `.all()` |
| `row['column']` | `model.column` |
| `conn.close()` | Automatic with context manager |

This approach gives you:
- **Database agnostic code** - Works with SQLite and PostgreSQL
- **Type safety** - IDE autocomplete for model attributes
- **Connection pooling** - Better concurrent access handling
- **Cleaner code** - No raw SQL strings
- **Easy migration** - Just change `DATABASE_URL` to switch databases

---

## FAQ

### Q: Do I need to modify models.py?
**A: NO.** Your models.py is already complete with all 11 tables. Just reuse them.

### Q: Do I need to change database.py when adding columns?
**A: NO.** database.py is for connections. models.py is for schema.

### Q: Will Flask routes change?
**A: NO.** Routes keep using `db.session`. Only agent scripts change.

### Q: What does database.py replace?
**A: Only `sqlite3`.** It doesn't replace `db.session` in Flask routes.

### Q: How do I switch to PostgreSQL later?
**A: Change ONE line in .env** - the DATABASE_URL. No code changes!

### Q: Why not use db.session in agent scripts?
**A: No Flask context.** Agent scripts run outside Flask, so they can't use `db.session`.

---

## Files to Modify Summary

| File | Action | Priority |
|------|--------|----------|
| `database.py` | Create NEW | 1 |
| `agent_api_flow_transcriptions.py` | Update imports & get_agent_config() | 2 |
| `services/campaign_worker.py` | Update all DB methods | 3 |
| `services/tool_service.py` | Update get_agent_tools() | 4 |

---

## Quick Reference Card

```python
# 1. Import
from database import get_session
from models import Agent, User, Campaign

# 2. Read
with get_session() as session:
    agent = session.query(Agent).get(id)           # By ID
    agent = session.query(Agent).filter_by(name="X").first()  # By filter

# 3. Create
with get_session() as session:
    agent = Agent(name="New", user_id=1, prompt="...")
    session.add(agent)

# 4. Update
with get_session() as session:
    agent = session.query(Agent).get(id)
    agent.name = "Updated"

# 5. Delete
with get_session() as session:
    agent = session.query(Agent).get(id)
    session.delete(agent)

# 6. List with filter
with get_session() as session:
    agents = session.query(Agent).filter_by(user_id=1).all()

# 7. Count
with get_session() as session:
    count = session.query(Agent).filter_by(user_id=1).count()
```

---

## Assessment Summary

| Aspect | Rating | Notes |
|--------|--------|-------|
| Architecture | Excellent | Clean separation of concerns |
| SQLite handling | Excellent | StaticPool + WAL + foreign keys |
| PostgreSQL readiness | Good | Pool settings tuned for voice latency |
| Error handling | Good | Auto rollback, proper logging |
| Migration complexity | Low | 4 files to update, models unchanged |

**Overall: 8/10 - Solid plan. Execute it.**
