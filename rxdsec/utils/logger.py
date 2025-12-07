"""
Advanced Logging Utilities for RxDsec CLI
==========================================
Production-grade logging with rotation, formatting, and debug support.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.logging import RichHandler


# Default log directory
DEFAULT_LOG_DIR = Path.home() / ".rxdsec" / "logs"

# Log format strings
CONSOLE_FORMAT = "%(message)s"
FILE_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DEBUG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(funcName)s | %(message)s"


class LogConfig:
    """Logging configuration"""
    
    def __init__(
        self,
        level: int = logging.INFO,
        log_dir: Optional[Path] = None,
        enable_file: bool = True,
        enable_console: bool = True,
        max_file_size: int = 10 * 1024 * 1024,  # 10MB
        backup_count: int = 5,
        debug_mode: bool = False
    ):
        self.level = level
        self.log_dir = log_dir or DEFAULT_LOG_DIR
        self.enable_file = enable_file
        self.enable_console = enable_console
        self.max_file_size = max_file_size
        self.backup_count = backup_count
        self.debug_mode = debug_mode


def setup_logging(
    name: str = "rxdsec",
    config: Optional[LogConfig] = None,
    verbose: bool = False
) -> logging.Logger:
    """
    Set up logging for the application.
    
    Args:
        name: Logger name
        config: Logging configuration
        verbose: Enable verbose/debug output
    
    Returns:
        Configured logger
    """
    config = config or LogConfig()
    
    if verbose:
        config.level = logging.DEBUG
        config.debug_mode = True
    
    # Get or create logger
    logger = logging.getLogger(name)
    logger.setLevel(config.level)
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Console handler with Rich
    if config.enable_console:
        console_handler = RichHandler(
            console=Console(stderr=True),
            show_time=config.debug_mode,
            show_path=config.debug_mode,
            rich_tracebacks=True,
            tracebacks_show_locals=config.debug_mode,
            markup=True
        )
        console_handler.setLevel(config.level)
        console_handler.setFormatter(logging.Formatter(CONSOLE_FORMAT))
        logger.addHandler(console_handler)
    
    # File handler with rotation
    if config.enable_file:
        try:
            config.log_dir.mkdir(parents=True, exist_ok=True)
            
            log_file = config.log_dir / f"{name}.log"
            
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=config.max_file_size,
                backupCount=config.backup_count,
                encoding='utf-8'
            )
            file_handler.setLevel(logging.DEBUG)  # Capture everything to file
            
            file_format = DEBUG_FORMAT if config.debug_mode else FILE_FORMAT
            file_handler.setFormatter(logging.Formatter(file_format, datefmt="%Y-%m-%d %H:%M:%S"))
            
            logger.addHandler(file_handler)
        except Exception as e:
            # Can't log to file, just use console
            if config.enable_console:
                logger.warning(f"Failed to set up file logging: {e}")
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the given name.
    
    Args:
        name: Logger name (usually __name__)
    
    Returns:
        Logger instance
    """
    return logging.getLogger(name)


class LogContext:
    """
    Context manager for temporary log level changes.
    
    Usage:
        with LogContext("rxdsec", logging.DEBUG):
            # Debug logging enabled here
            do_something()
    """
    
    def __init__(self, logger_name: str = "rxdsec", level: int = logging.DEBUG):
        self.logger = logging.getLogger(logger_name)
        self.new_level = level
        self.old_level = self.logger.level
    
    def __enter__(self):
        self.logger.setLevel(self.new_level)
        return self.logger
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.logger.setLevel(self.old_level)
        return False


def log_exception(
    logger: logging.Logger,
    message: str = "An error occurred",
    exc_info: bool = True
):
    """
    Log an exception with full traceback.
    
    Args:
        logger: Logger to use
        message: Error message
        exc_info: Include exception info
    """
    logger.exception(message, exc_info=exc_info)


class SessionLogger:
    """
    Logger for a specific session with session ID tracking.
    
    Usage:
        session_log = SessionLogger("quest_123")
        session_log.info("Starting quest")
    """
    
    def __init__(self, session_id: str, base_logger: Optional[logging.Logger] = None):
        self.session_id = session_id
        self.logger = base_logger or logging.getLogger("rxdsec")
        self._session_dir: Optional[Path] = None
    
    def _format_message(self, message: str) -> str:
        return f"[{self.session_id}] {message}"
    
    def debug(self, message: str, *args, **kwargs):
        self.logger.debug(self._format_message(message), *args, **kwargs)
    
    def info(self, message: str, *args, **kwargs):
        self.logger.info(self._format_message(message), *args, **kwargs)
    
    def warning(self, message: str, *args, **kwargs):
        self.logger.warning(self._format_message(message), *args, **kwargs)
    
    def error(self, message: str, *args, **kwargs):
        self.logger.error(self._format_message(message), *args, **kwargs)
    
    def critical(self, message: str, *args, **kwargs):
        self.logger.critical(self._format_message(message), *args, **kwargs)
    
    def exception(self, message: str, *args, **kwargs):
        self.logger.exception(self._format_message(message), *args, **kwargs)


def cleanup_old_logs(log_dir: Optional[Path] = None, max_age_days: int = 30):
    """
    Clean up old log files.
    
    Args:
        log_dir: Directory containing logs
        max_age_days: Maximum age of logs to keep
    """
    log_dir = log_dir or DEFAULT_LOG_DIR
    
    if not log_dir.exists():
        return
    
    cutoff = datetime.now().timestamp() - (max_age_days * 24 * 60 * 60)
    
    for log_file in log_dir.glob("*.log*"):
        try:
            if log_file.stat().st_mtime < cutoff:
                log_file.unlink()
        except Exception:
            pass


__all__ = [
    'setup_logging',
    'get_logger',
    'LogConfig',
    'LogContext',
    'SessionLogger',
    'log_exception',
    'cleanup_old_logs',
]
