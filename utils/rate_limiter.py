"""
Simple IP-based Rate Limiter for Public API
Tracks call attempts per IP address without external dependencies
"""
from datetime import datetime, timedelta
from collections import defaultdict
from threading import Lock

class RateLimiter:
    """In-memory rate limiter using IP addresses"""

    def __init__(self, max_calls=5, time_window_hours=1):
        """
        Initialize rate limiter

        Args:
            max_calls: Maximum number of calls allowed
            time_window_hours: Time window in hours
        """
        self.max_calls = max_calls
        self.time_window = timedelta(hours=time_window_hours)
        self.call_history = defaultdict(list)
        self.lock = Lock()

    def is_allowed(self, ip_address):
        """
        Check if IP address is allowed to make a call

        Args:
            ip_address: IP address to check

        Returns:
            tuple: (allowed: bool, remaining_calls: int, reset_time: datetime)
        """
        with self.lock:
            now = datetime.now()
            cutoff_time = now - self.time_window

            # Remove old entries
            self.call_history[ip_address] = [
                timestamp for timestamp in self.call_history[ip_address]
                if timestamp > cutoff_time
            ]

            current_calls = len(self.call_history[ip_address])
            remaining = max(0, self.max_calls - current_calls)

            # Calculate reset time (when oldest call expires)
            if self.call_history[ip_address]:
                oldest_call = min(self.call_history[ip_address])
                reset_time = oldest_call + self.time_window
            else:
                reset_time = now + self.time_window

            return (current_calls < self.max_calls, remaining, reset_time)

    def record_call(self, ip_address):
        """
        Record a call attempt from an IP address

        Args:
            ip_address: IP address making the call
        """
        with self.lock:
            self.call_history[ip_address].append(datetime.now())

    def cleanup_old_entries(self):
        """Remove expired entries to prevent memory bloat"""
        with self.lock:
            now = datetime.now()
            cutoff_time = now - self.time_window

            # Clean up old entries
            for ip in list(self.call_history.keys()):
                self.call_history[ip] = [
                    timestamp for timestamp in self.call_history[ip]
                    if timestamp > cutoff_time
                ]

                # Remove empty entries
                if not self.call_history[ip]:
                    del self.call_history[ip]


# Global rate limiter instance
# 5 calls per hour per IP
website_rate_limiter = RateLimiter(max_calls=5, time_window_hours=1)
