

def check_signal(df):
    """Trigger signal"""
    df["RSI"] = compute_rsi(df["close"])
    df["MA"] = compute_ma(df["close"], 14)

    last_rsi = df["RSI"].iloc[-1]
    last_ma = df["MA"].iloc[-1]
    last_price = df["close"].iloc[-1]

    signal = None
    if last_rsi < 30 and last_price > last_ma:
        signal = "BUY"
    elif last_rsi > 70 and last_price < last_ma:
        signal = "SELL"
    return signal


def compute_ma(prices, period=14):
    return prices.rolling(window=period).mean()


def compute_rsi(prices, period=14):
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))