import json
import logging
import threading

import websocket

from config import BINANCE_WS_URL
from util import build_streams


class BinanceWS:
    """Binance Websocket Client"""
    def __init__(self, symbol_to_subs:list[str], on_message_callback):
        self.url = f"{BINANCE_WS_URL}/stream?streams={build_streams(symbol_to_subs)}"
        self.on_message_callback = on_message_callback
        self.ws = None
        self.is_shutting_down = threading.Event()
        self.stop_event = threading.Event()



    def run(self):
        self.ws = websocket.WebSocketApp(
            self.url,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        t = threading.Thread(name="BinanceWsThread",target=self._run_ws, daemon=True)
        t.start()
        logging.info(f"Binance websocket client listening to: {self.url}")

    def _run_ws(self):
        while not self.stop_event.is_set():
            self.ws.run_forever()
            if not self.stop_event.is_set():
                logging.warning("WebSocket disconnected, retrying in 5s...")
                self.stop_event.wait(5)

    def stop(self):
        logging.info("Stopping Binance websocket listener...")
        self.stop_event.set()
        if self.ws:
            self.ws.close()

    @staticmethod
    def on_close(ws,code, message):
        logging.info(f"Binance websocket client closed. Server closing response: ({code}) {message}")

    @staticmethod
    def on_error(ws, error):
        raise error

    def on_message(self, ws, message):
        data = json.loads(message)
        if "data" in data and "k" in data["data"]:
            self.on_message_callback(data["data"]["k"])
