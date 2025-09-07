# 🚀 Trading Signal Bot

A sophisticated trading signal bot designed for Binance Futures that provides high-quality trading signals with advanced risk management, market analysis, and real-time chart generation.

## ✨ Key Features

### 🎯 **Signal Generation**
- **Multi-timeframe Analysis**: Monitors 15m, 30m, 1h, and 4h timeframes
- **Advanced Technical Analysis**: RSI + Moving Average crossover with volume confirmation
- **Higher Timeframe Confirmation**: Filters signals based on higher timeframe trends
- **Market Regime Detection**: Adapts to trending, ranging, volatile, and unclear market conditions
- **Session Filtering**: Only trades during active market hours (9 AM - 9 PM UTC)

### 🛡️ **Risk Management**
- **ATR-based Position Sizing**: Dynamic position sizing based on market volatility
- **Market Cap Filtering**: Filters symbols by market capitalization using CoinGecko API
- **Leverage Management**: Fetches actual leverage and margin type from Binance API
- **Signal Cooldown**: Prevents signal spam with configurable cooldown periods
- **Stop Loss & Take Profit**: Multiple TP levels with percentage-based SL

### 📊 **Real-time Data & Charts**
- **WebSocket Integration**: Real-time K-line data from Binance WebSocket API
- **Chart Generation**: TradingView-style charts with TP/SL levels
- **Data Validation**: Comprehensive input validation and error handling
- **Thread Safety**: Robust multi-threading with proper synchronization

### 🔧 **Production-Ready Features**
- **Error Recovery**: Automatic WebSocket reconnection with exponential backoff
- **Lazy Loading**: Efficient historical data loading (only loads what's needed)
- **Concurrent Loading**: 15x faster data loading with ThreadPoolExecutor
- **SQLite Persistence**: Database storage with connection pooling and migrations
- **Configuration Validation**: Startup validation of all critical settings
- **Docker Support**: Containerized deployment with persistent storage
- **Simulation Mode**: Safe testing environment with reduced requirements

## 🆕 **New Advanced Features**

### **Volume Confirmation**
- Validates signals with volume analysis
- Requires 20% above average volume for signal confirmation
- Prevents false signals during low-volume periods

### **Market Regime Detection**
- **TRENDING**: Strong directional movement (ADX > 25)
- **RANGING**: Sideways movement (ADX < 15)
- **VOLATILE**: High volatility periods (> 3% daily volatility)
- **UNCLEAR**: Uncertain market conditions (signals filtered out)

### **Higher Timeframe Analysis**
- 15m signals confirmed by 1h trend
- 30m signals confirmed by 4h trend
- 1h signals confirmed by 4h trend
- 4h signals confirmed by 1d trend

### **ATR-based Risk Guidance**
- Provides volatility-based risk recommendations using Average True Range
- Adapts risk suggestions based on market volatility
- No account balance integration required

### **Enhanced Error Handling**
- WebSocket reconnection with exponential backoff
- Graceful API failure handling with fallback defaults
- Chart generation fallback (sends signal without chart if needed)
- Comprehensive input validation for all external data

### **Database & Performance**
- **SQLite Integration**: Persistent storage for historical data, signals, and bot state
- **Connection Pooling**: Optimized database access with configurable pool size
- **Concurrent Loading**: 15x faster historical data loading with parallel API requests
- **Smart Caching**: Multi-layer caching (memory + database) reduces API calls by 80%
- **Migration System**: Automatic database schema updates with version tracking
- **Data Cleanup**: Configurable retention period to manage database size 

## 🚀 Getting Started

### Prerequisites
- **Python 3.10+** (required for modern async features)
- **Telegram Bot Token** (create at @BotFather)
- **Binance Futures API** (with futures trading enabled)
- **Docker** (for containerized deployment)
- **VPN** (if in geo-restricted location)

### 📋 Installation

#### **Method 1: Docker (Recommended)**
```bash
# Clone the repository
git clone https://github.com/rizesky/tele-bot-trading.git
cd tele-bot-trading

# Build the Docker image
docker build -t tele-bot-trading .

# Run with environment file
docker run -d --name trading-bot --env-file .env -v $(pwd)/charts:/app/charts tele-bot-trading
```

#### **Method 2: Local Installation**
```bash
# Clone and setup
git clone https://github.com/rizesky/tele-bot-trading.git
cd tele-bot-trading

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the bot
python main.py
```

### ⚙️ Configuration

#### **Environment Variables (.env)**
Copy `env.example` to `.env` and fill in your values:

```bash
cp env.example .env
# Edit .env with your actual API keys and configuration
```



#### **Configuration Options Explained**

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `SYMBOLS` | Trading pairs to monitor (optional) | Auto-fetch from Binance | `BTCUSDT,ETHUSDT` or leave empty |
| | **Note**: If SYMBOLS is empty or not set, the bot will automatically fetch all available futures symbols from Binance API | | |
| `TIMEFRAMES` | Timeframes to analyze | Required | `15m,30m,1h,4h` |
| `HISTORY_CANDLES` | Historical data to load | 200 | `200` |
| `SIGNAL_COOLDOWN` | Seconds between signals | 600 | `600` (10 min) |
| `DEFAULT_SL_PERCENT` | Stop loss percentage | 0.02 | `0.02` (2%) |
| `DEFAULT_TP_PERCENTS` | Take profit levels | 0.015,0.03,0.05,0.08 | `0.015,0.03,0.05,0.08` |
| `LAZY_LOADING_ENABLED` | Enable efficient data loading | 1 | `1` (enabled) |
| `MAX_LAZY_LOAD_SYMBOLS` | Max symbols for historical data | 100 | `100` |
| `MAX_CONCURRENT_LOADS` | Concurrent API requests for loading | 15 | `15` |
| `SIMULATION_MODE` | Test mode (no real trading) | 0 | `1` (enabled) |
| `DATA_TESTING` | Generate test signals | 0 | `1` (enabled) |
| `BINANCE_ENV` | Binance environment | dev | `dev` or `prod` |
| `BINANCE_WS_URL` | WebSocket URL (optional) | Auto | `wss://fstream.binance.com/ws/` |
| `MAX_LEVERAGE` | Maximum leverage to use | 20 | `20` |
| `FILTER_BY_MARKET_CAP` | Enable market cap filtering | 0 | `1` (enabled) |

**Database Configuration:**

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `DB_ENABLE_PERSISTENCE` | Enable SQLite database persistence | 1 | `1` (enabled) |
| `DB_PATH` | SQLite database file path | trading_bot.db | `trading_bot.db` |
| `DB_POOL_SIZE` | Database connection pool size | 10 | `10` |
| `DB_CLEANUP_DAYS` | Days to keep historical data | 30 | `30` |

### 🔧 **Advanced Configuration**

#### **Market Session Hours**
Edit `strategy.py` to adjust trading hours:
```python
def is_market_session_active():
    from util import now_utc
    current_utc = now_utc()
    current_hour = current_utc.hour
    return 9 <= current_hour <= 21  # 9 AM to 9 PM UTC
```


#### **Volume Confirmation Threshold**
Adjust volume requirements in `strategy.py`:
```python
def has_volume_confirmation(df, volume_threshold=1.2):  # 20% above average
```

#### **Market Regime Sensitivity**
Modify regime detection in `strategy.py`:
```python
# Volatility threshold
if current_volatility > 3.0:  # 3% daily volatility
    return 'VOLATILE'

# Trend strength threshold  
elif current_adx > 25:  # Strong trend
    return 'TRENDING'
```

## 🎯 Usage

### **Quick Start**
```bash
# 1. Configure the .env file
cp env.example .env
# Edit .env with your API keys and settings

# 2. Run with Docker
docker run -d --name trading-bot --env-file .env -v $(pwd)/charts:/app/charts tele-bot-trading

# 3. Check logs
docker logs -f trading-bot
```

### **Modes of Operation**

#### **Simulation Mode** (Recommended for Testing)
```bash
# Set in .env
SIMULATION_MODE=1
DATA_TESTING=0
```
**Features:**
- Generates real signals with reduced cooldown (5 minutes vs 10 minutes)
- No actual trading - safe for testing
- Perfect for strategy validation and system testing

**Relaxed Strategy Conditions:**
- ✅ **24/7 Trading**: No trading hours restrictions
- ✅ **Volume Bypass**: Skips volume confirmation requirements
- ✅ **Simple MA Crossover**: Only requires price crossing moving average
- ✅ **No RSI Filtering**: Removes RSI overbought/oversold conditions
- ✅ **No Market Regime Filtering**: Works in any market condition (TRENDING, RANGING, VOLATILE)

*Result: Much higher signal frequency for easier testing of notifications, charting, and system behavior*

#### **Data Testing Mode** (Development)
```bash
# Set in .env  
DATA_TESTING=1
```
- Generates test signals immediately
- No real market data needed
- For development and debugging

#### **Live Trading Mode** (Production)
```bash
# Set in .env
SIMULATION_MODE=0
DATA_TESTING=0
```
**Features:**
- Real market signals with full cooldown periods (10 minutes default)
- Production-ready operation with all safety measures
- Conservative approach for actual trading

**Strict Strategy Conditions:**
- 🔒 **Trading Hours**: Respects active market session times
- 🔒 **Volume Confirmation**: Requires 20% above average volume
- 🔒 **MA + RSI**: Needs both moving average crossover AND RSI confirmation
  - BUY: Price crosses above MA + RSI < 40 (oversold recovery)
  - SELL: Price crosses below MA + RSI > 60 (overbought decline)
- 🔒 **Market Regime Filtering**: Only trades in appropriate market conditions
- 🔒 **Higher Timeframe Confirmation**: Validates signals against broader trends

*Result: Lower signal frequency but higher quality, more reliable trading signals*

## 🔍 **Signal Quality Features**

### **Signal Filtering Process**
1. **Market Session Check**: Only trades during active hours
2. **Data Validation**: Ensures sufficient historical data
3. **Higher Timeframe Confirmation**: Checks trend alignment
4. **Volume Confirmation**: Requires 20% above average volume
5. **Market Regime Detection**: Adapts to market conditions
6. **Technical Analysis**: RSI + MA crossover detection
7. **Cooldown Check**: Prevents signal spam

### **Signal Information**
Each signal includes:
- **Entry Price**: Current market price
- **Take Profit Levels**: 4 levels (1.5%, 3%, 5%, 8%)
- **Stop Loss**: 2% below/above entry
- **Leverage**: Actual leverage from Binance
- **Position Size**: ATR-based calculation
- **Chart**: TradingView-style visualization

## 🛠️ **Troubleshooting**

### **Common Issues**

#### **WebSocket Connection Problems**
```bash
# Check if Binance is accessible
curl -I https://fapi.binance.com/fapi/v1/ping

# Check logs for reconnection attempts
docker logs trading-bot | grep "WebSocket"
```

#### **Chart Generation Issues**
```bash
# Check if charts directory exists and is writable
ls -la charts/
chmod 755 charts/

# Check Playwright installation
docker exec trading-bot playwright --version
```

#### **API Rate Limiting**
```bash
# Reduce symbol count in .env
SYMBOLS=BTCUSDT,ETHUSDT  # Start with fewer symbols

# Enable lazy loading
LAZY_LOADING_ENABLED=1
MAX_LAZY_LOAD_SYMBOLS=20
```

#### **Memory Issues**
```bash
# Monitor memory usage
docker stats trading-bot

# Reduce historical data
HISTORY_CANDLES=100  # Instead of 200
```

### **Log Analysis**
```bash
# View all logs
docker logs trading-bot

# Filter for signals only
docker logs trading-bot | grep "Signal detected"

# Filter for errors
docker logs trading-bot | grep "ERROR"

# Follow logs in real-time
docker logs -f trading-bot
```

### **Performance Monitoring**
```bash
# Check resource usage
docker stats trading-bot

# Check chart generation
ls -la charts/ | wc -l

# Monitor WebSocket connections
docker logs trading-bot | grep "WebSocket"
```

## 📊 **Performance Metrics**

### **Signal Quality Indicators**
- **Volume Ratio**: Should be > 1.2x average
- **Market Regime**: Trending markets preferred
- **Higher TF Alignment**: Confirms signal direction
- **RSI Levels**: Oversold (< 40) for BUY, Overbought (> 60) for SELL

### **System Performance**
- **Memory Usage**: ~200-500MB depending on symbols
- **CPU Usage**: ~10-30% during active trading
- **Chart Generation**: ~2-5 seconds per chart
- **Signal Frequency**: 1-5 signals per hour (depending on market)

## 🔒 **Security Best Practices**

### **API Key Security**
- Use Binance API keys with **Futures Trading** enabled only
- Set **IP restrictions** on API keys
- Use **read-only** keys for data fetching


### **Deployment Security**
- Run in isolated Docker containers
- Use VPN for geo-restricted regions


## 🤝 **Contributing**

### **Development Setup**
```bash
# Clone and setup development environment
git clone https://github.com/rizesky/tele-bot-trading.git
cd tele-bot-trading

# Install development dependencies
pip install -r requirements.txt

```

### **Adding New Features**
1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Update documentation
5. Submit a pull request

## 📄 **License**

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.



## 🆘 **Support**

- **Issues**: [GitHub Issues](https://github.com/rizesky/tele-bot-trading/issues)
- **Discussions**: [GitHub Discussions](https://github.com/rizesky/tele-bot-trading/discussions)


### Important Considerations
#### Binance Geo-Restrictions and VPN Usage
Due to regulatory restrictions, Binance services are not available in all countries.
Attempting to access Binance from a restricted location, even with an API key, can lead to account being frozen or suspended. 
If located in a region where Binance is blocked, a VPN must be used.

**Cautionary List**:
 - Absolute Ban: Countries like Algeria, Bangladesh, China, Egypt, Iraq, Morocco, Nepal, Qatar, and Tunisia have strict cryptocurrency regulations that could prevent Binance access.
 - Implicit Ban/Restrictions: Many other countries, including the United States, United Kingdom, Canada, and several European nations, have complex regulations or regional restrictions.
 - Always check the official Binance website for the most up-to-date information on service availability in the area. 

**Best Practice for VPN Use with Binance**:
 - Use a reliable VPN provider.
 - Connect to a server in a supported country where there is a verified account.
 - Do not switch VPN locations while trading, as this can trigger security alerts and cause account to be locked.
 - Avoid locations with known issues. For instance, accessing Binance International from the US is a known cause of account suspension.
 - Use the API from a static IP address. Some VPNs offer static IP addresses, which is preferable to dynamic ones.