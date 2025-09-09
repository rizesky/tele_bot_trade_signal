import logging

import pandas as pd
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException

import config
from rate_limiter import BinanceRateLimiter, RateLimitConfig, RateLimitedBinanceClient


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
        
        # Initialize rate limiter if enabled
        self.rate_limiter = None
        if config.RATE_LIMITING_ENABLED:
            rate_limit_config = RateLimitConfig(
                max_weight_per_minute=config.RATE_LIMIT_MAX_WEIGHT_PER_MINUTE,
                max_requests_per_minute=config.RATE_LIMIT_MAX_REQUESTS_PER_MINUTE,
                safety_margin_percent=config.RATE_LIMIT_SAFETY_MARGIN,
                warning_threshold_percent=config.RATE_LIMIT_WARNING_THRESHOLD,
                retry_delay_seconds=config.RATE_LIMIT_RETRY_DELAY,
                max_retry_attempts=config.RATE_LIMIT_MAX_RETRIES,
                enable_detailed_logging=config.RATE_LIMIT_DETAILED_LOGGING,
                log_interval_seconds=config.RATE_LIMIT_LOG_INTERVAL
            )
            self.rate_limiter = BinanceRateLimiter(rate_limit_config)
            logging.info("Rate limiting enabled for Binance API")
        else:
            logging.info("Rate limiting disabled for Binance API")

    def get_futures_symbols(self)->list[str]:
        """
        Retrieves all USDⓈ-M futures symbols from the exchange.

        Returns:
            list: A list of all futures symbols (e.g., 'BTCUSDT').
            Returns an empty list if the request fails.
        """
        # Apply rate limiting if enabled
        if self.rate_limiter:
            # Exchange info has weight 1
            wait_time = self.rate_limiter.wait_if_needed(1)
            if wait_time > 0:
                logging.debug(f"Rate limiting: waited {wait_time:.2f}s for futures symbols")
        
        try:
            exchange_info = self.client.futures_exchange_info()
            symbols = [s['symbol'] for s in exchange_info['symbols']]
            
            # Record the request in rate limiter
            if self.rate_limiter:
                self.rate_limiter.record_request(1)
            
            return symbols
        except (BinanceAPIException, BinanceRequestException) as e:
            if self.rate_limiter and self._is_rate_limit_error(e):
                self.rate_limiter.block_request(f"Rate limit error fetching symbols: {e}")
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
        # Apply rate limiting if enabled
        if self.rate_limiter:
            # Ticker stats has weight 1 per symbol, but we're getting all symbols
            # Estimate weight as 1 for the entire request
            wait_time = self.rate_limiter.wait_if_needed(1)
            if wait_time > 0:
                logging.debug(f"Rate limiting: waited {wait_time:.2f}s for futures symbols with stats")
        
        try:
            # Get 24h ticker statistics for all futures symbols
            ticker_stats = self.client.futures_ticker()
            
            # Record the request in rate limiter
            if self.rate_limiter:
                self.rate_limiter.record_request(1)
            
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
            if self.rate_limiter and self._is_rate_limit_error(e):
                self.rate_limiter.block_request(f"Rate limit error fetching symbol stats: {e}")
            logging.error(f"Error fetching futures symbols with stats: {e}")
            return []
        except Exception as e:
            logging.error(f"An unexpected error occurred fetching symbol stats: {e}")
            return []

    def load_historical_data(self, symbol, interval, limit=100):
        """
        Load historical data from the Binance API with rate limiting.

        Args:
            symbol (str): The trading pair symbol (e.g., 'BTCUSDT').
            interval (str): The time interval (e.g., Client.KLINE_INTERVAL_1HOUR).
            limit (int): The number of recent klines to retrieve.

        Returns:
            pd.DataFrame: A DataFrame with OHLCV data. Returns an empty DataFrame on error.
        """
        # Apply rate limiting if enabled
        if self.rate_limiter:
            # Calculate weight for this request
            weight = self.rate_limiter.calculate_weight_for_klines(limit)
            
            # Wait if necessary to avoid rate limits
            wait_time = self.rate_limiter.wait_if_needed(weight)
            if wait_time > 0:
                logging.debug(f"Rate limiting: waited {wait_time:.2f}s for {symbol}-{interval} (limit={limit}, weight={weight})")
        
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

            # Record the request in rate limiter
            if self.rate_limiter:
                weight = self.rate_limiter.calculate_weight_for_klines(limit)
                self.rate_limiter.record_request(weight)

            return df[['open', 'high', 'low', 'close', 'volume']]

        except (BinanceAPIException, BinanceRequestException) as e:
            # Check if it's a rate limit error
            if self.rate_limiter and self._is_rate_limit_error(e):
                weight = self.rate_limiter.calculate_weight_for_klines(limit)
                self.rate_limiter.block_request(f"Rate limit error for {symbol}-{interval}: {e}")
                logging.error(f"Rate limit exceeded for {symbol} {interval}: {e}")
            else:
                logging.error(f"Error loading historical data for {symbol} {interval}: {e}")
            
            # Return empty DataFrame if API fails
            return pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])
    
    def _is_rate_limit_error(self, error) -> bool:
        """Check if the error is related to rate limiting."""
        error_str = str(error).lower()
        rate_limit_indicators = [
            '429',  # Too Many Requests
            '418',  # I'm a teapot (Binance's way of saying you're banned)
            'rate limit',
            'too many requests',
            'weight limit',
            'request limit'
        ]
        return any(indicator in error_str for indicator in rate_limit_indicators)
    
    def get_rate_limit_stats(self):
        """Get current rate limiting statistics."""
        if self.rate_limiter:
            return self.rate_limiter.get_usage_stats()
        return None
    
    def get_optimal_klines_limit(self, desired_candles: int) -> int:
        """
        Get the optimal limit parameter for klines requests to minimize weight usage.
        
        Args:
            desired_candles: Number of candles you want to retrieve
            
        Returns:
            int: Optimal limit parameter that minimizes weight cost
        """
        if desired_candles <= 0:
            return 1
        
        # Enforce Binance API limit of 1500 candles
        if desired_candles > 1500:
            logging.warning(f"Requested {desired_candles} candles exceeds Binance limit of 1500, capping to 1500")
            desired_candles = 1500
        
        # Weight optimization strategy
        if desired_candles <= 99:
            # Use multiple small requests (weight 1 each)
            return min(desired_candles, 99)
        elif desired_candles <= 499:
            # Use single request with weight 2
            return min(desired_candles, 499)
        elif desired_candles <= 1000:
            # Use single request with weight 5
            return min(desired_candles, 1000)
        else:
            # For large requests, chunk into 1000-candle batches (weight 5 each)
            return 1000