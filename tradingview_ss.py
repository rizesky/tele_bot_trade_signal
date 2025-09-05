import json
import logging

import pandas as pd
from playwright.sync_api import sync_playwright


class TradingViewChart:
    def __init__(self, width=1200, height=600):
        self.width = width
        self.height = height

    def prepare_data(self, raw_df):
        """
        Convert DataFrame to TradingView format
        Works with either a 'time' column (UNIX seconds) or a datetime index.
        """
        ohlc_data = []
        rsi_data = []
        ma_data = []

        for idx, row in raw_df.iterrows():
            # Pick time from 'time' column if available, else use index
            if "time" in row:
                time_seconds = int(row["time"])
            else:
                time_seconds = int(pd.to_datetime(idx).timestamp())

            # OHLC
            ohlc_data.append({
                "time": time_seconds,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            })

            # RSI
            if "RSI" in row and pd.notna(row["RSI"]):
                rsi_data.append({
                    "time": time_seconds,
                    "value": float(row["RSI"])
                })

            # MA
            if "MA" in row and pd.notna(row["MA"]):
                ma_data.append({
                    "time": time_seconds,
                    "value": float(row["MA"])
                })

        return ohlc_data, rsi_data, ma_data

    def calculate_levels(self, ss_df, tp_percentages=[1, 2, 3, 4], sl_percentage=2):
        """Calculate TP and SL levels based on latest price"""
        latest_price = float(ss_df['close'].iloc[-1])
        tp_levels = [latest_price * (1 + pct / 100) for pct in tp_percentages]
        sl_level = latest_price * (1 - sl_percentage / 100)
        return tp_levels, sl_level

    def create_html(self, ohlc_data, rsi_data=None, ma_data=None, tp_levels=None, sl_level=None, symbol=""):
        """Create HTML with TradingView chart by loading a template file"""

        # --- Pre-processing Step: Filter and Sort Data ---

        # 1. Remove duplicates by time (if any exist)
        # A dictionary is a good way to get unique items
        unique_ohlc = {d['time']: d for d in ohlc_data}.values()

        # 2. Sort the data by time in ascending order
        sorted_ohlc_data = sorted(unique_ohlc, key=lambda x: x['time'])

        # Apply the same logic for other time-series data
        sorted_ma_data = []
        if ma_data:
            unique_ma = {d['time']: d for d in ma_data}.values()
            sorted_ma_data = sorted(unique_ma, key=lambda x: x['time'])

        sorted_rsi_data = []
        if rsi_data:
            unique_rsi = {d['time']: d for d in rsi_data}.values()
            sorted_rsi_data = sorted(unique_rsi, key=lambda x: x['time'])



        # Convert data to JSON with proper formatting
        ohlc_json = json.dumps(sorted_ohlc_data)
        rsi_json = json.dumps(sorted_rsi_data or [])
        ma_json = json.dumps(sorted_ma_data or [])
        tp_json = json.dumps(tp_levels or [])
        sl_json = json.dumps(sl_level) if sl_level else "null"

        # Define the path to the HTML template file
        template_path = "templates/chart_template.pyhtml"
        # template_path = "templates/test.html"

        try:
            # Read the HTML template file
            with open(template_path, 'r', encoding='utf-8') as file:
                html_template = file.read()

            # Replace placeholders with dynamic data
            rendered_html = html_template.format(
                symbol=symbol,
                ohlc_json=ohlc_json,
                rsi_json=rsi_json,
                ma_json=ma_json,
                tp_json=tp_json,
                sl_json=sl_json
            )
            return rendered_html

        except FileNotFoundError:
            logging.error(f"Error: The file '{template_path}' was not found.")
            return "<html><body><h1>Error: Template file not found.</h1></body></html>"
        except Exception as e:
            logging.error(f"An error occurred: {e}")
            return f"<html><body><h1>An error occurred: {e}</h1></body></html>"

    def take_screenshot(self, ss_df, symbol="Chart", output_path="",
                        tp_percentages=[1, 2, 3, 4], sl_percentage=2)-> str | None:

        """
        Generate chart screenshot

        Args:
            ss_df: DataFrame with datetime index and columns [open, high, low, close, RSI, MA]
            symbol: Chart title
            output_path: Output file path
            tp_percentages: TP levels as percentages above current price
            sl_percentage: SL level as percentage below current price
        """
        if output_path == "":
            raise Exception("output_path is empty")
        try:
            # Prepare data
            ohlc_data, rsi_data, ma_data = self.prepare_data(ss_df)
            if not ohlc_data:
                print("Error: No valid OHLC data found")
                return None

            # Calculate levels
            tp_levels, sl_level = self.calculate_levels(ss_df, tp_percentages, sl_percentage)

            # Create HTML
            html = self.create_html(ohlc_data, rsi_data, ma_data, tp_levels, sl_level, symbol)

            # Screenshot with Playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
                page = browser.new_page(viewport={'width': self.width + 100, 'height': self.height + 100})
                page.set_content(html)
                # page.pause()
                # return
                page.wait_for_function("document.querySelector('#chart canvas')", timeout=10000)
                page.wait_for_timeout(1000)  # Wait for rendering

                page.screenshot(path=output_path, clip={
                    'x': 0, 'y': 0, 'width': self.width + 40, 'height': self.height + 40
                })
                browser.close()
            return output_path

        except Exception as e:
            raise e


# Simple usage example
if __name__ == "__main__":
    # Sample data with your DataFrame format
    dates = pd.date_range('2025-09-01 19:30:00', periods=100, freq='30T')
    df = pd.DataFrame({
        'open': [109000 + i * 50 for i in range(100)],
        'high': [109000 + i * 50 + 200 for i in range(100)],
        'low': [109000 + i * 50 - 150 for i in range(100)],
        'close': [(109000 + i * 50) - 30 if i<50 else +25 for i in range(100)],
        'RSI': [50 + (i % 30) if i > 20 else None for i in range(100)],
        'MA': [109000 + i * 45 if i > 10 else None for i in range(100)]
    }, index=dates)

    # Generate chart
    chart = TradingViewChart(width=1200, height=600)
    chart.take_screenshot(
        ss_df=df,
        symbol="BTCUSDT Analysis",
        output_path="simple_chart.png",
        tp_percentages=[1, 2, 3, 4],
        sl_percentage=2
    )