import logging
import time

from binance import MARGIN_BUY_TYPE

import config
from charting_service import ChartingService
from config import MAX_LEVERAGE
from risk_manager import RiskManager
from strategy import check_signal
from telegram_client import format_signal_message, send_message_with_retry
from trade_manager import TradeManager
from util import create_realistic_test_data


class StrategyExecutor:
    """Handles the execution of trading strategies and manages signals."""

    def __init__(self, trade_manager:TradeManager|None,charting_service:ChartingService|None,risk_manager:RiskManager|None):
        self.trade_manager = trade_manager
        self.signal_cooldown = {}
        self.charting_service = charting_service
        self.risk_manager = risk_manager

    def handle_kline(self, k):
        """Callback for new kline data from the WebSocket."""
        symbol = k["s"]
        interval = k["i"]

        # Update kline data in the trade manager
        self.trade_manager.update_kline_data(k)
        df = self.trade_manager.get_kline_data(symbol, interval)

        # Process signals with the updated data
        self.process_signals(symbol, interval, df)

    def handle_chart_callback(self,chart_path, error, symbol, interval, entry_prices, tp_list, sl, signal_info, leverage,
                              margin_type):
        """Handles the result from the chart plotting task."""
        if error:
            logging.error(f"Chart generation failed for {symbol}-{interval}: {error}")
        else:
            self._send_signal_notif(symbol=symbol, interval=interval, entry_prices=entry_prices,
                                    tp_list=tp_list, sl=sl, chart_path=chart_path, signal_info=signal_info,
                                    leverage=leverage, margin_type=margin_type)
            self.signal_cooldown[(symbol, interval)] = time.time()

    def process_signals(self, symbol, interval, df):
        """Process signals based on available data."""
        min_candles_needed = 20 if config.SIMULATION_MODE or config.DATA_TESTING else 50
        if len(df) < min_candles_needed:
            logging.warning(f"Signals skipped. Need at least {min_candles_needed} candles, currently have {len(df)}.")
            return

        key = (symbol, interval)
        current_time = time.time()
        last_signal_time = self.signal_cooldown.get(key, 0)
        cooldown_seconds = 300 if config.SIMULATION_MODE else config.SIGNAL_COOLDOWN

        time_diff= current_time - last_signal_time
        if  time_diff< cooldown_seconds:
            logging.debug(f"On cooldown time for {cooldown_seconds} seconds, time left: {time_diff} seconds. Ignoring signal")
            return

        signal_info = check_signal(df)
        if signal_info:
            last_price = df["close"].iloc[-1]
            # --- Fetch leverage and margin type ---
            leverage, margin_type = self.risk_manager.get_configured_leverage_and_margin_type(symbol)
            entry_prices, tp_list, sl = self._generate_trade_parameters(signal_info, last_price)

            if entry_prices:
                self.charting_service.submit_plot_chart_task(
                    ohlc_df=df,
                    symbol=symbol,
                    timeframe=interval,
                    tp_levels=tp_list,
                    sl_level=sl,
                    callback=lambda path, error: self.handle_chart_callback(path, error, symbol, interval, entry_prices,
                                                                            tp_list, sl, signal_info, leverage,
                                                                            margin_type)
                )
                self.signal_cooldown[key] = current_time

    @staticmethod
    def _generate_trade_parameters(signal_info, last_price):
        """Helper to generate trade parameters based on signal and config."""

        # Access the final, pre-calculated values from the config file
        sl_percent = config.DEFAULT_SL_PERCENT
        tp_percents = config.DEFAULT_TP_PERCENTS

        if signal_info == "BUY":
            entry_prices = [last_price]
            # Calculate TP levels using the list of percentages
            tp_list = [last_price * (1 + p) for p in tp_percents]
            # Calculate SL level using the percentage
            sl = last_price * (1 - sl_percent)
            return entry_prices, tp_list, sl
        elif signal_info == "SELL":
            entry_prices = [last_price]
            # Calculate TP levels using the list of percentages
            tp_list = [last_price * (1 - p) for p in tp_percents]
            # Calculate SL level using the percentage
            sl = last_price * (1 + sl_percent)
            return entry_prices, tp_list, sl

        return None, None, None

    @staticmethod
    def _send_signal_notif(symbol, interval, entry_prices, tp_list, sl, chart_path, signal_info, leverage, margin_type):
        """Sends the formatted signal message to Telegram."""
        if config.SIMULATION_MODE:
            original_msg = format_signal_message(symbol, interval, entry_prices, tp_list, sl,leverage,margin_type)
            msg = f"🚦 [SIMULATION] 🚦\n{original_msg}"
        else:
            msg = format_signal_message(symbol, interval, entry_prices, tp_list, sl,leverage,margin_type)
        send_message_with_retry(msg, chart_path)
        app_mode = "SIMULATION" if config.SIMULATION_MODE else "REAL TRADE"
        logging.info(f"Sent {signal_info} signal for {symbol}-{interval} ({app_mode})")

    def run_testing_mode(self):
        """Generates immediate test signals for DATA_TESTING mode."""
        for symbol in config.SYMBOLS:
            for interval in config.TIMEFRAMES:
                try:
                    df = create_realistic_test_data(periods=50, base_price=30000)
                    test_signal = "BUY" if hash(symbol + interval) % 2 == 0 else "SELL"
                    last_price = df['close'].iloc[-1]
                    entry_prices, tp_list, sl = self._generate_trade_parameters(test_signal, last_price)

                    if entry_prices:
                        self.charting_service.submit_plot_chart_task(
                            ohlc_df=df,
                            symbol=symbol,
                            timeframe=interval,
                            tp_levels=tp_list,
                            sl_level=sl,
                            callback=lambda path, error: self.handle_chart_callback(path, error, symbol, interval,
                                                                                    entry_prices,
                                                                                    tp_list, sl, test_signal, MAX_LEVERAGE,
                                                                                    "Isolated"))
                        logging.info(f"TESTING: {test_signal} signal sent for {symbol} {interval}")
                        time.sleep(1)
                except Exception as e:
                    logging.error(f"Error in testing mode for {symbol} {interval}: {e}")
