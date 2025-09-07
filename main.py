import logging
import logging.handlers
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
from database import get_database


class AppRunner:

    def __init__(self):
        # Initialize database first (if enabled)
        if config.DB_ENABLE_PERSISTENCE:
            self.db = get_database()
            logging.info("Database initialized and ready")
        else:
            self.db = None
            logging.info("Database persistence disabled")
            
        self.binance_client = BinanceFuturesClient(BINANCE_API_KEY, BINANCE_API_SECRET)
        self.stop_event = threading.Event()
        self.is_shutting_down = threading.Event() #to prevent double shutting down call
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
        if self.db:
            self.db.close()
        self.stop_event.set()

    def _validate_configuration(self):
        """Validate critical configuration values before starting the application"""
        validation_errors = []
        
        # Validate API credentials
        if not BINANCE_API_KEY or not BINANCE_API_SECRET:
            validation_errors.append("Binance API credentials are missing")
        
        # Validate Telegram configuration
        if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
            validation_errors.append("Telegram configuration is missing")
            
        # Validate symbols configuration
        # SYMBOLS is optional - if empty, the symbol manager will auto-fetch from Binance
        # No validation needed here as both empty and populated SYMBOLS are valid
            
        # Validate timeframes
        if not config.TIMEFRAMES:
            validation_errors.append("No timeframes configured")
            
        # Validate numeric configurations
        if config.HISTORY_CANDLES <= 0:
            validation_errors.append("HISTORY_CANDLES must be positive")
            
        if config.SIGNAL_COOLDOWN < 0:
            validation_errors.append("SIGNAL_COOLDOWN must be non-negative")
            
        if config.DEFAULT_SL_PERCENT <= 0 or config.DEFAULT_SL_PERCENT >= 1:
            validation_errors.append("DEFAULT_SL_PERCENT must be between 0 and 1")
            
        # Validate TP percentages
        for tp_percent in config.DEFAULT_TP_PERCENTS:
            if tp_percent <= 0 or tp_percent >= 1:
                validation_errors.append(f"TP percentage {tp_percent} must be between 0 and 1")
                
        # Log validation results
        if validation_errors:
            for error in validation_errors:
                logging.error(f"Configuration error: {error}")
            return False
        else:
            logging.info("Configuration validation passed")
            return True

    def run(self):
        mode = "SIMULATION" if config.SIMULATION_MODE else "LIVE TRADING"
        logging.info(f"Starting in {mode} mode")

        # Validate configuration before starting
        if not self._validate_configuration():
            logging.error("Configuration validation failed. Exiting.")
            return

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
    # Ensure logs directory exists
    import os
    os.makedirs("logs", exist_ok=True)
    
    logging.basicConfig(
        # level=logging.DEBUG,  # change to debug for development
        level=logging.INFO,  
        format=(
            "%(asctime)s [%(levelname)s] [%(process)d:%(threadName)s] "
            "%(name)s:%(filename)s:%(lineno)d - %(message)s"
        ),
        handlers=[
            # File logging with rotation
            logging.handlers.RotatingFileHandler(
                "logs/trading_bot.log",
                maxBytes=10*1024*1024,  # 10MB
                backupCount=5
            ),
            logging.StreamHandler(sys.stdout),  # console
        ]
    )


if __name__ == "__main__":
    setup_logging()
    if config.DATA_TESTING:
        logging.info("Running in DATA_TESTING mode - generating test signals with charts")
        
        # Initialize required services for chart generation
        from database import get_database
        binance_client = BinanceFuturesClient(BINANCE_API_KEY, BINANCE_API_SECRET)
        charting_service = ChartingService()
        risk_manager = RiskManager(binance_client)
        
        # Start charting service
        charting_service.start()
        
        # Create strategy executor with charting enabled
        strategy_runner = StrategyExecutor(None, charting_service, risk_manager)
        strategy_runner.run_testing_mode()
        
        # Cleanup
        charting_service.stop()
        logging.info("DATA_TESTING mode completed")
    else:
        app = AppRunner()
        app.run()
