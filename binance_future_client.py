import logging

import pandas as pd
from binance import Client, BinanceAPIException, BinanceRequestException


class BinanceFuturesClient:
    """A client to interact with the Binance Futures API."""

    def __init__(self, api_key, api_secret):
        """
        Initializes the Binance client.

        Args:
            api_key (str):  Binance API key.
            api_secret (str):  Binance API secret.
        """
        self.client = Client(api_key, api_secret)

    def get_futures_symbols(self)->list[str]:
        """
        Retrieves all USDⓈ-M futures symbols from the exchange.

        Returns:
            list: A list of all futures symbols (e.g., 'BTCUSDT').
            Returns an empty list if the request fails.
        """
        try:
            exchange_info = self.client.futures_exchange_info()
            symbols = [s['symbol'] for s in exchange_info['symbols']]
            return symbols
        except (BinanceAPIException, BinanceRequestException) as e:
            logging.error(f"Error fetching futures symbols: {e}")
            return []
        except Exception as e:
            logging.error(f"An unexpected error occurred: {e}")
            return []

    def load_historical_data(self, symbol, interval, limit=100):
        """
        Load historical data from the Binance API.

        Args:
            symbol (str): The trading pair symbol (e.g., 'BTCUSDT').
            interval (str): The time interval (e.g., Client.KLINE_INTERVAL_1HOUR).
            limit (int): The number of recent klines to retrieve.

        Returns:
            pd.DataFrame: A DataFrame with OHLCV data. Returns an empty DataFrame on error.
        """
        try:
            klines = self.client.futures_klines(
                symbol=symbol,
                interval=interval,
                limit=limit
            )

            if not klines:
                return pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])

            # Convert to DataFrame
            df = pd.DataFrame(klines, columns=[
                'open_time', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_asset_volume', 'number_of_trades',
                'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
            ])

            # Convert to numeric and datetime
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col])

            df['timestamp'] = pd.to_datetime(df['open_time'], unit='ms')
            df.set_index('timestamp', inplace=True)

            return df[['open', 'high', 'low', 'close', 'volume']]

        except (BinanceAPIException, BinanceRequestException) as e:
            logging.error(f"Error loading historical data for {symbol} {interval}: {e}")
            # Return empty DataFrame if API fails
            return pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])