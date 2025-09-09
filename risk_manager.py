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

    def get_max_leverage_for_symbol(self, symbol: str) -> int:
        """
        Get the maximum available leverage for a symbol from Binance API.
        Falls back to MAX_LEVERAGE config if API fails.
        
        Args:
            symbol (str): The trading pair symbol (e.g., 'BTCUSDT')
            
        Returns:
            int: Maximum leverage available for the symbol, or fallback if API fails
        """
        try:
            # Get leverage bracket information
            leverage_brackets = self.binance_client.client.futures_leverage_bracket()
            
            for bracket in leverage_brackets:
                if bracket['symbol'] == symbol:
                    # Get the highest leverage from the brackets
                    max_leverage = 1
                    for tier in bracket['brackets']:
                        if 'initialLeverage' in tier:
                            max_leverage = max(max_leverage, tier['initialLeverage'])
                    
                    logging.info(f"Max leverage for {symbol}: {max_leverage}x (from Binance API)")
                    return max_leverage
            
            # If symbol not found, use fallback
            logging.warning(f"Symbol {symbol} not found in leverage brackets, using fallback: {config.MAX_LEVERAGE}x")
            return config.MAX_LEVERAGE
            
        except (BinanceAPIException, BinanceRequestException) as e:
            logging.warning(f"Binance API error for {symbol}, using fallback: {config.MAX_LEVERAGE}x - {e}")
            return config.MAX_LEVERAGE
        except Exception as e:
            logging.warning(f"Unexpected error fetching max leverage for {symbol}, using fallback: {config.MAX_LEVERAGE}x - {e}")
            return config.MAX_LEVERAGE

    def calculate_leverage_based_tp_sl(self, symbol: str, entry_price: float, signal_type: str) -> tuple[list[float], float, dict]:
        """
        Calculate TP/SL levels based on leverage and risk management rules.
        
        Args:
            symbol (str): Trading pair symbol
            entry_price (float): Entry price for the trade
            signal_type (str): 'BUY' or 'SELL'
            
        Returns:
            tuple: (tp_levels, sl_level, risk_info)
        """
        try:
            # Get max leverage for the symbol
            max_leverage = self.get_max_leverage_for_symbol(symbol)
            
            # Calculate risk-based stop loss distance
            # Higher leverage = tighter stop loss to maintain same risk per trade
            base_risk_percent = config.LEVERAGE_BASE_RISK_PERCENT
            sl_distance_percent = base_risk_percent / max_leverage
            
            # Ensure minimum and maximum SL distances
            min_sl_distance = config.LEVERAGE_MIN_SL_DISTANCE
            max_sl_distance = config.LEVERAGE_MAX_SL_DISTANCE
            sl_distance_percent = max(min_sl_distance, min(sl_distance_percent, max_sl_distance))
            
            # Calculate TP levels based on leverage
            # Higher leverage = tighter TP levels for faster profit taking
            base_tp_percent = config.LEVERAGE_BASE_TP_PERCENT
            tp_distance_percent = base_tp_percent / max_leverage
            
            # Ensure minimum and maximum TP distances
            min_tp_distance = config.LEVERAGE_MIN_TP_DISTANCE
            max_tp_distance = config.LEVERAGE_MAX_TP_DISTANCE
            tp_distance_percent = max(min_tp_distance, min(tp_distance_percent, max_tp_distance))
            
            # Calculate TP levels (4 levels)
            tp_levels = []
            for i in range(1, 5):  # TP1, TP2, TP3, TP4
                tp_multiplier = i * tp_distance_percent
                if signal_type == "BUY":
                    tp_price = entry_price * (1 + tp_multiplier)
                else:  # SELL
                    tp_price = entry_price * (1 - tp_multiplier)
                tp_levels.append(tp_price)
            
            # Calculate stop loss
            if signal_type == "BUY":
                sl_price = entry_price * (1 - sl_distance_percent)
            else:  # SELL
                sl_price = entry_price * (1 + sl_distance_percent)
            
            # Calculate risk-reward ratio
            risk_amount = abs(entry_price - sl_price)
            reward_amount = abs(tp_levels[0] - entry_price)
            risk_reward_ratio = reward_amount / risk_amount if risk_amount > 0 else 0
            
            # Prepare risk information
            risk_info = {
                'max_leverage': max_leverage,
                'sl_distance_percent': sl_distance_percent,
                'tp_distance_percent': tp_distance_percent,
                'risk_reward_ratio': risk_reward_ratio,
                'risk_per_trade_percent': sl_distance_percent * max_leverage
            }
            
            logging.info(f"Leverage-based TP/SL for {symbol} ({signal_type}): "
                        f"Leverage={max_leverage}x, SL={sl_distance_percent:.2f}%, "
                        f"TP={tp_distance_percent:.2f}%, R:R={risk_reward_ratio:.2f}")
            
            return tp_levels, sl_price, risk_info
            
        except Exception as e:
            logging.error(f"Error calculating leverage-based TP/SL for {symbol}: {e}")
            # Fallback to default calculation
            return self._fallback_tp_sl_calculation(entry_price, signal_type)

    def _fallback_tp_sl_calculation(self, entry_price: float, signal_type: str) -> tuple[list[float], float, dict]:
        """Fallback TP/SL calculation using default percentages."""
        # Use default percentages from config
        sl_percent = config.DEFAULT_SL_PERCENT
        tp_percents = config.DEFAULT_TP_PERCENTS
        
        if signal_type == "BUY":
            tp_levels = [entry_price * (1 + p) for p in tp_percents]
            sl_price = entry_price * (1 - sl_percent)
        else:  # SELL
            tp_levels = [entry_price * (1 - p) for p in tp_percents]
            sl_price = entry_price * (1 + sl_percent)
        
        risk_info = {
            'max_leverage': 20,  # Default
            'sl_distance_percent': sl_percent,
            'tp_distance_percent': tp_percents[0],
            'risk_reward_ratio': tp_percents[0] / sl_percent,
            'risk_per_trade_percent': sl_percent
        }
        
        return tp_levels, sl_price, risk_info

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

