import logging
import time

from binance.exceptions import BinanceAPIException, BinanceRequestException

from binance_future_client import BinanceFuturesClient
import config
from database import get_database


class RiskManager:
    """
    Manages risk-related parameters, including fetching Binance leverage brackets
    and potentially filtering symbols by market cap.
    """

    def __init__(self, binance_client: BinanceFuturesClient):
        self.binance_client = binance_client
        self.leverage_brackets = {}
        self._coingecko_client = None

        # Cache to store leverage and margin data per symbol
        self._position_cache = {}
        # Cache duration in seconds
        self.CACHE_EXPIRY = 300  # 5 minutes
        
        # Database integration for persistent caching
        self.db = get_database() if config.DB_ENABLE_PERSISTENCE else None

    # --- Market Cap Filtering (using CoinGecko) ---
    # Free tier CoinGecko API has rate limits and might not provide real-time updates.
    # Consider caching results or using a paid plan for higher frequency.

    def _get_coingecko_client(self):
        if self._coingecko_client is None:
            try:
                from pycoingecko import CoinGeckoAPI
                # An API key may be needed for higher rate limits or specific endpoints
                # cg_api_key = config.COINGECKO_API_KEY # If available
                # self._coingecko_client = CoinGeckoAPI(api_key=cg_api_key) if cg_api_key else CoinGeckoAPI()
                self._coingecko_client = CoinGeckoAPI()  # Using the free tier
                logging.info("CoinGecko API client initialized.")
            except ImportError:
                logging.error("pycoingecko library not installed. Market cap filtering will be unavailable.")
                return None
        return self._coingecko_client

    def get_market_cap_usd(self, coin_id: str) -> float | None:
        """
        Fetches the current market capitalization for a given coin_id from CoinGecko.
        Note: CoinGecko uses 'bitcoin', 'ethereum' as IDs, not 'BTCUSDT', 'ETHUSDT'.
        A mapping from Binance symbol to CoinGecko ID is required.
        """
        cg = self._get_coingecko_client()
        if not cg:
            return None

        try:
            # Use 'get_coins_markets' for market cap data
            # vs_currency should match the strategy's quote asset (e.g., 'usd')
            market_data = cg.get_coins_markets(vs_currency='usd', ids=coin_id)
            if market_data and market_data[0].get('market_cap'):
                return float(market_data[0]['market_cap'])
            logging.warning(f"Market cap data not found for CoinGecko ID: {coin_id}")
            return None
        except Exception as e:
            logging.error(f"Error fetching market cap for {coin_id}: {e}")
            return None

    def filter_symbols_by_market_cap(self, symbols: list, min_market_cap_usd: float) -> list:
        """
        Filters a list of symbols based on their market capitalization.
        Requires a mapping from Binance symbol to CoinGecko ID.
        """
        filtered_symbols = []
        # This is crucial:  Binance symbols (BTCUSDT) don't directly map to CoinGecko IDs (bitcoin)
        symbol_to_coingecko_id = {
            "BTCUSDT": "bitcoin",
            "ETHUSDT": "ethereum",
            "BNBUSDT": "binancecoin",
            "SOLUSDT": "solana",
            # Add more as needed, or dynamically fetch
        }

        for symbol in symbols:
            coingecko_id = symbol_to_coingecko_id.get(symbol)
            if not coingecko_id:
                logging.warning(f"No CoinGecko ID mapping found for Binance symbol: {symbol}. Skipping.")
                continue

            market_cap = self.get_market_cap_usd(coingecko_id)
            if market_cap is not None and market_cap >= min_market_cap_usd:
                filtered_symbols.append(symbol)
            else:
                logging.info(
                    f"Filtering out {symbol} (Market Cap: {market_cap}) as it's below threshold {min_market_cap_usd}.")
        return filtered_symbols

    def get_configured_leverage_and_margin_type(self, symbol: str) -> tuple[int, str]:
        """
        Retrieves the currently configured leverage and margin type for a symbol,
        using a local cache with an expiry and proper error handling.

        Args:
            symbol (str): The trading pair symbol (e.g., 'BTCUSDT').

        Returns:
            tuple[int, str]: A tuple containing (leverage, marginType), with fallback defaults.
        """
        if self.db:
            cached_info = self.db.get_cached_position_info(symbol, max_age_hours=1)
            if cached_info:
                logging.debug(f"Fetching leverage and margin from database cache for symbol {symbol}.")
                return cached_info

        # 2. Check in-memory cache
        current_time = time.time()
        if symbol in self._position_cache:
            cache_entry = self._position_cache[symbol]
            if current_time - cache_entry['timestamp'] < self.CACHE_EXPIRY:
                logging.debug(f"Fetching leverage and margin from memory cache for symbol {symbol}.")
                return cache_entry['leverage'], cache_entry['margin_type']
            else:
                logging.info(f"Memory cache for symbol {symbol} has expired. Calling API.")

        # 3. If cache is not present or expired, call the API
        try:
            positions = self.binance_client.client.futures_position_information()

            for position in positions:
                if position.get('symbol') == symbol:
                    leverage = int(position.get('leverage', 20))  # Default to 20 if missing
                    margin_type = position.get('marginType', 'ISOLATED')  # Default to ISOLATED if missing

                    # Store the new data in both memory and database cache
                    self._position_cache[symbol] = {
                        'leverage': leverage,
                        'margin_type': margin_type,
                        'timestamp': current_time
                    }
                    
                    # Store in database for persistence
                    if self.db:
                        self.db.cache_position_info(symbol, leverage, margin_type)

                    logging.info(f"Fetched leverage and margin from API for symbol {symbol}: {leverage}x {margin_type}")
                    return leverage, margin_type

            # If no position is found, return default values and cache them
            default_leverage = 20
            default_margin = 'ISOLATED'
            self._position_cache[symbol] = {
                'leverage': default_leverage,
                'margin_type': default_margin,
                'timestamp': current_time
            }
            logging.info(f"Position for symbol {symbol} not found. Using default settings: {default_leverage}x {default_margin}")
            return default_leverage, default_margin

        except (BinanceAPIException, BinanceRequestException) as e:
            logging.error(f"API error fetching position info for {symbol}: {e}")

            # If the API call fails, try to return stale data from the cache as a fallback
            if symbol in self._position_cache:
                logging.warning(f"API call failed. Using expired cache data for {symbol} as fallback.")
                cache_entry = self._position_cache[symbol]
                return cache_entry['leverage'], cache_entry['margin_type']

            # If no cache available, return safe defaults instead of None
            logging.warning(f"No cache available for {symbol}. Using safe defaults: 20x ISOLATED")
            return 20, 'ISOLATED'
            
        except Exception as e:
            logging.error(f"Unexpected error fetching position info for {symbol}: {e}")
            
            # Return safe defaults instead of None to prevent crashes
            logging.warning(f"Using safe defaults for {symbol}: 20x ISOLATED")
            return 20, 'ISOLATED'

