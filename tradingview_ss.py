import json
import logging

import pandas as pd
from playwright.async_api import Browser
from structs import TradingViewChartData


class TradingViewChart:
    def __init__(self, browser: Browser, width=1200, height=600):
        self.browser = browser
        self.width = width
        self.height = height

    @staticmethod
    def prepare_data(raw_df):
        """
        Convert DataFrame to TradingView format
        Works with either a 'time' column (UNIX seconds) or a datetime index.
        """
        # Validate input DataFrame
        if raw_df is None or raw_df.empty:
            logging.warning("prepare_data received None or empty DataFrame")
            return [], [], []
            
        ohlc_data = []
        rsi_data = []
        ma_data = []

        for idx, row in raw_df.iterrows():
            # Pick time from 'time' column if available, else use index
            if "time" in row:
                time_seconds = int(row["time"])
            else:
                time_seconds = int(pd.to_datetime(idx, utc=True).timestamp())

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

    @staticmethod
    def create_html(chart_data: TradingViewChartData) -> str:
        """Create HTML with TradingView chart by loading a template file"""

        # --- Pre-processing Step: Filter and Sort Data ---

        # 1. Remove duplicates by time (if any exist)
        # A dictionary is a good way to get unique items
        unique_ohlc = {d['time']: d for d in chart_data.ohlc_data}.values()

        # 2. Sort the data by time in ascending order
        sorted_ohlc_data = sorted(unique_ohlc, key=lambda x: x['time'])

        # Apply the same logic for other time-series data
        sorted_ma_data = []
        if chart_data.ma_data:
            unique_ma = {d['time']: d for d in chart_data.ma_data}.values()
            sorted_ma_data = sorted(unique_ma, key=lambda x: x['time'])

        sorted_rsi_data = []
        if chart_data.rsi_data:
            unique_rsi = {d['time']: d for d in chart_data.rsi_data}.values()
            sorted_rsi_data = sorted(unique_rsi, key=lambda x: x['time'])



        # Convert data to JSON with proper formatting
        ohlc_json = json.dumps(sorted_ohlc_data)
        rsi_json = json.dumps(sorted_rsi_data or [])
        ma_json = json.dumps(sorted_ma_data or [])
        tp_json = json.dumps(chart_data.tp_levels or [])
        sl_json = json.dumps(chart_data.sl_level) if chart_data.sl_level else "null"

        # Define the path to the HTML template file
        template_path = "templates/chart_template.pyhtml"

        try:
            # Read the HTML template file
            with open(template_path, 'r', encoding='utf-8') as file:
                html_template = file.read()

            # Replace placeholders with dynamic data
            rendered_html = html_template.format(
                symbol=chart_data.symbol,
                ohlc_json=ohlc_json,
                rsi_json=rsi_json,
                ma_json=ma_json,
                tp_json=tp_json,
                sl_json=sl_json,
                width=chart_data.width,
                height=chart_data.height,
            )
            return rendered_html

        except FileNotFoundError:
            logging.error(f"Error: The file '{template_path}' was not found.")
            return "<html><body><h1>Error: Template file not found.</h1></body></html>"
        except Exception as e:
            logging.error(f"An error occurred: {e}")
            return f"<html><body><h1>An error occurred: {e}</h1></body></html>"

    async def take_screenshot_async(self, ss_df, symbol="Chart", output_path="",
                                    tp_levels=None, sl_level=None):
        """
        Asynchronously generate chart screenshot using the shared browser instance.
        """
        if tp_levels is None:
            tp_levels = []

        if not output_path:
            raise ValueError("output_path cannot be empty")

        page=None
        try:
            ohlc_data, rsi_data, ma_data = self.prepare_data(ss_df)
            if not ohlc_data:
                logging.error("No valid OHLC data found")
                return None

            chart_data = TradingViewChartData(
                ohlc_data=ohlc_data,
                rsi_data=rsi_data,
                ma_data=ma_data,
                tp_levels=tp_levels,
                sl_level=sl_level,
                symbol=symbol,
                width=self.width,
                height=self.height
            )
            html = self.create_html(chart_data)

            page = await self.browser.new_page(viewport={'width': self.width + 100, 'height': self.height + 100})
            page.on("pageerror", lambda x: logging.error(f"Browser JS Error: {x}"))
            await page.set_content(html)

            # Wait for the chart canvas to exist
            await page.wait_for_function("document.querySelector('#chart canvas')", timeout=10000)
            # Wait until the chart has finished drawing
            await page.wait_for_function("window.chartReady === true", timeout=10000)
            # Optional: small extra delay
            await page.wait_for_timeout(200)

            # Verify canvas has content (non-zero dimensions)
            canvas_info = await page.evaluate("""
                        () => {
                            const canvas = document.querySelector('#chart canvas');
                            if (!canvas) return { exists: false };
                            return {
                                exists: true,
                                width: canvas.width,
                                height: canvas.height,
                                hasContent: canvas.width > 0 && canvas.height > 0
                            };
                        }
                    """)

            logging.info(f"Canvas info: {canvas_info}")

            if not canvas_info.get('hasContent', False):
                raise Exception("Chart canvas has no content")


            container = page.locator(".container")
            await container.screenshot(path=output_path)
            await page.close()
            return output_path


        except Exception as e:
            logging.error(f"Chart rendering failed: {e}")
            # Debug information
            if page is not None:
                page_content = await page.content()
                logging.debug(f"Page content length: {len(page_content)}")
                # Check if external resources loaded
                try:
                    js_loaded = await page.evaluate("typeof window.LightweightCharts !== 'undefined'")
                    logging.info(f"TradingView JS loaded: {js_loaded}")
                except Exception as e:
                    raise e
            raise e


        finally:

            await page.close()
