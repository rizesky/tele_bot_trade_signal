import os

from dotenv import load_dotenv

load_dotenv()

import logging
import sys

BINANCE_WS_URL = os.getenv("BINANCE_WS_URL")
BINANCE_ENV=os.getenv("BINANCE_ENV", "dev")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")

SYMBOLS = [s.strip().upper() for s in os.getenv("SYMBOLS", "").split(",")]
TIMEFRAMES = [tf.strip() for tf in os.getenv("TIMEFRAMES", "").split(",")]
LEVERAGE = os.getenv("LEVERAGE", "20x [Isolated]")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_SEND_MESSAGE_URL = os.getenv("TELEGRAM_SEND_MESSAGE_URL").format(token=TELEGRAM_BOT_TOKEN)
TELEGRAM_SEND_PHOTO_URL = os.getenv("TELEGRAM_SEND_PHOTO_URL").format(token=TELEGRAM_BOT_TOKEN)

DEFAULT_SL_PERCENT = float(os.getenv("DEFAULT_SL_PERCENT", 0.02))
DEFAULT_TP_PERCENTS = [float(x) for x in os.getenv("DEFAULT_TP_PERCENTS", "0.015,0.03,0.05,0.08").split(",")]

MAX_SYMBOLS_FOR_TEST = int(os.getenv("MAX_SYMBOLS_FOR_TEST", 120))
HISTORY_CANDLES = int(os.getenv("HISTORY_CANDLES", 200))
SIGNAL_COOLDOWN = int(os.getenv("SIGNAL_COOLDOWN", 600))
DATA_TESTING = True if int(os.getenv("DATA_TESTING", 0))==1 else False # default false
SIMULATION_MODE = True if int(os.getenv("SIMULATION_MODE", 0)) == 1 else False  # Default false


# basic config
logging.basicConfig(

    level=logging.INFO, # change to debug for development
    format='%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),  # console
        # logging.FileHandler("bot.log")      # file appender optional
    ]
)

logger = logging.getLogger("TradingBot")

