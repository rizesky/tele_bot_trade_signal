import os
from dotenv import load_dotenv


load_dotenv()

import logging
import sys

BINANCE_WS_URL = os.getenv("BINANCE_WS_URL")
SYMBOLS = [s.strip().upper() for s in os.getenv("SYMBOLS", "").split(",")]
TIMEFRAMES = [tf.strip() for tf in os.getenv("TIMEFRAMES", "").split(",")]

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_SEND_MESSAGE_URL = os.getenv("TELEGRAM_SEND_MESSAGE_URL").format(token=TELEGRAM_BOT_TOKEN)
TELEGRAM_SEND_PHOTO_URL = os.getenv("TELEGRAM_SEND_PHOTO_URL").format(token=TELEGRAM_BOT_TOKEN)

LEVERAGE = os.getenv("LEVERAGE", "20x [Isolated]")
DEFAULT_SL_PERCENT = float(os.getenv("DEFAULT_SL_PERCENT", 0.02))
DEFAULT_TP_PERCENTS = [float(x) for x in os.getenv("DEFAULT_TP_PERCENTS", "0.015,0.03,0.05,0.08").split(",")]

MAX_SYMBOLS_FOR_TEST = int(os.getenv("MAX_SYMBOLS_FOR_TEST", 120))
HISTORY_CANDLES = int(os.getenv("HISTORY_CANDLES", 200))
SIGNAL_COOLDOWN = int(os.getenv("SIGNAL_COOLDOWN", 600))
APP_MODE=os.getenv("APP_MODE", "dev")
DATA_TESTING = False if int(os.getenv("DATA_TESTING", 0))<=0 else True # default false


# basic config
logging.basicConfig(
    level=logging.INFO,  # bisa diubah ke INFO di production
    format='%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),  # tampil di console
        # logging.FileHandler("bot.log")      # simpan ke file
    ]
)

logger = logging.getLogger("TradingBot")

