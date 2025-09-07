import logging

import pandas as pd
import config


def compute_ma(prices: pd.Series, period: int = 14) -> pd.Series:
    return prices.rolling(window=period).mean()


def compute_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def compute_volume_sma(volume: pd.Series, period: int = 20) -> pd.Series:
    """Calculate Simple Moving Average of volume for comparison"""
    return volume.rolling(window=period).mean()


def has_volume_confirmation(df: pd.DataFrame, volume_threshold: float = 1.2) -> bool:
    """
    Check if current volume confirms the potential signal.
    Volume should be above average to confirm price movement.
    
    Args:
        df: DataFrame with OHLCV data
        volume_threshold: Minimum volume multiplier (1.2 = 20% above average)
    """
    if len(df) < 20:  # Need at least 20 candles for volume average
        return False
        
    try:
        current_volume = float(df['volume'].iloc[-1])
        volume_sma = compute_volume_sma(df['volume'])
        avg_volume = float(volume_sma.iloc[-1]) if not volume_sma.empty else 0
        
        # Check if current volume is significantly above average
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
    except (IndexError, ValueError, ZeroDivisionError):
        return False
    return volume_ratio >= volume_threshold


def is_market_session_active() -> bool:
    """
    Check if current time is within active trading hours.
    Avoids trading during low-liquidity periods.
    """
    from util import now_utc
    
    # Get current UTC time
    current_utc = now_utc()
    current_hour = current_utc.hour
    
    # Active hours: 9 AM to 9 PM UTC
    # This corresponds to:
    # - Jakarta (UTC+7): 4 PM to 4 AM next day
    # - New York (UTC-5): 4 AM to 4 PM
    # - London (UTC+0): 9 AM to 9 PM
    return 9 <= current_hour <= 21


def compute_atr(df: pd.DataFrame, period: int = 14) -> float:
    """
    Calculate Average True Range (ATR) for volatility-based position sizing.
    
    Args:
        df: DataFrame with OHLCV data
        period: ATR calculation period (default 14)
    """
    high = df['high']
    low = df['low']
    close = df['close']
    
    # Calculate True Range components
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    
    # True Range is the maximum of the three
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # ATR is the moving average of True Range
    atr = true_range.rolling(window=period).mean()
    
    if atr.empty:
        return 0
    try:
        return float(atr.iloc[-1])
    except (IndexError, ValueError):
        return 0


def calculate_risk_guidance(atr: float, current_price: float, multiplier: int = 2) -> dict:
    """
    Calculate ATR-based risk guidance for position sizing.
    Provides risk recommendations without needing actual account balance.
    
    Args:
        atr: Average True Range value
        current_price: Current asset price
        multiplier: ATR multiplier for stop loss (default 2x)
    """
    if atr <= 0 or current_price <= 0:
        return {
            'stop_loss_distance': 0,
            'stop_loss_percent': 0,
            'recommended_risk_percent': 1.0,
            'volatility_level': 'UNKNOWN',
            'position_guidance': 'Invalid parameters',
            'atr_value': 0
        }
    
    # Calculate stop loss distance and percentage
    stop_loss_distance = atr * multiplier
    stop_loss_percent = (stop_loss_distance / current_price) * 100
    
    # Provide risk recommendations based on volatility
    if stop_loss_percent > 5:  # High volatility
        recommended_risk = 0.5
        volatility_level = 'HIGH'
        guidance = f"High volatility ({stop_loss_percent:.1f}% SL) - Use 0.5% risk per trade"
    elif stop_loss_percent > 2:  # Medium volatility
        recommended_risk = 1.0
        volatility_level = 'MEDIUM'
        guidance = f"Medium volatility ({stop_loss_percent:.1f}% SL) - Use 1% risk per trade"
    else:  # Low volatility
        recommended_risk = 1.5
        volatility_level = 'LOW'
        guidance = f"Low volatility ({stop_loss_percent:.1f}% SL) - Can use 1.5% risk per trade"
    
    return {
        'stop_loss_distance': round(stop_loss_distance, 4),
        'stop_loss_percent': round(stop_loss_percent, 2),
        'recommended_risk_percent': recommended_risk,
        'volatility_level': volatility_level,
        'position_guidance': guidance,
        'atr_value': round(atr, 4)
    }


def detect_market_regime(df: pd.DataFrame) -> str:
    """
    Detect current market regime to filter signals appropriately.
    
    Args:
        df: DataFrame with OHLCV data
    """
    if len(df) < 50:  # Need sufficient data
        return 'UNCLEAR'
    
    # Calculate volatility (standard deviation of returns)
    returns = df['close'].pct_change().dropna()
    volatility = returns.std() * 100  # Convert to percentage
    
    # Calculate trend strength using ADX-like indicator
    high = df['high']
    low = df['low']
    close = df['close']
    
    # Calculate directional movement
    dm_plus = high.diff()
    dm_minus = -low.diff()
    
    # True range
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # Smoothed values
    period = 14
    dm_plus_smooth = dm_plus.rolling(period).mean()
    dm_minus_smooth = dm_minus.rolling(period).mean()
    tr_smooth = true_range.rolling(period).mean()
    
    # Calculate directional indicators
    di_plus = 100 * (dm_plus_smooth / tr_smooth)
    di_minus = 100 * (dm_minus_smooth / tr_smooth)
    
    # Calculate ADX (trend strength)
    dx = 100 * abs(di_plus - di_minus) / (di_plus + di_minus)
    adx = dx.rolling(period).mean()
    
    # Get latest values with safe access
    try:
        # volatility is already a scalar (result of .std()), not a Series
        current_volatility = float(volatility) if not pd.isna(volatility) else 0
    except (ValueError, TypeError):
        current_volatility = 0
        
    try:
        current_adx = float(adx.iloc[-1]) if not adx.empty else 0
    except (IndexError, ValueError):
        current_adx = 0
    
    # Classify market regime
    if current_volatility > 3.0:  # High volatility
        return 'VOLATILE'
    elif current_adx > 25:  # Strong trend
        return 'TRENDING'
    elif current_adx < 15:  # Weak trend (ranging)
        return 'RANGING'
    else:
        return 'UNCLEAR'


def is_signal_appropriate_for_regime(signal: str, market_regime: str) -> bool:
    """
    Check if the signal is appropriate for the current market regime.
    
    Args:
        signal: Signal type ('BUY' or 'SELL')
        market_regime: Current market regime
    """
    # In trending markets, both BUY and SELL signals are appropriate
    if market_regime == 'TRENDING':
        return True
    
    # In ranging markets, be more selective
    elif market_regime == 'RANGING':
        return True  # Allow both for now, can be made more restrictive
    
    # In volatile markets, be cautious
    elif market_regime == 'VOLATILE':
        return True  # Allow both for now, can be made more restrictive
    
    # In unclear markets, be very selective
    elif market_regime == 'UNCLEAR':
        return False  # Skip signals in unclear market conditions
    
    return True


def check_signal(df):
    """
    Advanced signal detection with multiple confirmations:
    1. Market session validation
    2. Market regime detection
    3. Volume confirmation
    4. MA crossover detection
    5. RSI confirmation
    """

    # Ensure DataFrame has enough data and no NaNs from indicator calculation
    if len(df) < 50:  # Needs at least 50 candles to calculate indicators and check crosses
        logging.debug(f"Not enough data for signal check: {len(df)} candles.")
        return None

    # Check if we're in an active trading session (skip in simulation mode)
    if not config.SIMULATION_MODE and not is_market_session_active():
        logging.debug("Signal skipped: Outside active trading hours")
        return None

    # Work with a copy to avoid modifying the original DataFrame
    df_work = df.copy()

    # Detect market regime
    market_regime = detect_market_regime(df_work)
    logging.debug(f"Market regime detected: {market_regime}")

    # Calculate technical indicators
    df_work["RSI"] = compute_rsi(df_work["close"])
    df_work["MA"] = compute_ma(df_work["close"], 14)  # Using period 14 as per original code

    # After computing, drop any rows that have NaN values (first 'period' rows for MA/RSI)
    df_cleaned = df_work.dropna()
    if len(df_cleaned) < 2:  # Need at least two rows for comparisons
        logging.debug("Not enough clean data after indicator calculation for signal check.")
        return None

    try:
        last_rsi = float(df_cleaned["RSI"].iloc[-1])
        last_ma = float(df_cleaned["MA"].iloc[-1])
        last_price = float(df_cleaned["close"].iloc[-1])

        # Previous candle values for cross-over detection
        prev_ma = float(df_cleaned["MA"].iloc[-2])
        prev_price = float(df_cleaned["close"].iloc[-2])
    except (IndexError, ValueError):
        logging.debug("Error accessing indicator values for signal check")
        return None

    # Check volume confirmation (more relaxed in simulation mode)
    if config.SIMULATION_MODE:
        volume_confirmed = True  # Skip volume confirmation in simulation mode
        logging.debug("Volume confirmation bypassed in simulation mode")
    else:
        volume_confirmed = has_volume_confirmation(df_cleaned)
    
    signal = None

    # Buy Signal Conditions (relaxed in simulation mode):
    # 1. Price crosses above MA (MA cross-up)
    # 2. RSI confirmation (relaxed in simulation mode)
    # 3. Volume confirms the movement
    if config.SIMULATION_MODE:
        # Relaxed conditions for simulation - just need MA crossover
        if prev_price < prev_ma and last_price > last_ma and volume_confirmed:
            signal = "BUY"
        elif prev_price > prev_ma and last_price < last_ma and volume_confirmed:
            signal = "SELL"
    else:
        # Strict conditions for live trading
        if (prev_price < prev_ma and last_price > last_ma and 
            last_rsi < 40 and volume_confirmed):
            signal = "BUY"
        elif (prev_price > prev_ma and last_price < last_ma and 
              last_rsi > 60 and volume_confirmed):
            signal = "SELL"

    # Check if signal is appropriate for current market regime (skip in simulation mode)
    if signal and not config.SIMULATION_MODE and not is_signal_appropriate_for_regime(signal, market_regime):
        logging.debug(f"Signal {signal} skipped: Not appropriate for {market_regime} market regime")
        return None

    # Log successful signal detection
    if signal:
        try:
            current_vol = float(df_cleaned['volume'].iloc[-1])
            avg_vol = float(compute_volume_sma(df_cleaned['volume']).iloc[-1])
            volume_ratio = current_vol / avg_vol if avg_vol > 0 else 0
        except (IndexError, ValueError, TypeError, ZeroDivisionError):
            volume_ratio = 0
        logging.info(
            f"{signal} Signal detected: Price crossed MA ({prev_price:.2f}->{last_price:.2f} over/under {prev_ma:.2f}->{last_ma:.2f}), "
            f"RSI is {last_rsi:.2f}, Volume ratio: {volume_ratio:.2f}x, Market regime: {market_regime}")

    # Log when volume confirmation fails
    if not volume_confirmed and (prev_price < prev_ma and last_price > last_ma) or (prev_price > prev_ma and last_price < last_ma):
        logging.debug("Signal potential detected but volume confirmation failed")

    return signal

