import json
import logging
import threading

import websocket

from config import BINANCE_WS_URL
from util import build_streams


class BinanceWS:
    def __init__(self, on_message_callback):
        self.url = f"{BINANCE_WS_URL}/stream?streams={build_streams()}"
        self.on_message_callback = on_message_callback
        self.ws = None
        self.stop_event = threading.Event()



    def run(self):
        self.ws = websocket.WebSocketApp(
            self.url,
            on_message=self.on_message,
            on_error=self.on_error,
        )
        t = threading.Thread(target=self._run_ws, daemon=True)
        t.start()
        logging.info(f"Binance WS listener started and connected to {self.url}")

    def _run_ws(self):
        while not self.stop_event.is_set():
            self.ws.run_forever()
            if not self.stop_event.is_set():
                logging.warning("WebSocket disconnected, retrying in 5s...")
                self.stop_event.wait(5)

    def stop(self):
        logging.info("Stopping Binance WS listener...")
        self.stop_event.set()
        if self.ws:
            self.ws.close()

    def on_error(self, ws, error):
        logging.error(error)

    def on_message(self, ws, message):
        data = json.loads(message)
        if "data" in data and "k" in data["data"]:
            self.on_message_callback(data["data"]["k"])
