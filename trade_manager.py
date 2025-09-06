import logging

import pandas as pd

import config
from binance_future_client import BinanceFuturesClient
from symbol_manager import SymbolManager


class TradeManager:
    """Manages all trading data and interactions with the Binance client."""

    def __init__(self, binance_client: BinanceFuturesClient, symbol_manager: SymbolManager):
        self.binance_client = binance_client
        self.symbol_manager = symbol_manager
        self.klines = {}
        self.historical_loaded = {}
        self.has_historical_loader = self._historical_loader_exists()

    def _historical_loader_exists(self) -> bool:
        """Check if the historical data loader is available."""
        try:
            return self.binance_client.load_historical_data is not None
        except (AttributeError, ImportError):
            logging.warning("Historical data loader not available - using only real-time data")
            return False

    def initialize_historical_data(self):
        """Preload historical data for all symbols and timeframes."""
        if not self.has_historical_loader:
            return

        symbols = self.symbol_manager.get_symbols()
        if not symbols:
            logging.error("Symbol list is empty, cannot load historical data.")
            return

        for symbol in symbols:
            logging.info(f"Loading historical data for {symbol} {config.TIMEFRAMES}")
            for interval in config.TIMEFRAMES:
                key = (symbol, interval)
                try:
                    historical_df = self.binance_client.load_historical_data(symbol, interval,
                                                                             limit=config.HISTORY_CANDLES)
                    if not historical_df.empty:
                        self.klines[key] = historical_df
                        self.historical_loaded[key] = True
                        logging.info(f"Loaded {len(historical_df)} historical candles for {symbol} {interval}")
                    else:
                        logging.error(f"Failed to load historical data for {symbol} {interval}")
                except Exception as e:
                    logging.error(f"Error loading historical data for {symbol} {interval}: {e}")

    def update_kline_data(self, k):
        """Updates the kline data from a WebSocket message."""
        symbol, interval = k["s"], k["i"]
        key = (symbol, interval)
        ts = pd.to_datetime(k["t"], unit="ms")

        if key not in self.klines:
            self.klines[key] = pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])

        new_row = pd.DataFrame([{
            'open': float(k["o"]),
            'high': float(k["h"]),
            'low': float(k["l"]),
            'close': float(k["c"]),
            'volume': float(k["v"])
        }], index=[ts])

        self.klines[key] = pd.concat([self.klines[key], new_row])
        self.klines[key].sort_index(inplace=True)
        if len(self.klines[key]) > config.HISTORY_CANDLES:
            self.klines[key] = self.klines[key].iloc[-config.HISTORY_CANDLES:]

    def get_kline_data(self, symbol, interval):
        """Retrieves kline data for a given symbol and interval."""
        return self.klines.get((symbol, interval), pd.DataFrame())
