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
    """Helper function to get timeframes from the environment and handle empty values."""
    env_timeframes = os.getenv("TIMEFRAMES", "")
    if env_timeframes:
        return [tf.strip() for tf in env_timeframes.split(",")]
    return []


BINANCE_WS_URL = os.getenv("BINANCE_WS_URL")
BINANCE_ENV=os.getenv("BINANCE_ENV", "dev")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")


SYMBOLS = _get_symbols_from_env()
TIMEFRAMES = _get_timeframes_from_env()

MAX_LEVERAGE = os.getenv("MAX_LEVERAGE", "20")
FILTER_BY_MARKET_CAP= True if int(os.getenv("FILTER_BY_MARKET_CAP", 0)) == 1 else False # Default true

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_SEND_MESSAGE_URL = os.getenv("TELEGRAM_SEND_MESSAGE_URL").format(token=TELEGRAM_BOT_TOKEN)
TELEGRAM_SEND_PHOTO_URL = os.getenv("TELEGRAM_SEND_PHOTO_URL").format(token=TELEGRAM_BOT_TOKEN)

DEFAULT_SL_PERCENT = float(os.getenv("DEFAULT_SL_PERCENT", 0.02))
DEFAULT_TP_PERCENTS = [float(x) for x in os.getenv("DEFAULT_TP_PERCENTS", "0.015,0.03,0.05,0.08").split(",")]


HISTORY_CANDLES = int(os.getenv("HISTORY_CANDLES", 200))
SIGNAL_COOLDOWN = int(os.getenv("SIGNAL_COOLDOWN", 600))
DATA_TESTING = True if int(os.getenv("DATA_TESTING", 0))==1 else False # default false
SIMULATION_MODE = True if int(os.getenv("SIMULATION_MODE", 0)) == 1 else False  # Default false


