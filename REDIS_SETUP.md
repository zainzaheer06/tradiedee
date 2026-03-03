# Redis Setup Guide - Multiprocess Metrics Solution

## Why Redis?

Your LiveKit agent uses **worker processes** to handle calls. Each worker has **separate memory**, so:
- ❌ Regular Prometheus metrics don't work (separate process memory)
- ✅ Redis provides **shared memory** across all processes
- ✅ All workers can write metrics to Redis
- ✅ Metrics server reads from Redis and exposes to Prometheus

---

## Step 1: Install Redis

### Option A: Docker (Easiest!)

```powershell
# Start Redis container
docker run -d `
  --name redis `
  -p 6379:6379 `
  redis:latest

# Verify it's running
docker ps | Select-String redis
```

### Option B: Windows Native

```powershell
# Using Chocolatey
choco install redis-64

# Or download from:
# https://github.com/microsoftarchive/redis/releases
```

### Option C: WSL

```powershell
# Install WSL
wsl --install

# In WSL terminal:
sudo apt-get update
sudo apt-get install redis-server
sudo service redis-server start
```

**Test Redis:**
```powershell
# Install Redis client
pip install redis

# Test connection
python -c "import redis; r=redis.Redis(); print(r.ping())"
# Should output: True
```

---

## Step 2: Update Your Agent

### Replace metrics imports

**In `agent-after-promotheus.py`:**

```python
# OLD (doesn't work with multiprocess)
from services.metrics_service import track_call_metrics, increment_active_calls, decrement_active_calls

# NEW (works with multiprocess!)
from services.redis_metrics import track_call_metrics, increment_active_calls, decrement_active_calls
```

That's it! Your metrics are now stored in Redis.

---

## Step 3: Start the Metrics Server

The metrics server reads from Redis and exposes to Prometheus:

```powershell
# In a NEW terminal window
cd C:\Users\mzain\Python-projects\Commercial\nevoxai_server\nevoxai-project

python redis_metrics_server.py
```

You should see:
```
🚀 Starting Redis Metrics Server on port 8009...
✅ Redis connected successfully
📊 Metrics endpoint: http://localhost:8009/metrics
```

**Keep this running!** Prometheus will scrape it every 15 seconds.

---

## Step 4: Update Prometheus Config

Update `prometheus.yml`:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  # Nevox metrics from Redis
  - job_name: 'nevox-redis-metrics'
    static_configs:
      - targets: ['host.docker.internal:8009']
        labels:
          service: 'voice-agent-metrics'

  # LiveKit system metrics
  - job_name: 'livekit-system'
    static_configs:
      - targets: ['host.docker.internal:8000']
        labels:
          service: 'livekit-worker'
```

**Restart Prometheus:**
```powershell
docker restart prometheus
```

---

## Step 5: Test It!

### 1. Start Redis (if not running)
```powershell
docker start redis
```

### 2. Start Metrics Server
```powershell
python redis_metrics_server.py
```

### 3. Start Your Agent
```powershell
python agent-after-promotheus.py console
```

### 4. Make a Test Call

Call your agent and have a conversation.

### 5. Check Metrics

**In browser:**
- Metrics: http://localhost:8009/metrics
- Health: http://localhost:8009/health

**You should see:**
```
nevox_calls_total{agent_id="51",period="today"} 1.0
nevox_cost_usd_total{agent_id="51",period="today"} 0.0027
nevox_tokens_total{agent_id="51",period="today",token_type="cached"} 22656.0
nevox_active_calls_current{agent_id="51"} 0.0
```

### 6. Check Prometheus

Go to: http://localhost:9090

Try query:
```promql
nevox_calls_total
```

You should see data!

---

## What Gets Cached in Redis

### 1. Metrics (Per Call)
- ✅ Total calls
- ✅ Costs (total, LLM, TTS, cache savings)
- ✅ Tokens (uncached, cached, completion)
- ✅ Call duration (histogram)
- ✅ Messages per call
- ✅ Active calls (real-time gauge)
- ✅ Errors by type
- ✅ Calls by hour

### 2. Agent Configurations (Optional)

Add to your Flask backend when creating calls:

```python
from services.redis_service import redis_service

# Cache agent config
redis_service.cache_agent_config(
    agent_id=51,
    config={
        'id': 51,
        'name': 'NHC Agent',
        'prompt': agent.prompt,
        'greeting': agent.greeting,
        'voice_id': agent.voice_id,
        'voice_name': agent.voice_name
    },
    ttl=3600  # 1 hour
)
```

Then in your agent:

```python
from services.redis_service import redis_service

# Try Redis cache first
agent_config = redis_service.get_agent_config(agent_id)

if not agent_config:
    # Fallback to database
    agent_config = get_agent_config_from_db(agent_id)
    # Cache it
    redis_service.cache_agent_config(agent_id, agent_config)
```

---

## Available Metrics

### Counters (Cumulative)
```promql
nevox_calls_total{agent_id="51", period="today"}
nevox_cost_usd_total{agent_id="51", period="today"}
nevox_tokens_total{agent_id="51", token_type="cached", period="today"}
```

### Gauges (Current Values)
```promql
nevox_active_calls_current{agent_id="51"}
nevox_cache_hit_rate_pct{agent_id="51", period="today"}
nevox_avg_call_duration_sec{agent_id="51", period="today"}
```

### Errors
```promql
nevox_errors_count{agent_id="51", error_type="llm", period="today"}
nevox_errors_count{agent_id="51", error_type="tts", period="today"}
```

---

## Grafana Queries

### Total Cost Today
```promql
sum(nevox_cost_usd_total{period="today"})
```

### Cost Per Agent
```promql
sum by (agent_id) (nevox_cost_usd_total{period="today"})
```

### Active Calls
```promql
sum(nevox_active_calls_current)
```

### Cache Hit Rate
```promql
nevox_cache_hit_rate_pct{period="today"}
```

### Average Call Duration
```promql
nevox_avg_call_duration_sec{period="today"}
```

### Error Rate
```promql
sum by (error_type) (nevox_errors_count{period="today"})
```

---

## Redis Management

### View Data
```powershell
# Connect to Redis CLI
docker exec -it redis redis-cli

# View all keys
KEYS *

# Get specific metric
GET metrics:2026-01-05:calls_total:agent:51

# View agent config
GET agent:config:51

# Get active calls
GET metrics:gauge:active_calls:agent:51
```

### Clear Data
```powershell
# Clear all metrics (keeps configs)
docker exec -it redis redis-cli
KEYS metrics:* | xargs redis-cli DEL

# Clear everything (⚠️ Warning!)
docker exec -it redis redis-cli FLUSHDB
```

### Monitor Redis
```powershell
# Watch commands in real-time
docker exec -it redis redis-cli MONITOR

# Get stats
docker exec -it redis redis-cli INFO
```

---

## Architecture

```
┌─────────────────┐
│  Worker 1       │───┐
│  (Call A)       │   │
└─────────────────┘   │
                      │
┌─────────────────┐   │    ┌──────────┐    ┌─────────────┐    ┌─────────────┐
│  Worker 2       │───┼───▶│  Redis   │───▶│ Metrics     │───▶│ Prometheus  │
│  (Call B)       │   │    │  :6379   │    │ Server      │    │  :9090      │
└─────────────────┘   │    └──────────┘    │  :8009      │    └─────────────┘
                      │                     └─────────────┘           │
┌─────────────────┐   │                                               │
│  Worker 3       │───┘                                               ▼
│  (Call C)       │                                            ┌─────────────┐
└─────────────────┘                                            │  Grafana    │
                                                               │  :3000      │
                                                               └─────────────┘
```

1. **Workers** write metrics to **Redis** (shared memory)
2. **Metrics Server** reads from Redis every 15s
3. **Prometheus** scrapes metrics server
4. **Grafana** visualizes from Prometheus

---

## Troubleshooting

### Redis not connecting
```powershell
# Check if Redis is running
docker ps | Select-String redis

# Start Redis
docker start redis

# Check logs
docker logs redis
```

### No metrics showing
```powershell
# Check metrics server is running
curl http://localhost:8009/health

# Check Redis has data
docker exec -it redis redis-cli
KEYS metrics:*

# Make a test call to generate metrics
```

### Metrics server error
```powershell
# Check Python dependencies
pip install redis flask prometheus_client

# Check logs
python redis_metrics_server.py
```

---

## Production Deployment

### 1. Run as Services

**Metrics Server (systemd on Linux):**
```ini
[Unit]
Description=Nevox Redis Metrics Server
After=redis.service

[Service]
WorkingDirectory=/path/to/nevoxai-project
ExecStart=/usr/bin/python3 redis_metrics_server.py
Restart=always

[Install]
WantedBy=multi-user.target
```

### 2. Redis Persistence

Update docker-compose.yml:
```yaml
services:
  redis:
    image: redis:latest
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    command: redis-server --appendonly yes

volumes:
  redis-data:
```

### 3. Monitoring

Add Redis monitoring to Grafana:
- Redis memory usage
- Connected clients
- Commands per second

---

## Summary

✅ **Redis solves the multiprocess problem!**

- Workers write to Redis (shared memory)
- Metrics server exposes to Prometheus
- Works seamlessly with your existing setup
- No code changes needed in agent logic

**Three services to run:**
1. Redis (port 6379)
2. Metrics Server (port 8009)
3. Your Agent (worker processes)

**Start all:**
```powershell
# Terminal 1: Redis
docker start redis

# Terminal 2: Metrics Server
python redis_metrics_server.py

# Terminal 3: Agent
python agent-after-promotheus.py console
```

That's it! 🎉
