import logging
import signal
import threading
import time

import pandas as pd

import config
from client_binance_http import BinanceFuturesClient
from client_binance_ws import BinanceWS
from charting import plot_chart
from config import DATA_TESTING, SYMBOLS, TIMEFRAMES, SIMULATION_MODE, HISTORY_CANDLES
from strategy import check_signal
from client_telegram import format_signal_message, send_message_with_retry

klines = {}
signal_cooldown = {}
historical_loaded = {}


binance_client=BinanceFuturesClient(api_key=config.BINANCE_API_KEY,api_secret=config.BINANCE_API_SECRET)

def historical_loader_exists()->bool:
    try:
        return binance_client.load_historical_data is not None
    except ImportError:
        logging.warning("Historical data loader not available - using only real-time data")
        return False


HAS_HISTORICAL_LOADER=historical_loader_exists()

def initialize_historical_data():
    """Preload historical data for all symbols and timeframes"""
    if not HAS_HISTORICAL_LOADER:
        return


    for symbol in SYMBOLS:
        logging.info(f"Loading historical data for {symbol} {TIMEFRAMES}")
        for interval in TIMEFRAMES:
            key = (symbol, interval)
            try:

                historical_df = binance_client.load_historical_data(symbol, interval, limit=HISTORY_CANDLES)

                if not historical_df.empty:
                    klines[key] = historical_df
                    historical_loaded[key] = True
                    logging.info(f"Loaded {len(historical_df)} historical candles for {symbol} {interval}")
                else:
                    logging.error(f"Failed to load historical data for {symbol} {interval}")

            except Exception as e:
                logging.error(f"Error loading historical data for {symbol} {interval}: {e}")


def on_kline(k):
    symbol = k["s"]
    interval = k["i"]
    key = (symbol, interval)

    # logging.info(f"Kline: {k}")

    if key not in klines:
        klines[key] = pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])

    # gunakan open time (t) sebagai index
    ts = pd.to_datetime(k["t"], unit="ms")

    new_row = pd.DataFrame([{
        'open': float(k["o"]),
        'high': float(k["h"]),
        'low': float(k["l"]),
        'close': float(k["c"]),
        'volume': float(k["v"])
    }], index=[ts])

    # concat tanpa ignore_index supaya tetap DatetimeIndex
    klines[key] = pd.concat([klines[key], new_row])
    klines[key].sort_index(inplace=True)

    # keep hanya HISTORY_CANDLES terakhir
    if len(klines[key]) > HISTORY_CANDLES:
        klines[key] = klines[key].iloc[-HISTORY_CANDLES:]

    process_signals(symbol, interval, klines[key])


def process_signals(symbol, interval, df):
    """Process signals based on available data"""
    # We can process signals with as little as 20 candles for testing
    min_candles_needed = 20 if SIMULATION_MODE or DATA_TESTING else 50

    if len(df) < min_candles_needed:
        logging.warn(f"Skipping signals. Total candles data does not meet the minimum required data which is {min_candles_needed}, current {len(df)}")
        return

    # Check cooldown
    key = (symbol, interval)
    current_time = time.time()
    last_signal_time = signal_cooldown.get(key, 0)

    # Shorter cooldown for simulation/testing
    cooldown_seconds = 300 if SIMULATION_MODE else 600  # 5 min vs 10 min

    if current_time - last_signal_time < cooldown_seconds:
        return

    signal_info = check_signal(df)

    if signal_info:
        last_price = df["close"].iloc[-1]

        if signal_info == "BUY":
            entry_prices = [last_price]
            tp_list = [last_price * (1 + i * 0.01) for i in range(1, 5)]
            sl = last_price * 0.99
        elif signal_info == "SELL":
            entry_prices = [last_price]
            tp_list = [last_price * (1 - i * 0.01) for i in range(1, 5)]
            sl = last_price * 1.01
        else:
            return

        # Generate chart
        chart_path = plot_chart(ohlc_df=df,symbol= symbol,timeframe= interval, take_profit_levels=tp_list, stop_loss_level=sl)

        # Prepare message
        if SIMULATION_MODE:
            original_msg = format_signal_message(symbol, interval, entry_prices, tp_list, sl)
            msg = f"🚦 [SIMULATION] 🚦\n{original_msg}"
        else:
            msg = format_signal_message(symbol, interval, entry_prices, tp_list, sl)

        send_message_with_retry(msg, chart_path)

        app_mode = "SIMULATION" if SIMULATION_MODE else "REAL TRADE"
        logging.info(f"Sent {signal_info} signal for {symbol}-{interval} ({app_mode})")

        signal_cooldown[key] = current_time


def run_testing_mode():
    """Run in DATA_TESTING mode - generate immediate test signals"""
    logging.info("Running in DATA_TESTING mode - generating test signals")

    for symbol in SYMBOLS:
        for interval in TIMEFRAMES:
            try:
                from charting import create_realistic_test_data
                # Create smaller test dataset for faster testing
                df = create_realistic_test_data(periods=50, base_price=30000)

                test_signal = "BUY" if hash(symbol + interval) % 2 == 0 else "SELL"
                last_price = df['close'].iloc[-1]

                if test_signal == "BUY":
                    entry_prices = [last_price]
                    tp_list = [last_price * (1 + i * 0.01) for i in range(1, 5)]
                    sl = last_price * 0.99
                else:
                    entry_prices = [last_price]
                    tp_list = [last_price * (1 - i * 0.01) for i in range(1, 5)]
                    sl = last_price * 1.01

                chart_path = plot_chart(df, symbol, interval, take_profit_levels=tp_list, stop_loss_level=sl)
                msg = format_signal_message(symbol, interval, entry_prices, tp_list, sl)
                send_message_with_retry(msg, chart_path)

                logging.info(f"TESTING: {test_signal} signal sent for {symbol} {interval}")
                time.sleep(1)  # Short delay between symbols

            except Exception as e:
                logging.error(f"Error in testing mode for {symbol} {interval}: {str(e)}")
                continue


if __name__ == "__main__":
    logging.info(f"""App Configuration:
    Historical Loader: {HAS_HISTORICAL_LOADER}
    Data Testing mode: {DATA_TESTING}
    Simulation mode: {SIMULATION_MODE}""")

    # Preload historical data if available
    if HAS_HISTORICAL_LOADER and not DATA_TESTING:
        initialize_historical_data()

    ws = BinanceWS(on_kline)
    stop_event = threading.Event()


    def shutdown(signum=None, frame=None):
        logging.info("Shutdown signal received, stopping...")
        ws.stop()
        stop_event.set()


    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)


    if DATA_TESTING:
        logging.info("Starting in DATA_TESTING mode")
        run_testing_mode()
        logging.info("DATA_TESTING mode completed")
    else:
        mode = "SIMULATION" if SIMULATION_MODE else "LIVE TRADING"
        logging.info(f"Starting in {mode} mode")

        ws.run()

        try:
            while not stop_event.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            shutdown()