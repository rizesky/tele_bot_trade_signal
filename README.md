# Trading Signal Bot

Cryptocurrency trading signal bot for Binance Futures with technical analysis, risk management, and automated chart generation.

## Features

### Signal Generation
- Multi-timeframe analysis (15m, 30m, 1h, 4h)
- RSI + Moving Average crossover with volume confirmation
- Higher timeframe trend confirmation
- Market regime detection (trending, ranging, volatile)
- Trading session filtering (9 AM - 9 PM UTC)

### Risk Management
- ATR-based position sizing
- Market cap filtering via CoinGecko API
- Leverage and margin type management
- Configurable signal cooldown
- Multiple take profit levels

### Technical Features
- Real-time WebSocket data from Binance
- TradingView-style chart generation
- SQLite database with automatic cleanup
- Docker containerization
- Thread-safe multi-processing
- Automatic error recovery

## Key Concepts & Architecture

### Lazy Loading System

The bot uses intelligent **lazy loading** for historical data to optimize performance and API usage:

#### How It Works
```
Signal #1 for BTCUSDT-15m:
├── Load 200 historical candles (API call)
├── Store in memory + real-time updates
└── Mark as loaded

Signal #2 for BTCUSDT-15m (same symbol):
├── Check: Already loaded? ✅ YES
├── Action: REUSE existing data (no API call)
└── Use: Cached data + live updates
```

#### Benefits
- **API Efficiency**: Historical data loaded only ONCE per symbol/timeframe
- **Memory Optimized**: Maintains exactly 200 candles per symbol (sliding window)
- **Fast Response**: Subsequent signals use cached data instantly
- **Scalable**: Works efficiently with 300+ symbols

#### Configuration
```bash
# Enable/disable lazy loading (recommended: enabled)
LAZY_LOADING_ENABLED=1

# Maximum symbols to load historical data for
MAX_LAZY_LOAD_SYMBOLS=100

# Concurrent API requests for faster loading
MAX_CONCURRENT_LOADS=15
```

#### Impact of Disabling
```bash
LAZY_LOADING_ENABLED=0  # ⚠️ Not recommended
```
**Consequences:**
- 📈 **Memory**: 5-10x higher usage (all symbols loaded upfront)
- 🌐 **API Calls**: 300+ requests at startup (rate limiting risk)
- ⏱️ **Startup Time**: 5-15 minutes vs 30 seconds
- 💰 **API Costs**: Higher usage, potential rate limit penalties

### Market Regime Detection

The bot automatically detects and adapts to different market conditions:

#### Market Regimes
```python
TRENDING    # Strong directional movement (signals encouraged)
RANGING     # Sideways price action (signals discouraged) 
VOLATILE    # High volatility/noise (signals filtered)
UNCLEAR     # Insufficient data (signals cautious)
```

#### How It Works
- **Price action analysis**: Detects breakouts, ranges, and volatility
- **Adaptive filtering**: Rejects inappropriate signals for current regime
- **Risk adjustment**: Modifies signal confidence based on market state

#### Configuration Impact
```bash
# Live Trading Mode
Market regime filtering: ENABLED    # Strict regime-appropriate signals

# Simulation Mode  
Market regime filtering: DISABLED   # All signals allowed for testing
```

### Higher Timeframe Confirmation

Multi-timeframe analysis prevents false signals:

#### Confirmation Logic
```
15m signal → Check 30m trend → Check 1h trend → Check 4h trend
    ↓              ↓              ↓              ↓
If all higher timeframes align → CONFIRM signal
If higher timeframes conflict → REJECT signal
```

#### Benefits
- **Reduced false positives**: Filters out counter-trend noise
- **Better entries**: Signals align with broader market direction
- **Risk reduction**: Prevents trading against major trends

### Trading Session Filtering

Signals are filtered by trading session to avoid low-liquidity periods:

#### Active Hours
```bash
Active Trading: 09:00 - 21:00 UTC (12 hours)
Quiet Hours:    21:00 - 09:00 UTC (12 hours)
```

#### Logic
- **High liquidity**: Signals allowed during active session
- **Low liquidity**: Signals suppressed during quiet hours
- **Rationale**: Better fills and reduced slippage during active hours

### Intelligent Symbol Selection

The bot features an advanced symbol selection system for production optimization:

#### How Symbol Selection Works
```
When MAX_SYMBOLS is set:
├── Fetch all available futures symbols from Binance
├── Get 24h volume/volatility statistics for each symbol
├── Apply quality scoring algorithm
├── Filter by volume and market cap requirements
├── Select top N symbols based on strategy
└── Use selected symbols for trading
```

#### Selection Strategies

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

#### Multi-Layer Filtering
```
All Binance Futures Symbols (300+)
    ↓ USDT Pairs Only
    ↓ MIN_DAILY_VOLUME_USDT Filter
    ↓ MIN_MARKET_CAP_USD Filter (if enabled)
    ↓ Selection Strategy Applied
    ↓ MAX_SYMBOLS Limit
Final Symbol Set (50-200 symbols)
```

#### Configuration Examples

**Conservative Production**
```bash
MAX_SYMBOLS=50
SYMBOL_SELECTION_STRATEGY=quality
MIN_DAILY_VOLUME_USDT=5000000      # $5M minimum
MIN_MARKET_CAP_USD=1000000000      # $1B minimum
```

**Aggressive Production**
```bash
MAX_SYMBOLS=200
SYMBOL_SELECTION_STRATEGY=volume
MIN_DAILY_VOLUME_USDT=1000000      # $1M minimum
MIN_MARKET_CAP_USD=0               # No market cap filter
```

**Testing Setup**
```bash
MAX_SYMBOLS=20
SYMBOL_SELECTION_STRATEGY=random
MIN_DAILY_VOLUME_USDT=100000       # $100K minimum
```

#### Benefits
- **Quality Focus**: Only high-volume, active symbols selected
- **Resource Efficiency**: 60-80% reduction in memory/database usage when limited
- **Flexible Configuration**: Unlimited (undefined) or limited (set number)
- **Performance Optimization**: Reduced WebSocket streams and API calls
- **Smart Filtering**: Multi-layer filtering ensures quality symbols

### Database Management

The bot includes automatic database management to prevent unlimited growth:

- **Automatic cleanup**: Removes data older than 7 days (configurable)
- **Size monitoring**: Triggers cleanup when database exceeds 200MB
- **Data compression**: Keeps every 4th record for data older than 3 days
- **Background maintenance**: Runs cleanup every 6 hours automatically

## Installation

### Docker (Recommended)
```bash
git clone https://github.com/rizesky/tele-bot-trading.git
cd tele-bot-trading
docker build -t tele-bot-trading .
docker run -d --name trading-bot --env-file .env -v $(pwd)/charts:/app/charts tele-bot-trading
```

### Local Installation
```bash
git clone https://github.com/rizesky/tele-bot-trading.git
cd tele-bot-trading
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Configuration

Copy `env.example` to `.env` and configure:

### Required Settings
```bash
# Binance API
BINANCE_API_KEY=your_binance_api_key
BINANCE_API_SECRET=your_binance_api_secret
BINANCE_ENV=dev  # or prod

# Telegram
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
TELEGRAM_SEND_MESSAGE_URL=https://api.telegram.org/bot{token}/sendMessage
TELEGRAM_SEND_PHOTO_URL=https://api.telegram.org/bot{token}/sendPhoto

# Trading
TIMEFRAMES=15m,30m,1h,4h
SYMBOLS=  # Leave empty to auto-fetch all symbols
```

### Performance & Memory Configuration
```bash
# Lazy loading (recommended: enabled)
LAZY_LOADING_ENABLED=1
MAX_LAZY_LOAD_SYMBOLS=100
MAX_CONCURRENT_LOADS=15

# Historical data per symbol/timeframe
HISTORY_CANDLES=200

# Signal cooldown for simulation mode (live mode uses timeframe-based cooldown)
SIGNAL_COOLDOWN=300
```

### Symbol Selection & Limiting
```bash
# Maximum symbols to monitor (undefined = unlimited)
MAX_SYMBOLS=100

# Selection strategy: quality, volume, or random
SYMBOL_SELECTION_STRATEGY=quality

# Volume and market cap filters
MIN_DAILY_VOLUME_USDT=1000000
MIN_MARKET_CAP_USD=1000000000

# No refresh intervals needed - uses standard weekly refresh
```

### Database Configuration
```bash
# Data retention (days to keep historical data)
DB_CLEANUP_DAYS=7

# Size limits for automatic cleanup
DB_MAX_SIZE_MB=200
DB_MAX_RECORDS=1000000

# Automatic maintenance
DB_AUTO_CLEANUP_ENABLED=1
DB_CLEANUP_INTERVAL_HOURS=6
```

### Risk Management
```bash
DEFAULT_SL_PERCENT=0.02
DEFAULT_TP_PERCENTS=0.015,0.03,0.05,0.08
MAX_LEVERAGE=20
FILTER_BY_MARKET_CAP=0
```

## Operation Modes

### Live Trading Mode (Production)
```bash
SIMULATION_MODE=0
DATA_TESTING=0
```
**Characteristics:**
- Real market signals with full validation
- **Strict signal conditions**: RSI < 40 for BUY, RSI > 60 for SELL
- **Volume confirmation**: Required for all signals
- **Market regime filtering**: Signals rejected if inappropriate for market conditions
- **Signal cooldown**: Timeframe-based (15m=15min, 1h=1hour, 4h=4hours)
- **Higher timeframe confirmation**: Required for signal validation

### Simulation Mode (Testing)
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
- **Purpose**: Safe testing without conservative restrictions

### Data Testing Mode (Development)
```bash
DATA_TESTING=1
```
**Characteristics:**
- **Artificial test data**: Uses generated OHLCV data (not real market)
- **Immediate signals**: Generates test signals instantly on startup
- **Default symbols**: BTCUSDT, ETHUSDT, BNBUSDT if none configured
- **Purpose**: Development, debugging, and feature testing

### Trading Mode Comparison

| Feature | Live Trading | Simulation | Data Testing |
|---------|-------------|------------|--------------|
| **Data Source** | Real Market | Real Market | Artificial |
| **RSI Thresholds** | Strict (40/60) | Any Level | Test Data |
| **Volume Check** | Required | Bypassed | Test Data |
| **Market Regime** | Enforced | Bypassed | N/A |
| **Signal Cooldown** | Timeframe Duration | 5 minutes | None |
| **Purpose** | Production | Testing | Development |

## Signal Quality

Each signal includes:
- Entry price (current market price)
- Take profit levels (1.5%, 3%, 5%, 8%)
- Stop loss (2% from entry)
- Leverage (fetched from Binance)
- ATR-based position sizing guidance
- TradingView-style chart

## Technical Architecture & Performance

### Thread Safety & Concurrency

The bot uses advanced concurrency patterns for optimal performance:

- **Thread-safe data access**: All shared data protected with `threading.RLock()`
- **Async signal processing**: `ThreadPoolExecutor` prevents WebSocket blocking
- **Connection pooling**: Database connections reused across threads
- **Non-blocking chart generation**: Playwright runs in dedicated thread

### Memory Management

#### Sliding Window Data
```python
# Only keeps recent candles per symbol
HISTORY_CANDLES=200  # Per symbol/timeframe

# Example: 100 symbols × 4 timeframes × 200 candles = 80,000 total candles
```

#### Data Lifecycle
```
WebSocket Candle → Update DataFrame → Keep 200 recent → Drop oldest
```

### Signal Processing Pipeline

```
WebSocket Data → TradeManager → StrategyExecutor → TelegramClient
     ↓              ↓               ↓                  ↓
Real-time       Cache/Update    Async Process     Send Alert
WebSocket       DataFrames      (ThreadPool)      + Chart
```

### Performance Metrics

#### Expected Resource Usage
- **Memory**: 200-500MB (depending on symbol count and lazy loading)
- **CPU**: 10-30% during active trading
- **Database**: 50-75MB/month growth (with auto-cleanup)
- **Network**: 1-5 Mbps (WebSocket + API calls)

#### Signal Frequency
- **Live mode**: 1-5 signals per hour (strict conditions)
- **Simulation mode**: 5-15 signals per hour (relaxed conditions)
- **Data testing**: Immediate test signals on startup

### Database Performance

#### Connection Pooling
```bash
DB_POOL_SIZE=10  # Concurrent connections
```

#### WAL Mode (Write-Ahead Logging)
- **Concurrent reads**: Multiple threads can read simultaneously
- **Non-blocking writes**: Writers don't block readers
- **Better performance**: ~3x faster than default journaling

#### Automatic Optimization
- **VACUUM**: Reclaims space after cleanup
- **ANALYZE**: Updates query planner statistics
- **Compression**: Reduces storage by 60-80% for old data

## Docker Deployment

### Build and Run
```bash
docker build -t tele-bot-trading .
docker run -d --name trading-bot \
  --env-file .env \
  -v $(pwd)/charts:/app/charts \
  -v $(pwd)/logs:/app/logs \
  tele-bot-trading
```

### Check Logs
```bash
docker logs -f trading-bot
```

### Database Maintenance
The bot automatically manages database size, but you can monitor:
```bash
docker exec trading-bot ls -la trading_bot.db
```

## Common Configuration Pitfalls

### Symbol Configuration
```bash
# ✅ CORRECT: Leave empty for auto-fetch OR specify symbols
SYMBOLS=                    # Auto-fetch all symbols
SYMBOLS=BTCUSDT,ETHUSDT    # Specific symbols only

# ✅ CORRECT: Smart symbol limiting
MAX_SYMBOLS=100             # Limit to top 100 symbols
# MAX_SYMBOLS=               # Undefined = unlimited (comment out)
```

### Timeframe Syntax
```bash
# ❌ WRONG: Invalid timeframe format
TIMEFRAMES=15min,30min,1hour

# ✅ CORRECT: Use Binance standard format
TIMEFRAMES=15m,30m,1h,4h
```

### Trading Mode Conflicts
```bash
# ❌ WRONG: Conflicting modes
SIMULATION_MODE=1
DATA_TESTING=1      # Both enabled = undefined behavior

# ✅ CORRECT: One mode at a time
SIMULATION_MODE=1   # OR
DATA_TESTING=1      # NOT both
```

### Database Path Issues
```bash
# ❌ WRONG: Relative path in Docker
DB_PATH=./data/trading.db

# ✅ CORRECT: Absolute path or filename
DB_PATH=trading_bot.db              # In working directory
DB_PATH=/app/data/trading_bot.db    # Absolute path
```

## Troubleshooting

### Common Startup Issues

#### "No symbols found" Error
```bash
# Check symbol configuration
echo $SYMBOLS

# If empty, ensure API keys work and auto-fetch is enabled
curl -H "X-MBX-APIKEY: $BINANCE_API_KEY" \
     "https://fapi.binance.com/fapi/v1/exchangeInfo"

# Check if MAX_SYMBOLS is too restrictive
echo $MAX_SYMBOLS
```

#### "No Telegram messages" Issue
```bash
# Verify configuration
echo $TELEGRAM_BOT_TOKEN
echo $TELEGRAM_CHAT_ID

# Test Telegram connectivity
curl -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
     -d "chat_id=$TELEGRAM_CHAT_ID&text=Test message"
```

#### Database Connection Errors
```bash
# Check file permissions
ls -la trading_bot.db*

# Reset database (nuclear option)
rm trading_bot.db*
# Bot will recreate on restart
```

### Performance Troubleshooting

#### High Memory Usage
```bash
# Check lazy loading status
docker logs trading-bot | grep "LAZY_LOADING_ENABLED"

# Reduce symbol limit
MAX_LAZY_LOAD_SYMBOLS=50  # in .env

# Or disable lazy loading completely
LAZY_LOADING_ENABLED=0   # ⚠️ Not recommended
```

#### WebSocket Connection Issues
```bash
# Check connectivity
curl -I https://fapi.binance.com/fapi/v1/ping

# Check WebSocket logs
docker logs trading-bot | grep -i "websocket\|connection"

# Test VPN/firewall
telnet fstream.binance.com 443
```

#### Chart Generation Failures
```bash
# Check Playwright browser
docker exec trading-bot ls -la /usr/bin/chromium

# Check chart directory permissions
docker exec trading-bot ls -la charts/

# Manual chart test
docker exec trading-bot python -c "
from playwright.async_api import async_playwright
import asyncio
async def test(): 
    p = await async_playwright().start()
    b = await p.chromium.launch()
    await b.close()
    await p.stop()
    print('Playwright OK')
asyncio.run(test())
"
```

## Security

### API Key Setup
- Enable "Futures Trading" permission only
- Set IP restrictions on Binance API keys
- Use testnet for development (BINANCE_ENV=dev)

### VPN Requirements
Due to geo-restrictions, VPN may be required in certain regions:
- Use consistent VPN location
- Avoid switching locations during operation
- Consider static IP addresses

## Development

### Adding New Features
1. Fork the repository
2. Create feature branch
3. Test with SIMULATION_MODE=1
4. Submit pull request

### Database Schema
The bot uses SQLite with automatic migrations:
- `historical_data`: OHLCV data with automatic cleanup
- `signals`: Trading signals with metadata
- `bot_state`: Persistent configuration
- `api_cache`: Cached API responses

## Donations

If this project helped you make money or saved you time, consider supporting its development:

- **PayPal**: [Donate via PayPal](https://paypal.me/rizesky)
- **GitHub Sponsors**: [Sponsor on GitHub](https://github.com/sponsors/rizesky)

Every donation helps keep this project maintained and improved! 🙏

## License

MIT License - see LICENSE file for details.