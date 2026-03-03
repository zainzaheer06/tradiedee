"""
API Rate Limiter Service
Redis-based per-user rate limiting for API v1 endpoints

Uses sliding window counter pattern:
- Key: api_rate:{user_id}
- Value: number of requests in current window
- TTL: auto-expires at end of window

Falls back to "allow all" if Redis is unavailable (no blocking).
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Tuple

from services.redis_service import redis_service

logger = logging.getLogger(__name__)

# Saudi Arabia Timezone (UTC+3)
SAUDI_TZ = timezone(timedelta(hours=3))

# Defaults
DEFAULT_RATE_LIMIT = 200       # calls per window
DEFAULT_WINDOW_SECONDS = 3600  # 1 hour


class APIRateLimiter:
    """
    Redis-based per-user API rate limiter

    Uses a sliding window counter stored in Redis.
    Each user gets their own counter key with auto-expiry.
    """

    def __init__(self, default_limit: int = DEFAULT_RATE_LIMIT,
                 window_seconds: int = DEFAULT_WINDOW_SECONDS):
        self.default_limit = default_limit
        self.window_seconds = window_seconds

    def check_and_increment(self, user_id: int, limit: int = None) -> Tuple[bool, int, int, int]:
        """
        Check if user is within rate limit and increment counter.

        Args:
            user_id: The user's ID
            limit: Override rate limit (uses default if None)

        Returns:
            Tuple of (allowed, remaining, limit, reset_seconds)
            - allowed: True if request is within limit
            - remaining: How many requests left in window
            - limit: The applied rate limit
            - reset_seconds: Seconds until the window resets
        """
        effective_limit = limit or self.default_limit

        # If Redis is down, allow all (fail-open)
        if not redis_service.is_connected():
            logger.debug("Redis unavailable — rate limiter disabled (fail-open)")
            return True, effective_limit, effective_limit, self.window_seconds

        try:
            key = f"api_rate:{user_id}"
            pipe = redis_service.client.pipeline()

            # Increment counter
            pipe.incr(key)
            # Get TTL to see if key is new
            pipe.ttl(key)

            results = pipe.execute()
            current_count = results[0]  # int — count after increment
            ttl = results[1]            # int — seconds remaining (-1 if no TTL, -2 if key doesn't exist)

            # If key is brand new (no TTL set yet), set the window expiry
            if ttl == -1:
                redis_service.client.expire(key, self.window_seconds)
                ttl = self.window_seconds

            remaining = max(0, effective_limit - current_count)
            allowed = current_count <= effective_limit

            if not allowed:
                logger.warning(
                    f"Rate limit exceeded: user_id={user_id} "
                    f"({current_count}/{effective_limit} in {self.window_seconds}s window)"
                )

            return allowed, remaining, effective_limit, max(ttl, 0)

        except Exception as e:
            logger.error(f"Rate limiter error: {e} — failing open")
            return True, effective_limit, effective_limit, self.window_seconds

    def get_usage(self, user_id: int) -> dict:
        """
        Get current rate limit usage for a user (for display/debugging).

        Returns:
            Dict with current count, limit, remaining, reset_seconds
        """
        effective_limit = self.default_limit

        if not redis_service.is_connected():
            return {
                'current': 0,
                'limit': effective_limit,
                'remaining': effective_limit,
                'reset_seconds': self.window_seconds,
                'redis_available': False
            }

        try:
            key = f"api_rate:{user_id}"
            current = redis_service.client.get(key)
            ttl = redis_service.client.ttl(key)

            current_count = int(current) if current else 0
            reset_seconds = max(ttl, 0) if ttl and ttl > 0 else self.window_seconds

            return {
                'current': current_count,
                'limit': effective_limit,
                'remaining': max(0, effective_limit - current_count),
                'reset_seconds': reset_seconds,
                'redis_available': True
            }
        except Exception as e:
            logger.error(f"Error getting rate limit usage: {e}")
            return {
                'current': 0,
                'limit': effective_limit,
                'remaining': effective_limit,
                'reset_seconds': self.window_seconds,
                'redis_available': False
            }

    def reset(self, user_id: int) -> bool:
        """
        Reset rate limit counter for a user (admin function).

        Returns:
            True if reset, False on error
        """
        if not redis_service.is_connected():
            return False

        try:
            key = f"api_rate:{user_id}"
            redis_service.client.delete(key)
            logger.info(f"Rate limit reset for user_id={user_id}")
            return True
        except Exception as e:
            logger.error(f"Error resetting rate limit: {e}")
            return False


# Global instance — 100 calls per hour per user
api_rate_limiter = APIRateLimiter(
    default_limit=DEFAULT_RATE_LIMIT,
    window_seconds=DEFAULT_WINDOW_SECONDS
)
