"""
Redis Metrics Server
Reads metrics from Redis and exposes them to Prometheus
Solves the multiprocess issue!
"""
import logging
from flask import Flask, Response
from prometheus_client import generate_latest, CollectorRegistry, Gauge, Counter
from services.redis_service import redis_service
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Create custom registry (don't use global REGISTRY)
registry = CollectorRegistry()

# Define Prometheus metrics
CALLS_TOTAL = Gauge('nevox_calls_total', 'Total calls from Redis', ['agent_id', 'period'], registry=registry)
COST_TOTAL = Gauge('nevox_cost_usd_total', 'Total cost from Redis', ['agent_id', 'period'], registry=registry)
TOKENS_TOTAL = Gauge('nevox_tokens_total', 'Total tokens from Redis', ['agent_id', 'token_type', 'period'], registry=registry)
CACHE_HIT_RATE = Gauge('nevox_cache_hit_rate_pct', 'Cache hit rate from Redis', ['agent_id', 'period'], registry=registry)
AVG_DURATION = Gauge('nevox_avg_call_duration_sec', 'Average call duration from Redis', ['agent_id', 'period'], registry=registry)
ACTIVE_CALLS = Gauge('nevox_active_calls_current', 'Currently active calls from Redis', ['agent_id'], registry=registry)
ERROR_COUNT = Gauge('nevox_errors_count', 'Error count from Redis', ['agent_id', 'error_type', 'period'], registry=registry)


@app.route('/metrics')
def metrics():
    """
    Expose Redis metrics to Prometheus
    This endpoint is scraped by Prometheus every 15 seconds
    """
    if not redis_service.is_connected():
        logger.error("❌ Redis not connected!")
        return Response("# Redis not connected\n", mimetype='text/plain'), 503

    try:
        today = datetime.now().strftime('%Y-%m-%d')

        # Get only agents that have data (FULLY DYNAMIC!)
        agent_ids = []

        # Scan Redis for all agents with calls today
        # Pattern: metrics:2026-01-05:calls_total:agent:*
        pattern = f"metrics:{today}:calls_total:agent:*"
        keys = redis_service.client.keys(pattern)

        for key in keys:
            # Extract agent ID from key: "metrics:2026-01-05:calls_total:agent:51" -> 51
            # Key is already a string, no need to decode
            if isinstance(key, bytes):
                key = key.decode('utf-8')
            agent_id = int(key.split(':')[-1])
            calls = redis_service.get_metric('calls_total', agent_id, today)
            if calls > 0:
                agent_ids.append(agent_id)

        # If no agents have data today, don't export anything
        # (Grafana will show "No data" which is correct)
        if not agent_ids:
            logger.info(f"⚠️ No agents with data today ({today})")
            return Response("# No agents with data today\n", mimetype='text/plain')

        logger.info(f"✅ Exporting metrics for {len(agent_ids)} agent(s): {agent_ids}")

        for agent_id in agent_ids:
            agent_str = str(agent_id)

            # === TODAY'S METRICS ===
            # Total calls
            calls = redis_service.get_metric('calls_total', agent_id, today)
            CALLS_TOTAL.labels(agent_id=agent_str, period='today').set(calls)

            # Total cost (stored in cents, convert to USD)
            cost_cents = redis_service.get_metric('cost_cents_total', agent_id, today)
            COST_TOTAL.labels(agent_id=agent_str, period='today').set(cost_cents / 100)

            # Tokens
            uncached_tokens = redis_service.get_metric('tokens_uncached', agent_id, today)
            cached_tokens = redis_service.get_metric('tokens_cached', agent_id, today)
            completion_tokens = redis_service.get_metric('tokens_completion', agent_id, today)

            TOKENS_TOTAL.labels(agent_id=agent_str, token_type='uncached', period='today').set(uncached_tokens)
            TOKENS_TOTAL.labels(agent_id=agent_str, token_type='cached', period='today').set(cached_tokens)
            TOKENS_TOTAL.labels(agent_id=agent_str, token_type='completion', period='today').set(completion_tokens)

            # Cache hit rate
            total_prompt = uncached_tokens + cached_tokens
            if total_prompt > 0:
                cache_rate = (cached_tokens / total_prompt) * 100
                CACHE_HIT_RATE.labels(agent_id=agent_str, period='today').set(cache_rate)

            # Average call duration
            duration_stats = redis_service.get_histogram_stats('call_duration', agent_id, today)
            if duration_stats:
                AVG_DURATION.labels(agent_id=agent_str, period='today').set(duration_stats.get('avg', 0))

            # Active calls (gauge)
            active = redis_service.get_gauge('active_calls', agent_id)
            ACTIVE_CALLS.labels(agent_id=agent_str).set(active)

            # Errors
            for error_type in ['llm', 'tts', 'stt', 'recording', 'webhook', 'system']:
                error_count = redis_service.get_metric(f'errors_{error_type}', agent_id, today)
                ERROR_COUNT.labels(agent_id=agent_str, error_type=error_type, period='today').set(error_count)

        logger.info(f"✅ Metrics updated for {len(agent_ids)} agents")

        # Generate Prometheus format
        return Response(generate_latest(registry), mimetype='text/plain')

    except Exception as e:
        logger.error(f"❌ Error generating metrics: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return Response(f"# Error: {e}\n", mimetype='text/plain'), 500

# In redis_metrics_server.py, add this endpoint:
@app.route('/redis-stats')
def redis_stats():
    info = redis_service.client.info('memory')
    return {
        'used_memory_mb': info['used_memory'] / 1024 / 1024,
        'used_memory_peak_mb': info['used_memory_peak'] / 1024 / 1024,
        'connected_clients': redis_service.client.info('clients')['connected_clients']
    }


@app.route('/health')
def health():
    """Health check endpoint"""
    if redis_service.is_connected():
        stats = redis_service.get_stats()
        return {
            'status': 'healthy',
            'redis': 'connected',
            'stats': stats
        }
    else:
        return {'status': 'unhealthy', 'redis': 'disconnected'}, 503


@app.route('/')
def index():
    """Info page"""
    return """
    <h1>Nevox Redis Metrics Server</h1>
    <ul>
        <li><a href="/metrics">/metrics</a> - Prometheus metrics endpoint</li>
        <li><a href="/health">/health</a> - Health check</li>
    </ul>
    <p>This server reads metrics from Redis and exposes them to Prometheus.</p>
    <p>Prometheus scrapes <code>/metrics</code> every 15 seconds.</p>
    """


if __name__ == '__main__':
    logger.info("🚀 Starting Redis Metrics Server on port 8009...")

    # Check Redis connection
    if not redis_service.is_connected():
        logger.error("❌ Redis is not connected! Metrics will not work.")
        logger.error("   Start Redis: docker run -d -p 6379:6379 redis")
    else:
        logger.info("✅ Redis connected successfully")
        stats = redis_service.get_stats()
        logger.info(f"📊 Redis stats: {stats}")

    logger.info("📊 Metrics endpoint: http://localhost:8009/metrics")
    logger.info("💚 Health check: http://localhost:8009/health")

    app.run(host='0.0.0.0', port=8009, threaded=True)
