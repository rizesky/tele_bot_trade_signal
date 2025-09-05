import asyncio
import logging
import os
import threading
from datetime import datetime

import pandas as pd
from playwright.async_api import async_playwright

from tradingview_ss import TradingViewChart


class ChartingService:
    def __init__(self):
        self.browser = None
        self.chart_generator = None
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(
            name="ChartingServiceThread",
            target=self._run_async_loop,
            daemon=True
        )
        self._is_ready = threading.Event()
        self.chart_queue = asyncio.Queue()  # Use an asyncio queue for communication

    def _run_async_loop(self):
        """Runs the async event loop in a separate thread."""
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._init_browser())
            self.loop.run_until_complete(self._consume_tasks()) # Start consuming tasks
        finally:
            self.loop.close()

    async def _init_browser(self):
        """Initializes the Playwright browser."""
        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=True, args=['--no-sandbox'])
            self.chart_generator = TradingViewChart(width=1200, height=600, browser=self.browser)
            self._is_ready.set()
            logging.info("Charting service is ready and browser context initialized.")
        except Exception as e:
            logging.error(f"Failed to initialize Playwright browser: {e}")

    async def _consume_tasks(self):
        """Consumes tasks from the queue and executes them."""
        while True:
            try:
                task_data = await self.chart_queue.get()
                ohlc_df, symbol, timeframe, tp_levels, sl_level, callback = task_data
                try:
                    chart_path = await self._async_plot_chart(ohlc_df, symbol, timeframe, tp_levels, sl_level)
                    if callback:
                        self.loop.call_soon_threadsafe(callback, chart_path, None)
                except Exception as e:
                    logging.error(f"Error during chart generation: {e}")
                    if callback:
                        self.loop.call_soon_threadsafe(callback, None, e)
                self.chart_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error consuming chart task: {e}")

    def start(self):
        """Starts the charting service."""
        self.thread.start()

    def stop(self):
        """Stops the charting service."""
        logging.warning("Stopping charting service...")
        self.loop.call_soon_threadsafe(self.chart_queue.put_nowait, (None, None, None, None, None, None))
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join()

    def submit_plot_chart_task(self, ohlc_df: pd.DataFrame, symbol: str, timeframe: str, tp_levels, sl_level, callback):
        """
        Submits a chart plotting task to the async event loop without blocking.
        A callback function is provided to handle the result.
        """
        self._is_ready.wait()  # Wait until the browser is ready
        self.loop.call_soon_threadsafe(
            self.chart_queue.put_nowait,
            (ohlc_df, symbol, timeframe, tp_levels, sl_level, callback)
        )

    async def _async_plot_chart(self, ohlc_df: pd.DataFrame, symbol: str, timeframe: str, tp_levels, sl_level) -> str:
        """Asynchronous chart generation using the shared browser instance."""
        chart_title = f"{symbol}_{timeframe}"
        os.makedirs("charts", exist_ok=True)
        chart_out_path = f"charts/{chart_title}_{datetime.now().strftime('%Y%m%d-%H%M%S')}.png"

        chart_filename = await self.chart_generator.take_screenshot_async(
            ss_df=ohlc_df,
            symbol=f"{symbol}-{timeframe}",
            output_path=chart_out_path,
            tp_levels=tp_levels,
            sl_level=sl_level
        )
        if chart_filename is None:
            raise Exception("Chart is not generated, file not found")
        return chart_filename




