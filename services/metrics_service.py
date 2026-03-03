"""
Prometheus Metrics Service for Voice Agent Analytics
Tracks costs, tokens, call performance, and recordings
Zero impact on call latency (async collection)
"""
import logging
import os
from prometheus_client import Counter, Histogram, Gauge, start_http_server, REGISTRY

logger = logging.getLogger(__name__)

# ==========================================
# PROMETHEUS METRICS DEFINITIONS
# ==========================================

# Token usage metrics
LLM_PROMPT_TOKENS = Counter(
    'nevox_llm_prompt_tokens_total',
    'LLM prompt tokens used',
    ['agent_id', 'cached']
)
LLM_COMPLETION_TOKENS = Counter(
    'nevox_llm_completion_tokens_total',
    'LLM completion tokens',
    ['agent_id']
)
TTS_CHARACTERS = Counter(
    'nevox_tts_characters_total',
    'TTS characters generated',
    ['agent_id', 'voice']
)
STT_DURATION = Counter(
    'nevox_stt_duration_seconds_total',
    'STT audio duration processed',
    ['agent_id']
)

# Cost metrics (in USD cents to avoid floating point issues)
LLM_COST = Counter(
    'nevox_llm_cost_cents_total',
    'LLM cost in USD cents',
    ['agent_id']
)
TTS_COST = Counter(
    'nevox_tts_cost_cents_total',
    'TTS cost in USD cents',
    ['agent_id']
)
TOTAL_COST = Counter(
    'nevox_total_cost_cents_total',
    'Total call cost in USD cents',
    ['agent_id']
)
CACHE_SAVINGS = Counter(
    'nevox_cache_savings_cents_total',
    'Money saved from prompt caching (USD cents)',
    ['agent_id']
)

# Call performance metrics
CALL_DURATION = Histogram(
    'nevox_call_duration_seconds',
    'Call duration distribution',
    ['agent_id'],
    buckets=[10, 30, 60, 120, 300, 600, 1800]
)
ACTIVE_CALLS = Gauge(
    'nevox_active_calls',
    'Currently active calls',
    ['agent_id']
)
MESSAGES_PER_CALL = Histogram(
    'nevox_messages_per_call',
    'Number of messages per call',
    ['agent_id'],
    buckets=[1, 5, 10, 20, 50, 100]
)
CALL_STATUS = Counter(
    'nevox_call_status_total',
    'Call completion status',
    ['agent_id', 'status']
)

# Recording metrics
RECORDING_SIZE = Histogram(
    'nevox_recording_size_bytes',
    'Recording file sizes',
    ['agent_id'],
    buckets=[1e5, 5e5, 1e6, 5e6, 1e7, 5e7]
)
RECORDING_UPLOAD_DURATION = Histogram(
    'nevox_recording_upload_seconds',
    'Time taken to upload recording',
    ['agent_id'],
    buckets=[1, 5, 10, 20, 30, 60]
)
RECORDING_SUCCESS = Counter(
    'nevox_recording_success_total',
    'Recording upload success/failure',
    ['agent_id', 'status']
)

# ==========================================
# LATENCY & PERFORMANCE METRICS
# ==========================================
TTS_LATENCY = Histogram(
    'nevox_tts_latency_seconds',
    'Time to first TTS byte (TTFB)',
    ['agent_id', 'voice'],
    buckets=[0.1, 0.3, 0.5, 1.0, 2.0, 5.0]
)

LLM_LATENCY = Histogram(
    'nevox_llm_response_seconds',
    'LLM response time',
    ['agent_id'],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)

CALL_SETUP_TIME = Histogram(
    'nevox_call_setup_seconds',
    'Time from room creation to first greeting',
    ['agent_id'],
    buckets=[1, 2, 5, 10, 20, 30]
)

# ==========================================
# ERROR TRACKING METRICS
# ==========================================
ERRORS_TOTAL = Counter(
    'nevox_errors_total',
    'Total errors by type',
    ['agent_id', 'error_type']  # error_type: llm, tts, stt, recording, webhook, system
)

CALL_FAILURES = Counter(
    'nevox_call_failures_total',
    'Failed calls by reason',
    ['agent_id', 'failure_reason']  # disconnect, timeout, error, hangup
)

# ==========================================
# QUALITY METRICS
# ==========================================
USER_INTERRUPTIONS = Counter(
    'nevox_user_interruptions_total',
    'Number of times user interrupted agent',
    ['agent_id']
)

TURN_COUNT = Histogram(
    'nevox_conversation_turns',
    'Number of back-and-forth turns per call',
    ['agent_id'],
    buckets=[1, 3, 5, 10, 20, 50, 100]
)

GREETING_LATENCY = Histogram(
    'nevox_greeting_latency_seconds',
    'Time from participant join to greeting sent',
    ['agent_id'],
    buckets=[0.5, 1, 2, 3, 5, 10]
)

# ==========================================
# BUSINESS METRICS
# ==========================================
CALLS_BY_HOUR = Counter(
    'nevox_calls_by_hour_total',
    'Total calls by hour of day',
    ['agent_id', 'hour']  # hour: 0-23
)

PEAK_CONCURRENT = Gauge(
    'nevox_peak_concurrent_calls',
    'Peak concurrent calls (resets daily)',
    ['agent_id']
)

AVERAGE_HANDLE_TIME = Gauge(
    'nevox_average_handle_time_seconds',
    'Moving average call duration',
    ['agent_id']
)

logger.info("📊 Prometheus metrics initialized (including latency, errors, quality metrics)")


# ==========================================
# COST CALCULATION FUNCTION
# ==========================================

def calculate_call_cost(usage_summary) -> dict:
    """Calculate cost breakdown from LiveKit UsageSummary"""
    
    COST_PER_1K_PROMPT = 0.00015
    COST_PER_1K_CACHED = 0.000075
    COST_PER_1K_COMPLETION = 0.0006
    COST_PER_1K_TTS_CHARS = 0.00018

    prompt_tokens = usage_summary.llm_prompt_tokens
    cached_tokens = usage_summary.llm_prompt_cached_tokens
    completion_tokens = usage_summary.llm_completion_tokens
    tts_chars = usage_summary.tts_characters_count

    uncached_tokens = prompt_tokens - cached_tokens
    llm_prompt_cost = uncached_tokens / 1000 * COST_PER_1K_PROMPT
    llm_cached_cost = cached_tokens / 1000 * COST_PER_1K_CACHED
    llm_completion_cost = completion_tokens / 1000 * COST_PER_1K_COMPLETION
    tts_cost = tts_chars / 1000 * COST_PER_1K_TTS_CHARS

    total_llm_cost = llm_prompt_cost + llm_cached_cost + llm_completion_cost
    total_cost = total_llm_cost + tts_cost

    cache_savings = cached_tokens / 1000 * (COST_PER_1K_PROMPT - COST_PER_1K_CACHED)

    return {
        'llm_prompt_tokens': prompt_tokens,
        'llm_uncached_tokens': uncached_tokens,
        'llm_cached_tokens': cached_tokens,
        'llm_completion_tokens': completion_tokens,
        'tts_characters': tts_chars,
        'tts_duration': usage_summary.tts_audio_duration,
        'stt_duration': usage_summary.stt_audio_duration,
        'llm_cost': round(total_llm_cost, 6),
        'tts_cost': round(tts_cost, 6),
        'total_cost': round(total_cost, 6),
        'cache_savings': round(cache_savings, 6),
        'cache_hit_rate': round(cached_tokens / prompt_tokens * 100, 1) if prompt_tokens > 0 else 0
    }


# ==========================================
# METRICS TRACKING FUNCTION
# ==========================================

def track_call_metrics(
    usage_summary,
    agent_id: int,
    call_duration: int,
    message_count: int,
    voice_id: str = "unknown",
    call_status: str = "completed"
):
    """Track all metrics for a completed call"""
    try:
        cost_breakdown = calculate_call_cost(usage_summary)
        agent_id_str = str(agent_id)

        # Token metrics
        LLM_PROMPT_TOKENS.labels(agent_id=agent_id_str, cached='false').inc(
            cost_breakdown['llm_uncached_tokens']
        )
        LLM_PROMPT_TOKENS.labels(agent_id=agent_id_str, cached='true').inc(
            cost_breakdown['llm_cached_tokens']
        )
        LLM_COMPLETION_TOKENS.labels(agent_id=agent_id_str).inc(
            cost_breakdown['llm_completion_tokens']
        )
        TTS_CHARACTERS.labels(agent_id=agent_id_str, voice=voice_id).inc(
            cost_breakdown['tts_characters']
        )
        STT_DURATION.labels(agent_id=agent_id_str).inc(
            cost_breakdown['stt_duration']
        )

        # Cost metrics (convert to cents)
        LLM_COST.labels(agent_id=agent_id_str).inc(
            int(cost_breakdown['llm_cost'] * 100)
        )
        TTS_COST.labels(agent_id=agent_id_str).inc(
            int(cost_breakdown['tts_cost'] * 100)
        )
        TOTAL_COST.labels(agent_id=agent_id_str).inc(
            int(cost_breakdown['total_cost'] * 100)
        )
        CACHE_SAVINGS.labels(agent_id=agent_id_str).inc(
            int(cost_breakdown['cache_savings'] * 100)
        )

        # Call performance metrics
        CALL_DURATION.labels(agent_id=agent_id_str).observe(call_duration)
        MESSAGES_PER_CALL.labels(agent_id=agent_id_str).observe(message_count)
        CALL_STATUS.labels(agent_id=agent_id_str, status=call_status).inc()

        logger.info(
            f"📊 Metrics tracked: ${cost_breakdown['total_cost']:.4f} "
            f"(saved ${cost_breakdown['cache_savings']:.4f} from cache, "
            f"{cost_breakdown['cache_hit_rate']:.1f}% hit rate)"
        )

        return cost_breakdown

    except Exception as e:
        logger.error(f"❌ Failed to track metrics: {e}")
        return None


def start_metrics_server(port: int = 8009):
    """Start Prometheus HTTP server (simple, non-blocking)"""
    try:
        start_http_server(port)
        logger.info(f"📊 Prometheus metrics server started on port {port}")
        logger.info(f"   Access metrics at: http://localhost:{port}/metrics")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to start metrics server: {e}")
        return False


def increment_active_calls(agent_id: int):
    """Mark a call as active"""
    ACTIVE_CALLS.labels(agent_id=str(agent_id)).inc()


def decrement_active_calls(agent_id: int):
    """Mark a call as completed"""
    ACTIVE_CALLS.labels(agent_id=str(agent_id)).dec()


def track_recording_metrics(agent_id: int, file_size_bytes: int, upload_duration: float, success: bool):
    """Track recording upload metrics"""
    agent_id_str = str(agent_id)
    RECORDING_SIZE.labels(agent_id=agent_id_str).observe(file_size_bytes)
    RECORDING_UPLOAD_DURATION.labels(agent_id=agent_id_str).observe(upload_duration)
    RECORDING_SUCCESS.labels(
        agent_id=agent_id_str,
        status='success' if success else 'failed'
    ).inc()


# ==========================================
# NEW MONITORING HELPER FUNCTIONS
# ==========================================

def track_tts_latency(agent_id: int, voice_id: str, latency_seconds: float):
    """Track TTS time-to-first-byte"""
    TTS_LATENCY.labels(agent_id=str(agent_id), voice=voice_id).observe(latency_seconds)


def track_llm_latency(agent_id: int, latency_seconds: float):
    """Track LLM response time"""
    LLM_LATENCY.labels(agent_id=str(agent_id)).observe(latency_seconds)


def track_call_setup_time(agent_id: int, setup_seconds: float):
    """Track time from room creation to first greeting"""
    CALL_SETUP_TIME.labels(agent_id=str(agent_id)).observe(setup_seconds)


def track_greeting_latency(agent_id: int, latency_seconds: float):
    """Track time from participant join to greeting sent"""
    GREETING_LATENCY.labels(agent_id=str(agent_id)).observe(latency_seconds)


def track_error(agent_id: int, error_type: str):
    """
    Track errors by type
    error_type: 'llm', 'tts', 'stt', 'recording', 'webhook', 'system'
    """
    ERRORS_TOTAL.labels(agent_id=str(agent_id), error_type=error_type).inc()


def track_call_failure(agent_id: int, failure_reason: str):
    """
    Track failed calls
    failure_reason: 'disconnect', 'timeout', 'error', 'hangup'
    """
    CALL_FAILURES.labels(agent_id=str(agent_id), failure_reason=failure_reason).inc()


def track_user_interruption(agent_id: int):
    """Track when user interrupts agent"""
    USER_INTERRUPTIONS.labels(agent_id=str(agent_id)).inc()


def track_conversation_turns(agent_id: int, turn_count: int):
    """Track number of back-and-forth turns in conversation"""
    TURN_COUNT.labels(agent_id=str(agent_id)).observe(turn_count)


def track_call_by_hour(agent_id: int, hour: int):
    """Track calls by hour of day (0-23)"""
    CALLS_BY_HOUR.labels(agent_id=str(agent_id), hour=str(hour)).inc()


def update_peak_concurrent(agent_id: int, current_concurrent: int):
    """Update peak concurrent calls if current exceeds previous peak"""
    current_peak = PEAK_CONCURRENT.labels(agent_id=str(agent_id))._value._value if hasattr(PEAK_CONCURRENT.labels(agent_id=str(agent_id)), '_value') else 0
    if current_concurrent > current_peak:
        PEAK_CONCURRENT.labels(agent_id=str(agent_id)).set(current_concurrent)


def update_average_handle_time(agent_id: int, avg_duration: float):
    """Update moving average handle time"""
    AVERAGE_HANDLE_TIME.labels(agent_id=str(agent_id)).set(avg_duration)