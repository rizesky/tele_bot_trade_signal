import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
import json
import pandas as pd
from typing import Optional, List, Dict, Any

import config
from util import now_utc


class DatabaseManager:
    """
    SQLite database manager with connection pooling, migrations, and thread safety.
    Stores historical data, signals, and bot state for persistence across restarts.
    """
    
    def __init__(self, db_path: str = "trading_bot.db"):
        self.db_path = db_path
        self.pool_size = config.DB_POOL_SIZE
        self.connection_pool = []
        self.pool_lock = threading.Lock()
        self._local = threading.local()
        
        # Initialize database and run migrations
        self._initialize_database()
        self._run_migrations()
        
        logging.info(f"Database initialized: {db_path} with pool size {self.pool_size}")
    
    def _initialize_database(self):
        """Initialize database with connection pool"""
        with self.pool_lock:
            for _ in range(self.pool_size):
                conn = sqlite3.connect(
                    self.db_path, 
                    check_same_thread=False,
                    timeout=30.0
                )
                conn.execute("PRAGMA foreign_keys = ON")
                conn.execute("PRAGMA journal_mode = WAL")  # Better concurrency
                conn.execute("PRAGMA synchronous = NORMAL")  # Better performance
                self.connection_pool.append(conn)
    
    @contextmanager
    def get_connection(self):
        """Get a database connection from the pool (thread-safe)"""
        with self.pool_lock:
            if self.connection_pool:
                conn = self.connection_pool.pop()
            else:
                # Pool exhausted, create temporary connection
                conn = sqlite3.connect(
                    self.db_path, 
                    check_same_thread=False,
                    timeout=30.0
                )
                conn.execute("PRAGMA foreign_keys = ON")
                logging.warning("Database pool exhausted, created temporary connection")
        
        try:
            yield conn
        finally:
            with self.pool_lock:
                if len(self.connection_pool) < self.pool_size:
                    self.connection_pool.append(conn)
                else:
                    conn.close()
    
    def _run_migrations(self):
        """Run database migrations"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Create migrations table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS migrations (
                    id INTEGER PRIMARY KEY,
                    version INTEGER UNIQUE,
                    name TEXT,
                    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Get current version
            cursor.execute("SELECT MAX(version) FROM migrations")
            current_version = cursor.fetchone()[0] or 0
            
            # Apply migrations
            migrations = self._get_migrations()
            for version, name, sql in migrations:
                if version > current_version:
                    logging.info(f"Applying migration {version}: {name}")
                    cursor.executescript(sql)
                    cursor.execute(
                        "INSERT INTO migrations (version, name) VALUES (?, ?)",
                        (version, name)
                    )
            
            conn.commit()
    
    def _get_migrations(self):
        """Define database migrations"""
        return [
            (1, "initial_schema", """
                -- Historical OHLCV data storage
                CREATE TABLE IF NOT EXISTS historical_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    interval TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, interval, timestamp)
                );
                
                CREATE INDEX IF NOT EXISTS idx_historical_symbol_interval 
                ON historical_data(symbol, interval, timestamp DESC);
                
                -- Trading signals storage
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    interval TEXT NOT NULL,
                    signal_type TEXT NOT NULL, -- BUY/SELL
                    price REAL NOT NULL,
                    rsi REAL,
                    volume_ratio REAL,
                    market_regime TEXT,
                    entry_prices TEXT, -- JSON array
                    tp_levels TEXT, -- JSON array
                    sl_level REAL,
                    leverage INTEGER,
                    margin_type TEXT,
                    position_size REAL,
                    timestamp TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE INDEX IF NOT EXISTS idx_signals_symbol_time 
                ON signals(symbol, timestamp DESC);
                
                -- Bot state and configuration
                CREATE TABLE IF NOT EXISTS bot_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                -- Symbol management
                CREATE TABLE IF NOT EXISTS symbols (
                    symbol TEXT PRIMARY KEY,
                    is_active BOOLEAN DEFAULT 1,
                    last_signal_time TIMESTAMP,
                    signal_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                -- Performance metrics
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    metric_name TEXT NOT NULL,
                    metric_value REAL NOT NULL,
                    symbol TEXT,
                    interval TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE INDEX IF NOT EXISTS idx_metrics_name_time 
                ON metrics(metric_name, timestamp DESC);
            """),
            
            (2, "add_caching_tables", """
                -- Cache for API responses to reduce calls
                CREATE TABLE IF NOT EXISTS api_cache (
                    cache_key TEXT PRIMARY KEY,
                    cache_value TEXT NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE INDEX IF NOT EXISTS idx_cache_expires 
                ON api_cache(expires_at);
                
                -- Leverage and margin type cache
                CREATE TABLE IF NOT EXISTS position_cache (
                    symbol TEXT PRIMARY KEY,
                    leverage INTEGER NOT NULL,
                    margin_type TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """),
        ]
    
    def store_historical_data(self, symbol: str, interval: str, df: pd.DataFrame):
        """Store historical OHLCV data in database"""
        if df.empty:
            return
            
        with self.get_connection() as conn:
            try:
                # Prepare data for insertion
                data = []
                for timestamp, row in df.iterrows():
                    # Convert pandas Timestamp to Unix timestamp (integer)
                    timestamp_unix = int(timestamp.timestamp() * 1000)  # Store as milliseconds
                    data.append((
                        symbol, interval, timestamp_unix,
                        float(row['open']), float(row['high']), 
                        float(row['low']), float(row['close']), 
                        float(row['volume'])
                    ))
                
                # Insert with conflict resolution
                conn.executemany("""
                    INSERT OR REPLACE INTO historical_data 
                    (symbol, interval, timestamp, open, high, low, close, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, data)
                
                conn.commit()
                logging.debug(f"Stored {len(data)} historical records for {symbol}-{interval}")
                
            except Exception as e:
                logging.error(f"Error storing historical data for {symbol}-{interval}: {e}")
                conn.rollback()
    
    def load_historical_data(self, symbol: str, interval: str, limit: int = 200) -> pd.DataFrame:
        """Load historical data from database"""
        with self.get_connection() as conn:
            try:
                query = """
                    SELECT timestamp, open, high, low, close, volume 
                    FROM historical_data 
                    WHERE symbol = ? AND interval = ? 
                    ORDER BY timestamp DESC 
                    LIMIT ?
                """
                
                df = pd.read_sql_query(query, conn, params=(symbol, interval, limit))
                
                if not df.empty:
                    # Convert Unix timestamp (milliseconds) back to pandas Timestamp
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                    df.set_index('timestamp', inplace=True)
                    df.sort_index(inplace=True)  # Oldest first
                    
                return df
                
            except Exception as e:
                logging.error(f"Error loading historical data for {symbol}-{interval}: {e}")
                return pd.DataFrame()
    
    def store_signal(self, signal_data: Dict[str, Any]):
        """Store trading signal in database"""
        with self.get_connection() as conn:
            try:
                conn.execute("""
                    INSERT INTO signals 
                    (symbol, interval, signal_type, price, rsi, volume_ratio, market_regime,
                     entry_prices, tp_levels, sl_level, leverage, margin_type, position_size, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    signal_data['symbol'], signal_data['interval'], signal_data['signal_type'],
                    signal_data['price'], signal_data.get('rsi'), signal_data.get('volume_ratio'),
                    signal_data.get('market_regime'), json.dumps(signal_data.get('entry_prices')),
                    json.dumps(signal_data.get('tp_levels')), signal_data.get('sl_level'),
                    signal_data.get('leverage'), signal_data.get('margin_type'),
                    signal_data.get('position_size'), signal_data['timestamp']
                ))
                
                conn.commit()
                logging.debug(f"Stored signal: {signal_data['signal_type']} for {signal_data['symbol']}")
                
            except Exception as e:
                logging.error(f"Error storing signal: {e}")
                conn.rollback()
    
    def get_last_signal_time(self, symbol: str, interval: str) -> Optional[datetime]:
        """Get timestamp of last signal for symbol/interval"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT timestamp FROM signals 
                WHERE symbol = ? AND interval = ? 
                ORDER BY timestamp DESC LIMIT 1
            """, (symbol, interval))
            
            result = cursor.fetchone()
            return datetime.fromisoformat(result[0]) if result else None
    
    def cache_position_info(self, symbol: str, leverage: int, margin_type: str):
        """Cache position info to reduce API calls"""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO position_cache (symbol, leverage, margin_type, updated_at)
                VALUES (?, ?, ?, ?)
            """, (symbol, leverage, margin_type, now_utc()))
            conn.commit()
    
    def get_cached_position_info(self, symbol: str, max_age_hours: int = 1) -> Optional[tuple]:
        """Get cached position info if not expired"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT leverage, margin_type FROM position_cache 
                WHERE symbol = ? AND updated_at > datetime('now', '-{} hours')
            """.format(max_age_hours), (symbol,))
            
            result = cursor.fetchone()
            return (result[0], result[1]) if result else None
    
    def store_bot_state(self, key: str, value: Any):
        """Store bot state for persistence"""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO bot_state (key, value, updated_at)
                VALUES (?, ?, ?)
            """, (key, json.dumps(value), now_utc()))
            conn.commit()
    
    def get_bot_state(self, key: str, default=None):
        """Get bot state"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM bot_state WHERE key = ?", (key,))
            result = cursor.fetchone()
            
            if result:
                try:
                    return json.loads(result[0])
                except json.JSONDecodeError:
                    return result[0]
            return default
    
    def cleanup_old_data(self, days: int = 30):
        """Clean up old data to manage database size"""
        with self.get_connection() as conn:
            cutoff_date = now_utc().strftime('%Y-%m-%d %H:%M:%S')
            
            # Clean old historical data (keep recent data)
            conn.execute("""
                DELETE FROM historical_data 
                WHERE created_at < datetime('now', '-{} days')
            """.format(days))
            
            # Clean old cache entries
            conn.execute("DELETE FROM api_cache WHERE expires_at < datetime('now')")
            
            # Clean old metrics
            conn.execute("""
                DELETE FROM metrics 
                WHERE timestamp < datetime('now', '-{} days')
            """.format(days))
            
            conn.commit()
            logging.info(f"Cleaned up data older than {days} days")
    
    def close(self):
        """Close all database connections"""
        with self.pool_lock:
            for conn in self.connection_pool:
                conn.close()
            self.connection_pool.clear()
        logging.info("Database connections closed")


# Global database instance
db = None

def get_database() -> DatabaseManager:
    """Get global database instance"""
    global db
    if db is None:
        db = DatabaseManager()
    return db
