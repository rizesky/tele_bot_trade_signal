import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Optional

import config
from database import get_database


class DatabaseMaintenanceService:
    """
    Background service for database maintenance tasks including:
    - Automatic cleanup based on size/record limits
    - Periodic maintenance scheduling
    - Database health monitoring
    """
    
    def __init__(self):
        self.db = get_database() if config.DB_ENABLE_PERSISTENCE else None
        self.maintenance_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.last_cleanup = datetime.now()
        self.cleanup_interval = timedelta(hours=config.DB_CLEANUP_INTERVAL_HOURS)
        
    def start(self):
        """Start the database maintenance service"""
        if not self.db or not config.DB_AUTO_CLEANUP_ENABLED:
            logging.info("Database maintenance service disabled")
            return
            
        if self.maintenance_thread and self.maintenance_thread.is_alive():
            logging.warning("Database maintenance service already running")
            return
            
        self.stop_event.clear()
        self.maintenance_thread = threading.Thread(
            target=self._maintenance_loop,
            name="DatabaseMaintenance",
            daemon=True
        )
        self.maintenance_thread.start()
        logging.info(f"Database maintenance service started (cleanup every {config.DB_CLEANUP_INTERVAL_HOURS}h)")
        
        # Log initial database stats
        self._log_database_stats()
    
    def stop(self):
        """Stop the database maintenance service"""
        if not self.maintenance_thread:
            return
            
        logging.info("Stopping database maintenance service...")
        self.stop_event.set()
        
        if self.maintenance_thread.is_alive():
            self.maintenance_thread.join(timeout=5)
            
        logging.info("Database maintenance service stopped")
    
    def _maintenance_loop(self):
        """Main maintenance loop"""
        while not self.stop_event.is_set():
            try:
                current_time = datetime.now()
                
                # Check if it's time for maintenance
                if current_time - self.last_cleanup >= self.cleanup_interval:
                    self._perform_maintenance()
                    self.last_cleanup = current_time
                
                # Wait for next check (every 30 minutes)
                self.stop_event.wait(timeout=1800)  # 30 minutes
                
            except Exception as e:
                logging.error(f"Error in database maintenance loop: {e}")
                # Wait a bit before retrying to avoid rapid error loops
                self.stop_event.wait(timeout=300)  # 5 minutes
    
    def _perform_maintenance(self):
        """Perform database maintenance tasks"""
        try:
            logging.info("Starting scheduled database maintenance...")
            
            # Get stats before maintenance
            stats_before = self.db.get_database_stats()
            
            # Perform automatic cleanup if needed
            cleanup_result = self.db.auto_cleanup_if_needed()
            
            # Log maintenance results
            if cleanup_result:
                logging.info("Database maintenance completed with cleanup")
            else:
                stats_after = self.db.get_database_stats()
                logging.info(f"Database maintenance completed - no cleanup needed")
                logging.info(f"  • Current size: {stats_after.get('file_size_mb', 0):.1f} MB")
                logging.info(f"  • Total records: {stats_after.get('historical_records', 0):,}")
                
            # Check for potential issues
            self._check_database_health()
            
        except Exception as e:
            logging.error(f"Error during database maintenance: {e}")
    
    def _check_database_health(self):
        """Check database health and log warnings if needed"""
        try:
            stats = self.db.get_database_stats()
            
            # Check growth rate
            size_mb = stats.get('file_size_mb', 0)
            records = stats.get('historical_records', 0)
            
            # Warn if approaching limits
            if size_mb > config.DB_MAX_SIZE_MB * 0.8:  # 80% of limit
                logging.warning(f"Database size ({size_mb:.1f} MB) approaching limit ({config.DB_MAX_SIZE_MB} MB)")
            
            if records > config.DB_MAX_RECORDS * 0.8:  # 80% of limit
                logging.warning(f"Record count ({records:,}) approaching limit ({config.DB_MAX_RECORDS:,})")
            
            # Check for very old data that should have been cleaned
            oldest_data = stats.get('oldest_data')
            if oldest_data and oldest_data != 'N/A':
                try:
                    oldest_date = datetime.fromisoformat(oldest_data.replace('Z', '+00:00'))
                    days_old = (datetime.now() - oldest_date).days
                    
                    if days_old > config.DB_CLEANUP_DAYS * 2:  # More than 2x retention period
                        logging.warning(f"Found data {days_old} days old (retention: {config.DB_CLEANUP_DAYS} days)")
                        
                except Exception as e:
                    logging.debug(f"Error parsing oldest data date: {e}")
            
        except Exception as e:
            logging.error(f"Error checking database health: {e}")
    
    def _log_database_stats(self):
        """Log current database statistics"""
        try:
            stats = self.db.get_database_stats()
            
            logging.info("Database Statistics:")
            logging.info(f"  • File size: {stats.get('file_size_mb', 0):.1f} MB")
            logging.info(f"  • Historical records: {stats.get('historical_records', 0):,}")
            logging.info(f"  • Signal records: {stats.get('signal_records', 0):,}")
            logging.info(f"  • Data range: {stats.get('oldest_data', 'N/A')} to {stats.get('newest_data', 'N/A')}")
            
            # Log top symbols
            top_symbols = stats.get('top_symbols', [])
            if top_symbols:
                logging.info("  • Top symbols by data volume:")
                for symbol, count in top_symbols:
                    logging.info(f"    - {symbol}: {count:,} records")
            
        except Exception as e:
            logging.error(f"Error logging database stats: {e}")
    
    def force_cleanup(self, retention_days: int = None):
        """Force immediate database cleanup (for manual maintenance)"""
        if not self.db:
            logging.warning("Database not available for cleanup")
            return None
            
        logging.info("Starting forced database cleanup...")
        
        if retention_days is None:
            retention_days = config.DB_CLEANUP_DAYS
            
        try:
            stats_before = self.db.get_database_stats()
            cleanup_result = self.db.cleanup_old_data(retention_days)
            stats_after = self.db.get_database_stats()
            
            logging.info("Forced cleanup completed:")
            logging.info(f"  • Size: {stats_before.get('file_size_mb', 0):.1f} to {stats_after.get('file_size_mb', 0):.1f} MB")
            logging.info(f"  • Records: {stats_before.get('historical_records', 0):,} to {stats_after.get('historical_records', 0):,}")
            
            return cleanup_result
            
        except Exception as e:
            logging.error(f"Error during forced cleanup: {e}")
            return None
    
    def get_maintenance_status(self) -> dict:
        """Get current maintenance service status"""
        return {
            'running': self.maintenance_thread.is_alive() if self.maintenance_thread else False,
            'last_cleanup': self.last_cleanup.isoformat(),
            'next_cleanup': (self.last_cleanup + self.cleanup_interval).isoformat(),
            'cleanup_interval_hours': config.DB_CLEANUP_INTERVAL_HOURS,
            'auto_cleanup_enabled': config.DB_AUTO_CLEANUP_ENABLED,
            'max_size_mb': config.DB_MAX_SIZE_MB,
            'max_records': config.DB_MAX_RECORDS,
            'retention_days': config.DB_CLEANUP_DAYS
        }


# Global maintenance service instance
maintenance_service = None

def get_maintenance_service() -> DatabaseMaintenanceService:
    """Get global maintenance service instance"""
    global maintenance_service
    if maintenance_service is None:
        maintenance_service = DatabaseMaintenanceService()
    return maintenance_service
