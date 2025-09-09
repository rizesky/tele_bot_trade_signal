import os

from dotenv import load_dotenv

load_dotenv()

def _get_symbols_from_env() -> list[str]:
    """Helper function to get symbols from the environment and handle empty values."""
    env_symbols = os.getenv("SYMBOLS", "")
    if env_symbols:
        return [s.strip().upper() for s in env_symbols.split(",")]
    return []

def _get_timeframes_from_env() -> list[str]:
    """Helper function to get timeframes from the environment with default values."""
    env_timeframes = os.getenv("TIMEFRAMES", "15m,30m,1h,4h")
    if env_timeframes:
        return [tf.strip() for tf in env_timeframes.split(",")]
    return ["15m", "30m", "1h", "4h"]


BINANCE_WS_URL = os.getenv("BINANCE_WS_URL")
BINANCE_ENV=os.getenv("BINANCE_ENV", "dev")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")


SYMBOLS = _get_symbols_from_env()
TIMEFRAMES = _get_timeframes_from_env()

MAX_LEVERAGE = os.getenv("MAX_LEVERAGE", "20")
FILTER_BY_MARKET_CAP= True if int(os.getenv("FILTER_BY_MARKET_CAP", 0)) == 1 else False # Default false

# Leverage-based TP/SL configuration
LEVERAGE_BASED_TP_SL_ENABLED = True if int(os.getenv("LEVERAGE_BASED_TP_SL_ENABLED", 1)) == 1 else False
LEVERAGE_BASE_RISK_PERCENT = float(os.getenv("LEVERAGE_BASE_RISK_PERCENT", "2.0"))  # Base risk per trade
LEVERAGE_BASE_TP_PERCENT = float(os.getenv("LEVERAGE_BASE_TP_PERCENT", "1.0"))  # Base TP distance
LEVERAGE_MIN_SL_DISTANCE = float(os.getenv("LEVERAGE_MIN_SL_DISTANCE", "0.1"))  # Minimum SL distance %
LEVERAGE_MAX_SL_DISTANCE = float(os.getenv("LEVERAGE_MAX_SL_DISTANCE", "5.0"))  # Maximum SL distance %
LEVERAGE_MIN_TP_DISTANCE = float(os.getenv("LEVERAGE_MIN_TP_DISTANCE", "0.2"))  # Minimum TP distance %
LEVERAGE_MAX_TP_DISTANCE = float(os.getenv("LEVERAGE_MAX_TP_DISTANCE", "3.0"))  # Maximum TP distance %

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_SEND_MESSAGE_URL = os.getenv("TELEGRAM_SEND_MESSAGE_URL", "https://api.telegram.org/bot{token}/sendMessage").format(token=TELEGRAM_BOT_TOKEN) if TELEGRAM_BOT_TOKEN else None
TELEGRAM_SEND_PHOTO_URL = os.getenv("TELEGRAM_SEND_PHOTO_URL", "https://api.telegram.org/bot{token}/sendPhoto").format(token=TELEGRAM_BOT_TOKEN) if TELEGRAM_BOT_TOKEN else None

DEFAULT_SL_PERCENT = float(os.getenv("DEFAULT_SL_PERCENT", 0.02))
DEFAULT_TP_PERCENTS = [float(x) for x in os.getenv("DEFAULT_TP_PERCENTS", "0.015,0.03,0.05,0.08").split(",")]


HISTORY_CANDLES = int(os.getenv("HISTORY_CANDLES", 200))
SIGNAL_COOLDOWN = int(os.getenv("SIGNAL_COOLDOWN", 600))
DATA_TESTING = True if int(os.getenv("DATA_TESTING", 0))==1 else False # default false
SIMULATION_MODE = True if int(os.getenv("SIMULATION_MODE", 0)) == 1 else False  # Default false

# Lazy loading configuration for historical data
LAZY_LOADING_ENABLED = True if int(os.getenv("LAZY_LOADING_ENABLED", 1)) == 1 else False  # Default true
MAX_LAZY_LOAD_SYMBOLS = int(os.getenv("MAX_LAZY_LOAD_SYMBOLS", 100))  # Maximum symbols to lazy load historical data for
MAX_CONCURRENT_LOADS = int(os.getenv("MAX_CONCURRENT_LOADS", 15))  # Maximum concurrent API requests for historical data

# Symbol selection and limiting (production-ready)
MAX_SYMBOLS = int(os.getenv("MAX_SYMBOLS", 0)) if os.getenv("MAX_SYMBOLS") is not None else None  # Maximum symbols to monitor (None/undefined = unlimited)
SYMBOL_SELECTION_STRATEGY = os.getenv("SYMBOL_SELECTION_STRATEGY", "quality").lower()  # quality, volume, random
MIN_DAILY_VOLUME_USDT = float(os.getenv("MIN_DAILY_VOLUME_USDT", 1000000))  # Minimum $1M daily volume
MIN_MARKET_CAP_USD = float(os.getenv("MIN_MARKET_CAP_USD", 0))  # Minimum market cap in USD (0 = disabled, requires CoinGecko)

# Database configuration
DB_PATH = os.getenv("DB_PATH", "trading_bot.db")  # SQLite database path
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", 10))  # Connection pool size
DB_ENABLE_PERSISTENCE = True if int(os.getenv("DB_ENABLE_PERSISTENCE", 1)) == 1 else False  # Enable database persistence
DB_CLEANUP_DAYS = int(os.getenv("DB_CLEANUP_DAYS", 7))  # Days to keep historical data (reduced from 30 to 7)

# Database size management
DB_MAX_SIZE_MB = float(os.getenv("DB_MAX_SIZE_MB", 200))  # Maximum database size in MB before cleanup
DB_MAX_RECORDS = int(os.getenv("DB_MAX_RECORDS", 1000000))  # Maximum total records before cleanup
DB_AUTO_CLEANUP_ENABLED = True if int(os.getenv("DB_AUTO_CLEANUP_ENABLED", 1)) == 1 else False  # Enable automatic cleanup
DB_CLEANUP_INTERVAL_HOURS = int(os.getenv("DB_CLEANUP_INTERVAL_HOURS", 6))  # Hours between cleanup checks

# Rate limiting configuration
RATE_LIMITING_ENABLED = True if int(os.getenv("RATE_LIMITING_ENABLED", 1)) == 1 else False  # Enable rate limiting
RATE_LIMIT_SAFETY_MARGIN = float(os.getenv("RATE_LIMIT_SAFETY_MARGIN", 0.1))  # 10% safety margin
RATE_LIMIT_WARNING_THRESHOLD = float(os.getenv("RATE_LIMIT_WARNING_THRESHOLD", 0.8))  # 80% warning threshold
RATE_LIMIT_MAX_WEIGHT_PER_MINUTE = int(os.getenv("RATE_LIMIT_MAX_WEIGHT_PER_MINUTE", 1200))  # Binance standard limit
RATE_LIMIT_MAX_REQUESTS_PER_MINUTE = int(os.getenv("RATE_LIMIT_MAX_REQUESTS_PER_MINUTE", 1200))  # Binance standard limit
RATE_LIMIT_RETRY_DELAY = float(os.getenv("RATE_LIMIT_RETRY_DELAY", 1.0))  # Retry delay in seconds
RATE_LIMIT_MAX_RETRIES = int(os.getenv("RATE_LIMIT_MAX_RETRIES", 3))  # Maximum retry attempts
RATE_LIMIT_DETAILED_LOGGING = True if int(os.getenv("RATE_LIMIT_DETAILED_LOGGING", 1)) == 1 else False  # Enable detailed logging
RATE_LIMIT_LOG_INTERVAL = int(os.getenv("RATE_LIMIT_LOG_INTERVAL", 60))  # Log interval in seconds


