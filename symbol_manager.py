import logging
import threading
from datetime import timedelta

from util import now_utc

import config
from binance_future_client import BinanceFuturesClient


class SymbolManager:
    """Manages the fetching and periodic refreshing of the futures symbols list."""

    def __init__(self, binance_client: BinanceFuturesClient):
        self.binance_client = binance_client
        self.symbols = []
        self._last_refresh_time = None
        self._refresh_interval_days = 7
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
        """Fetches the latest symbols from Binance API and updates the shared list."""
        try:
            new_symbols = self.binance_client.get_futures_symbols()
            if new_symbols:
                with self._lock:
                    #TODO delete this line, only for limit testing
                    new_symbols = new_symbols[:100] if len(new_symbols) > 100 else new_symbols
                    
                    self.symbols = new_symbols
                logging.info(f"Symbols list refreshed. Total symbols: {len(new_symbols)}")
            else:
                logging.error("Failed to fetch new symbols. Retaining old list.")
        except Exception as e:
            logging.error(f"Error fetching symbols: {e}. Retaining old list.")
