import logging
import time

import config
from charting_service import ChartingService
from config import MAX_LEVERAGE
from risk_manager import RiskManager
from strategy import check_signal
from telegram_client import format_signal_message, send_message_with_retry
from trade_manager import TradeManager
from util import create_realistic_test_data
from database import get_database
from util import now_utc
from structs import ChartData, ChartCallbackData, SignalNotificationData


class StrategyExecutor:
    """Handles the execution of trading strategies and manages signals."""
    def __init__(self, trade_manager:TradeManager|None,charting_service:ChartingService|None,risk_manager:RiskManager|None):
        self.trade_manager = trade_manager
        self.signal_cooldown = {}
        self.charting_service = charting_service
        self.risk_manager = risk_manager
        
        # Database integration for signal storage
        self.db = get_database() if config.DB_ENABLE_PERSISTENCE else None

    def handle_kline(self, k):
        """Callback for new kline data from the WebSocket with input validation."""
        # Validate input data structure
        if not self._validate_kline_input(k):
            logging.warning("Invalid kline data received, skipping processing")
            return
            
        symbol = k["s"]
        interval = k["i"]

        # Update kline data in the trade manager
        self.trade_manager.update_kline_data(k)
        df = self.trade_manager.get_kline_data(symbol, interval)

        # Process signals with the updated data
        self.process_signals(symbol, interval, df)

    def _validate_kline_input(self, k):
        """Basic validation of kline data structure before processing"""
        if not isinstance(k, dict):
            logging.debug("Kline data is not a dictionary")
            return False
        
        # Check only essential fields
        required_fields = ['s', 'i', 'o', 'h', 'l', 'c', 'v', 't']
        for field in required_fields:
            if field not in k:
                logging.debug(f"Missing required field '{field}' in kline data")
                return False
        
        # Basic data type validation (no strict value checking)
        try:
            # Just try to convert, don't validate ranges or relationships
            float(k['o'])  # open
            float(k['h'])  # high  
            float(k['l'])  # low
            float(k['c'])  # close
            float(k['v'])  # volume
            int(k['t'])    # timestamp
            
        except (ValueError, TypeError):
            logging.debug("Basic data type validation failed")
            return False
        except Exception:
            logging.debug("Unexpected error during basic validation")
            return False
            
        return True

    def handle_chart_callback(self, callback_data: ChartCallbackData):
        """Handles the result from the chart plotting task with proper error handling."""
        if callback_data.error:
            logging.error(f"Chart generation failed for {callback_data.symbol}-{callback_data.interval}: {callback_data.error}")
            # Send signal notification without chart as fallback
            logging.info(f"Sending signal notification without chart for {callback_data.symbol}-{callback_data.interval}")
            notif_data = SignalNotificationData(
                symbol=callback_data.symbol, interval=callback_data.interval,
                entry_prices=callback_data.entry_prices, tp_list=callback_data.tp_list,
                sl=callback_data.sl, chart_path=None, signal_info=callback_data.signal_info,
                leverage=callback_data.leverage, margin_type=callback_data.margin_type, risk_guidance=None
            )
            self._send_signal_notif(notif_data)
        else:
            # Validate chart file exists and is readable
            chart_path = callback_data.chart_path
            if chart_path and not self._validate_chart_file(chart_path):
                logging.warning(f"Chart file validation failed for {callback_data.symbol}-{callback_data.interval}, sending without chart")
                chart_path = None
                
            notif_data = SignalNotificationData(
                symbol=callback_data.symbol, interval=callback_data.interval,
                entry_prices=callback_data.entry_prices, tp_list=callback_data.tp_list,
                sl=callback_data.sl, chart_path=chart_path, signal_info=callback_data.signal_info,
                leverage=callback_data.leverage, margin_type=callback_data.margin_type, risk_guidance=None
            )
            self._send_signal_notif(notif_data)
        
        # Always update cooldown to prevent spam
        self.signal_cooldown[(callback_data.symbol, callback_data.interval)] = time.time()

    def _validate_chart_file(self, chart_path):
        """Validate that the chart file exists and is readable"""
        try:
            import os
            if not os.path.exists(chart_path):
                logging.warning(f"Chart file does not exist: {chart_path}")
                return False
                
            # Check file size (should be reasonable for a chart image)
            file_size = os.path.getsize(chart_path)
            if file_size < 1024:  # Less than 1KB is suspicious
                logging.warning(f"Chart file too small: {file_size} bytes")
                return False
                
            if file_size > 50 * 1024 * 1024:  # More than 50MB is too large
                logging.warning(f"Chart file too large: {file_size} bytes")
                return False
                
            return True
        except Exception as e:
            logging.warning(f"Error validating chart file {chart_path}: {e}")
            return False

    def process_signals(self, symbol, interval, df):
        """Process signals based on available data with higher timeframe confirmation."""
        min_candles_needed = 20 if config.SIMULATION_MODE or config.DATA_TESTING else 50
        
        # Check if we need to lazy load historical data for this symbol
        if len(df) < min_candles_needed and self.trade_manager.has_historical_loader:
            # Try to lazy load historical data if we don't have enough real-time data
            logging.info(f"Insufficient real-time data for {symbol}-{interval} ({len(df)} candles), attempting lazy load...")
            lazy_loaded = self.trade_manager.lazy_load_historical_data(symbol, interval)
            
            if lazy_loaded:
                # Get the updated data after lazy loading
                df = self.trade_manager.get_kline_data(symbol, interval)
                logging.info(f"After lazy loading: {len(df)} candles available for {symbol}-{interval}")
        
        # Final check for sufficient data
        if len(df) < min_candles_needed:
            logging.warning(f"Signals skipped. Need at least {min_candles_needed} candles, currently have {len(df)}.")
            return

        key = (symbol, interval)
        current_time = time.time()
        
        # Check cooldown
        if self.db:
            last_signal_time_db = self.db.get_last_signal_time(symbol, interval)
            if last_signal_time_db:
                last_signal_timestamp = last_signal_time_db.timestamp()
            else:
                last_signal_timestamp = 0
        else:
            last_signal_timestamp = self.signal_cooldown.get(key, 0)
        
        cooldown_seconds = 300 if config.SIMULATION_MODE else config.SIGNAL_COOLDOWN
        time_diff = current_time - last_signal_timestamp
        
        if time_diff < cooldown_seconds:
            logging.debug(f"On cooldown time for {cooldown_seconds} seconds, time left: {cooldown_seconds - time_diff:.1f} seconds. Ignoring signal")
            return

        # Check higher timeframe trend confirmation
        if not self._check_higher_timeframe_trend(symbol, interval):
            logging.debug(f"Signal skipped for {symbol}-{interval}: Higher timeframe trend not confirmed")
            return

        signal_info = check_signal(df)
        if signal_info:
            try:
                last_price = float(df["close"].iloc[-1])
            except (IndexError, ValueError, TypeError):
                logging.warning(f"Error getting last price for {symbol}-{interval}")
                return
            # --- Fetch leverage and margin type ---
            leverage, margin_type = self.risk_manager.get_configured_leverage_and_margin_type(symbol)
            entry_prices, tp_list, sl, risk_guidance = self._generate_trade_parameters(signal_info, last_price, df)

            if entry_prices:
                # Use clean data specifically for chart generation to prevent rendering issues
                clean_df = self.trade_manager.get_clean_kline_data_for_chart(symbol, interval)
                
                # Validate that we have enough clean data for charting
                if len(clean_df) < min_candles_needed:
                    logging.warning(f"Not enough clean data for charting {symbol}-{interval}: {len(clean_df)} < {min_candles_needed}")
                    return
                
                chart_data = ChartData(
                    ohlc_df=clean_df,  # Use clean data instead of raw data
                    symbol=symbol,
                    timeframe=interval,
                    tp_levels=tp_list,
                    sl_level=sl,
                    callback=lambda path, error: self.handle_chart_callback(
                        ChartCallbackData(
                            chart_path=path, error=error, symbol=symbol, interval=interval,
                            entry_prices=entry_prices, tp_list=tp_list, sl=sl,
                            signal_info=signal_info, leverage=leverage, margin_type=margin_type
                        )
                    )
                )
                self.charting_service.submit_plot_chart_task(chart_data)
                self.signal_cooldown[key] = current_time

    def _check_higher_timeframe_trend(self, symbol, interval):
        """
        Check if higher timeframe trend supports the potential signal.
        This helps filter out counter-trend signals.
        
        Args:
            symbol: Trading pair symbol
            interval: Current timeframe
            
        Returns:
            bool: True if higher timeframe trend is confirmed
        """
        # Define higher timeframe mapping
        higher_timeframes = {
            '15m': '1h',
            '30m': '4h', 
            '1h': '4h',
            '4h': '1d'
        }
        
        higher_tf = higher_timeframes.get(interval)
        if not higher_tf:
            # For daily or higher timeframes, no higher TF to check
            return True
            
        try:
            # Get higher timeframe data
            higher_df = self.trade_manager.get_kline_data(symbol, higher_tf)
            
            if len(higher_df) < 20:  # Need sufficient data
                logging.debug(f"Insufficient higher timeframe data for {symbol}-{higher_tf}")
                return True  # Don't block signal if no higher TF data
                
            # Calculate trend using simple moving average
            higher_df['MA_20'] = higher_df['close'].rolling(20).mean()
            higher_df['MA_50'] = higher_df['close'].rolling(50).mean()
            
            # Clean data
            higher_df_clean = higher_df.dropna()
            if len(higher_df_clean) < 2:
                return True
                
            try:
                current_price = float(higher_df_clean['close'].iloc[-1])
                ma_20 = float(higher_df_clean['MA_20'].iloc[-1])
                ma_50 = float(higher_df_clean['MA_50'].iloc[-1])
            except (IndexError, ValueError, TypeError):
                logging.debug(f"Error accessing higher timeframe values for {symbol}-{higher_tf}")
                return True
            
            # Check if higher timeframe is in uptrend (MA20 > MA50 and price > MA20)
            is_uptrend = ma_20 > ma_50 and current_price > ma_20
            is_downtrend = ma_20 < ma_50 and current_price < ma_20
            
            logging.debug(f"Higher TF trend for {symbol}-{higher_tf}: Uptrend={is_uptrend}, Downtrend={is_downtrend}")
            
            # For now, allow both trends (can be made more restrictive)
            # In a more sophisticated system, signals could be filtered by higher TF trend direction
            return True  # Allow all signals for now
            
        except Exception as e:
            logging.warning(f"Error checking higher timeframe trend for {symbol}-{interval}: {e}")
            return True  # Don't block signals on error

    def _generate_trade_parameters(self, signal_info, last_price, df=None):
        """Generate trade parameters with ATR-based position sizing."""

        # Access the final, pre-calculated values from the config file
        sl_percent = config.DEFAULT_SL_PERCENT
        tp_percents = config.DEFAULT_TP_PERCENTS

        if signal_info == "BUY":
            entry_prices = [last_price]
            # Calculate TP levels using the list of percentages
            tp_list = [last_price * (1 + p) for p in tp_percents]
            # Calculate SL level using the percentage
            sl = last_price * (1 - sl_percent)
            
            # Add ATR-based risk guidance if data is available
            risk_guidance = None
            if df is not None and len(df) >= 14:
                try:
                    from strategy import compute_atr, calculate_risk_guidance
                    atr = compute_atr(df)
                    if atr > 0:
                        risk_guidance = calculate_risk_guidance(atr, last_price)
                        logging.info(f"ATR Risk Guidance for BUY: {risk_guidance['position_guidance']}")
                except Exception as e:
                    logging.warning(f"Error calculating ATR-based risk guidance: {e}")
            
            return entry_prices, tp_list, sl, risk_guidance
            
        elif signal_info == "SELL":
            entry_prices = [last_price]
            # Calculate TP levels using the list of percentages
            tp_list = [last_price * (1 - p) for p in tp_percents]
            # Calculate SL level using the percentage
            sl = last_price * (1 + sl_percent)
            
            # Add ATR-based risk guidance if data is available
            risk_guidance = None
            if df is not None and len(df) >= 14:
                try:
                    from strategy import compute_atr, calculate_risk_guidance
                    atr = compute_atr(df)
                    if atr > 0:
                        risk_guidance = calculate_risk_guidance(atr, last_price)
                        logging.info(f"ATR Risk Guidance for SELL: {risk_guidance['position_guidance']}")
                except Exception as e:
                    logging.warning(f"Error calculating ATR-based risk guidance: {e}")
            
            return entry_prices, tp_list, sl, risk_guidance

        return None, None, None, None

    def _send_signal_notif(self, notif_data: SignalNotificationData):
        """Sends the formatted signal message to Telegram and stores in database."""
        # Store signal in database for persistence and analysis
        if self.db:
            signal_data = {
                'symbol': notif_data.symbol,
                'interval': notif_data.interval,
                'signal_type': notif_data.signal_info,
                'price': notif_data.entry_prices[0] if notif_data.entry_prices else 0,
                'entry_prices': notif_data.entry_prices,
                'tp_levels': notif_data.tp_list,
                'sl_level': notif_data.sl,
                'leverage': notif_data.leverage,
                'margin_type': notif_data.margin_type,
                'timestamp': now_utc()
            }
            self.db.store_signal(signal_data)
        
        # Send Telegram notification
        # Note: risk_guidance is set to None to keep messages clean and simple for now
        # The ATR risk guidance feature is implemented but disabled in Telegram messages
        # It can be enabled by passing risk_guidance instead of None
        if config.SIMULATION_MODE:
            original_msg = format_signal_message(notif_data.symbol, notif_data.interval, notif_data.entry_prices, notif_data.tp_list, notif_data.sl, notif_data.leverage, notif_data.margin_type, risk_guidance=None)
            msg = f"🚦 [SIMULATION] 🚦\n{original_msg}"
        else:
            msg = format_signal_message(notif_data.symbol, notif_data.interval, notif_data.entry_prices, notif_data.tp_list, notif_data.sl, notif_data.leverage, notif_data.margin_type, risk_guidance=None)
        send_message_with_retry(msg, notif_data.chart_path)
        app_mode = "SIMULATION" if config.SIMULATION_MODE else "REAL TRADE"
        logging.info(f"Sent {notif_data.signal_info} signal for {notif_data.symbol}-{notif_data.interval} ({app_mode})")

    def run_testing_mode(self):
        """Generates immediate test signals for DATA_TESTING mode."""
        if config.SYMBOLS is None:
            logging.error("No symbols found in config")
            return
        for symbol in config.SYMBOLS:
            for interval in config.TIMEFRAMES:
                try:
                    df = create_realistic_test_data(periods=50, base_price=30000)
                    test_signal = "BUY" if hash(symbol + interval) % 2 == 0 else "SELL"
                    try:
                        last_price = float(df['close'].iloc[-1])
                    except (IndexError, ValueError, TypeError):
                        logging.warning(f"Error getting test last price for {symbol}-{interval}")
                        continue
                    entry_prices, tp_list, sl, risk_guidance = self._generate_trade_parameters(test_signal, last_price)

                    if entry_prices:
                        # Only generate charts if charting service is available
                        if self.charting_service:
                            chart_data = ChartData(
                                ohlc_df=df,
                                symbol=symbol,
                                timeframe=interval,
                                tp_levels=tp_list,
                                sl_level=sl,
                                callback=lambda path, error: self.handle_chart_callback(
                                    ChartCallbackData(
                                        chart_path=path, error=error, symbol=symbol, interval=interval,
                                        entry_prices=entry_prices, tp_list=tp_list, sl=sl,
                                        signal_info=test_signal, leverage=MAX_LEVERAGE, margin_type="Isolated"
                                    )
                                )
                            )
                            self.charting_service.submit_plot_chart_task(chart_data)
                            logging.info(f"TESTING: {test_signal} signal sent for {symbol} {interval} with chart")
                        else:
                            logging.info(f"TESTING: {test_signal} signal generated for {symbol} {interval} (no chart - charting service disabled)")
                        time.sleep(1)
                except Exception as e:
                    logging.error(f"Error in testing mode for {symbol} {interval}: {e}")
