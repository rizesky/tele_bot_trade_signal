import logging
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from config import BINANCE_ENV, TIMEFRAMES

symbol_separator = "&" if BINANCE_ENV == "dev" else "/" # for dev, we can hit testnet.binance.vision, and usually the separator is different from the prod


def now_utc() -> datetime:
    """
    Get current UTC datetime.
    """
    return datetime.now(timezone.utc)


def now_utc_timestamp() -> float:
    """
    Get current UTC timestamp (Unix seconds).
    """
    return now_utc().timestamp()


def now_utc_strftime(format_str: str = "%Y%m%d-%H%M%S") -> str:
    """
    Get current UTC datetime formatted as string.
    
    Args:
        format_str (str): Format string for datetime
    """
    return now_utc().strftime(format_str)


def pd_now_utc() -> pd.Timestamp:
    """
    Get current UTC timestamp as pandas Timestamp.
    """
    return pd.Timestamp.now(tz='UTC')


def build_streams(symbols):
    """Create URL stream multiple symbols & interval"""
    streams = []
    for sym in symbols:
        for tf in TIMEFRAMES:
            streams.append(f"{sym.lower()}@kline_{tf}")
    return symbol_separator.join(streams)


def compress_image(image_path, max_size_kb=1024):
    """
    Compress image to under specified size using PIL with better compression
    """
    try:
        from PIL import Image
        import io

        if not os.path.exists(image_path):
            return image_path

        file_size = os.path.getsize(image_path) / 1024  # KB
        if file_size <= max_size_kb:
            return image_path

        # Compress the image using PIL with progressive compression
        img = Image.open(image_path)

        # Convert to RGB if RGBA
        if img.mode == 'RGBA':
            img = img.convert('RGB')

        # Save with progressive compression for better size reduction
        img.save(image_path, format='PNG', optimize=True, compress_level=9)

        # If still too large, reduce quality further
        new_size = os.path.getsize(image_path) / 1024
        if new_size > max_size_kb:
            # Resize slightly if needed
            width, height = img.size
            img = img.resize((int(width * 0.9), int(height * 0.9)), Image.LANCZOS)
            img.save(image_path, format='PNG', optimize=True, compress_level=9)

        return image_path

    except ImportError:
        logging.error("PIL not available for image compression")
        return image_path
    except Exception as e:
        logging.error(f"Error compressing image: {e}")
        return image_path



def create_realistic_test_data(periods=200, base_price=30000):
    np.random.seed(42)
    dates = pd.date_range(end=pd_now_utc(), periods=periods, freq="15min")

    # Create price movement with trend and noise
    trend = np.linspace(0, 0.02, periods)
    noise = np.cumsum(np.random.normal(0, 0.001, periods))
    price_multiplier = 1 + trend + noise
    close_prices = base_price * price_multiplier

    # Create DataFrame with proper OHLC structure
    df = pd.DataFrame(index=dates)
    df['close'] = close_prices
    df['open'] = df['close'].shift(1).fillna(close_prices[0] * 0.999)

    # Initialize high and low columns with base values
    df['high'] = df[['open', 'close']].max(axis=1)
    df['low'] = df[['open', 'close']].min(axis=1)

    # Add realistic volatility to high/low
    volatility = np.random.uniform(0.001, 0.003, len(df))

    # Bullish candles
    bullish_mask = df['close'] > df['open']
    df.loc[bullish_mask, 'high'] = df.loc[bullish_mask, 'close'] * (1 + volatility[bullish_mask])
    df.loc[bullish_mask, 'low'] = df.loc[bullish_mask, 'open'] * (1 - volatility[bullish_mask] * 0.5)

    # Bearish candles
    bearish_mask = ~bullish_mask
    df.loc[bearish_mask, 'high'] = df.loc[bearish_mask, 'open'] * (1 + volatility[bearish_mask])
    df.loc[bearish_mask, 'low'] = df.loc[bearish_mask, 'close'] * (1 - volatility[bearish_mask] * 0.5)

    # Ensure OHLC relationships are correct
    df['high'] = df[['high', 'open', 'close']].max(axis=1)
    df['low'] = df[['low', 'open', 'close']].min(axis=1)

    # Add volume data
    df['volume'] = np.random.lognormal(10, 1, len(df))

    return df