# Rate Limiting Guide

This guide explains the rate limiting system implemented to prevent your trading bot from getting banned by Binance due to API overuse.

## Overview

Binance has strict rate limits on their API to prevent abuse. The rate limiting system in this bot:

- **Tracks API weight usage** based on request types and parameters
- **Prevents hitting rate limits** by queuing requests when necessary
- **Monitors usage in real-time** and provides warnings
- **Optimizes request parameters** to minimize weight usage
- **Provides detailed logging** for monitoring and debugging

## How Binance Rate Limiting Works

### Weight-Based System

Binance uses a weight-based system for the `/fapi/v1/klines` endpoint:

| Limit Range | Weight Cost |
|-------------|-------------|
| 1 ≤ limit < 100 | 1 weight |
| 100 ≤ limit < 500 | 2 weight |
| 500 ≤ limit ≤ 1000 | 5 weight |
| limit > 1000 | 10 weight |

### Rate Limits

- **Weight limit**: 1200 per minute
- **Request limit**: 1200 per minute
- **IP-based**: All requests from your IP count toward the limit

## Configuration

Add these settings to your `.env` file:

```bash
# Enable rate limiting (HIGHLY RECOMMENDED)
RATE_LIMITING_ENABLED=1

# Safety margin (10% = use only 90% of limits)
RATE_LIMIT_SAFETY_MARGIN=0.1

# Warning threshold (80% = warn when usage exceeds 80%)
RATE_LIMIT_WARNING_THRESHOLD=0.8

# Binance standard limits (don't change unless you have special access)
RATE_LIMIT_MAX_WEIGHT_PER_MINUTE=1200
RATE_LIMIT_MAX_REQUESTS_PER_MINUTE=1200

# Retry settings
RATE_LIMIT_RETRY_DELAY=1.0
RATE_LIMIT_MAX_RETRIES=3

# Logging
RATE_LIMIT_DETAILED_LOGGING=1
RATE_LIMIT_LOG_INTERVAL=60
```

## Features

### 1. Weight Calculation

The system automatically calculates the correct weight for each request:

```python
# Examples:
limit=50   -> weight=1  (efficient for small requests)
limit=200  -> weight=2  (good balance)
limit=500  -> weight=5  (for larger requests)
limit=1500 -> weight=10 (very expensive)
```

### 2. Request Optimization

The bot optimizes request parameters to minimize weight usage:

```python
# Instead of requesting 1500 candles (weight 10):
# The bot will make 2 requests of 750 candles each (weight 5 + 5 = 10)
# This approach is more efficient for rate limiting
```

### 3. Real-time Monitoring

The system monitors usage and provides warnings:

```
2024-01-15 10:30:00 [WARNING] High API usage: Weight 85.2%, Requests 78.1%
2024-01-15 10:35:00 [INFO] API Usage Summary: 150 requests, 450 weight used, 2 blocked, 1 retries
```

### 4. Automatic Queuing

When approaching limits, the bot automatically waits:

```
2024-01-15 10:30:00 [DEBUG] Rate limiting: waited 2.34s for BTCUSDT-1h (limit=200, weight=2)
```

## Monitoring

### Log Messages

The bot provides detailed logging about rate limiting:

- **DEBUG**: Individual request timing and weight usage
- **INFO**: Periodic usage summaries
- **WARNING**: High usage alerts
- **ERROR**: Rate limit violations

### Statistics

Current usage can be checked through the API:

```python
stats = binance_client.get_rate_limit_stats()
print(f"Weight usage: {stats['weight_usage_percent']:.1f}%")
print(f"Request usage: {stats['request_usage_percent']:.1f}%")
```

## Best Practices

### 1. Use Appropriate Limits

- **Small requests** (1-99 candles): Use for real-time updates
- **Medium requests** (100-499 candles): Good for historical data
- **Large requests** (500-1000 candles): Use sparingly
- **Very large requests** (>1000 candles): Avoid unless necessary

### 2. Monitor Usage

- Enable detailed logging to track usage patterns
- Set up alerts for high usage warnings
- Monitor the logs for blocked requests

### 3. Optimize Configuration

- **Conservative**: Higher safety margin (0.2 = 20%)
- **Balanced**: Default safety margin (0.1 = 10%)
- **Aggressive**: Lower safety margin (0.05 = 5%) - **RISKY**

### 4. Database Caching

Enable database persistence to reduce API calls:

```bash
DB_ENABLE_PERSISTENCE=1
```

This caches historical data and reduces the need for repeated API calls.

## Testing

Run the rate limiting test script to verify everything works:

```bash
python test_rate_limiting.py
```

The test script will verify:
- Weight calculation accuracy
- Rate limiting logic
- Binance API integration
- Historical data loading
- High-load simulation

## Troubleshooting

### High Usage Warnings

When frequent warnings appear:

1. **Check your symbol count**: Too many symbols = more API calls
2. **Reduce MAX_SYMBOLS**: Limit to 50-100 symbols
3. **Increase safety margin**: Set to 0.2 (20%)
4. **Enable lazy loading**: Set LAZY_LOADING_ENABLED=1

### Blocked Requests

If requests are being blocked:

1. **Check your internet connection**: Slow connections can cause timeouts
2. **Reduce concurrent loads**: Lower MAX_CONCURRENT_LOADS
3. **Increase retry delay**: Set RATE_LIMIT_RETRY_DELAY=2.0

### API Bans

When API bans occur (HTTP 418):

1. **Stop the bot immediately**
2. **Wait 24-48 hours** before restarting
3. **Increase safety margin** to 0.3 (30%)
4. **Reduce symbol count** significantly
5. **Contact Binance support** if the issue persists

## Advanced Configuration

### Custom Weight Limits

For special API access:

```bash
# For higher limits (requires special access)
RATE_LIMIT_MAX_WEIGHT_PER_MINUTE=2400
RATE_LIMIT_MAX_REQUESTS_PER_MINUTE=2400
```

### Disable Rate Limiting

**NOT RECOMMENDED** - Only for testing:

```bash
RATE_LIMITING_ENABLED=0
```

## Integration with Other Systems

The rate limiter is automatically integrated with:

- **BinanceFuturesClient**: All API calls are rate-limited
- **TradeManager**: Historical data loading respects limits
- **SymbolManager**: Symbol fetching is rate-limited
- **Main Application**: Monitoring and logging

## Performance Impact

Rate limiting adds minimal overhead:

- **CPU**: <1% additional usage
- **Memory**: ~1MB for tracking data
- **Latency**: 0-5 seconds delay when queuing requests
- **Throughput**: Slightly reduced but prevents bans

## Conclusion

The rate limiting system is essential for preventing API bans while maintaining good performance. Always keep it enabled in production and monitor the logs for any issues.

For questions or issues, check the logs first, then run the test script to verify the system is working correctly.
