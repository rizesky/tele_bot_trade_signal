import logging
import os

from config import BINANCE_ENV, SYMBOLS, TIMEFRAMES

symbol_separator = "&" if BINANCE_ENV == "dev" else "/" # for dev, we can hit testnet.binance.vision, and usually the separator is different from the prod

def build_streams():
    """Buat URL stream multiple symbols & interval"""
    streams = []
    for sym in SYMBOLS:
        for tf in TIMEFRAMES:
            streams.append(f"{sym.lower()}@kline_{tf}")
    return symbol_separator.join(streams)


def compress_image(image_path, max_size_kb=1024):
    """
    Compress image to under specified size using PIL with better compression
    """
    try:
        from PIL import Image
        import io

        if not os.path.exists(image_path):
            return image_path

        file_size = os.path.getsize(image_path) / 1024  # KB
        if file_size <= max_size_kb:
            return image_path

        # Compress the image using PIL with progressive compression
        img = Image.open(image_path)

        # Convert to RGB if RGBA
        if img.mode == 'RGBA':
            img = img.convert('RGB')

        # Save with progressive compression for better size reduction
        img.save(image_path, format='PNG', optimize=True, compress_level=9)

        # If still too large, reduce quality further
        new_size = os.path.getsize(image_path) / 1024
        if new_size > max_size_kb:
            # Resize slightly if needed
            width, height = img.size
            img = img.resize((int(width * 0.9), int(height * 0.9)), Image.LANCZOS)
            img.save(image_path, format='PNG', optimize=True, compress_level=9)

        return image_path

    except ImportError:
        logging.error("PIL not available for image compression")
        return image_path
    except Exception as e:
        logging.error(f"Error compressing image: {e}")
        return image_path