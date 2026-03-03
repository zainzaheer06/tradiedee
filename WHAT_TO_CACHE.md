# What to Cache in Redis - Priority Guide

## ✅ HIGH PRIORITY - Already Implemented

### 1. Metrics (Solves Multiprocess Issue!)
**Why:** Worker processes can't share memory. Redis provides shared storage.

**What gets cached:**
- Call counts
- Costs (total, LLM, TTS, savings)
- Token usage
- Call duration
- Active calls gauge
- Error counts

**How long:** 30 days (auto-expires)

**Code:** Already in `redis_metrics.py`

---

## 🎯 RECOMMENDED - Add These

### 2. Agent Configurations
**Why:** Avoid database queries on every call (100+ ms saved per call)

**What to cache:**
```python
{
    'id': 51,
    'name': 'NHC Agent',
    'prompt': '...',  # Full prompt
    'greeting': 'السلام عليكم',
    'voice_id': 'KjDucWgG5NYuMBznv52L',
    'voice_name': 'Hiba'
}
```

**How long:** 1 hour (3600 seconds)

**Where:** Your Flask backend before creating call

**Example:**
```python
# In your Flask app (when creating call)
from services.redis_service import redis_service

agent = Agent.query.get(agent_id)
redis_service.cache_agent_config(
    agent_id=agent.id,
    config={
        'id': agent.id,
        'name': agent.name,
        'prompt': agent.prompt,
        'greeting': agent.greeting,
        'voice_id': agent.voice_id,
        'voice_name': agent.voice_name
    },
    ttl=3600
)
```

**Invalidate when:** Agent is updated in database

---

### 3. Tool Definitions
**Why:** Tools are pre-loaded but this makes them instant

**What to cache:**
```python
[
    {
        'name': 'get_property_info',
        'description': 'Get property details',
        'parameters': {...}
    },
    {
        'name': 'book_appointment',
        'description': 'Book viewing appointment',
        'parameters': {...}
    }
]
```

**How long:** 1 hour

**Where:** `tool_service.py`

**Example:**
```python
# In tool_service.py
def get_tools_for_agent(agent_id):
    # Try cache first
    tools = redis_service.get_tools(agent_id)

    if tools is None:
        # Load from database
        tools = load_tools_from_db(agent_id)
        # Cache them
        redis_service.cache_tools(agent_id, tools, ttl=3600)

    return tools
```

---

## 💡 OPTIONAL - Advanced Caching

### 4. Knowledge Base Context
**Why:** RAG queries take 100-500ms. Cache frequent queries.

**What to cache:**
```python
# Key: f"kb:{agent_id}:{query_hash}"
# Value: Retrieved context text
```

**How long:** 10 minutes (600 seconds)

**Example:**
```python
import hashlib

def get_kb_context(agent_id, query):
    # Hash the query
    query_hash = hashlib.md5(query.encode()).hexdigest()
    cache_key = f"kb:{agent_id}:{query_hash}"

    # Try cache
    cached = redis_service.client.get(cache_key)
    if cached:
        return json.loads(cached)

    # Retrieve from vector DB
    context = kb_service.retrieve_context(agent_id, query)

    # Cache it
    redis_service.client.setex(cache_key, 600, json.dumps(context))

    return context
```

---

### 5. API Rate Limiting
**Why:** Track API calls per agent to prevent abuse

**What to cache:**
```python
# Key: f"ratelimit:{agent_id}:{date}"
# Value: number of calls
```

**How long:** 24 hours

**Example:**
```python
def check_rate_limit(agent_id, max_calls=1000):
    today = datetime.now().strftime('%Y-%m-%d')
    key = f"ratelimit:{agent_id}:{today}"

    current = redis_service.client.get(key) or 0

    if int(current) >= max_calls:
        raise Exception(f"Rate limit exceeded: {current}/{max_calls}")

    redis_service.client.incr(key)
    redis_service.client.expire(key, 86400)  # 24 hours
```

---

### 6. Session State (For Stateful Conversations)
**Why:** Track conversation state across multiple turns

**What to cache:**
```python
{
    'room_name': 'call-51-123456',
    'user_name': 'محمد',
    'context': {
        'looking_for': 'villa',
        'budget': '1M SAR',
        'location': 'Riyadh'
    },
    'last_intent': 'property_search'
}
```

**How long:** 2 hours (call duration + buffer)

**Example:**
```python
# During call
session_data = {
    'user_name': extracted_name,
    'preferences': {
        'property_type': 'villa',
        'budget': '1M'
    }
}

redis_service.set_session_data(room_name, session_data, ttl=7200)

# Later in conversation
session = redis_service.get_session_data(room_name)
if session:
    user_name = session.get('user_name')
    # Personalize response
```

---

### 7. Frequent Responses (Template Caching)
**Why:** Common responses can be pre-generated

**What to cache:**
```python
# Common greetings, FAQs, standard responses
{
    'greeting_ar': 'السلام عليكم ورحمة الله وبركاته',
    'goodbye_ar': 'شكراً جزيلاً على وقتك. مع السلامة',
    'hold_on': 'لحظة من فضلك...',
    'error_message': 'عذراً، حدث خطأ. هل يمكنك إعادة السؤال؟'
}
```

**How long:** 24 hours

---

## ❌ DON'T CACHE

### 1. Live Call Audio
- Too large
- Streaming data
- Use S3/storage instead

### 2. Real-time Transcriptions
- Changes constantly
- Store in database after call ends

### 3. API Keys / Secrets
- Security risk
- Use environment variables or secret manager

### 4. Large Prompts (> 100KB)
- Redis is for hot data
- Keep in database

---

## Cache TTL Guidelines

| Data Type | TTL | Reason |
|-----------|-----|--------|
| Metrics | 30 days | Historical analysis |
| Agent Config | 1 hour | Moderate update frequency |
| Tools | 1 hour | Rarely change |
| KB Context | 10 minutes | Queries vary |
| Session Data | 2 hours | Call duration |
| Rate Limits | 24 hours | Daily reset |
| Templates | 24 hours | Static content |

---

## Memory Management

### Estimate Redis Usage

**Per agent:**
- Config: ~5 KB
- Tools: ~2 KB
- Daily metrics: ~10 KB

**For 50 agents:**
- Configs: 250 KB
- Tools: 100 KB
- Metrics (30 days): 15 MB

**Total: ~16 MB** (Very small!)

### Monitor Memory
```powershell
docker exec -it redis redis-cli INFO memory
```

---

## Implementation Priority

### Phase 1: Metrics (✅ Done!)
- Implement Redis metrics
- Start metrics server
- Configure Prometheus

### Phase 2: Agent Configs (Recommended Next!)
```python
# In your Flask create_call endpoint:
redis_service.cache_agent_config(agent_id, agent_config)

# In agent-after-promotheus.py:
config = redis_service.get_agent_config(agent_id)
if not config:
    config = get_from_database(agent_id)
    redis_service.cache_agent_config(agent_id, config)
```

### Phase 3: Tools (Optional)
```python
# Cache tools on first load
tools = redis_service.get_tools(agent_id)
if not tools:
    tools = tool_service.load_from_db(agent_id)
    redis_service.cache_tools(agent_id, tools)
```

### Phase 4: Advanced (If Needed)
- KB context caching
- Session state
- Rate limiting

---

## Quick Start

1. **Start Redis:**
   ```powershell
   docker run -d -p 6379:6379 redis
   ```

2. **Update agent imports:**
   ```python
   from services.redis_metrics import track_call_metrics
   ```

3. **Start metrics server:**
   ```powershell
   python redis_metrics_server.py
   ```

4. **Make a call and check:**
   ```powershell
   curl http://localhost:8009/metrics
   ```

Done! 🎉
