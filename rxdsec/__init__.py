"""RxDsec CLI - Fully local, GGUF-only agentic coding terminal"""

__version__ = "1.0.0"
__author__ = "RxDsec Team"

from .agent.core import RxDsecAgent
from .cli.tui import run_tui
from .output.renderer import render_output

__all__ = ["RxDsecAgent", "run_tui", "render_output"]