"""
RxDsec CLI Package
===================
Command-line interface for RxDsec.
"""

from .main import app, main_entry
from .tui import run_tui, SLASH_COMMANDS
from .quest import quest_app, run_quest
from .review import review_app, run_review
from .worktree import worktree_app
from .lpe import lpe_app

__all__ = [
    # Main
    'app',
    'main_entry',
    
    # TUI
    'run_tui',
    'SLASH_COMMANDS',
    
    # Quest
    'quest_app',
    'run_quest',
    
    # Review
    'review_app',
    'run_review',
    
    # Worktree
    'worktree_app',
    
    # LPE
    'lpe_app',
]

__version__ = "1.0.0"