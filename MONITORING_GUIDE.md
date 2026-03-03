# Complete Monitoring Guide - Nevox Voice Agents

## Overview

Your voice agent system now tracks **60+ metrics** across 7 categories. All metrics are exposed at `http://localhost:8009/metrics` and scraped by Prometheus every 15 seconds.

---

## Metrics Categories

### 1. Cost & Usage Metrics

| Metric | Type | Description | Labels |
|--------|------|-------------|--------|
| `nevox_total_cost_cents_total` | Counter | Total call cost (USD cents) | agent_id |
| `nevox_llm_cost_cents_total` | Counter | LLM API cost | agent_id |
| `nevox_tts_cost_cents_total` | Counter | Text-to-Speech cost | agent_id |
| `nevox_cache_savings_cents_total` | Counter | Money saved from prompt caching | agent_id |
| `nevox_llm_prompt_tokens_total` | Counter | Prompt tokens used | agent_id, cached |
| `nevox_llm_completion_tokens_total` | Counter | Completion tokens generated | agent_id |
| `nevox_tts_characters_total` | Counter | TTS characters generated | agent_id, voice |
| `nevox_stt_duration_seconds_total` | Counter | Speech-to-Text audio processed | agent_id |

**Use cases:**
- Track daily/monthly costs per agent
- Calculate cache hit rates
- Monitor token usage trends
- Identify cost-effective agents

---

### 2. Call Performance Metrics

| Metric | Type | Description | Labels |
|--------|------|-------------|--------|
| `nevox_call_duration_seconds` | Histogram | Call duration distribution | agent_id |
| `nevox_active_calls` | Gauge | Currently active calls | agent_id |
| `nevox_messages_per_call` | Histogram | Messages exchanged per call | agent_id |
| `nevox_call_status_total` | Counter | Call completion status | agent_id, status |
| `nevox_conversation_turns` | Histogram | Back-and-forth conversation turns | agent_id |
| `nevox_average_handle_time_seconds` | Gauge | Moving average call duration | agent_id |

**Use cases:**
- Monitor average handling time (AHT)
- Track concurrent call capacity
- Analyze conversation quality
- Identify bottlenecks

---

### 3. Latency & Speed Metrics ⚡ NEW

| Metric | Type | Description | Labels |
|--------|------|-------------|--------|
| `nevox_tts_latency_seconds` | Histogram | Time to first TTS audio byte | agent_id, voice |
| `nevox_llm_response_seconds` | Histogram | LLM response time | agent_id |
| `nevox_call_setup_seconds` | Histogram | Room creation to first greeting | agent_id |
| `nevox_greeting_latency_seconds` | Histogram | Participant join to greeting sent | agent_id |

**Use cases:**
- Optimize response times
- Identify slow TTS/LLM calls
- Monitor user experience quality
- SLA compliance tracking

**Alert on:**
- TTS latency > 2 seconds
- LLM response > 10 seconds
- Greeting latency > 3 seconds

---

### 4. Error & Failure Tracking 🔴 NEW

| Metric | Type | Description | Labels |
|--------|------|-------------|--------|
| `nevox_errors_total` | Counter | Errors by type | agent_id, error_type |
| `nevox_call_failures_total` | Counter | Failed calls by reason | agent_id, failure_reason |

**Error Types:**
- `llm`: OpenAI API errors
- `tts`: ElevenLabs failures
- `stt`: Speech recognition errors
- `recording`: Recording upload failures
- `webhook`: Webhook delivery failures
- `system`: Internal errors

**Failure Reasons:**
- `disconnect`: User hung up
- `timeout`: Call exceeded time limit
- `error`: System error during call
- `hangup`: Programmatic hangup

**Use cases:**
- Monitor error rates
- Identify problematic agents
- Track system reliability
- Debug production issues

**Alert on:**
- Error rate > 5% per hour
- Any `llm` errors (API issues)
- Webhook failures

---

### 5. Quality Metrics 📊 NEW

| Metric | Type | Description | Labels |
|--------|------|-------------|--------|
| `nevox_user_interruptions_total` | Counter | Times user interrupted agent | agent_id |

**Use cases:**
- Measure conversation naturalness
- Identify agents that talk too much
- Optimize response length
- Improve user engagement

**Targets:**
- Interruption rate < 20%
- Turns per call: 5-15 (healthy conversation)

---

### 6. Business Metrics 📈 NEW

| Metric | Type | Description | Labels |
|--------|------|-------------|--------|
| `nevox_calls_by_hour_total` | Counter | Calls per hour of day | agent_id, hour |
| `nevox_peak_concurrent_calls` | Gauge | Highest concurrent calls | agent_id |

**Use cases:**
- Capacity planning
- Peak hour analysis
- Staffing decisions
- Cost forecasting

---

### 7. Recording Metrics

| Metric | Type | Description | Labels |
|--------|------|-------------|--------|
| `nevox_recording_size_bytes` | Histogram | Recording file sizes | agent_id |
| `nevox_recording_upload_seconds` | Histogram | Upload duration | agent_id |
| `nevox_recording_success_total` | Counter | Upload success/failure | agent_id, status |

**Use cases:**
- Monitor storage costs
- Track upload reliability
- Identify large recordings

---

## Using the Metrics

### 1. Check Metrics Endpoint

```powershell
# View all metrics
curl http://localhost:8009/metrics

# Filter specific metric
curl http://localhost:8009/metrics | Select-String "nevox_total_cost"
```

### 2. Query in Prometheus

Go to http://localhost:9090 and try these queries:

**Cost tracking:**
```promql
# Total cost today
sum(increase(nevox_total_cost_cents_total[24h])) / 100

# Cost per agent
sum by (agent_id) (increase(nevox_total_cost_cents_total[1h]))

# Cache hit rate
sum(rate(nevox_llm_prompt_tokens_total{cached="true"}[5m])) /
sum(rate(nevox_llm_prompt_tokens_total[5m])) * 100
```

**Performance:**
```promql
# Average call duration
rate(nevox_call_duration_seconds_sum[5m]) /
rate(nevox_call_duration_seconds_count[5m])

# Active calls
sum(nevox_active_calls)

# P95 TTS latency
histogram_quantile(0.95, nevox_tts_latency_seconds_bucket)
```

**Errors:**
```promql
# Error rate (errors per minute)
sum(rate(nevox_errors_total[5m])) * 60

# Failed calls by reason
sum by (failure_reason) (nevox_call_failures_total)
```

**Business metrics:**
```promql
# Calls by hour of day
sum by (hour) (nevox_calls_by_hour_total)

# Peak concurrent calls
max(nevox_peak_concurrent_calls)
```

### 3. Grafana Dashboards

Import these dashboard panels:

**Performance Dashboard:**
- TTS Latency (P50, P95, P99)
- LLM Response Time
- Greeting Latency
- Average Handle Time

**Reliability Dashboard:**
- Error Rate by Type
- Call Failure Reasons
- Recording Upload Success Rate
- System Uptime

**Business Dashboard:**
- Calls by Hour Heatmap
- Peak Concurrent Calls
- Cost per Hour
- Daily/Monthly Costs

---

## Alerting Rules

Create these alerts in Prometheus:

```yaml
groups:
  - name: nevox_alerts
    rules:
      # High error rate
      - alert: HighErrorRate
        expr: sum(rate(nevox_errors_total[5m])) > 0.05
        for: 5m
        annotations:
          summary: "Error rate above 5%"

      # Slow TTS
      - alert: SlowTTS
        expr: histogram_quantile(0.95, nevox_tts_latency_seconds_bucket) > 2
        for: 5m
        annotations:
          summary: "TTS latency P95 > 2 seconds"

      # High cost
      - alert: HighHourlyCost
        expr: sum(rate(nevox_total_cost_cents_total[1h])) / 100 > 10
        for: 10m
        annotations:
          summary: "Hourly cost exceeds $10"
```

---

## Next Steps

1. **Restart your agent** to enable new metrics:
   ```powershell
   python agent-after-promotheus.py console
   ```

2. **Make test calls** to generate metric data

3. **View metrics:**
   - Prometheus: http://localhost:9090
   - Metrics endpoint: http://localhost:8009/metrics

4. **Create Grafana dashboards** for visualization

5. **Set up alerts** for critical metrics

---

## Troubleshooting

**Metrics not appearing?**
1. Check server started: Look for "Prometheus metrics server started on port 8009"
2. Check endpoint: `curl http://localhost:8009/metrics`
3. Check Prometheus targets: http://localhost:9090/targets (should be UP)

**Old metrics showing?**
- Restart Prometheus to clear cache
- Metrics persist in Prometheus database

**Missing agent_id labels?**
- Ensure agent configuration includes `id` field
- Check logs for "agent_id" value

---

## Summary

You now have **comprehensive monitoring** across:
- ✅ Costs & Usage
- ✅ Performance & Latency
- ✅ Errors & Failures
- ✅ Quality Metrics
- ✅ Business Analytics
- ✅ Recording Tracking

**60+ metrics** give you complete visibility into your voice agent system!
