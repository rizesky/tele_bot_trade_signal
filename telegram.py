import logging
import os

import requests

from config import TELEGRAM_SEND_MESSAGE_URL, TELEGRAM_CHAT_ID, LEVERAGE


def format_signal_message(symbol: str, interval: str, entry_prices: list,
                          signal_details: list, sl_price: float) -> str:
    """
    Multi-line message untuk sinyal trading.
    """
    tf_label = {
        "15m": "Short-Term",
        "30m": "Mid-Term",
        "1h": "Medium-Term",
        "4h": "Long-Term"
    }.get(interval, "Signal")

    # entry price
    entry_str = "\n".join(f"{i+1}) {p:.6f}" for i, p in enumerate(entry_prices))

    # signal details
    details_str = "\n".join(f"{i+1}) {p:.6f}" for i, p in enumerate(signal_details))

    msg = (f"#{symbol.upper()} {interval.upper()} | 📊 {tf_label}\n\n"
           f"Entry price :\n{entry_str}\n\n"
           f"- ⏳ - Signal details :\n{details_str}\n\n"
           f"❌ Stop-Loss : {sl_price:.6f}\n"
           f"🧲 Leverage : {LEVERAGE}")
    return msg


def send_message(text: str, chart_path: str = None):
    """
    Kirim pesan ke Telegram, dengan optional chart sebagai photo.
    """
    try:
        if chart_path:
            url = TELEGRAM_SEND_MESSAGE_URL.replace("sendMessage", "sendPhoto")
            with open(chart_path, "rb") as photo:
                r = requests.post(
                    url,
                    data={"chat_id": TELEGRAM_CHAT_ID, "caption": text, "parse_mode": "Markdown"},
                    files={"photo": photo},
                    timeout=15
                )
        else:
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "Markdown"
            }
            r = requests.post(TELEGRAM_SEND_MESSAGE_URL, json=payload, timeout=15)

        r.raise_for_status()
        return r.json()
    except Exception as e:
        logging.error("Failed to send telegram message", exc_info=e)
        return None


def send_message_with_retry(msg:str, chart_path=None, max_retries=3):
    """Send message with retry logic and image validation"""

    if chart_path and os.path.exists(chart_path):
        # Validate image file
        file_size = os.path.getsize(chart_path)
        logging.info(f"Image file size: {file_size} bytes")

        # Check if file is too large (Telegram limit is 50MB, but let's be conservative)
        if file_size > 20 * 1024 * 1024:  # 20MB limit
            logging.error("Image too large, skipping image...")
            chart_path = None
        elif file_size < 1024:  # Less than 1KB is suspicious
            logging.error("Image too small, might be corrupted...")
            chart_path = None

    for attempt in range(max_retries):
        try:
            if chart_path and os.path.exists(chart_path):
                send_message(msg, chart_path)
            else:
                send_message(msg)  # Send without image
            logging.info(f"Message sent successfully on attempt {attempt + 1}")
            break
        except Exception as e:
            logging.error(f"Attempt {attempt + 1} failed: {e}")
            if attempt == max_retries - 1:
                # Last attempt, send without image
                try:
                    send_message(msg)
                    logging.warn("Sent message without image as fallback")
                except Exception as e2:
                    logging.error(f"Final fallback also failed: {e2}")
            else:
                import time
                time.sleep(1)  # Wait before retry