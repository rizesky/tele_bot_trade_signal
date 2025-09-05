import logging
import signal
import sys
import threading
import time

import config
from binance_future_client import BinanceFuturesClient
from binance_ws_client import BinanceWS
from charting_service import ChartingService
from config import FILTER_BY_MARKET_CAP, BINANCE_API_KEY, BINANCE_API_SECRET
from risk_manager import RiskManager
from strategy_executor import StrategyExecutor
from symbol_manager import SymbolManager
from trade_manager import TradeManager


class AppRunner:

    def __init__(self):
        self.binance_client = BinanceFuturesClient(BINANCE_API_KEY, BINANCE_API_SECRET)
        self.stop_event = threading.Event()
        self.is_shutting_down = threading.Event() #to prevent doubel shutting down calll
        self.ws = None
        self.symbol_manager = SymbolManager(self.binance_client)
        self.charting_service = ChartingService()
        self.risk_manager = RiskManager(self.binance_client)

    def shutdown_handler(self, signum, frame):
        """Method to handle graceful shutdown within the class."""

        if self.is_shutting_down.is_set():
            logging.info("Shutdown already in progress, ignoring signal...")
            return

        logging.info("Shutdown signal received, stopping...")

        self.is_shutting_down.set()
        if self.ws:
            self.ws.stop()
        if self.symbol_manager:
            self.symbol_manager.stop()
        if self.charting_service:
            self.charting_service.stop()
        self.stop_event.set()

    def run(self):
        mode = "SIMULATION" if config.SIMULATION_MODE else "LIVE TRADING"
        logging.info(f"Starting in {mode} mode")

        # Start the SymbolManager worker thread
        self.symbol_manager.start()
        # Wait for the charting service to be ready
        self.charting_service.start()

        # Pass the SymbolManager instance to the TradeManager
        trade_manager = TradeManager(self.binance_client, symbol_manager=self.symbol_manager)

        # Pass the required services to StrategyExecutor
        strats_executor = StrategyExecutor(
            trade_manager=trade_manager,
            charting_service=self.charting_service,
            risk_manager=self.risk_manager
        )

        if trade_manager.has_historical_loader:
            trade_manager.initialize_historical_data()

        symbols_to_subscribe = self.symbol_manager.get_symbols()

        # Apply market cap filtering
        if FILTER_BY_MARKET_CAP:
            min_market_cap = 10_000_000_000  # Example: $10 Billion USD
            if symbols_to_subscribe and min_market_cap > 0:
                logging.info(f"Applying market cap filter (min: ${min_market_cap:.2f} USD).")
                symbols_to_subscribe = self.risk_manager.filter_symbols_by_market_cap(
                    symbols_to_subscribe, min_market_cap
                )
                logging.info(f"Symbols after market cap filter: {len(symbols_to_subscribe)}")

            if not symbols_to_subscribe:
                logging.error("No symbols available to subscribe after filtering. Exiting.")
                self.shutdown_handler(None, None)
                return

        self.ws = BinanceWS(symbol_to_subs=symbols_to_subscribe, on_message_callback=strats_executor.handle_kline)

        # Register the signal handler to call the instance method
        signal.signal(signal.SIGINT, self.shutdown_handler)
        signal.signal(signal.SIGTERM, self.shutdown_handler)

        self.ws.run()

        try:
            while not self.stop_event.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            if not self.is_shutting_down.is_set():
                self.shutdown_handler(None, None)


def setup_logging():
    logging.basicConfig(

        level=logging.INFO,  # change to debug for development
        format=(
            "%(asctime)s [%(levelname)s] [%(process)d:%(threadName)s] "
            "%(name)s:%(filename)s:%(lineno)d - %(message)s"
        ),
        handlers=[
            logging.StreamHandler(sys.stdout),  # console
            # logging.FileHandler("bot.log")      # file appender optional
        ]
    )


if __name__ == "__main__":
    setup_logging()
    if config.DATA_TESTING:
        logging.info("Running in DATA_TESTING mode - generating test signals")
        strategy_runner = StrategyExecutor(None,None,None)
        strategy_runner.run_testing_mode()
        logging.info("DATA_TESTING mode completed")
    else:
        app = AppRunner()
        app.run()
