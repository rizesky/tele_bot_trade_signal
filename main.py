import logging
import signal
import threading
import time

import pandas as pd

from binance_ws import BinanceWS
from charting import plot_chart, create_realistic_test_data
from config import DATA_TESTING
from strategy import check_signal
from telegram import format_signal_message, send_message_with_retry

klines = {}

# ----- Fungsi trigger -----
def on_kline(k):
    symbol = k["s"]
    interval = k["i"]

    if (symbol, interval) not in klines:
        klines[(symbol, interval)] = []

    klines[(symbol, interval)].append(float(k["c"]))

    if DATA_TESTING:
        # Create realistic test data
        df = create_realistic_test_data(periods=200, base_price=30000)
        last_price = df['close'].iloc[-1]

        entry_prices = [last_price]
        tp_list = [last_price * (1 + i * 0.01) for i in range(1, 5)]
        sl = last_price * 0.99

        chart_path = plot_chart(df, symbol, interval, tp_list=tp_list, sl=sl)
        msg = format_signal_message(symbol, interval, entry_prices, tp_list, sl)
        send_message_with_retry(msg, chart_path)
        logging.info("TESTING mode: dummy signal sent.")
        return

    # Real/prod
    if len(klines[(symbol, interval)]) >= 100:
        df = pd.DataFrame({"close": klines[(symbol, interval)][-100:]})
        signal_info = check_signal(df)

        if signal_info:  # trigger sinyal
            last_price = df["close"].iloc[-1]

            if signal_info == "BUY":
                entry_prices = [last_price]
                tp_list = [last_price * (1 + i * 0.01) for i in range(1, 5)]
                sl = last_price * 0.99
            elif signal_info == "SELL":
                entry_prices = [last_price]
                tp_list = [last_price * (1 - i * 0.01) for i in range(1, 5)]
                sl = last_price * 1.01

            chart_path = plot_chart(df, symbol, interval, tp_list=tp_list, sl=sl)
            msg = format_signal_message(symbol, interval, entry_prices, tp_list, sl)
            send_message_with_retry(msg, chart_path)
            logging.info(f"Signal sent for {symbol} {interval}")


if __name__ == "__main__":
    ws = BinanceWS(on_kline)

    stop_event = threading.Event()


    def shutdown(signum=None, frame=None):
        logging.info("Shutdown signal received, stopping...")
        ws.stop()
        stop_event.set()


    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    ws.run()

    # Tunggu sampai stop_event diset
    try:
        while not stop_event.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown()
