"""
RxDsec Utils Package
=====================
Utility functions for git, logging, spinners, and file operations.
"""

from .git import (
    create_worktree,
    list_worktrees,
    delete_worktree,
    attach_worktree,
    WorktreeInfo,
)

from .spinner import (
    Spinner,
    SpinnerStyle,
    spinner,
    ProgressTracker,
    animate_text,
    pulse_text,
)

from .logger import (
    setup_logging,
    get_logger,
    LogConfig,
    LogContext,
    SessionLogger,
    log_exception,
    cleanup_old_logs,
)

__all__ = [
    # Git utilities
    'create_worktree',
    'list_worktrees',
    'delete_worktree',
    'attach_worktree',
    'WorktreeInfo',
    
    # Spinner utilities
    'Spinner',
    'SpinnerStyle',
    'spinner',
    'ProgressTracker',
    'animate_text',
    'pulse_text',
    
    # Logging utilities
    'setup_logging',
    'get_logger',
    'LogConfig',
    'LogContext',
    'SessionLogger',
    'log_exception',
    'cleanup_old_logs',
]

__version__ = "1.0.0"