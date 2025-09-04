import mplfinance as mpf
import pandas as pd
import numpy as np
import os
from datetime import datetime
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Polygon
from matplotlib.lines import Line2D
from scipy.stats import linregress
import matplotlib.dates as mdates
from matplotlib import ticker


def identify_supply_demand_zones(df, window=20, strength_threshold=0.002):
    """
    Improved supply and demand zone identification
    """
    zones = []

    if len(df) < window * 2:
        return zones

    # Find significant swing highs and lows
    swing_highs = []
    swing_lows = []

    for i in range(window, len(df) - window):
        current_high = df['high'].iloc[i]
        current_low = df['low'].iloc[i]

        # Check for swing high
        if current_high == df['high'].iloc[i - window:i + window + 1].max():
            swing_highs.append((i, current_high))

        # Check for swing low
        if current_low == df['low'].iloc[i - window:i + window + 1].min():
            swing_lows.append((i, current_low))

    # Create zones from swing points
    for idx, price in swing_highs:
        zones.append({
            'type': 'supply',
            'start_idx': max(0, idx - window),
            'end_idx': min(len(df) - 1, idx + window),
            'level': price,
            'strength': 1.0
        })

    for idx, price in swing_lows:
        zones.append({
            'type': 'demand',
            'start_idx': max(0, idx - window),
            'end_idx': min(len(df) - 1, idx + window),
            'level': price,
            'strength': 1.0
        })

    # Remove overlapping zones
    filtered_zones = []
    for zone in zones:
        overlap = False
        for existing in filtered_zones:
            if abs(zone['level'] - existing['level']) / existing['level'] < 0.005:
                overlap = True
                break
        if not overlap:
            filtered_zones.append(zone)

    return filtered_zones[:8]  # Max 8 zones


def calculate_trend_lines(df, lookback=50):
    """Calculate more accurate trend lines"""
    trend_lines = []

    if len(df) < lookback:
        return trend_lines

    recent_df = df.tail(lookback).copy()
    recent_df.reset_index(drop=True, inplace=True)

    # Find significant swing points
    swing_highs = []
    swing_lows = []

    window = 5
    for i in range(window, len(recent_df) - window):
        current_high = recent_df['high'].iloc[i]
        current_low = recent_df['low'].iloc[i]

        if current_high == recent_df['high'].iloc[i - window:i + window + 1].max():
            swing_highs.append((i, current_high))
        if current_low == recent_df['low'].iloc[i - window:i + window + 1].min():
            swing_lows.append((i, current_low))

    # Create trend lines from swing points
    if len(swing_highs) >= 2:
        # Use most recent swing highs
        recent_highs = sorted(swing_highs, key=lambda x: x[0])[-3:]
        x_vals = [point[0] for point in recent_highs]
        y_vals = [point[1] for point in recent_highs]

        if len(x_vals) >= 2:
            try:
                slope, intercept, r_value, _, _ = linregress(x_vals, y_vals)
                if abs(r_value) > 0.5:
                    start_idx = len(df) - lookback + x_vals[0]
                    end_idx = len(df) - lookback + x_vals[-1]
                    trend_lines.append({
                        'type': 'resistance',
                        'start_idx': start_idx,
                        'end_idx': end_idx,
                        'start_price': intercept + slope * x_vals[0],
                        'end_price': intercept + slope * x_vals[-1]
                    })
            except:
                pass

    if len(swing_lows) >= 2:
        recent_lows = sorted(swing_lows, key=lambda x: x[0])[-3:]
        x_vals = [point[0] for point in recent_lows]
        y_vals = [point[1] for point in recent_lows]

        if len(x_vals) >= 2:
            try:
                slope, intercept, r_value, _, _ = linregress(x_vals, y_vals)
                if abs(r_value) > 0.5:
                    start_idx = len(df) - lookback + x_vals[0]
                    end_idx = len(df) - lookback + x_vals[-1]
                    trend_lines.append({
                        'type': 'support',
                        'start_idx': start_idx,
                        'end_idx': end_idx,
                        'start_price': intercept + slope * x_vals[0],
                        'end_price': intercept + slope * x_vals[-1]
                    })
            except:
                pass

    return trend_lines


def create_realistic_test_data(periods=200, base_price=30000):
    """Create more realistic test data"""
    np.random.seed(42)
    dates = pd.date_range(end=pd.Timestamp.now(), periods=periods, freq="15T")

    # Create trend with noise
    trend = np.linspace(0, 0.02, periods)
    noise = np.random.normal(0, 0.001, periods)
    price_multiplier = 1 + trend + np.cumsum(noise)
    close_prices = base_price * price_multiplier

    df = pd.DataFrame(index=dates)
    df['close'] = close_prices
    df['open'] = df['close'].shift(1).fillna(close_prices[0])

    # Add realistic OHLC
    volatility = np.random.uniform(0.001, 0.004, periods)
    for i in range(len(df)):
        if i > 0:
            df['open'].iloc[i] = df['close'].iloc[i - 1]

        current_close = df['close'].iloc[i]
        current_open = df['open'].iloc[i]

        # Determine if bullish or bearish candle
        if current_close > current_open:
            df['high'].iloc[i] = current_close * (1 + volatility[i] * 0.8)
            df['low'].iloc[i] = current_open * (1 - volatility[i] * 0.6)
        else:
            df['high'].iloc[i] = current_open * (1 + volatility[i] * 0.8)
            df['low'].iloc[i] = current_close * (1 - volatility[i] * 0.6)

    # Ensure correct OHLC relationships
    df['high'] = df[['high', 'open', 'close']].max(axis=1)
    df['low'] = df[['low', 'open', 'close']].min(axis=1)

    return df


def plot_chart(df: pd.DataFrame, symbol: str, interval: str, tp_list=None, sl=None) -> str:
    """
    Create TradingView-style professional chart
    """
    df = df.copy()

    # Ensure proper index
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.date_range(end=pd.Timestamp.now(), periods=len(df), freq="15min")

    # Calculate indicators
    if len(df) >= 20:
        df['MA20'] = df['close'].rolling(window=20).mean()
    if len(df) >= 50:
        df['MA50'] = df['close'].rolling(window=50).mean()
    if len(df) >= 200:
        df['MA200'] = df['close'].rolling(window=200).mean()

    # Identify zones and trend lines
    zones = identify_supply_demand_zones(df)
    trend_lines = calculate_trend_lines(df)

    # Create TradingView-like style
    mc = mpf.make_marketcolors(
        up='#00b15e',  # Green for up candles
        down='#ff5b5a',  # Red for down candles
        edge='inherit',
        wick={'up': '#00b15e', 'down': '#ff5b5a'},
        volume='in',
        alpha=1.0
    )

    style = mpf.make_mpf_style(
        marketcolors=mc,
        gridstyle=':',
        gridcolor='#2a2e39',
        facecolor='#131722',
        figcolor='#131722',
        edgecolor='#363c4e',
        y_on_right=False,
        rc={
            'axes.labelcolor': '#d1d4dc',
            'text.color': '#d1d4dc',
            'xtick.color': '#d1d4dc',
            'ytick.color': '#d1d4dc'
        }
    )

    # Prepare additional plots
    apdict = []
    if 'MA20' in df.columns:
        apdict.append(mpf.make_addplot(df['MA20'], color='#f2a900', width=1.2, alpha=0.8))
    if 'MA50' in df.columns:
        apdict.append(mpf.make_addplot(df['MA50'], color='#2962ff', width=1.2, alpha=0.8))
    if 'MA200' in df.columns:
        apdict.append(mpf.make_addplot(df['MA200'], color='#ff6d00', width=1.2, alpha=0.8))

    # Create filename
    os.makedirs("charts", exist_ok=True)
    filename = f"charts/{symbol}_{interval}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

    # Create the main plot
    fig, axes = mpf.plot(
        df,
        type='candle',
        style=style,
        addplot=apdict if apdict else None,
        volume=False,
        returnfig=True,
        figsize=(16, 10),
        tight_layout=True,
        panel_ratios=(6, 1),
        scale_width_adjustment=dict(candle=0.8, volume=0.8),
        warn_too_much_data=len(df) + 1000
    )

    ax = axes[0]

    # Add supply/demand zones
    price_range = df['high'].max() - df['low'].min()
    zone_height = price_range * 0.005

    for zone in zones:
        try:
            start_date = df.index[zone['start_idx']]
            end_date = df.index[zone['end_idx']]
            level = zone['level']

            if zone['type'] == 'supply':
                color = '#ff4757'
                alpha = 0.2
                label = 'SUPPLY'
            else:
                color = '#2ed573'
                alpha = 0.2
                label = 'DEMAND'

            # Draw zone rectangle
            rect = Rectangle(
                (start_date, level - zone_height / 2),
                (end_date - start_date),
                zone_height,
                facecolor=color,
                alpha=alpha,
                edgecolor='none',
                zorder=1
            )
            ax.add_patch(rect)

            # Add zone label
            ax.text(end_date, level, f' {label}',
                    color=color, fontsize=10, fontweight='bold',
                    va='center', ha='left', alpha=0.8,
                    bbox=dict(boxstyle='round,pad=0.2', facecolor=color, alpha=0.3))

        except (IndexError, KeyError):
            continue

    # Add trend lines
    for trend in trend_lines:
        try:
            start_date = df.index[trend['start_idx']]
            end_date = df.index[trend['end_idx']]

            if trend['type'] == 'resistance':
                color = '#ff4757'
                linestyle = '--'
            else:
                color = '#2ed573'
                linestyle = '--'

            ax.plot([start_date, end_date],
                    [trend['start_price'], trend['end_price']],
                    color=color, linewidth=2, linestyle=linestyle, alpha=0.8)

        except (IndexError, KeyError):
            continue

    # Add TP/SL lines
    if tp_list:
        for i, tp in enumerate(tp_list):
            ax.axhline(y=tp, color='#2ed573', linestyle='--', linewidth=1.5, alpha=0.7)
            ax.text(df.index[-1], tp, f' TP{i + 1}: {tp:.2f}',
                    color='#2ed573', fontsize=9, fontweight='bold',
                    va='center', ha='left', backgroundcolor='rgba(46, 213, 115, 0.2)')

    if sl:
        ax.axhline(y=sl, color='#ff4757', linestyle='--', linewidth=2, alpha=0.8)
        ax.text(df.index[-1], sl, f' SL: {sl:.2f}',
                color='#ff4757', fontsize=9, fontweight='bold',
                va='center', ha='left', backgroundcolor='rgba(255, 71, 87, 0.2)')

    # Customize chart appearance
    ax.set_facecolor('#131722')
    ax.grid(True, alpha=0.2, color='#2a2e39')
    ax.set_title(f'{symbol} {interval.upper()} - Trading Analysis',
                 color='#d1d4dc', fontsize=16, fontweight='bold', pad=20)

    # Format x-axis
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')

    # Format y-axis
    ax.yaxis.set_major_formatter(ticker.StrMethodFormatter('{x:,.0f}'))

    # Style the spines
    for spine in ax.spines.values():
        spine.set_color('#363c4e')
        spine.set_linewidth(1)

    # Add legend
    legend_elements = []
    if 'MA20' in df.columns:
        legend_elements.append(Line2D([0], [0], color='#f2a900', lw=2, label='MA20'))
    if 'MA50' in df.columns:
        legend_elements.append(Line2D([0], [0], color='#2962ff', lw=2, label='MA50'))
    if 'MA200' in df.columns:
        legend_elements.append(Line2D([0], [0], color='#ff6d00', lw=2, label='MA200'))

    if legend_elements:
        ax.legend(handles=legend_elements, loc='upper left',
                  facecolor='#131722', edgecolor='#363c4e',
                  labelcolor='#d1d4dc', fontsize=9)

    # Save the chart
    try:
        plt.savefig(filename, facecolor='#131722', dpi=100, bbox_inches='tight',
                    edgecolor='none', transparent=False, format='png')
        plt.close('all')

        # Check file size and optimize if needed
        if os.path.exists(filename):
            file_size = os.path.getsize(filename)
            if file_size > 5 * 1024 * 1024:  # >5MB
                plt.savefig(filename, facecolor='#131722', dpi=72, bbox_inches='tight',
                            edgecolor='none', transparent=False, format='png')
                plt.close('all')

    except Exception as e:
        print(f"Error saving chart: {e}")
        # Create fallback simple chart
        fig, ax = plt.subplots(figsize=(12, 8), facecolor='#131722')
        ax.set_facecolor('#131722')
        ax.plot(df.index, df['close'], color='#00b15e', linewidth=2)
        ax.set_title(f'{symbol} {interval.upper()}', color='white')
        ax.tick_params(colors='white')
        plt.savefig(filename, facecolor='#131722', dpi=72, bbox_inches='tight')
        plt.close('all')

    return filename