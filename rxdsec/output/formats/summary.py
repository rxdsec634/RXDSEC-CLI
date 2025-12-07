"""
Advanced Summary Formatter for RxDsec CLI
==========================================
Beautiful summary cards with emoji and styling.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from rich.align import Align
from rich.console import Group
from rich.panel import Panel
from rich.text import Text
from rich.box import DOUBLE, ROUNDED, HEAVY


def detect_summary_type(content: str) -> str:
    """
    Detect the type of summary based on content.
    
    Args:
        content: Summary text
    
    Returns:
        Summary type: "success", "error", "warning", "info"
    """
    content_lower = content.lower()
    
    success_words = ['success', 'complete', 'done', 'finished', 'passed', 'created', 'updated', 'fixed', 'resolved']
    error_words = ['error', 'fail', 'exception', 'crash', 'bug', 'broken', 'issue']
    warning_words = ['warning', 'caution', 'note', 'attention', 'careful', 'deprecated']
    
    if any(word in content_lower for word in error_words):
        return "error"
    elif any(word in content_lower for word in warning_words):
        return "warning"
    elif any(word in content_lower for word in success_words):
        return "success"
    else:
        return "info"


def format_summary(
    content: str,
    summary_type: Optional[str] = None,
    title: Optional[str] = None
) -> Panel:
    """
    Format a summary into a beautiful card panel.
    
    Args:
        content: Summary content
        summary_type: Type ("success", "error", "warning", "info") or auto-detect
        title: Optional custom title
    
    Returns:
        Rich Panel with formatted summary
    """
    # Auto-detect type if not provided
    if not summary_type:
        summary_type = detect_summary_type(content)
    
    # Configure styling based on type
    styles = {
        "success": {
            "emoji": "✅",
            "title": "Quest Complete",
            "border": "green",
            "text_style": "green",
            "box": DOUBLE,
        },
        "error": {
            "emoji": "❌",
            "title": "Error",
            "border": "red",
            "text_style": "red",
            "box": HEAVY,
        },
        "warning": {
            "emoji": "⚠️",
            "title": "Warning",
            "border": "yellow",
            "text_style": "yellow",
            "box": ROUNDED,
        },
        "info": {
            "emoji": "ℹ️",
            "title": "Summary",
            "border": "blue",
            "text_style": "blue",
            "box": ROUNDED,
        },
    }
    
    style = styles.get(summary_type, styles["info"])
    
    # Build content
    text = Text()
    
    # Add emoji header
    header = Text(f"{style['emoji']} ", style="bold")
    
    # Process content - highlight key information
    processed_content = highlight_summary_content(content, summary_type)
    
    # Create centered text
    full_text = Text()
    full_text.append_text(processed_content)
    
    # Build title
    display_title = title or style["title"]
    
    return Panel(
        Align.center(full_text),
        title=f"{style['emoji']} {display_title}",
        border_style=style["border"],
        box=style["box"],
        padding=(1, 2)
    )


def highlight_summary_content(content: str, summary_type: str) -> Text:
    """
    Highlight important parts of summary content.
    
    Args:
        content: Raw content
        summary_type: Summary type for styling
    
    Returns:
        Rich Text with highlights
    """
    text = Text()
    
    # Pattern for numbers (counts, times, etc.)
    number_pattern = r'\b(\d+(?:\.\d+)?)\s*(files?|lines?|changes?|seconds?|minutes?|tests?|errors?|warnings?|bytes?|KB|MB|GB)?\b'
    
    # Pattern for file paths
    path_pattern = r'[\w./\\-]+\.[a-zA-Z]{1,5}'
    
    # Pattern for quoted strings
    quoted_pattern = r'"([^"]+)"|\'([^\']+)\''
    
    last_end = 0
    
    # Find and highlight patterns
    for match in re.finditer(number_pattern + '|' + path_pattern + '|' + quoted_pattern, content):
        # Add text before match
        if match.start() > last_end:
            text.append(content[last_end:match.start()])
        
        matched_text = match.group(0)
        
        # Determine highlight style
        if re.match(number_pattern, matched_text):
            text.append(matched_text, style="bold cyan")
        elif re.match(path_pattern, matched_text):
            text.append(matched_text, style="italic")
        else:
            text.append(matched_text, style="bold")
        
        last_end = match.end()
    
    # Add remaining text
    if last_end < len(content):
        text.append(content[last_end:])
    
    return text


def format_stats_summary(stats: Dict[str, int], title: str = "Summary") -> Panel:
    """
    Format a statistics summary card.
    
    Args:
        stats: Dictionary of stat names to values
        title: Panel title
    
    Returns:
        Rich Panel with stats
    """
    text = Text()
    
    for i, (name, value) in enumerate(stats.items()):
        if i > 0:
            text.append("  │  ", style="dim")
        text.append(f"{name}: ", style="dim")
        text.append(str(value), style="bold cyan")
    
    return Panel(
        Align.center(text),
        title=title,
        border_style="blue",
        box=ROUNDED,
        padding=(0, 2)
    )


def format_completion_summary(
    task: str,
    duration: float,
    tools_used: List[str],
    files_modified: List[str]
) -> Panel:
    """
    Format a task completion summary.
    
    Args:
        task: Task description
        duration: Duration in seconds
        tools_used: List of tools used
        files_modified: List of files modified
    
    Returns:
        Rich Panel with completion summary
    """
    text = Text()
    
    # Task
    text.append("Task: ", style="dim")
    text.append(task[:60] + "..." if len(task) > 60 else task, style="bold")
    text.append("\n\n")
    
    # Duration
    text.append("Duration: ", style="dim")
    if duration < 60:
        text.append(f"{duration:.1f}s", style="cyan")
    else:
        minutes = int(duration // 60)
        seconds = int(duration % 60)
        text.append(f"{minutes}m {seconds}s", style="cyan")
    text.append("\n")
    
    # Tools
    if tools_used:
        text.append("Tools: ", style="dim")
        text.append(", ".join(tools_used[:5]), style="magenta")
        if len(tools_used) > 5:
            text.append(f" +{len(tools_used) - 5} more", style="dim")
        text.append("\n")
    
    # Files
    if files_modified:
        text.append("Files: ", style="dim")
        text.append(str(len(files_modified)), style="green")
        text.append(" modified", style="dim")
    
    return Panel(
        text,
        title="✅ Quest Complete",
        border_style="green",
        box=DOUBLE,
        padding=(1, 2)
    )


__all__ = [
    'format_summary',
    'format_stats_summary',
    'format_completion_summary',
    'detect_summary_type',
    'highlight_summary_content',
]