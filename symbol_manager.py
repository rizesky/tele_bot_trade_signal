import logging
import threading
from datetime import timedelta

from util import now_utc

import config
from binance_future_client import BinanceFuturesClient


class SymbolManager:
    """Manages the fetching and periodic refreshing of the futures symbols list with intelligent selection."""

    def __init__(self, binance_client: BinanceFuturesClient):
        self.binance_client = binance_client
        self.symbols = []
        self.symbol_stats = []  # Store detailed symbol statistics for quality selection
        self._last_refresh_time = None
        self._refresh_interval_days = 7  # Standard weekly refresh
        self._lock = threading.Lock()
        self._refresh_event = threading.Event()
        self._stop_event = threading.Event()
        self._worker_thread = threading.Thread(name="SymbolManagerThread", target=self._refresh_symbols_worker, daemon=True)

    def start(self):
        """Starts the worker thread to periodically refresh symbols."""
        if len(config.SYMBOLS)>0:
            logging.info(f"Using symbols from config: {config.SYMBOLS}. Automatic refresh disabled.")
            self.symbols = config.SYMBOLS
        else:
            self._worker_thread.start()
            logging.info("Started symbol refresh worker thread.")
            self._wait_for_initial_refresh()

    def stop(self):
        """Stops the worker thread."""
        logging.info("Stopping symbol refresh worker thread...")
        self._stop_event.set()
        self._refresh_event.set()  # Wake up the worker to check the stop event
        if self._worker_thread.is_alive():
            self._worker_thread.join()

    def get_symbols(self):
        """Thread-safe way to get the current list of symbols."""
        with self._lock:
            return self.symbols

    def _wait_for_initial_refresh(self):
        """Blocks until the initial symbol list has been fetched."""
        logging.info("Waiting for initial symbol list refresh...")
        self._refresh_event.wait()
        logging.info("Initial symbol list fetched.")

    def _refresh_symbols_worker(self):
        """Worker thread function to periodically refresh symbols."""
        while not self._stop_event.is_set():
            now = now_utc()
            if self._last_refresh_time is None or now - self._last_refresh_time > timedelta(
                    days=self._refresh_interval_days):
                self._fetch_and_update_symbols()
                self._last_refresh_time = now
                self._refresh_event.set()  # Signal main thread that refresh is complete

            # Wait for either the interval to pass or the stop event to be set
            self._stop_event.wait(timeout=3600)  # Check every hour

    def _fetch_and_update_symbols(self):
        """Fetches the latest symbols from Binance API and updates the shared list with intelligent selection."""
        try:
            if config.MAX_SYMBOLS is not None and config.MAX_SYMBOLS > 0:
                # Use intelligent selection with quality metrics
                logging.info(f"Fetching symbols with quality metrics (limit: {config.MAX_SYMBOLS})")
                symbol_data = self.binance_client.get_futures_symbols_with_stats()
                
                if symbol_data:
                    selected_symbols = self._select_best_symbols(symbol_data)
                    
                    with self._lock:
                        self.symbols = selected_symbols
                        self.symbol_stats = symbol_data[:len(selected_symbols)]  # Store stats for selected symbols
                        
                    logging.info(f"Quality-based symbol selection completed. Selected {len(selected_symbols)} symbols")
                    self._log_symbol_selection_summary()
                else:
                    logging.error("Failed to fetch symbol quality data. Retaining old list.")
            else:
                # Use basic symbol fetch (unlimited symbols)
                new_symbols = self.binance_client.get_futures_symbols()
                if new_symbols:
                    with self._lock:
                        self.symbols = new_symbols
                    
                    logging.info(f"Basic symbols list refreshed. Total symbols: {len(new_symbols)}")
                else:
                    logging.error("Failed to fetch new symbols. Retaining old list.")
                    
        except Exception as e:
            logging.error(f"Error fetching symbols: {e}. Retaining old list.")

    def _select_best_symbols(self, symbol_data: list[dict]) -> list[str]:
        """Select the best symbols based on the configured strategy."""
        if not symbol_data:
            return []
            
        # Apply volume filter first
        filtered_data = [
            s for s in symbol_data 
            if s['volume_24h_usdt'] >= config.MIN_DAILY_VOLUME_USDT
        ]
        
        logging.info(f"After volume filter (min ${config.MIN_DAILY_VOLUME_USDT:,.0f}): {len(filtered_data)} symbols")
        
        # Apply market cap filter if enabled
        if config.MIN_MARKET_CAP_USD > 0:
            logging.info(f"Applying market cap filter (min ${config.MIN_MARKET_CAP_USD:,.0f} USD)")
            # Import risk manager for market cap filtering
            try:
                from risk_manager import RiskManager
                from binance_future_client import BinanceFuturesClient
                
                # Create temporary risk manager for filtering
                temp_risk_manager = RiskManager(self.binance_client)
                symbols_before_mc = [s['symbol'] for s in filtered_data]
                symbols_after_mc = temp_risk_manager.filter_symbols_by_market_cap(
                    symbols_before_mc, config.MIN_MARKET_CAP_USD
                )
                
                # Filter symbol_data to keep only symbols that passed market cap filter
                filtered_data = [s for s in filtered_data if s['symbol'] in symbols_after_mc]
                logging.info(f"After market cap filter: {len(filtered_data)} symbols")
                
            except Exception as e:
                logging.warning(f"Market cap filtering failed: {e}. Continuing without market cap filter.")
        
        if not filtered_data:
            logging.warning("No symbols meet filtering requirements. Using top symbols without filters.")
            filtered_data = symbol_data
        
        # Apply selection strategy
        if config.SYMBOL_SELECTION_STRATEGY == "quality":
            # Already sorted by quality score in get_futures_symbols_with_stats()
            selected_data = filtered_data[:config.MAX_SYMBOLS]
        elif config.SYMBOL_SELECTION_STRATEGY == "volume":
            # Sort by volume (descending)
            filtered_data.sort(key=lambda x: x['volume_24h_usdt'], reverse=True)
            selected_data = filtered_data[:config.MAX_SYMBOLS]
        elif config.SYMBOL_SELECTION_STRATEGY == "random":
            # Random selection (for testing)
            import random
            selected_data = random.sample(filtered_data, min(config.MAX_SYMBOLS, len(filtered_data)))
        else:
            logging.warning(f"Unknown selection strategy '{config.SYMBOL_SELECTION_STRATEGY}'. Using quality strategy.")
            selected_data = filtered_data[:config.MAX_SYMBOLS]
        
        return [s['symbol'] for s in selected_data]
    
    def _log_symbol_selection_summary(self):
        """Log a summary of the selected symbols for monitoring."""
        if not self.symbol_stats:
            return
            
        logging.info("=== Symbol Selection Summary ===")
        logging.info(f"Strategy: {config.SYMBOL_SELECTION_STRATEGY.upper()}")
        limit_text = f"limit: {config.MAX_SYMBOLS}" if config.MAX_SYMBOLS is not None else "unlimited"
        logging.info(f"Selected: {len(self.symbols)} symbols ({limit_text})")
        
        # Show top 10 selected symbols with their stats
        top_symbols = self.symbol_stats[:10]
        logging.info("Top selected symbols:")
        for i, stat in enumerate(top_symbols, 1):
            logging.info(
                f"  {i:2d}. {stat['symbol']:12s} | "
                f"Vol: ${stat['volume_24h_usdt']:>12,.0f} | "
                f"Change: {stat['price_change_percent']:>6.2f}% | "
                f"Quality: {stat['quality_score']:>6.2f}"
            )
        
        if len(self.symbol_stats) > 10:
            logging.info(f"  ... and {len(self.symbol_stats) - 10} more symbols")
    
    def get_symbol_stats(self) -> list[dict]:
        """Get detailed statistics for currently selected symbols."""
        with self._lock:
            return self.symbol_stats.copy()
