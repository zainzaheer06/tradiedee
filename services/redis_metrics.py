"""
Redis-based Metrics Tracking
Works with multiprocess workers!
"""
import logging
from datetime import datetime
from services.redis_service import redis_service

logger = logging.getLogger(__name__)


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


def track_call_metrics(
    usage_summary,
    agent_id: int,
    call_duration: int,
    message_count: int,
    voice_id: str = "unknown",
    call_status: str = "completed"
):
    """
    Track metrics in Redis (works across all worker processes!)

    Args:
        usage_summary: LiveKit UsageSummary object
        agent_id: Agent ID
        call_duration: Call duration in seconds
        message_count: Number of messages in call
        voice_id: ElevenLabs voice ID
        call_status: completed, error, timeout, hangup
    """
    try:
        cost_breakdown = calculate_call_cost(usage_summary)

        # === TRACK IN REDIS ===
        # Calls count
        redis_service.increment_metric('calls_total', agent_id, 1)

        # Costs (in cents)
        redis_service.increment_metric('cost_cents_total', agent_id, cost_breakdown['total_cost'] * 100)
        redis_service.increment_metric('llm_cost_cents', agent_id, cost_breakdown['llm_cost'] * 100)
        redis_service.increment_metric('tts_cost_cents', agent_id, cost_breakdown['tts_cost'] * 100)
        redis_service.increment_metric('cache_savings_cents', agent_id, cost_breakdown['cache_savings'] * 100)

        # Tokens
        redis_service.increment_metric('tokens_uncached', agent_id, cost_breakdown['llm_uncached_tokens'])
        redis_service.increment_metric('tokens_cached', agent_id, cost_breakdown['llm_cached_tokens'])
        redis_service.increment_metric('tokens_completion', agent_id, cost_breakdown['llm_completion_tokens'])

        # TTS/STT
        redis_service.increment_metric('tts_characters', agent_id, cost_breakdown['tts_characters'])
        redis_service.increment_metric('stt_duration_seconds', agent_id, cost_breakdown['stt_duration'])

        # Call performance
        redis_service.track_histogram('call_duration', agent_id, call_duration)
        redis_service.track_histogram('messages_per_call', agent_id, message_count)

        # Call status
        redis_service.increment_metric(f'call_status_{call_status}', agent_id, 1)

        # Hour tracking
        current_hour = datetime.now().hour
        redis_service.increment_metric(f'calls_hour_{current_hour}', agent_id, 1)

        logger.info(
            f"📊 Metrics tracked in Redis: ${cost_breakdown['total_cost']:.4f} "
            f"(saved ${cost_breakdown['cache_savings']:.4f} from cache, "
            f"{cost_breakdown['cache_hit_rate']:.1f}% hit rate)"
        )

        return cost_breakdown

    except Exception as e:
        logger.error(f"❌ Failed to track Redis metrics: {e}")
        return None


def increment_active_calls(agent_id: int):
    """Mark a call as active (updates gauge in Redis)"""
    current = redis_service.get_gauge('active_calls', agent_id)
    redis_service.set_gauge('active_calls', agent_id, current + 1)
    logger.debug(f"📈 Active calls for agent {agent_id}: {current + 1}")


def decrement_active_calls(agent_id: int):
    """Mark a call as completed (updates gauge in Redis)"""
    current = redis_service.get_gauge('active_calls', agent_id)
    redis_service.set_gauge('active_calls', agent_id, max(0, current - 1))
    logger.debug(f"📉 Active calls for agent {agent_id}: {max(0, current - 1)}")


def track_error(agent_id: int, error_type: str):
    """
    Track errors in Redis

    Args:
        agent_id: Agent ID
        error_type: 'llm', 'tts', 'stt', 'recording', 'webhook', 'system'
    """
    redis_service.increment_metric(f'errors_{error_type}', agent_id, 1)
    logger.warning(f"⚠️ Error tracked: {error_type} for agent {agent_id}")


def track_latency(agent_id: int, metric_name: str, latency_seconds: float):
    """
    Track latency metrics

    Args:
        agent_id: Agent ID
        metric_name: 'tts_latency', 'llm_latency', 'greeting_latency'
        latency_seconds: Latency in seconds
    """
    redis_service.track_histogram(metric_name, agent_id, latency_seconds)


# Export functions
__all__ = [
    'track_call_metrics',
    'increment_active_calls',
    'decrement_active_calls',
    'track_error',
    'track_latency',
    'calculate_call_cost'
]

logger.info("📊 Redis metrics module loaded")
