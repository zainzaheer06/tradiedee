# Database Performance Optimization Guide

## Your System Profile

**Application Type:** Voice Agent Platform (NevoxAI)
- Real-time voice calls (latency-sensitive)
- Campaign management (burst traffic)
- Call logs (read-heavy, large dataset)
- Multi-worker deployment

**Current Stats:**
- 26 users
- 111 agents
- 1,743 call logs (and growing!)
- 75 campaigns

---

## Current database.py Analysis

### ✅ Strengths

1. **Good Connection Pooling**
   ```python
   pool_size=10, max_overflow=40  # Handles bursts well
   pool_timeout=10                # Fail fast for voice
   pool_recycle=1800              # Prevents stale connections
   pool_pre_ping=True             # Detects dead connections
   ```

2. **Separate Read/Write Sessions**
   - `get_session()` for writes
   - `get_readonly_session()` for reads (no commit overhead)

3. **Voice-Optimized**
   - Low timeout prevents hanging calls
   - Pre-ping prevents mid-call failures

### ⚠️ Limitations

1. **Per-Process Pooling**
   - 4 workers × 50 max connections = 200 total
   - PostgreSQL default limit: ~100-200
   - Will hit connection limit under load

2. **No Monitoring**
   - Can't see slow queries
   - No performance metrics
   - Hard to debug bottlenecks

3. **No Database Indexes**
   - Large table scans on call_log (1,743+ rows)
   - Campaign queries likely slow
   - User/agent lookups could be faster

4. **Single Database**
   - All queries hit primary
   - No read replicas for scaling

---

## Phase 1: Immediate Optimizations (Do Now!)

### 1. Add Database Indexes

**Why:** Indexes speed up queries 10-100x
**Impact:** High
**Effort:** Low (5 minutes)

Create this file: `scripts/db/create_indexes.sql`

```sql
-- User lookups (login, auth)
CREATE INDEX IF NOT EXISTS idx_user_email ON "user"(email);
CREATE INDEX IF NOT EXISTS idx_user_username ON "user"(username);

-- Agent queries (most common)
CREATE INDEX IF NOT EXISTS idx_agent_user_id ON agent(user_id);
CREATE INDEX IF NOT EXISTS idx_agent_created_at ON agent(created_at);

-- Call logs (CRITICAL - largest table, frequent queries)
CREATE INDEX IF NOT EXISTS idx_call_log_user_id ON call_log(user_id);
CREATE INDEX IF NOT EXISTS idx_call_log_agent_id ON call_log(agent_id);
CREATE INDEX IF NOT EXISTS idx_call_log_created_at ON call_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_call_log_status ON call_log(status);
CREATE INDEX IF NOT EXISTS idx_call_log_call_type ON call_log(call_type);

-- Composite index for common dashboard query
CREATE INDEX IF NOT EXISTS idx_call_log_user_created ON call_log(user_id, created_at DESC);

-- Campaign queries
CREATE INDEX IF NOT EXISTS idx_campaign_user_id ON campaign(user_id);
CREATE INDEX IF NOT EXISTS idx_campaign_status ON campaign(status);
CREATE INDEX IF NOT EXISTS idx_campaign_created_at ON campaign(created_at DESC);

-- Campaign contacts (filtered by campaign and status)
CREATE INDEX IF NOT EXISTS idx_campaign_contact_campaign_id ON campaign_contact(campaign_id);
CREATE INDEX IF NOT EXISTS idx_campaign_contact_status ON campaign_contact(status);
CREATE INDEX IF NOT EXISTS idx_campaign_contact_phone ON campaign_contact(phone_number);

-- Workflows
CREATE INDEX IF NOT EXISTS idx_workflow_user_id ON workflow(user_id);
CREATE INDEX IF NOT EXISTS idx_workflow_is_active ON workflow(is_active);

-- Tools
CREATE INDEX IF NOT EXISTS idx_tool_user_id ON tool(user_id);
CREATE INDEX IF NOT EXISTS idx_tool_is_active ON tool(is_active);

-- Knowledge base
CREATE INDEX IF NOT EXISTS idx_knowledge_base_agent_id ON knowledge_base(agent_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_base_status ON knowledge_base(status);

-- Webhook logs (for debugging/monitoring)
CREATE INDEX IF NOT EXISTS idx_webhook_log_workflow_id ON webhook_log(workflow_id);
CREATE INDEX IF NOT EXISTS idx_webhook_log_call_log_id ON webhook_log(call_log_id);
CREATE INDEX IF NOT EXISTS idx_webhook_log_created_at ON webhook_log(created_at DESC);
```

**Run it:**
```bash
# On your server
psql $DATABASE_URL -f scripts/db/create_indexes.sql

# Or using Python
python scripts/db/create_indexes.py
```

**Expected Impact:**
- Call log queries: 10-100x faster
- Dashboard load time: 2-5x faster
- Campaign listing: 5-10x faster

---

### 2. Enable Query Logging

Add to `database.py`:

```python
# After load_dotenv()
import logging

# Log slow queries (>100ms)
logging.basicConfig()
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

# Optional: Log ALL queries (debugging only!)
# engine = create_engine(DATABASE_URL, echo=True)
```

**View logs:**
```bash
# Check slow queries
grep "slow query" /var/log/your-app.log
```

---

### 3. Optimize Connection Pool Settings

**Current settings are good for:**
- 1-2 workers
- Low-medium traffic
- Single server

**For production (4+ workers), update database.py:**

```python
# Reduce per-process connections
pool_size=5              # Lower base (was 10)
max_overflow=15          # Lower overflow (was 40)
pool_timeout=5           # Even faster fail (was 10)
pool_recycle=1800        # Keep
pool_pre_ping=True       # Keep
```

**Why lower?**
- 4 workers × 20 max = 80 total (safer)
- Still handles bursts
- Prevents "too many connections"

---

### 4. Add Query Timeouts

Prevent long-running queries from hanging:

```python
# In database.py, add to engine config:
connect_args={
    'connect_timeout': 10,
    'options': '-c statement_timeout=30000'  # 30 second timeout
}
```

---

## Phase 2: Scaling for High Traffic

### When You Need This:
- 500+ concurrent users
- Multiple app servers
- 1000+ requests/min
- Running campaigns with 1000s of contacts

### 1. Add PgBouncer (Connection Pooler)

**What:** Centralized connection pool
**When:** Multiple servers or >10 workers
**Impact:** 5-10x more efficient connection usage

**Without PgBouncer:**
```
4 servers × 4 workers × 20 conns = 320 DB connections ❌
```

**With PgBouncer:**
```
4 servers × 4 workers → PgBouncer → 50 DB connections ✅
```

**Installation:**
```bash
sudo apt install pgbouncer
```

Config `/etc/pgbouncer/pgbouncer.ini`:
```ini
[databases]
nevox_prod = host=your-db-host port=5432 dbname=nevox_prod

[pgbouncer]
listen_addr = 127.0.0.1
listen_port = 6432
pool_mode = transaction
default_pool_size = 20
max_client_conn = 1000
```

Update `.env`:
```env
# Point to PgBouncer instead of PostgreSQL
DATABASE_URL=postgresql://nevox_prod:password@localhost:6432/nevox_prod
```

**Benefit:** Handle 1000s of workers with only 20-50 real DB connections

---

### 2. Add Read Replicas

**What:** Separate database for read queries
**When:** Read-heavy workload (dashboard, reports, analytics)
**Impact:** 2-3x more read capacity

**On Alibaba Cloud RDS:**
1. Create read replica in RDS console
2. Get replica endpoint
3. Update your app:

```python
# database.py
READ_REPLICA_URL = os.environ.get('READ_REPLICA_URL')

# Create separate engine for reads
if READ_REPLICA_URL:
    read_engine = create_engine(READ_REPLICA_URL, ...)

@contextmanager
def get_readonly_session():
    # Use read replica if available
    eng = read_engine if READ_REPLICA_URL else engine
    session = sessionmaker(bind=eng)()
    try:
        yield session
    finally:
        session.close()
```

**Use for:**
- Dashboard queries
- Call log listings
- Analytics/reports
- Campaign status checks

**Don't use for:**
- Agent creation (write)
- Call initiation (write)
- Real-time data (replica lag ~100ms)

---

### 3. Add Redis Caching

**What:** In-memory cache for frequent queries
**When:** Same queries run repeatedly
**Impact:** 10-100x faster for cached data

**Install:**
```bash
pip install redis
```

**Example:**
```python
import redis
import json

redis_client = redis.Redis(host='localhost', port=6379, db=0)

def get_agent(agent_id):
    # Check cache first
    cached = redis_client.get(f"agent:{agent_id}")
    if cached:
        return json.loads(cached)

    # Query database
    with get_readonly_session() as session:
        agent = session.query(Agent).get(agent_id)
        if agent:
            data = {'id': agent.id, 'name': agent.name, ...}
            # Cache for 5 minutes
            redis_client.setex(f"agent:{agent_id}", 300, json.dumps(data))
            return data
```

**Cache:**
- Agent configurations (rarely change)
- User profiles
- Workflow definitions
- NOT: Call logs, real-time data

---

## Phase 3: Advanced Optimizations

### 1. Partition Large Tables

**When:** call_log table > 100,000 rows

**Example (monthly partitions):**
```sql
CREATE TABLE call_log_2025_01 PARTITION OF call_log
FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');

CREATE TABLE call_log_2025_02 PARTITION OF call_log
FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');
```

**Benefit:** Queries only scan relevant partition

---

### 2. Add Monitoring

**Install pg_stat_statements:**
```sql
CREATE EXTENSION pg_stat_statements;
```

**Find slow queries:**
```sql
SELECT
    query,
    calls,
    mean_exec_time,
    max_exec_time
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;
```

---

### 3. Optimize Queries

**Bad (N+1 queries):**
```python
# Fetches agents, then queries for each user
agents = session.query(Agent).all()
for agent in agents:
    user = session.query(User).get(agent.user_id)  # ❌ Extra query!
```

**Good (JOIN):**
```python
# Single query with join
agents = session.query(Agent).join(User).all()
```

---

## Performance Targets

### Current State (SQLite)
- Dashboard load: 2-5 seconds
- Call initiation: 500-1000ms
- Campaign query: 1-3 seconds

### After Phase 1 (Indexes + Tuning)
- Dashboard load: 500ms-1s ✅
- Call initiation: 100-200ms ✅
- Campaign query: 200-500ms ✅

### After Phase 2 (PgBouncer + Replicas)
- Dashboard load: 200-500ms ✅✅
- Call initiation: 50-100ms ✅✅
- Campaign query: 100-200ms ✅✅
- Can handle 1000+ concurrent users ✅✅

---

## Monitoring Checklist

Monitor these metrics:

1. **Connection Pool**
   ```python
   print(f"Pool size: {engine.pool.size()}")
   print(f"Checked out: {engine.pool.checkedout()}")
   ```

2. **Query Performance**
   - Log queries >100ms
   - Track P95/P99 latency

3. **Database Load**
   ```sql
   -- Active connections
   SELECT count(*) FROM pg_stat_activity;

   -- Long-running queries
   SELECT pid, now() - query_start as duration, query
   FROM pg_stat_activity
   WHERE state = 'active' AND now() - query_start > interval '5 seconds';
   ```

4. **Table Sizes**
   ```sql
   SELECT
       schemaname,
       tablename,
       pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
   FROM pg_tables
   WHERE schemaname = 'public'
   ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
   ```

---

## Summary: What to Do When

### Now (< 1 hour):
1. ✅ Add indexes (biggest impact!)
2. ✅ Enable query logging
3. ✅ Adjust pool settings if needed

### Later (when traffic grows):
1. Add PgBouncer (>10 workers)
2. Add read replica (read-heavy workload)
3. Add Redis caching (repeated queries)

### Much Later (scale problems):
1. Partition large tables
2. Advanced monitoring
3. Query optimization

---

## Key Takeaway

Your current `database.py` is **already well-configured** for:
- ✅ Single server
- ✅ Low-medium traffic
- ✅ Voice call latency requirements

**Next steps:**
1. Add indexes (do this today!)
2. Monitor query performance
3. Add PgBouncer when you scale to multiple servers

**You don't need PgBouncer yet if:**
- Single server
- <10 workers
- Current setup works fine

**You DO need PgBouncer when:**
- Multiple servers
- >10 workers total
- "Too many connections" errors
