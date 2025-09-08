import asyncio
import logging
import os
import threading

from util import now_utc_strftime
from structs import ChartData

import pandas as pd
from playwright.async_api import async_playwright

from tradingview_ss import TradingViewChart


class ChartingService:
    def __init__(self):
        self.browser = None
        self.playwright = None
        self.chart_generator = None
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(
            name="ChartingServiceThread",
            target=self._run_async_loop,
            daemon=True
        )
        self._is_ready = threading.Event()
        self._stop_event = asyncio.Event()
        self.chart_queue = None  # Will be initialized in the async loop
        
    
    def _run_async_loop(self):
        """Runs the async event loop in a separate thread."""
        asyncio.set_event_loop(self.loop)
        try:
            # Initialize queue in the async loop
            self.chart_queue = asyncio.Queue()
            self._stop_event = asyncio.Event()
            
            self.loop.run_until_complete(self._init_browser())
            self.loop.run_until_complete(self._consume_tasks())
        finally:
            # Cleanup resources
            try:
                self.loop.run_until_complete(self._cleanup())
            except Exception as e:
                logging.error(f"Error during charting service cleanup: {e}")
            finally:
                self.loop.close()

    async def _init_browser(self):
        """Initializes the Playwright browser."""
        try:
            self.playwright = await async_playwright().start()
            
            # Use system Chromium in Docker environment
            import os
            if os.path.exists('/usr/bin/chromium'):
                executable_path = '/usr/bin/chromium'
            elif os.path.exists('/usr/bin/chromium-browser'):
                executable_path = '/usr/bin/chromium-browser'
            else:
                executable_path = None
            
            if executable_path:
                self.browser = await self.playwright.chromium.launch(
                    headless=True,
                    executable_path=executable_path,
                    args=[
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                        '--disable-extensions',
                        '--disable-plugins',
                        '--disable-web-security',
                        '--disable-features=VizDisplayCompositor',
                        '--no-first-run',
                        '--no-default-browser-check',
                        '--disable-background-timer-throttling',
                        '--disable-renderer-backgrounding'
                    ]
                )
                logging.info(f"Using system Chromium: {executable_path}")
            else:
                self.browser = await self.playwright.chromium.launch(
                    headless=True, 
                    args=[
                        '--no-sandbox', 
                        '--disable-dev-shm-usage',
                        '--disable-gpu'
                    ]
                )
                logging.info("Using Playwright's Chromium")
                
            logging.info(f"Browser type: {self.browser.browser_type.name}")
            logging.info(f"Browser version: {self.browser.version}")
            self.chart_generator = TradingViewChart(width=1200, height=600, browser=self.browser)
            self._is_ready.set()
            logging.info("Charting service is ready and browser context initialized.")
        except Exception as e:
            logging.error(f"Failed to initialize Playwright browser: {e}")

    async def _consume_tasks(self):
        """Consumes tasks from the queue and executes them."""
        while not self._stop_event.is_set():
            try:
                # Wait for either a chart task or stop event
                done, pending = await asyncio.wait([
                    asyncio.create_task(self.chart_queue.get()),
                    asyncio.create_task(self._stop_event.wait())
                ], return_when=asyncio.FIRST_COMPLETED)
                
                # Cancel pending tasks
                for task in pending:
                    task.cancel()
                
                # Check if stop event was set
                if self._stop_event.is_set():
                    break
                    
                # Get the chart data from completed task
                chart_data = done.pop().result()
                
                # Skip if this is a sentinel value (None) indicating shutdown
                if chart_data is None:
                    break
                    
                try:
                    chart_path = await self._async_plot_chart(chart_data)
                    if chart_data.callback:
                        chart_data.callback(chart_path, None)
                except Exception as e:
                    logging.error(f"Error during chart generation: {e}")
                    if chart_data.callback:
                        chart_data.callback(None, e)
                finally:
                    self.chart_queue.task_done()
                    
            except asyncio.CancelledError:
                logging.info("Chart task consumer cancelled")
                break
            except Exception as e:
                logging.error(f"Error consuming chart task: {e}")

    def start(self):
        """Starts the charting service."""
        self.thread.start()

    async def _cleanup(self):
        """Cleanup Playwright resources."""
        try:
            if self.browser:
                await self.browser.close()
                logging.info("Browser closed")
            if self.playwright:
                await self.playwright.stop()
                logging.info("Playwright stopped")
        except Exception as e:
            logging.error(f"Error during Playwright cleanup: {e}")

    def stop(self):
        """Stops the charting service."""
        logging.info("Stopping charting service...")
        
        if self.loop and not self.loop.is_closed():
            # Signal the stop event
            self.loop.call_soon_threadsafe(self._stop_event.set)
            
            # Add sentinel value to queue to wake up consumer
            try:
                self.loop.call_soon_threadsafe(self.chart_queue.put_nowait, None)
            except Exception as e:
                logging.debug(f"Error adding sentinel to queue: {e}")
        
        # Wait for thread to finish
        if self.thread.is_alive():
            self.thread.join(timeout=5)
            if self.thread.is_alive():
                logging.warning("Charting service thread did not stop gracefully")
        
        logging.info("Charting service stopped")

    def submit_plot_chart_task(self, chart_data: ChartData):
        """
        Submits a chart plotting task to the async event loop without blocking.
        A callback function is provided to handle the result.
        """
        # Validate input DataFrame
        if chart_data.ohlc_df is None or chart_data.ohlc_df.empty:
            logging.warning(f"Chart task skipped for {chart_data.symbol}-{chart_data.timeframe}: DataFrame is None or empty")
            if chart_data.callback:
                chart_data.callback(None, "Empty DataFrame")
            return
        
        # Check if service is shutting down
        if self.loop is None or self.loop.is_closed():
            logging.warning("Chart task skipped: service is shutting down")
            if chart_data.callback:
                chart_data.callback(None, "Service shutting down")
            return
            
        self._is_ready.wait()  # Wait until the browser is ready
        
        try:
            self.loop.call_soon_threadsafe(
                self.chart_queue.put_nowait,
                chart_data
            )
        except Exception as e:
            logging.error(f"Error submitting chart task: {e}")
            if chart_data.callback:
                chart_data.callback(None, str(e))

    async def _async_plot_chart(self, chart_data: ChartData) -> str:
        """Asynchronous chart generation using the shared browser instance."""
        chart_title = f"{chart_data.symbol}_{chart_data.timeframe}"
        os.makedirs("charts", exist_ok=True)
        chart_out_path = f"charts/{chart_title}_{now_utc_strftime()}.png"

        chart_filename = await self.chart_generator.take_screenshot_async(
            ss_df=chart_data.ohlc_df,
            symbol=f"{chart_data.symbol}-{chart_data.timeframe}",
            output_path=chart_out_path,
            tp_levels=chart_data.tp_levels,
            sl_level=chart_data.sl_level
        )
        if chart_filename is None:
            raise Exception("Chart is not generated, file not found")
        return chart_filename




