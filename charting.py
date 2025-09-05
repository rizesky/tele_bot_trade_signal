import matplotlib
import numpy as np

from tradingview_ss import TradingViewChart

# Use non-interactive backend to avoid threading issues
matplotlib.use('Agg')

import os
from datetime import datetime
import pandas as pd


def plot_chart(
    ohlc_df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    take_profit_levels=None,
    stop_loss_level=None
) -> str:
    chart = TradingViewChart(width=1200, height=600)
    chart_title = symbol+"_"+timeframe
    os.makedirs("charts", exist_ok=True)
    chart_out_path="charts/"+chart_title+"_"+datetime.now().strftime("%Y%m%d-%H%M%S")+".png"
    chart_filename=chart.take_screenshot(
        ss_df=ohlc_df,
        symbol=symbol+"-"+timeframe,
        output_path=chart_out_path,
        tp_percentages=take_profit_levels,
        sl_percentage=stop_loss_level)
    if chart_filename is None:
        raise Exception("Chart is not generated, file not found")
    return chart_filename


def create_realistic_test_data(periods=200, base_price=30000):
    """Create more realistic test data with proper OHLC structure"""
    np.random.seed(42)
    dates = pd.date_range(end=pd.Timestamp.now(), periods=periods, freq="15min")

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