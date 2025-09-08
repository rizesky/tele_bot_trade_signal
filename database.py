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
        conn = None
        is_temporary = False
        
        with self.pool_lock:
            if self.connection_pool:
                conn = self.connection_pool.pop()
            else:
                # Check if we've reached the maximum temporary connections limit
                max_temp_connections = self.pool_size * 2  # Allow up to 2x pool size total
                current_active = self.pool_size - len(self.connection_pool)
                
                if current_active >= max_temp_connections:
                    logging.error("Database connection limit reached, waiting for available connection...")
                    # Wait for a connection to become available
                    import time
                    time.sleep(0.1)  # Brief wait before retry
                    if self.connection_pool:
                        conn = self.connection_pool.pop()
                    else:
                        raise Exception("Database connection pool exhausted and max temporary connections reached")
                else:
                    # Create temporary connection
                    conn = sqlite3.connect(
                        self.db_path, 
                        check_same_thread=False,
                        timeout=30.0
                    )
                    conn.execute("PRAGMA foreign_keys = ON")
                    is_temporary = True
                    logging.warning(f"Database pool exhausted, created temporary connection ({current_active}/{max_temp_connections})")
        
        try:
            yield conn
        finally:
            with self.pool_lock:
                if not is_temporary and len(self.connection_pool) < self.pool_size:
                    self.connection_pool.append(conn)
                else:
                    # Close temporary connections or excess connections
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
            
            (2, "add_trading_mode_field", """
                -- Add trading mode field to signals table
                ALTER TABLE signals ADD COLUMN trading_mode TEXT DEFAULT 'REAL';
                
                -- Create index for trading mode queries
                CREATE INDEX IF NOT EXISTS idx_signals_trading_mode 
                ON signals(trading_mode, timestamp DESC);
                
                -- Update existing records based on configuration
                UPDATE signals SET trading_mode = 'SIMULATION' WHERE trading_mode IS NULL;
            """),
            
            (3, "add_caching_tables", """
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
        """Store trading signal in database with trading mode"""
        with self.get_connection() as conn:
            try:
                # Determine trading mode based on configuration
                trading_mode = self._get_trading_mode()
                
                conn.execute("""
                    INSERT INTO signals 
                    (symbol, interval, signal_type, price, rsi, volume_ratio, market_regime,
                     entry_prices, tp_levels, sl_level, leverage, margin_type, position_size, 
                     timestamp, trading_mode)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    signal_data['symbol'], signal_data['interval'], signal_data['signal_type'],
                    signal_data['price'], signal_data.get('rsi'), signal_data.get('volume_ratio'),
                    signal_data.get('market_regime'), json.dumps(signal_data.get('entry_prices')),
                    json.dumps(signal_data.get('tp_levels')), signal_data.get('sl_level'),
                    signal_data.get('leverage'), signal_data.get('margin_type'),
                    signal_data.get('position_size'), signal_data['timestamp'], trading_mode
                ))
                
                conn.commit()
                logging.debug(f"Stored {trading_mode} signal: {signal_data['signal_type']} for {signal_data['symbol']}")
                
            except Exception as e:
                logging.error(f"Error storing signal: {e}")
                conn.rollback()
    
    def _get_trading_mode(self) -> str:
        """Determine current trading mode based on configuration"""
        if config.DATA_TESTING:
            return 'DATA_TESTING'
        elif config.SIMULATION_MODE:
            return 'SIMULATION'
        else:
            return 'REAL'
    
    def get_signals_by_mode(self, trading_mode: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get signals filtered by trading mode"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM signals 
                WHERE trading_mode = ? 
                ORDER BY timestamp DESC 
                LIMIT ?
            """, (trading_mode, limit))
            
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def get_trading_mode_stats(self) -> Dict[str, int]:
        """Get count of signals by trading mode"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT trading_mode, COUNT(*) as count
                FROM signals 
                GROUP BY trading_mode
                ORDER BY count DESC
            """)
            
            return dict(cursor.fetchall())
    
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
        """Clean up old data to manage database size with detailed reporting"""
        cleanup_stats = {
            'historical_data': 0,
            'signals': 0,
            'metrics': 0,
            'cache_entries': 0,
            'db_size_before': 0,
            'db_size_after': 0
        }
        
        try:
            # Get database size before cleanup
            import os
            if os.path.exists(self.db_path):
                cleanup_stats['db_size_before'] = os.path.getsize(self.db_path)
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Count records before cleanup
                cursor.execute("SELECT COUNT(*) FROM historical_data WHERE datetime(timestamp/1000, 'unixepoch') < datetime('now', '-{} days')".format(days))
                cleanup_stats['historical_data'] = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM signals WHERE timestamp < datetime('now', '-{} days')".format(days))
                cleanup_stats['signals'] = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM metrics WHERE timestamp < datetime('now', '-{} days')".format(days))
                cleanup_stats['metrics'] = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM api_cache WHERE expires_at < datetime('now')")
                cleanup_stats['cache_entries'] = cursor.fetchone()[0]
                
                # Clean old historical data (use timestamp, not created_at)
                cursor.execute("""
                    DELETE FROM historical_data 
                    WHERE datetime(timestamp/1000, 'unixepoch') < datetime('now', '-{} days')
                """.format(days))
                
                # Clean old signals
                cursor.execute("""
                    DELETE FROM signals 
                    WHERE timestamp < datetime('now', '-{} days')
                """.format(days))
                
                # Clean old cache entries
                cursor.execute("DELETE FROM api_cache WHERE expires_at < datetime('now')")
                
                # Clean old metrics
                cursor.execute("""
                    DELETE FROM metrics 
                    WHERE timestamp < datetime('now', '-{} days')
                """.format(days))
                
                conn.commit()
                
                # Optimize database after cleanup
                cursor.execute("VACUUM")
                cursor.execute("ANALYZE")
                
            # Get database size after cleanup
            if os.path.exists(self.db_path):
                cleanup_stats['db_size_after'] = os.path.getsize(self.db_path)
            
            # Calculate savings
            size_saved = cleanup_stats['db_size_before'] - cleanup_stats['db_size_after']
            total_records_cleaned = (cleanup_stats['historical_data'] + 
                                   cleanup_stats['signals'] + 
                                   cleanup_stats['metrics'] + 
                                   cleanup_stats['cache_entries'])
            
            logging.info(f"Database cleanup completed:")
            logging.info(f"  • Historical data: {cleanup_stats['historical_data']:,} records")
            logging.info(f"  • Signals: {cleanup_stats['signals']:,} records")
            logging.info(f"  • Metrics: {cleanup_stats['metrics']:,} records")
            logging.info(f"  • Cache entries: {cleanup_stats['cache_entries']:,} records")
            logging.info(f"  • Total records cleaned: {total_records_cleaned:,}")
            logging.info(f"  • Database size: {cleanup_stats['db_size_before']:,} → {cleanup_stats['db_size_after']:,} bytes")
            logging.info(f"  • Space saved: {size_saved:,} bytes ({size_saved/1024/1024:.1f} MB)")
            
        except Exception as e:
            logging.error(f"Error during database cleanup: {e}")
            return cleanup_stats
            
        return cleanup_stats
    
    def get_database_stats(self) -> Dict[str, Any]:
        """Get comprehensive database statistics"""
        stats = {}
        
        try:
            import os
            
            # File size
            if os.path.exists(self.db_path):
                stats['file_size_bytes'] = os.path.getsize(self.db_path)
                stats['file_size_mb'] = stats['file_size_bytes'] / 1024 / 1024
            else:
                stats['file_size_bytes'] = 0
                stats['file_size_mb'] = 0
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Record counts
                cursor.execute("SELECT COUNT(*) FROM historical_data")
                stats['historical_records'] = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM signals")
                stats['signal_records'] = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM metrics")
                stats['metric_records'] = cursor.fetchone()[0]
                
                # Oldest and newest data timestamps
                cursor.execute("""
                    SELECT 
                        MIN(datetime(timestamp/1000, 'unixepoch')) as oldest,
                        MAX(datetime(timestamp/1000, 'unixepoch')) as newest
                    FROM historical_data
                """)
                result = cursor.fetchone()
                stats['oldest_data'] = result[0] if result[0] else 'N/A'
                stats['newest_data'] = result[1] if result[1] else 'N/A'
                
                # Data by symbol
                cursor.execute("""
                    SELECT symbol, COUNT(*) as count 
                    FROM historical_data 
                    GROUP BY symbol 
                    ORDER BY count DESC 
                    LIMIT 5
                """)
                stats['top_symbols'] = cursor.fetchall()
                
                # Data by interval
                cursor.execute("""
                    SELECT interval, COUNT(*) as count 
                    FROM historical_data 
                    GROUP BY interval 
                    ORDER BY count DESC
                """)
                stats['data_by_interval'] = cursor.fetchall()
                
        except Exception as e:
            logging.error(f"Error getting database stats: {e}")
            stats['error'] = str(e)
        
        return stats
    
    def should_cleanup(self, max_size_mb: float = 500, max_records: int = 5000000) -> bool:
        """Check if database cleanup is needed based on size or record count"""
        try:
            stats = self.get_database_stats()
            
            # Check file size
            if stats.get('file_size_mb', 0) > max_size_mb:
                logging.warning(f"Database size ({stats['file_size_mb']:.1f} MB) exceeds limit ({max_size_mb} MB)")
                return True
            
            # Check record count
            total_records = stats.get('historical_records', 0) + stats.get('signal_records', 0)
            if total_records > max_records:
                logging.warning(f"Total records ({total_records:,}) exceeds limit ({max_records:,})")
                return True
            
            return False
            
        except Exception as e:
            logging.error(f"Error checking cleanup need: {e}")
            return False
    
    def auto_cleanup_if_needed(self, retention_days: int = None):
        """Automatically cleanup database if it exceeds size/record limits"""
        if retention_days is None:
            retention_days = config.DB_CLEANUP_DAYS
        
        try:
            if self.should_cleanup():
                logging.info("Database cleanup needed, starting automatic cleanup...")
                stats_before = self.get_database_stats()
                
                cleanup_stats = self.cleanup_old_data(retention_days)
                
                stats_after = self.get_database_stats()
                
                logging.info(f"Auto-cleanup completed:")
                logging.info(f"  • Records: {stats_before.get('historical_records', 0):,} → {stats_after.get('historical_records', 0):,}")
                logging.info(f"  • Size: {stats_before.get('file_size_mb', 0):.1f} MB → {stats_after.get('file_size_mb', 0):.1f} MB")
                
                return cleanup_stats
            else:
                logging.debug("Database cleanup not needed")
                return None
                
        except Exception as e:
            logging.error(f"Error in auto cleanup: {e}")
            return None
    
    def compress_old_data(self, compress_after_days: int = 3):
        """
        Compress old historical data by keeping only every Nth record for older data.
        This reduces storage while preserving data patterns.
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get data older than compress_after_days
                cursor.execute("""
                    SELECT DISTINCT symbol, interval 
                    FROM historical_data 
                    WHERE datetime(timestamp/1000, 'unixepoch') < datetime('now', '-{} days')
                    ORDER BY symbol, interval
                """.format(compress_after_days))
                
                symbol_intervals = cursor.fetchall()
                total_compressed = 0
                
                for symbol, interval in symbol_intervals:
                    # For each symbol/interval, keep only every 4th record for old data
                    # This reduces storage by ~75% while maintaining trend visibility
                    
                    cursor.execute("""
                        DELETE FROM historical_data 
                        WHERE symbol = ? AND interval = ? 
                        AND datetime(timestamp/1000, 'unixepoch') < datetime('now', '-{} days')
                        AND id NOT IN (
                            SELECT id FROM historical_data 
                            WHERE symbol = ? AND interval = ?
                            AND datetime(timestamp/1000, 'unixepoch') < datetime('now', '-{} days')
                            ORDER BY timestamp
                            LIMIT -1 OFFSET 0
                            -- Keep every 4th record using modulo on row_number
                        )
                        AND (id % 4) != 0
                    """.format(compress_after_days, compress_after_days), 
                    (symbol, interval, symbol, interval))
                    
                    compressed_count = cursor.rowcount
                    total_compressed += compressed_count
                    
                    if compressed_count > 0:
                        logging.debug(f"Compressed {compressed_count} records for {symbol}-{interval}")
                
                conn.commit()
                
                if total_compressed > 0:
                    logging.info(f"Data compression completed: {total_compressed:,} records removed")
                    # Optimize database after compression
                    cursor.execute("VACUUM")
                    
                return total_compressed
                
        except Exception as e:
            logging.error(f"Error during data compression: {e}")
            return 0
    
    def optimize_database(self):
        """Optimize database performance and storage"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                logging.info("Starting database optimization...")
                
                # Update table statistics
                cursor.execute("ANALYZE")
                
                # Rebuild indexes for better performance
                cursor.execute("REINDEX")
                
                # Compact database file
                cursor.execute("VACUUM")
                
                conn.commit()
                
                logging.info("Database optimization completed")
                
        except Exception as e:
            logging.error(f"Error during database optimization: {e}")
    
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
