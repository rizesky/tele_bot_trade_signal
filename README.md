# Advanced Trading Signal Bot

A sophisticated cryptocurrency trading signal bot for Binance Futures with advanced technical analysis, intelligent risk management, automated chart generation, and comprehensive rate limiting protection.

## **Key Features**

### **Advanced Signal Generation**
- **Multi-timeframe analysis** (15m, 30m, 1h, 4h) with higher timeframe confirmation
- **RSI + Moving Average crossover** with volume confirmation
- **Market regime detection** (trending, ranging, volatile) with adaptive filtering
- **Trading session filtering** (9 AM - 9 PM UTC) for optimal liquidity
- **ATR-based position sizing** with risk guidance
- **Multiple take profit levels** (1.5%, 3%, 5%, 8%)

### **Intelligent Risk Management**
- **Market cap filtering** via CoinGecko API integration
- **Leverage and margin type management** with Binance API integration
- **Configurable signal cooldown** with timeframe-based logic
- **Quality-based symbol selection** with volume and volatility scoring
- **Real-time risk assessment** with ATR calculations

### **Production-Ready Architecture**
- **Real-time WebSocket data** from Binance with automatic reconnection
- **TradingView-style chart generation** with Playwright automation
- **SQLite database** with automatic cleanup and optimization
- **Docker containerization** with multi-stage builds
- **Thread-safe multi-processing** with connection pooling
- **Comprehensive error recovery** and graceful shutdown

### **Advanced Rate Limiting System**
- **Weight-based API limiting** following Binance's exact specifications
- **Real-time usage monitoring** with automatic queuing
- **Safety margins** to prevent API bans (configurable 10% default)
- **Request optimization** to minimize weight usage
- **Concurrent request handling** with thread-safe operations
- **Detailed logging** and usage statistics

**For detailed rate limiting configuration and troubleshooting, see [RATE_LIMITING_GUIDE.md](RATE_LIMITING_GUIDE.md)**

## **Rate Limiting Protection**

### **Binance API Weight System**
The bot implements Binance's exact weight calculation system:

| Limit Range | Weight Cost | Use Case |
|-------------|-------------|----------|
| 1 ≤ limit < 100 | 1 weight | Small requests, real-time updates |
| 100 ≤ limit < 500 | 2 weight | Medium historical data |
| 500 ≤ limit ≤ 1000 | 5 weight | Large historical data |
| 1000 < limit ≤ 1500 | 10 weight | Maximum single request |

### **Rate Limiting Features**
- **Automatic weight calculation** for all API requests
- **Sliding window tracking** (1-minute intervals)
- **Safety margin enforcement** (10% default, configurable)
- **Request queuing** when approaching limits
- **Real-time monitoring** with detailed statistics
- **Error detection** for rate limit violations (HTTP 429, 418)

### **Configuration**
```bash
# Enable rate limiting (HIGHLY RECOMMENDED)
RATE_LIMITING_ENABLED=1

# Safety margin (10% = use only 90% of limits)
RATE_LIMIT_SAFETY_MARGIN=0.1

# Warning threshold (80% = warn when usage exceeds 80%)
RATE_LIMIT_WARNING_THRESHOLD=0.8

# Binance standard limits
RATE_LIMIT_MAX_WEIGHT_PER_MINUTE=1200
RATE_LIMIT_MAX_REQUESTS_PER_MINUTE=1200

# Retry and logging settings
RATE_LIMIT_RETRY_DELAY=1.0
RATE_LIMIT_MAX_RETRIES=3
RATE_LIMIT_DETAILED_LOGGING=1
```

## **Advanced Architecture**

### **Lazy Loading System**

The bot uses intelligent **lazy loading** for optimal performance and API efficiency:

#### **How It Works**
```
Signal #1 for BTCUSDT-15m:
├── Check: Historical data loaded? ❌ NO
├── Load: 200 historical candles (API call, weight=2)
├── Store: In memory + database cache
└── Mark: As loaded for future use

Signal #2 for BTCUSDT-15m (same symbol):
├── Check: Historical data loaded? ✅ YES
├── Action: REUSE existing data (no API call)
└── Use: Cached data + live WebSocket updates
```

#### **Benefits**
- **API Efficiency**: Historical data loaded only ONCE per symbol/timeframe
- **Memory Optimized**: Maintains exactly 200 candles per symbol (sliding window)
- **Fast Response**: Subsequent signals use cached data instantly
- **Scalable**: Works efficiently with 300+ symbols
- **Rate Limit Friendly**: Dramatically reduces API usage

#### **Configuration**
```bash
# Enable lazy loading (recommended: enabled)
LAZY_LOADING_ENABLED=1

# Maximum symbols to load historical data for
MAX_LAZY_LOAD_SYMBOLS=100

# Concurrent API requests for faster loading
MAX_CONCURRENT_LOADS=15
```

### **Intelligent Symbol Selection**

Advanced symbol selection system for production optimization:

#### **Selection Strategies**

**Quality Strategy (Recommended)**
```python
quality_score = (
    (volume_24h / 1M) * 0.6 +      # 60% Volume weight
    (price_change_abs) * 0.3 +      # 30% Volatility weight  
    (trade_count / 10K) * 0.1       # 10% Activity weight
)
```

**Volume Strategy**
- Prioritizes highest 24h trading volume
- Best for maximum liquidity and tight spreads
- Ideal for high-frequency trading strategies

**Random Strategy**
- Random selection from filtered symbols
- Useful for testing and avoiding bias
- Not recommended for production

#### **Multi-Layer Filtering**
```
All Binance Futures Symbols (300+)
    ↓ USDT Pairs Only
    ↓ MIN_DAILY_VOLUME_USDT Filter
    ↓ MIN_MARKET_CAP_USD Filter (if enabled)
    ↓ Selection Strategy Applied
    ↓ MAX_SYMBOLS Limit
Final Symbol Set (50-200 symbols)
```

### **Market Regime Detection**

The bot automatically detects and adapts to different market conditions:

#### **Market Regimes**
```python
TRENDING    # Strong directional movement (signals encouraged)
RANGING     # Sideways price action (signals discouraged) 
VOLATILE    # High volatility/noise (signals filtered)
UNCLEAR     # Insufficient data (signals cautious)
```

#### **Adaptive Filtering**
- **Price action analysis**: Detects breakouts, ranges, and volatility
- **Adaptive filtering**: Rejects inappropriate signals for current regime
- **Risk adjustment**: Modifies signal confidence based on market state

### **Higher Timeframe Confirmation**

Multi-timeframe analysis prevents false signals:

```
15m signal → Check 1h trend → Check 4h trend → Check 1d trend
    ↓              ↓              ↓              ↓
If all higher timeframes align → CONFIRM signal
If higher timeframes conflict → REJECT signal
```

### **Thread-Safe Concurrency**

Advanced concurrency patterns for optimal performance:

- **Thread-safe data access**: All shared data protected with `threading.RLock()`
- **Async signal processing**: `ThreadPoolExecutor` prevents WebSocket blocking
- **Connection pooling**: Database connections reused across threads
- **Non-blocking chart generation**: Playwright runs in dedicated thread
- **Rate-limited concurrent requests**: Each request respects API limits

## **Database Management**

### **Automatic Database Optimization**

The bot includes comprehensive database management:

- **Automatic cleanup**: Removes data older than 7 days (configurable)
- **Size monitoring**: Triggers cleanup when database exceeds 200MB
- **Data compression**: Keeps every 4th record for data older than 3 days
- **Background maintenance**: Runs cleanup every 6 hours automatically
- **WAL mode**: Write-Ahead Logging for better concurrency
- **Connection pooling**: 10 concurrent connections by default

### **Database Schema**
```sql
-- Historical OHLCV data with automatic cleanup
historical_data (symbol, interval, timestamp, open, high, low, close, volume)

-- Trading signals with metadata
signals (id, symbol, interval, signal_type, price, entry_prices, tp_levels, sl_level, leverage, margin_type, timestamp)

-- Bot state and configuration
bot_state (key, value, updated_at)

-- Cached API responses for performance
api_cache (key, data, expires_at)
```

## **Installation**

### **Docker (Recommended)**
```bash
# Build and run with Docker
docker build -t tele-bot-trading .
docker run -d --name trading-bot \
  --env-file .env \
  -v $(pwd)/charts:/app/charts \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/trading_bot.db:/app/trading_bot.db \
  tele-bot-trading
```

### **Local Installation**
```bash
git clone https://github.com/rizesky/tele-bot-trading.git
cd tele-bot-trading
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install  # Install browser binaries for chart generation
python main.py
```

## **Configuration**

### **Required Settings**
```bash
# Binance API
BINANCE_API_KEY=your_binance_api_key
BINANCE_API_SECRET=your_binance_api_secret
BINANCE_ENV=dev  # or prod

# Telegram
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id

# Trading
TIMEFRAMES=15m,30m,1h,4h
HISTORY_CANDLES=200  # Maximum: 1500 (Binance limit)
```

### **Rate Limiting Configuration**
```bash
# Enable rate limiting (HIGHLY RECOMMENDED)
RATE_LIMITING_ENABLED=1
RATE_LIMIT_SAFETY_MARGIN=0.1
RATE_LIMIT_WARNING_THRESHOLD=0.8
RATE_LIMIT_DETAILED_LOGGING=1
```

### **Performance & Memory Configuration**
```bash
# Lazy loading (recommended: enabled)
LAZY_LOADING_ENABLED=1
MAX_LAZY_LOAD_SYMBOLS=100
MAX_CONCURRENT_LOADS=15

# Symbol selection
MAX_SYMBOLS=100
SYMBOL_SELECTION_STRATEGY=quality
MIN_DAILY_VOLUME_USDT=1000000
MIN_MARKET_CAP_USD=1000000000
```

### **Database Configuration**
```bash
# Data retention and size limits
DB_CLEANUP_DAYS=7
DB_MAX_SIZE_MB=200
DB_MAX_RECORDS=1000000
DB_AUTO_CLEANUP_ENABLED=1
DB_CLEANUP_INTERVAL_HOURS=6
```

### **Risk Management**
```bash
DEFAULT_SL_PERCENT=0.02
DEFAULT_TP_PERCENTS=0.015,0.03,0.05,0.08
MAX_LEVERAGE=20
FILTER_BY_MARKET_CAP=0
```

## **Operation Modes**

### **Live Trading Mode (Production)**
```bash
SIMULATION_MODE=0
DATA_TESTING=0
```
**Characteristics:**
- Real market signals with full validation
- **Strict signal conditions**: RSI < 40 for BUY, RSI > 60 for SELL
- **Volume confirmation**: Required for all signals
- **Market regime filtering**: Signals rejected if inappropriate
- **Signal cooldown**: Timeframe-based (15m=15min, 1h=1hour, 4h=4hours)
- **Higher timeframe confirmation**: Required for signal validation
- **Rate limiting**: Full protection enabled

### **Simulation Mode (Testing)**
```bash
SIMULATION_MODE=1
DATA_TESTING=0
```
**Characteristics:**
- Real market data with **relaxed signal conditions**
- **Relaxed RSI**: Any RSI level accepted (no 40/60 thresholds)
- **Volume confirmation**: Bypassed (always true)
- **Market regime filtering**: Disabled
- **Signal cooldown**: 5 minutes (300 seconds)
- **Rate limiting**: Full protection enabled

### **Data Testing Mode (Development)**
```bash
DATA_TESTING=1
```
**Characteristics:**
- **Artificial test data**: Uses generated OHLCV data
- **Immediate signals**: Generates test signals instantly on startup
- **Default symbols**: BTCUSDT, ETHUSDT, BNBUSDT if none configured
- **Rate limiting**: Disabled for testing

## **Performance Metrics**

### **Expected Resource Usage**
- **Memory**: 200-500MB (depending on symbol count and lazy loading)
- **CPU**: 10-30% during active trading
- **Database**: 50-75MB/month growth (with auto-cleanup)
- **Network**: 1-5 Mbps (WebSocket + API calls)
- **API Usage**: 50-200 requests/hour (with rate limiting)

### **Signal Frequency**
- **Live mode**: 1-5 signals per hour (strict conditions)
- **Simulation mode**: 5-15 signals per hour (relaxed conditions)
- **Data testing**: Immediate test signals on startup

### **Rate Limiting Performance**
- **Weight usage**: Typically 10-30% of 1200 limit
- **Request queuing**: 0-5 seconds delay when approaching limits
- **API efficiency**: 60-80% reduction in API calls with lazy loading
- **Concurrent handling**: 15+ simultaneous requests with rate limiting

## **Docker Deployment**

### **Build and Run**
```bash
# Build the image
docker build -t tele-bot-trading .

# Run with environment file
docker run -d --name trading-bot \
  --env-file .env \
  -v $(pwd)/charts:/app/charts \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/trading_bot.db:/app/trading_bot.db \
  tele-bot-trading
```

### **Docker Deployment**
```bash
# Build and run with Docker
docker build -t tele-bot-trading .
docker run -d --name trading-bot \
  --env-file .env \
  -v $(pwd)/charts:/app/charts \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/trading_bot.db:/app/trading_bot.db \
  tele-bot-trading
```

### **Monitoring**
```bash
# Check logs
docker logs -f trading-bot

# Check rate limiting stats
docker exec trading-bot python -c "
from binance_future_client import BinanceFuturesClient
client = BinanceFuturesClient('key', 'secret')
stats = client.get_rate_limit_stats()
print(f'Weight usage: {stats[\"weight_usage_percent\"]:.1f}%')
"

# Check database size
docker exec trading-bot ls -la trading_bot.db
```

## **Troubleshooting**

### **Rate Limiting Issues**

**For comprehensive rate limiting troubleshooting, see [RATE_LIMITING_GUIDE.md](RATE_LIMITING_GUIDE.md)**

#### **High Usage Warnings**
```bash
# Check current usage
docker logs trading-bot | grep "High API usage"

# Solutions:
# 1. Reduce symbol count
MAX_SYMBOLS=50

# 2. Increase safety margin
RATE_LIMIT_SAFETY_MARGIN=0.2

# 3. Enable lazy loading
LAZY_LOADING_ENABLED=1
```

#### **API Bans (HTTP 418)**
```bash
# If you get banned:
# 1. Stop the bot immediately
docker stop trading-bot

# 2. Wait 24-48 hours before restarting
# 3. Increase safety margin significantly
RATE_LIMIT_SAFETY_MARGIN=0.3

# 4. Reduce symbol count
MAX_SYMBOLS=20

# 5. Contact Binance support if persistent
```

### **Performance Issues**

#### **High Memory Usage**
```bash
# Check lazy loading status
docker logs trading-bot | grep "LAZY_LOADING_ENABLED"

# Solutions:
# 1. Reduce symbol limit
MAX_LAZY_LOAD_SYMBOLS=50

# 2. Enable lazy loading
LAZY_LOADING_ENABLED=1

# 3. Reduce concurrent loads
MAX_CONCURRENT_LOADS=10
```

#### **WebSocket Connection Issues**
```bash
# Check connectivity
curl -I https://fapi.binance.com/fapi/v1/ping

# Check WebSocket logs
docker logs trading-bot | grep -i "websocket\|connection"

# Test VPN/firewall
telnet fstream.binance.com 443
```

### **Database Issues**
```bash
# Check database size
docker exec trading-bot ls -la trading_bot.db

# Check database integrity
docker exec trading-bot sqlite3 trading_bot.db "PRAGMA integrity_check;"

# Reset database (nuclear option)
docker exec trading-bot rm trading_bot.db*
# Bot will recreate on restart
```

## **Security**

### **API Key Setup**
- Enable "Futures Trading" permission only
- Set IP restrictions on Binance API keys
- Use testnet for development (BINANCE_ENV=dev)
- Monitor API usage regularly

### **Rate Limiting Security**
- Always enable rate limiting in production
- Use conservative safety margins (10-20%)
- Monitor usage statistics regularly
- Set up alerts for high usage warnings

### **VPN Requirements**
Due to geo-restrictions, VPN may be required:
- Use consistent VPN location
- Avoid switching locations during operation
- Consider static IP addresses
- Test connectivity before deployment

## **Advanced Usage**

### **Custom Signal Strategies**
```python
# Modify strategy.py for custom logic
def check_signal(df):
    # Your custom signal logic here
    # Return "BUY", "SELL", or None
    pass
```

### **Custom Risk Management**
```python
# Modify risk_manager.py for custom risk rules
def calculate_position_size(symbol, price, atr):
    # Your custom position sizing logic
    pass
```

### **Database Queries**
```sql
-- Get signal statistics
SELECT symbol, COUNT(*) as signal_count, 
       AVG(price) as avg_price
FROM signals 
WHERE timestamp > datetime('now', '-7 days')
GROUP BY symbol;

-- Get API usage statistics
SELECT * FROM api_cache 
WHERE key LIKE 'rate_limit_%';
```

## **Contributing**

### **Development Setup**
1. Fork the repository
2. Create feature branch
3. Test with `SIMULATION_MODE=1`
4. Run rate limiting tests: `python test_rate_limiting.py`
5. Submit pull request

### **Code Standards**
- Follow existing code style
- Add comprehensive tests for new features
- Update documentation for new functionality
- Ensure thread safety for concurrent operations

## **Monitoring & Analytics**

### **Rate Limiting Monitoring**
```bash
# Real-time usage monitoring
docker logs -f trading-bot | grep "Rate Limiter Stats"

# Usage statistics
docker exec trading-bot python -c "
from binance_future_client import BinanceFuturesClient
client = BinanceFuturesClient('key', 'secret')
stats = client.get_rate_limit_stats()
print(f'Weight: {stats[\"current_weight_used\"]}/{stats[\"weight_limit\"]}')
print(f'Requests: {stats[\"current_requests\"]}/{stats[\"request_limit\"]}')
print(f'Blocked: {stats[\"blocked_requests\"]}')
"
```

### **Performance Monitoring**
```bash
# Memory usage
docker stats trading-bot

# Database size
docker exec trading-bot ls -la trading_bot.db

# Signal frequency
docker logs trading-bot | grep "signal" | wc -l
```

## **Best Practices**

### **Production Deployment**
1. **Always enable rate limiting** (`RATE_LIMITING_ENABLED=1`)
2. **Use conservative safety margins** (10-20%)
3. **Enable lazy loading** for better performance
4. **Limit symbol count** (50-200 symbols)
5. **Monitor usage statistics** regularly
6. **Use simulation mode** for testing
7. **Set up proper logging** and monitoring

### **API Usage Optimization**
1. **Use lazy loading** to reduce API calls
2. **Optimize request limits** (use 200-500 candles)
3. **Monitor rate limiting** statistics
4. **Use database caching** for historical data
5. **Avoid unnecessary API calls**

### **Risk Management**
1. **Start with simulation mode** for testing
2. **Use conservative position sizes**
3. **Monitor market conditions**
4. **Set appropriate stop losses**
5. **Diversify across timeframes**

## **Support**

### **Common Issues**
- Check the troubleshooting section above
- Review logs for error messages
- Test with simulation mode first
- Verify API credentials and permissions

### **Getting Help**
- Create an issue on GitHub
- Include relevant logs and configuration
- Test with `DATA_TESTING=1` for debugging
- Run `python test_rate_limiting.py` for rate limiting issues

## **License**

MIT License - see [LICENSE](LICENSE) file for details.

## **Donations**

If this project helped you make money or saved you time, consider supporting its development:

- **PayPal**: [Donate via PayPal](https://paypal.me/rizesky)
- **GitHub Sponsors**: [Sponsor on GitHub](https://github.com/sponsors/rizesky)

Every donation helps keep this project maintained and improved!