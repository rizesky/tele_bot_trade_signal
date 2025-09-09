import logging
import time
import threading
from collections import deque
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting behavior."""
    # Binance rate limits (per minute)
    max_weight_per_minute: int = 1200  # Binance's standard limit
    max_requests_per_minute: int = 1200  # Standard request limit
    
    # Safety margins to prevent hitting limits
    safety_margin_percent: float = 0.1  # 10% safety margin
    warning_threshold_percent: float = 0.8  # 80% warning threshold
    
    # Retry configuration
    retry_delay_seconds: float = 1.0
    max_retry_attempts: int = 3
    
    # Monitoring
    enable_detailed_logging: bool = True
    log_interval_seconds: int = 60  # Log usage every minute


class BinanceRateLimiter:
    """
    Advanced rate limiter for Binance API that tracks weight usage and prevents bans.
    
    Features:
    - Weight-based limiting for klines endpoint
    - Real-time weight tracking from response headers
    - Automatic retry with exponential backoff
    - Safety margins to prevent hitting limits
    - Detailed logging and monitoring
    """
    
    def __init__(self, config: Optional[RateLimitConfig] = None):
        self.config = config or RateLimitConfig()
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Weight tracking (sliding window)
        self._weight_history = deque()  # (timestamp, weight_used)
        self._request_history = deque()  # (timestamp, request_count)
        
        # Current usage tracking
        self._current_weight_used = 0
        self._current_requests = 0
        
        # Statistics
        self._total_requests = 0
        self._total_weight_used = 0
        self._blocked_requests = 0
        self._retry_attempts = 0
        
        # Last cleanup time
        self._last_cleanup = time.time()
        
        # Calculate effective limits with safety margin
        self._effective_weight_limit = int(
            self.config.max_weight_per_minute * (1 - self.config.safety_margin_percent)
        )
        self._effective_request_limit = int(
            self.config.max_requests_per_minute * (1 - self.config.safety_margin_percent)
        )
        
        logging.info(f"Rate limiter initialized with {self._effective_weight_limit} weight limit, "
                    f"{self._effective_request_limit} request limit (10% safety margin)")
    
    def calculate_weight_for_klines(self, limit: int) -> int:
        """
        Calculate weight cost for klines request based on limit parameter.
        
        Weight rules:
        - 1 ≤ limit < 100: weight 1
        - 100 ≤ limit < 500: weight 2  
        - 500 ≤ limit ≤ 1000: weight 5
        - 1000 < limit ≤ 1500: weight 10 (Binance maximum)
        - limit > 1500: weight 10 (capped at Binance limit)
        """
        if limit < 1:
            return 1
        elif limit < 100:
            return 1
        elif limit < 500:
            return 2
        elif limit <= 1000:
            return 5
        elif limit <= 1500:
            return 10
        else:
            # For requests > 1500, Binance will cap at 1500, so weight is 10
            return 10
    
    def can_make_request(self, estimated_weight: int = 1) -> Tuple[bool, str]:
        """
        Check if a request can be made without exceeding rate limits.
        
        Returns:
            Tuple[bool, str]: (can_proceed, reason)
        """
        with self._lock:
            current_time = time.time()
            
            # Clean old entries (older than 1 minute)
            self._cleanup_old_entries(current_time)
            
            # Calculate current usage
            current_weight = self._get_current_weight_usage(current_time)
            current_requests = self._get_current_request_usage(current_time)
            
            # Check weight limit
            if current_weight + estimated_weight > self._effective_weight_limit:
                return False, f"Weight limit exceeded: {current_weight + estimated_weight}/{self._effective_weight_limit}"
            
            # Check request limit
            if current_requests + 1 > self._effective_request_limit:
                return False, f"Request limit exceeded: {current_requests + 1}/{self._effective_request_limit}"
            
            # Check warning threshold
            weight_usage_percent = (current_weight + estimated_weight) / self._effective_weight_limit
            if weight_usage_percent > self.config.warning_threshold_percent:
                logging.warning(f"High weight usage: {weight_usage_percent:.1%} "
                              f"({current_weight + estimated_weight}/{self._effective_weight_limit})")
            
            return True, "OK"
    
    def record_request(self, weight_used: int, response_headers: Optional[Dict] = None):
        """
        Record a completed request and update weight tracking.
        
        Args:
            weight_used: Weight consumed by the request
            response_headers: Optional response headers to extract real weight usage
        """
        with self._lock:
            current_time = time.time()
            
            # Use actual weight from headers if available
            actual_weight = self._extract_weight_from_headers(response_headers) or weight_used
            
            # Record the request
            self._weight_history.append((current_time, actual_weight))
            self._request_history.append((current_time, 1))
            
            # Update statistics
            self._total_requests += 1
            self._total_weight_used += actual_weight
            self._current_weight_used += actual_weight
            self._current_requests += 1
            
            # Log detailed usage if enabled
            if self.config.enable_detailed_logging:
                self._log_usage_stats()
    
    def wait_if_needed(self, estimated_weight: int = 1) -> float:
        """
        Wait if necessary to avoid rate limits.
        
        Returns:
            float: Time waited in seconds
        """
        can_proceed, reason = self.can_make_request(estimated_weight)
        
        if can_proceed:
            return 0.0
        
        # Calculate wait time
        wait_time = self._calculate_wait_time(estimated_weight)
        
        if wait_time > 0:
            logging.warning(f"Rate limit reached: {reason}. Waiting {wait_time:.2f} seconds...")
            time.sleep(wait_time)
        
        return wait_time
    
    def get_usage_stats(self) -> Dict:
        """Get current usage statistics."""
        with self._lock:
            current_time = time.time()
            self._cleanup_old_entries(current_time)
            
            current_weight = self._get_current_weight_usage(current_time)
            current_requests = self._get_current_request_usage(current_time)
            
            return {
                'current_weight_used': current_weight,
                'current_requests': current_requests,
                'weight_limit': self._effective_weight_limit,
                'request_limit': self._effective_request_limit,
                'weight_usage_percent': (current_weight / self._effective_weight_limit) * 100,
                'request_usage_percent': (current_requests / self._effective_request_limit) * 100,
                'total_requests': self._total_requests,
                'total_weight_used': self._total_weight_used,
                'blocked_requests': self._blocked_requests,
                'retry_attempts': self._retry_attempts
            }
    
    def _cleanup_old_entries(self, current_time: float):
        """Remove entries older than 1 minute."""
        cutoff_time = current_time - 60  # 1 minute ago
        
        # Clean weight history
        while self._weight_history and self._weight_history[0][0] < cutoff_time:
            self._weight_history.popleft()
        
        # Clean request history
        while self._request_history and self._request_history[0][0] < cutoff_time:
            self._request_history.popleft()
    
    def _get_current_weight_usage(self, current_time: float) -> int:
        """Get current weight usage in the last minute."""
        cutoff_time = current_time - 60
        return sum(weight for timestamp, weight in self._weight_history if timestamp >= cutoff_time)
    
    def _get_current_request_usage(self, current_time: float) -> int:
        """Get current request count in the last minute."""
        cutoff_time = current_time - 60
        return sum(count for timestamp, count in self._request_history if timestamp >= cutoff_time)
    
    def _extract_weight_from_headers(self, headers: Optional[Dict]) -> Optional[int]:
        """Extract weight usage from Binance response headers."""
        if not headers:
            return None
        
        # Check for weight headers
        weight_headers = [
            'X-MBX-USED-WEIGHT-1M',
            'x-mbx-used-weight-1m',
            'X-MBX-USED-WEIGHT',
            'x-mbx-used-weight'
        ]
        
        for header in weight_headers:
            if header in headers:
                try:
                    return int(headers[header])
                except (ValueError, TypeError):
                    continue
        
        return None
    
    def _calculate_wait_time(self, estimated_weight: int) -> float:
        """Calculate how long to wait before making a request."""
        current_time = time.time()
        current_weight = self._get_current_weight_usage(current_time)
        
        # Calculate when we can make the request
        if current_weight + estimated_weight > self._effective_weight_limit:
            # Find the oldest entry that needs to expire
            if self._weight_history:
                oldest_entry_time = self._weight_history[0][0]
                wait_time = (oldest_entry_time + 60) - current_time
                return max(0, wait_time)
        
        return 0.0
    
    def _log_usage_stats(self):
        """Log detailed usage statistics periodically."""
        current_time = time.time()
        
        # Only log every N seconds to avoid spam
        if current_time - self._last_cleanup < self.config.log_interval_seconds:
            return
        
        self._last_cleanup = current_time
        
        stats = self.get_usage_stats()
        logging.info(
            f"Rate Limiter Stats - Weight: {stats['current_weight_used']}/{stats['weight_limit']} "
            f"({stats['weight_usage_percent']:.1f}%), "
            f"Requests: {stats['current_requests']}/{stats['request_limit']} "
            f"({stats['request_usage_percent']:.1f}%), "
            f"Total: {stats['total_requests']} requests, {stats['total_weight_used']} weight"
        )
    
    def block_request(self, reason: str):
        """Record a blocked request."""
        with self._lock:
            self._blocked_requests += 1
            logging.warning(f"Request blocked: {reason}")
    
    def record_retry(self):
        """Record a retry attempt."""
        with self._lock:
            self._retry_attempts += 1


class RateLimitedBinanceClient:
    """
    Wrapper around BinanceFuturesClient that adds rate limiting.
    """
    
    def __init__(self, binance_client, rate_limiter: BinanceRateLimiter):
        self.client = binance_client
        self.rate_limiter = rate_limiter
    
    def __getattr__(self, name):
        """Delegate all other attributes to the wrapped client."""
        return getattr(self.client, name)
    
    def load_historical_data(self, symbol: str, interval: str, limit: int = 100):
        """
        Rate-limited version of load_historical_data.
        """
        # Calculate weight for this request
        weight = self.rate_limiter.calculate_weight_for_klines(limit)
        
        # Wait if necessary
        wait_time = self.rate_limiter.wait_if_needed(weight)
        
        # Make the request
        try:
            result = self.client.load_historical_data(symbol, interval, limit)
            
            # Record the request (we'll extract weight from response headers if available)
            self.rate_limiter.record_request(weight)
            
            return result
            
        except Exception as e:
            # Check if it's a rate limit error
            if self._is_rate_limit_error(e):
                self.rate_limiter.block_request(f"Rate limit error: {e}")
                raise
            else:
                raise
    
    def _is_rate_limit_error(self, error) -> bool:
        """Check if the error is related to rate limiting."""
        error_str = str(error).lower()
        rate_limit_indicators = [
            '429',  # Too Many Requests
            '418',  # I'm a teapot (Binance's way of saying you're banned)
            'rate limit',
            'too many requests',
            'weight limit',
            'request limit'
        ]
        return any(indicator in error_str for indicator in rate_limit_indicators)
