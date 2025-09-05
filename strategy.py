import logging


def compute_ma(prices, period=14):
    return prices.rolling(window=period).mean()


def compute_rsi(prices, period=14):
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def check_signal(df):
    """Refined signal trigger with MA cross-over and RSI confirmation"""

    # Ensure DataFrame has enough data and no NaNs from indicator calculation
    if len(df) < 50:  # Needs at least 50 candles to calculate indicators and check crosses
        logging.debug(f"Not enough data for signal check: {len(df)} candles.")
        return None

    df["RSI"] = compute_rsi(df["close"])
    df["MA"] = compute_ma(df["close"], 14)  # Using period 14 as per your original code

    # After computing, drop any rows that have NaN values (first 'period' rows for MA/RSI)
    df_cleaned = df.dropna()
    if len(df_cleaned) < 2:  # Need at least two rows for comparisons
        logging.debug("Not enough clean data after indicator calculation for signal check.")
        return None

    last_rsi = df_cleaned["RSI"].iloc[-1]
    last_ma = df_cleaned["MA"].iloc[-1]
    last_price = df_cleaned["close"].iloc[-1]

    # Previous candle values for cross-over detection
    prev_ma = df_cleaned["MA"].iloc[-2]
    prev_price = df_cleaned["close"].iloc[-2]

    signal = None

    # Buy Signal Conditions:
    # 1. Price crosses above MA (MA cross-up)
    # 2. RSI is in an oversold or just exiting oversold state (e.g., < 40, to catch entries early)
    if prev_price < prev_ma and last_price > last_ma and last_rsi < 40:  # < 40 is less strict than < 30
        signal = "BUY"
        logging.info(
            f"BUY Signal detected: Price crossed MA up ({prev_price:.2f}->{last_price:.2f} over {prev_ma:.2f}->{last_ma:.2f}), RSI is {last_rsi:.2f} (oversold/entering oversold).")

    # Sell Signal Conditions:
    # 1. Price crosses below MA (MA cross-down)
    # 2. RSI is in an overbought or just exiting overbought state (e.g., > 60)
    elif prev_price > prev_ma and last_price < last_ma and last_rsi > 60:  # > 60 is less strict than > 70
        signal = "SELL"
        logging.info(
            f"SELL Signal detected: Price crossed MA down ({prev_price:.2f}->{last_price:.2f} under {prev_ma:.2f}->{last_ma:.2f}), RSI is {last_rsi:.2f} (overbought/entering overbought).")

    return signal

