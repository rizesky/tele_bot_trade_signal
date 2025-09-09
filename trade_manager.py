import logging
import threading
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

import pandas as pd

import config
from binance_future_client import BinanceFuturesClient
from symbol_manager import SymbolManager
from database import get_database


class TradeManager:
    """Manages all trading data and interactions with the Binance client."""

    def __init__(self, binance_client: BinanceFuturesClient, symbol_manager: SymbolManager):
        self.binance_client = binance_client
        self.symbol_manager = symbol_manager
        self.klines = {}
        self.historical_loaded = {}
        self.has_historical_loader = self._historical_loader_exists()
        
        # Thread safety - use a single lock for all data access
        self._lock = threading.RLock()  # Reentrant lock for nested calls
        
        # Lazy loading configuration - only load data for symbols that actually generate signals
        self.symbols_with_signals = set()  # Track which symbols have generated signals
        self.max_lazy_load_symbols = config.MAX_LAZY_LOAD_SYMBOLS  # Maximum symbols to load historical data for
        self.lazy_loading_enabled = config.LAZY_LOADING_ENABLED  # Enable lazy loading by default
        
        # Concurrent loading optimization
        self.loading_queue = set()  # Track symbols currently being loaded to avoid duplicates
        self.max_concurrent_loads = config.MAX_CONCURRENT_LOADS  # Maximum concurrent API requests
        
        # Database integration
        self.db = get_database() if config.DB_ENABLE_PERSISTENCE else None

    def _historical_loader_exists(self) -> bool:
        """Check if the historical data loader is available."""
        try:
            return self.binance_client.load_historical_data is not None
        except (AttributeError, ImportError):
            logging.warning("Historical data loader not available - using only real-time data")
            return False

    def initialize_historical_data(self):
        """
        Initialize historical data loading strategy.
        With lazy loading enabled, this will only load data for a limited set of symbols
        to prevent memory issues and API rate limiting with 300+ symbols.
        """
        if not self.has_historical_loader:
            logging.info("Historical data loader not available - using real-time data only")
            return

        symbols = self.symbol_manager.get_symbols()
        if not symbols:
            logging.error("Symbol list is empty, cannot load historical data.")
            return

        if self.lazy_loading_enabled:
            # Lazy loading: Only load data for explicitly configured symbols
            # When SYMBOLS is empty (auto-fetch), don't preload any historical data
            # Historical data will be loaded on-demand when signals are first detected
            if config.SYMBOLS:
                symbols_to_load = config.SYMBOLS[:self.max_lazy_load_symbols]
                logging.info(f"Lazy loading enabled: Loading historical data for {len(symbols_to_load)} configured symbols")
                logging.info(f"Symbols to load: {symbols_to_load}")
                self._load_historical_data_for_symbols(symbols_to_load)
            else:
                logging.info(f"Lazy loading enabled: No symbols configured, historical data will be loaded on-demand")
                logging.info(f"Total symbols available: {len(symbols)}")
                # Don't preload any historical data - it will be loaded when signals are detected
        else:
            # Original behavior: load all symbols (not recommended for 300+ symbols)
            logging.warning("Loading historical data for ALL symbols - this may cause memory issues with 300+ symbols")
            self._load_historical_data_for_symbols(symbols)

    def _load_historical_data_for_symbols(self, symbols_to_load):
        """Helper method to load historical data for a specific set of symbols with concurrent loading."""
        logging.info(f"CONCURRENT LOADING: Starting historical data load for {len(symbols_to_load)} symbols...")
        
        # Create tasks for concurrent loading
        tasks = []
        for symbol in symbols_to_load:
            for interval in config.TIMEFRAMES:
                key = (symbol, interval)
                if key not in self.historical_loaded or not self.historical_loaded[key]:
                    tasks.append((symbol, interval, key))
        
        if not tasks:
            logging.info("CONCURRENT LOADING: No historical data to load (all already cached)")
            return
            
        logging.info(f"CONCURRENT LOADING: Processing {len(tasks)} symbol/interval combinations using {self.max_concurrent_loads} parallel workers...")
        import time
        start_time = time.time()
        
        # Load data concurrently using ThreadPoolExecutor
        successful_loads = 0
        with ThreadPoolExecutor(max_workers=self.max_concurrent_loads) as executor:
            # Submit all tasks
            future_to_task = {
                executor.submit(self._load_single_historical_data, symbol, interval): (symbol, interval, key)
                for symbol, interval, key in tasks
            }
            
            # Process completed tasks
            for future in as_completed(future_to_task):
                symbol, interval, key = future_to_task[future]
                try:
                    historical_df = future.result()
                    if historical_df is not None and not historical_df.empty:
                        self.klines[key] = historical_df
                        self.historical_loaded[key] = True
                        successful_loads += 1
                        logging.debug(f"Loaded {len(historical_df)} historical candles for {symbol} {interval}")
                    else:
                        logging.warning(f"No historical data available for {symbol} {interval}")
                except Exception as e:
                    logging.error(f"CONCURRENT LOADING ERROR: Error loading {symbol} {interval}: {e}")
                    
        end_time = time.time()
        duration = end_time - start_time
        logging.info(f"CONCURRENT LOADING COMPLETED: Finished in {duration:.2f}s - {successful_loads}/{len(tasks)} successful ({successful_loads/len(tasks)*100:.1f}% success rate)")

    def _load_single_historical_data(self, symbol, interval):
        """Load historical data for a single symbol/interval with database caching and rate limiting optimization."""
        try:
            # Try to load from database first if persistence is enabled
            if self.db:
                db_data = self.db.load_historical_data(symbol, interval, limit=config.HISTORY_CANDLES)
                if not db_data.empty and len(db_data) >= config.HISTORY_CANDLES * 0.8:  # At least 80% of requested data
                    logging.debug(f"Loaded {len(db_data)} candles from database for {symbol}-{interval}")
                    return db_data
            
            # Use optimal limit to minimize weight usage
            optimal_limit = self.binance_client.get_optimal_klines_limit(config.HISTORY_CANDLES)
            
            # Load from API with optimized limit
            api_data = self.binance_client.load_historical_data(symbol, interval, limit=optimal_limit)
            
            # Store in database for future use
            if self.db and api_data is not None and not api_data.empty:
                self.db.store_historical_data(symbol, interval, api_data)
                logging.debug(f"Cached {len(api_data)} candles to database for {symbol}-{interval}")
            
            return api_data
            
        except Exception as e:
            logging.error(f"Error loading historical data for {symbol} {interval}: {e}")
            return None

    def lazy_load_historical_data(self, symbol, interval):
        """
        Lazy load historical data for a specific symbol/interval when needed.
        This is called when a symbol generates its first signal to ensure we have historical context.
        """
        if not self.has_historical_loader:
            return False
            
        key = (symbol, interval)
        
        # Skip if already loaded
        if self.historical_loaded.get(key, False):
            return True
            
        # Check if we've hit the lazy loading limit
        if len(self.symbols_with_signals) >= self.max_lazy_load_symbols:
            logging.warning(f"Lazy loading limit reached ({self.max_lazy_load_symbols}). Skipping {symbol}-{interval}")
            return False
            
        # Skip if currently being loaded (avoid duplicate requests)
        if key in self.loading_queue:
            logging.debug(f"Already loading {symbol}-{interval}, skipping duplicate request")
            return False
            
        # Add to loading queue to prevent duplicates
        self.loading_queue.add(key)
        
        try:
            import time
            start_time = time.time()
            logging.info(f"LAZY LOADING: Loading on-demand data for {symbol}-{interval}...")
            historical_df = self._load_single_historical_data(symbol, interval)
            
            if historical_df is not None and not historical_df.empty:
                with self._lock:  # Thread-safe update
                    self.klines[key] = historical_df
                    self.historical_loaded[key] = True
                    self.symbols_with_signals.add(symbol)
                end_time = time.time()
                duration = end_time - start_time
                logging.info(f"LAZY LOADING SUCCESS: Successfully loaded {len(historical_df)} candles for {symbol}-{interval} in {duration:.2f}s")
                return True
            else:
                logging.warning(f"LAZY LOADING WARNING: No data available for {symbol}-{interval}")
                return False
        except Exception as e:
            logging.error(f"LAZY LOADING ERROR: Error loading {symbol}-{interval}: {e}")
            return False
        finally:
            # Remove from loading queue
            self.loading_queue.discard(key)

    def update_kline_data(self, k):
        """Updates the kline data from a WebSocket message with thread safety and optimized operations."""
        symbol, interval = k["s"], k["i"]
        key = (symbol, interval)
        ts = pd.to_datetime(k["t"], unit="ms")

        # Use thread-safe lock for all data modifications
        with self._lock:
            if key not in self.klines:
                self.klines[key] = pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])

            # Extract values once to avoid repeated dict lookups
            new_data = {
                'open': float(k["o"]),
                'high': float(k["h"]),
                'low': float(k["l"]),
                'close': float(k["c"]),
                'volume': float(k["v"])
            }

            # Check if this timestamp already exists to prevent duplicates
            if ts in self.klines[key].index:
                # Update existing row directly without creating new DataFrame
                try:
                    for col, value in new_data.items():
                        self.klines[key].loc[ts, col] = value
                except Exception as e:
                    logging.error(f"Error updating {symbol}-{interval} at {ts}: {e}")
                    # Recreate DataFrame if corrupted
                    self.klines[key] = pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])
            else:
                # Add new row efficiently
                if self.klines[key].empty:
                    self.klines[key] = pd.DataFrame([new_data], index=[ts])
                else:
                    # Use loc to add new row directly without concatenation
                    self.klines[key].loc[ts] = new_data
                    
                    # Only sort if the new timestamp is not at the end (most common case)
                    if len(self.klines[key]) > 1 and ts < self.klines[key].index[-2]:
                        self.klines[key].sort_index(inplace=True)
            
            # Keep only the most recent candles to prevent memory bloat
            # Use more efficient slicing instead of iloc
            df_len = len(self.klines[key])
            if df_len > config.HISTORY_CANDLES:
                excess_rows = df_len - config.HISTORY_CANDLES
                # Drop oldest rows more efficiently
                self.klines[key] = self.klines[key].iloc[excess_rows:]
            
            # Final safety check: ensure we still have a valid DataFrame
            if not isinstance(self.klines[key], pd.DataFrame):
                logging.error(f"CRITICAL: DataFrame corrupted for {symbol}-{interval} after update. Type: {type(self.klines[key])}")
                self.klines[key] = pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])

    def get_kline_data(self, symbol, interval):
        """Retrieves kline data for a given symbol and interval with thread safety."""
        with self._lock:
            data = self.klines.get((symbol, interval), pd.DataFrame())
            # Debug: Check if data is corrupted
            if not isinstance(data, pd.DataFrame):
                logging.error(f"CORRUPTION DETECTED: Expected DataFrame for {symbol}-{interval}, got {type(data)}: {data}")
                return pd.DataFrame()  # Return empty DataFrame as fallback
            return data.copy()
    
    def get_clean_kline_data_for_chart(self, symbol, interval):
        """
        Retrieves clean, validated kline data specifically for chart generation.
        This method ensures data integrity and removes any potential issues that could cause chart rendering problems.
        Thread-safe implementation.
        """
        with self._lock:
            df = self.klines.get((symbol, interval), pd.DataFrame())
            
            if df.empty:
                return df
                
            # Create a copy to avoid modifying the original data
            clean_df = df.copy()
        
        # Process the copy outside the lock to avoid holding it too long
        # Remove any rows with NaN values that could break chart rendering
        clean_df = clean_df.dropna()
        
        # Ensure we have the required OHLCV columns
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        if not all(col in clean_df.columns for col in required_columns):
            logging.warning(f"Missing required columns for {symbol}-{interval}. Available: {clean_df.columns.tolist()}")
            return pd.DataFrame()
        
        # Validate OHLC data integrity
        # High should be >= max(open, close) and Low should be <= min(open, close)
        invalid_rows = (
            (clean_df['high'] < clean_df[['open', 'close']].max(axis=1)) |
            (clean_df['low'] > clean_df[['open', 'close']].min(axis=1)) |
            (clean_df['high'] <= 0) | (clean_df['low'] <= 0) | 
            (clean_df['open'] <= 0) | (clean_df['close'] <= 0)
        )
        
        if invalid_rows.any():
            logging.warning(f"Found {invalid_rows.sum()} invalid OHLC rows for {symbol}-{interval}, removing them")
            clean_df = clean_df[~invalid_rows]
        
        # Ensure data is sorted by timestamp (index)
        clean_df = clean_df.sort_index()
        
        # Remove duplicate timestamps (keep the last one)
        clean_df = clean_df[~clean_df.index.duplicated(keep='last')]
        
        # Technical indicators removed for cleaner chart appearance
        # (RSI and MA are still calculated in signal logic but not displayed on charts)
        # Log data quality info for debugging
        if len(clean_df) < len(df):
            logging.info(f"Data cleaned for {symbol}-{interval}: {len(df)} -> {len(clean_df)} rows")
        
        return clean_df
