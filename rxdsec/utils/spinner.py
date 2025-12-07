"""
Advanced Spinner Utilities for RxDsec CLI
==========================================
Context manager based spinner and progress indicators for TUI.
"""

from __future__ import annotations

import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Generator, Iterator, Optional

from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner as RichSpinner
from rich.text import Text
from rich.panel import Panel
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeElapsedColumn,
)


class SpinnerStyle(Enum):
    """Available spinner animation styles"""
    DOTS = "dots"
    DOTS2 = "dots2"
    DOTS3 = "dots3"
    LINE = "line"
    PIPE = "pipe"
    ARROW = "arrow"
    BOUNCE = "bouncingBar"
    MOON = "moon"
    EARTH = "earth"
    STAR = "star"
    CLOCK = "clock"
    PONG = "pong"


@dataclass
class SpinnerConfig:
    """Configuration for spinner behavior"""
    style: SpinnerStyle = SpinnerStyle.DOTS
    text: str = "Loading..."
    success_text: str = "Done!"
    error_text: str = "Error"
    color: str = "cyan"
    show_elapsed: bool = True


class Spinner:
    """
    Advanced spinner with context manager support.
    
    Usage:
        with Spinner("Processing...") as spin:
            do_work()
            spin.update("Still working...")
        
        # Or with decorator
        @Spinner.wrap("Loading data")
        def load_data():
            return fetch()
    """
    
    def __init__(
        self,
        text: str = "Loading...",
        style: SpinnerStyle = SpinnerStyle.DOTS,
        color: str = "cyan",
        console: Optional[Console] = None
    ):
        self.text = text
        self.style = style
        self.color = color
        self.console = console or Console()
        self._live: Optional[Live] = None
        self._start_time: float = 0
        self._success: bool = True
        self._final_message: Optional[str] = None
    
    def __enter__(self) -> "Spinner":
        self._start_time = time.time()
        spinner = RichSpinner(self.style.value, text=Text(f" {self.text}", style=self.color))
        self._live = Live(spinner, console=self.console, refresh_per_second=10)
        self._live.__enter__()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = time.time() - self._start_time
        
        if exc_type is not None:
            self._success = False
            self._final_message = f"✗ Error: {exc_val}"
        elif self._success:
            self._final_message = self._final_message or f"✓ Done ({elapsed:.1f}s)"
        
        self._live.__exit__(exc_type, exc_val, exc_tb)
        
        # Print final message
        if self._final_message:
            style = "green" if self._success else "red"
            self.console.print(self._final_message, style=style)
        
        return False  # Don't suppress exceptions
    
    def update(self, text: str):
        """Update spinner text"""
        self.text = text
        if self._live:
            spinner = RichSpinner(self.style.value, text=Text(f" {text}", style=self.color))
            self._live.update(spinner)
    
    def success(self, message: str = "Done"):
        """Mark as successful with custom message"""
        elapsed = time.time() - self._start_time
        self._success = True
        self._final_message = f"✓ {message} ({elapsed:.1f}s)"
    
    def fail(self, message: str = "Failed"):
        """Mark as failed with custom message"""
        self._success = False
        self._final_message = f"✗ {message}"
    
    @staticmethod
    def wrap(text: str) -> Callable:
        """Decorator to wrap a function with a spinner"""
        def decorator(func: Callable) -> Callable:
            def wrapper(*args, **kwargs):
                with Spinner(text):
                    return func(*args, **kwargs)
            return wrapper
        return decorator


@contextmanager
def spinner(
    text: str = "Loading...",
    success_text: str = "Done",
    error_text: str = "Error"
) -> Generator[Spinner, None, None]:
    """
    Simple context manager for spinner.
    
    Usage:
        with spinner("Processing...") as s:
            do_work()
    """
    spin = Spinner(text)
    try:
        with spin:
            yield spin
        spin.success(success_text)
    except Exception:
        spin.fail(error_text)
        raise


class ProgressTracker:
    """
    Track progress of multi-step operations.
    
    Usage:
        with ProgressTracker("Building", total=10) as track:
            for i in range(10):
                track.advance()
                do_step(i)
    """
    
    def __init__(
        self,
        description: str = "Working",
        total: int = 100,
        console: Optional[Console] = None
    ):
        self.description = description
        self.total = total
        self.console = console or Console()
        self._progress: Optional[Progress] = None
        self._task_id = None
    
    def __enter__(self) -> "ProgressTracker":
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=self.console
        )
        self._progress.__enter__()
        self._task_id = self._progress.add_task(self.description, total=self.total)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._progress:
            self._progress.__exit__(exc_type, exc_val, exc_tb)
        return False
    
    def advance(self, amount: int = 1):
        """Advance progress by amount"""
        if self._progress and self._task_id is not None:
            self._progress.advance(self._task_id, amount)
    
    def update(self, description: str = None, completed: int = None):
        """Update progress description or completed count"""
        if self._progress and self._task_id is not None:
            kwargs = {}
            if description:
                kwargs["description"] = description
            if completed is not None:
                kwargs["completed"] = completed
            self._progress.update(self._task_id, **kwargs)


def animate_text(
    text: str,
    delay: float = 0.02,
    console: Optional[Console] = None
):
    """
    Animate text character by character (typewriter effect).
    
    Args:
        text: Text to animate
        delay: Delay between characters
        console: Rich console
    """
    console = console or Console()
    for char in text:
        console.print(char, end="", highlight=False)
        time.sleep(delay)
    console.print()  # Final newline


def pulse_text(
    text: str,
    duration: float = 2.0,
    console: Optional[Console] = None
):
    """
    Display pulsing text animation.
    
    Args:
        text: Text to pulse
        duration: Duration in seconds
        console: Rich console
    """
    console = console or Console()
    styles = ["dim", "normal", "bold"]
    start = time.time()
    
    with Live(console=console, refresh_per_second=4) as live:
        while time.time() - start < duration:
            for style in styles + styles[::-1]:
                if time.time() - start >= duration:
                    break
                live.update(Text(text, style=style))
                time.sleep(0.15)


__all__ = [
    'Spinner',
    'SpinnerStyle',
    'SpinnerConfig',
    'spinner',
    'ProgressTracker',
    'animate_text',
    'pulse_text',
]
