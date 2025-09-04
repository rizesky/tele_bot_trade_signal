
from config import APP_MODE, SYMBOLS, TIMEFRAMES

symbol_separator = "&" if APP_MODE == "dev" else "/" # untuk dev biasanya hit testnet.binance.vision, dan pemisah koinnya beda dengan yang prod

def build_streams():
    """Buat URL stream multiple symbols & interval"""
    streams = []
    for sym in SYMBOLS:
        for tf in TIMEFRAMES:
            streams.append(f"{sym.lower()}@kline_{tf}")
    return symbol_separator.join(streams)