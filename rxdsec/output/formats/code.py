"""
Code Block Formatter for RxDsec CLI
====================================
Format code blocks with syntax highlighting and titles.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from rich.panel import Panel
from rich.box import ROUNDED

from ..highlighter import highlight_code, detect_language


def format_code(
    code: str,
    language: Optional[str] = None,
    filename: Optional[str] = None,
    title: Optional[str] = None,
    line_numbers: bool = False,
    start_line: int = 1,
    theme: str = "monokai"
) -> Panel:
    """
    Format a code block with syntax highlighting in a panel.
    
    Args:
        code: Source code
        language: Programming language (auto-detected if not provided)
        filename: Optional filename for language detection and title
        title: Optional custom title
        line_numbers: Whether to show line numbers
        start_line: Starting line number
        theme: Pygments color theme
    
    Returns:
        Rich Panel with highlighted code
    """
    # Detect language if not provided
    if not language:
        language = detect_language(code, filename)
    
    # Generate title
    if not title:
        if filename:
            title = Path(filename).name
        else:
            title = f"Code ({language})" if language != 'text' else "Code"
    
    # Create highlighted syntax
    syntax = highlight_code(
        code=code,
        language=language,
        filename=filename,
        theme=theme,
        line_numbers=line_numbers,
        start_line=start_line
    )
    
    return Panel(
        syntax,
        title=title,
        border_style="cyan",
        box=ROUNDED,
        padding=(0, 1)
    )


def format_code_snippet(
    code: str,
    language: str = "python",
    context: str = ""
) -> Panel:
    """
    Format a small code snippet with optional context.
    
    Args:
        code: Code snippet
        language: Programming language
        context: Optional context description
    
    Returns:
        Rich Panel
    """
    syntax = highlight_code(code, language)
    
    title = context if context else f"Snippet ({language})"
    
    return Panel(
        syntax,
        title=title,
        border_style="cyan",
        box=ROUNDED
    )


__all__ = ['format_code', 'format_code_snippet']