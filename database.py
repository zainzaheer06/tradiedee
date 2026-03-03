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

    Usage:
        with get_readonly_session() as session:
            agent = session.query(Agent).filter_by(id=1).first()
            if agent:
                return {'id': agent.id, 'name': agent.name}
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
