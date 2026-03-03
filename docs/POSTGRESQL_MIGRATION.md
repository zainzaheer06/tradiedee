# SQLite to PostgreSQL Migration Plan

## Overview
Migrate NevoxAI voice agent platform from SQLite to PostgreSQL to resolve database locking issues during concurrent voice calls.

## Key Challenge
The codebase has **two database access patterns**:
1. **Flask-SQLAlchemy ORM** - Flask app, routes
2. **Raw sqlite3** - Agent scripts running outside Flask context

**Solution**: Create unified `database.py` module with connection pooling for both patterns.

---

## Files to Modify

| File | Changes |
|------|---------|
| `database.py` | **NEW** - Shared module with connection pooling |
| `.env` | Add `DATABASE_URL` for PostgreSQL |
| `app.py:37` | Update SQLALCHEMY_DATABASE_URI |
| `agent_api_flow_transcriptions.py:7,122-138` | Replace sqlite3 with database.py |
| `services/campaign_worker.py:14,33,47-51` | Replace sqlite3 with database.py |
| `services/tool_service.py:14,29-40,59,111` | Replace sqlite3 with database.py |

---

## Implementation Steps

### Step 1: Create `database.py` (NEW FILE)
Shared module providing:
- `get_db_connection()` - Context manager for raw SQL (replaces sqlite3.connect)
- `get_session()` - Context manager for ORM access
- Connection pooling (20 base + 30 overflow = 50 max connections)
- `RealDictCursor` for dict-like row access (replaces sqlite3.Row)

### Step 2: Update `.env`
```env
DATABASE_URL=postgresql://user:password@localhost:5432/nevoxai_db
```

### Step 3: Update `app.py`
- Line 37: Change `sqlite:///voice_agent.db` to `os.environ.get('DATABASE_URL')`
- Add engine pool options for concurrent connections

### Step 4: Update `agent_api_flow_transcriptions.py`
- Remove `import sqlite3`
- Add `from database import get_db_connection`
- Replace `sqlite3.connect()` with `get_db_connection()` context manager
- Change SQL placeholders: `?` → `%s`

### Step 5: Update `services/campaign_worker.py`
- Remove `import sqlite3` and `DB_PATH`
- Add `from database import get_db_connection`
- Update `get_db_connection()` method to use shared module
- Change SQL placeholders: `?` → `%s`

### Step 6: Update `services/tool_service.py`
- Remove `import sqlite3` and `_get_db_path()`
- Add `from database import get_db_connection`
- Change SQL placeholders: `?` → `%s`

### Step 7: Data Migration
- Create PostgreSQL schema (Flask-SQLAlchemy can auto-create via `db.create_all()`)
- Run data migration script to copy SQLite data to PostgreSQL
- Reset SERIAL sequences

---

## SQL Syntax Changes

| SQLite | PostgreSQL |
|--------|------------|
| `?` placeholder | `%s` placeholder |
| `sqlite3.Row` | `psycopg2.extras.RealDictCursor` |
| `PRAGMA table_info(t)` | `SELECT * FROM information_schema.columns WHERE table_name='t'` |
| `INTEGER PRIMARY KEY AUTOINCREMENT` | `SERIAL PRIMARY KEY` |

---

## Connection Pooling Strategy

```python
# For 50 max concurrent voice calls:
pool_size=20        # Base connections
max_overflow=30     # Extra during peak
pool_timeout=30     # Wait time for connection
pool_pre_ping=True  # Validate before use
```

Redis caching remains unchanged - reduces DB hits by 95%.

---

## Verification Steps

1. **Test database connection**: `python -c "from database import get_db_connection; ..."`
2. **Test Flask app**: Start app, verify login/dashboard work
3. **Test agent**: Run `python agent_api_flow_transcriptions.py`, make test call
4. **Test campaign worker**: Run `python -m services.campaign_worker`
5. **Verify concurrent calls**: Multiple simultaneous calls without locking

---

## Dependencies to Install

```bash
pip install psycopg2-binary
```

---

## Rollback Plan

Keep SQLite database as backup. If issues arise:
1. Stop services
2. Revert `.env` to use SQLite URI
3. Revert code changes
4. Restart services
