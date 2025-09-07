import json
import logging
import threading

import websocket

from config import BINANCE_WS_URL
from util import build_streams


class BinanceWS:
    """Binance Websocket Client with proper error handling and recovery"""
    def __init__(self, symbol_to_subs:list[str], on_message_callback):
        self.url = f"{BINANCE_WS_URL}/stream?streams={build_streams(symbol_to_subs)}"
        self.on_message_callback = on_message_callback
        self.ws = None
        self.is_shutting_down = threading.Event()
        self.stop_event = threading.Event()
        
        # Error handling and recovery configuration
        self.max_reconnect_attempts = 10  # Maximum reconnection attempts
        self.reconnect_delay = 5  # Delay between reconnection attempts (seconds)
        self.current_reconnect_attempts = 0
        self.last_error = None
        self.is_connected = False



    def run(self):
        """Start the WebSocket connection with proper error handling"""
        self.ws = websocket.WebSocketApp(
            self.url,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open
        )
        # Use non-daemon thread to ensure proper cleanup
        self.ws_thread = threading.Thread(name="BinanceWsThread", target=self._run_ws, daemon=False)
        self.ws_thread.start()
        logging.info(f"Binance websocket client listening to: {self.url}")

    def _run_ws(self):
        """Main WebSocket loop with automatic reconnection and error recovery"""
        while not self.stop_event.is_set():
            try:
                self.is_connected = False
                self.ws.run_forever()
                
                # If we reach here, connection was closed
                if not self.stop_event.is_set():
                    self._handle_reconnection()
                    
            except Exception as e:
                logging.error(f"Unexpected error in WebSocket loop: {e}")
                self.last_error = e
                if not self.stop_event.is_set():
                    self._handle_reconnection()
        
        logging.info("WebSocket thread stopped")

    def _handle_reconnection(self):
        """Handle WebSocket reconnection with exponential backoff"""
        if self.current_reconnect_attempts >= self.max_reconnect_attempts:
            logging.error(f"Max reconnection attempts ({self.max_reconnect_attempts}) reached. Stopping WebSocket.")
            self.stop_event.set()
            return
        
        self.current_reconnect_attempts += 1
        delay = min(self.reconnect_delay * (2 ** (self.current_reconnect_attempts - 1)), 60)  # Max 60 seconds
        
        logging.warning(f"WebSocket disconnected. Attempting reconnection {self.current_reconnect_attempts}/{self.max_reconnect_attempts} in {delay}s...")
        
        # Wait with exponential backoff
        self.stop_event.wait(delay)
        
        if not self.stop_event.is_set():
            # Reset connection state for retry
            self.is_connected = False
            self.last_error = None

    def stop(self):
        """Stop the WebSocket connection gracefully"""
        logging.info("Stopping Binance websocket listener...")
        self.stop_event.set()
        if self.ws:
            self.ws.close()
        # Wait for thread to finish
        if hasattr(self, 'ws_thread') and self.ws_thread.is_alive():
            self.ws_thread.join(timeout=5)

    def on_open(self, ws):
        """Called when WebSocket connection is established"""
        self.is_connected = True
        self.current_reconnect_attempts = 0  # Reset on successful connection
        self.last_error = None
        logging.info("WebSocket connection established successfully")

    def on_close(self, ws, code, message):
        """Called when WebSocket connection is closed"""
        self.is_connected = False
        if code == 1000:  # Normal closure
            logging.info("WebSocket connection closed normally")
        else:
            logging.warning(f"WebSocket connection closed unexpectedly. Code: {code}, Message: {message}")

    def on_error(self, ws, error):
        """Handle WebSocket errors gracefully instead of crashing"""
        self.is_connected = False
        self.last_error = error
        
        # Log the error but don't crash the application
        if isinstance(error, ConnectionRefusedError):
            logging.error("WebSocket connection refused. Check network connectivity.")
        elif isinstance(error, TimeoutError):
            logging.error("WebSocket connection timeout. Server may be overloaded.")
        elif isinstance(error, websocket.WebSocketException):
            logging.error(f"WebSocket error: {error}")
        else:
            logging.error(f"Unexpected WebSocket error: {error}")
        
        # Don't raise the error - let the reconnection logic handle it
        logging.info("Error handled, will attempt reconnection if not shutting down")

    def on_message(self, ws, message):
        """Handle incoming WebSocket messages with proper error handling"""
        try:
            # Validate message format before parsing
            if not message or not isinstance(message, str):
                logging.warning("Received invalid message format")
                return
                
            data = json.loads(message)
            
            # Validate message structure
            if not isinstance(data, dict):
                logging.warning("Received message is not a valid JSON object")
                return
                
            # Check for kline data
            if "data" in data and isinstance(data["data"], dict) and "k" in data["data"]:
                kline_data = data["data"]["k"]
                
                # Validate kline data structure
                if self._validate_kline_data(kline_data):
                    self.on_message_callback(kline_data)
                else:
                    logging.warning("Received invalid kline data structure")
            else:
                # Log other message types for debugging
                logging.debug(f"Received non-kline message: {data}")
                
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse WebSocket message as JSON: {e}")
        except Exception as e:
            logging.error(f"Unexpected error processing WebSocket message: {e}")
            # Add more debugging information
            import traceback
            logging.debug(f"Full traceback: {traceback.format_exc()}")

    def _validate_kline_data(self, kline_data):
        """Basic validation of kline data structure before processing"""
        required_fields = ['s', 'i', 'o', 'h', 'l', 'c', 'v', 't']
        
        if not isinstance(kline_data, dict):
            return False
            
        # Just check if required fields exist, don't validate values
        for field in required_fields:
            if field not in kline_data:
                return False
                
        return True
