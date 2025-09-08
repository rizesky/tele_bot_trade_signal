import logging

import pandas as pd
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException


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

    def get_futures_symbols_with_stats(self) -> list[dict]:
        """
        Retrieves futures symbols with volume and quality metrics for intelligent selection.
        
        Returns:
            list[dict]: List of symbol data with volume, price change, and other metrics.
                       Sorted by quality score (volume * price_change_abs * market_activity).
        """
        try:
            # Get 24h ticker statistics for all futures symbols
            ticker_stats = self.client.futures_ticker()
            
            # Filter for USDT pairs and calculate quality scores
            symbol_data = []
            for ticker in ticker_stats:
                symbol = ticker['symbol']
                
                # Only include USDT pairs (most liquid and relevant)
                if not symbol.endswith('USDT'):
                    continue
                    
                try:
                    volume_24h = float(ticker['quoteVolume'])  # 24h volume in USDT
                    price_change_percent = abs(float(ticker['priceChangePercent']))  # Absolute price change
                    count_trades = int(ticker['count'])  # Number of trades
                    
                    # Skip symbols with very low activity
                    if volume_24h < 100000:  # Less than $100k daily volume
                        continue
                    
                    # Calculate quality score (higher = better for trading)
                    # Factors: Volume (liquidity), Price movement (volatility), Trade count (activity)
                    quality_score = (
                        (volume_24h / 1000000) * 0.6 +  # Volume weight (60%)
                        (price_change_percent) * 0.3 +   # Volatility weight (30%)
                        (count_trades / 10000) * 0.1     # Activity weight (10%)
                    )
                    
                    symbol_data.append({
                        'symbol': symbol,
                        'volume_24h_usdt': volume_24h,
                        'price_change_percent': price_change_percent,
                        'trade_count': count_trades,
                        'quality_score': quality_score,
                        'current_price': float(ticker['lastPrice'])
                    })
                    
                except (ValueError, KeyError) as e:
                    logging.debug(f"Skipping {symbol} due to data parsing error: {e}")
                    continue
            
            # Sort by quality score (descending - best symbols first)
            symbol_data.sort(key=lambda x: x['quality_score'], reverse=True)
            
            logging.info(f"Retrieved {len(symbol_data)} quality futures symbols with stats")
            return symbol_data
            
        except (BinanceAPIException, BinanceRequestException) as e:
            logging.error(f"Error fetching futures symbols with stats: {e}")
            return []
        except Exception as e:
            logging.error(f"An unexpected error occurred fetching symbol stats: {e}")
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