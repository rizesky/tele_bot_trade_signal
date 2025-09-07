from dataclasses import dataclass
from typing import Optional, List, Any
import pandas as pd


@dataclass
class ChartData:
    ohlc_df: pd.DataFrame
    symbol: str
    timeframe: str
    tp_levels: List[float]
    sl_level: float
    callback: Optional[Any] = None


@dataclass
class SignalNotificationData:
    symbol: str
    interval: str
    entry_prices: List[float]
    tp_list: List[float]
    sl: float
    chart_path: Optional[str]
    signal_info: str
    leverage: int
    margin_type: str
    risk_guidance: Optional[dict] = None


@dataclass
class ChartCallbackData:
    chart_path: Optional[str]
    error: Optional[Exception]
    symbol: str
    interval: str
    entry_prices: List[float]
    tp_list: List[float]
    sl: float
    signal_info: str
    leverage: int
    margin_type: str


@dataclass
class TradingViewChartData:
    ohlc_data: List[dict]
    rsi_data: Optional[List[dict]] = None
    ma_data: Optional[List[dict]] = None
    tp_levels: Optional[List[float]] = None
    sl_level: Optional[float] = None
    symbol: str = ""
    width: int = 1200
    height: int = 600
