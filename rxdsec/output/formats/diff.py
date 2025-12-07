"""
Advanced Diff Formatter for RxDsec CLI
=======================================
Beautiful git-style diff rendering with colors and context.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from rich.console import Group
from rich.panel import Panel
from rich.text import Text
from rich.box import ROUNDED


def parse_diff_header(line: str) -> Optional[Tuple[str, str]]:
    """
    Parse diff header to extract file names.
    
    Args:
        line: Diff header line
    
    Returns:
        Tuple of (old_file, new_file) or None
    """
    # Git diff format: diff --git a/file b/file
    match = re.match(r'^diff --git a/(.+?) b/(.+?)$', line)
    if match:
        return match.group(1), match.group(2)
    return None


def format_diff(raw_diff: str) -> Panel:
    """
    Format a diff string into a beautiful Rich panel.
    
    Features:
    - Green for additions (+)
    - Red for deletions (-)
    - Cyan for diff headers
    - Blue for line number markers
    
    Args:
        raw_diff: Raw diff string
    
    Returns:
        Rich Panel with formatted diff
    """
    lines = raw_diff.split('\n')
    text = Text()
    
    current_file = ""
    stats = {"additions": 0, "deletions": 0}
    
    for line in lines:
        if not line:
            text.append('\n')
            continue
        
        # Diff header
        if line.startswith('diff --git'):
            header = parse_diff_header(line)
            if header:
                current_file = header[1]
            text.append(f"\n{line}\n", style="bold cyan")
        
        # File markers
        elif line.startswith('---'):
            text.append(line + '\n', style="bold red dim")
        
        elif line.startswith('+++'):
            text.append(line + '\n', style="bold green dim")
        
        # Hunk headers (@@ ... @@)
        elif line.startswith('@@'):
            # Extract line numbers
            match = re.match(r'^(@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@)(.*)', line)
            if match:
                text.append(match.group(1), style="bold blue")
                if match.group(2):
                    text.append(match.group(2), style="dim")
                text.append('\n')
            else:
                text.append(line + '\n', style="bold blue")
        
        # Additions
        elif line.startswith('+'):
            text.append(line + '\n', style="green")
            stats["additions"] += 1
        
        # Deletions
        elif line.startswith('-'):
            text.append(line + '\n', style="red")
            stats["deletions"] += 1
        
        # Index and other metadata
        elif line.startswith(('index ', 'new file', 'deleted file', 'similarity', 'rename')):
            text.append(line + '\n', style="dim")
        
        # Context lines (unchanged)
        else:
            text.append(line + '\n', style="dim white")
    
    # Build title with stats
    title = "Changes"
    if current_file:
        title = f"Changes: {current_file}"
    
    stats_text = ""
    if stats["additions"] or stats["deletions"]:
        stats_text = f" (+{stats['additions']}/-{stats['deletions']})"
    
    return Panel(
        text,
        title=title + stats_text,
        border_style="yellow",
        box=ROUNDED,
        padding=(0, 1)
    )


def format_inline_diff(old_line: str, new_line: str) -> Tuple[Text, Text]:
    """
    Format inline diff showing character-level changes.
    
    Args:
        old_line: Original line
        new_line: New line
    
    Returns:
        Tuple of (formatted_old, formatted_new)
    """
    import difflib
    
    old_text = Text()
    new_text = Text()
    
    matcher = difflib.SequenceMatcher(None, old_line, new_line)
    
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == 'equal':
            old_text.append(old_line[i1:i2])
            new_text.append(new_line[j1:j2])
        elif op == 'delete':
            old_text.append(old_line[i1:i2], style="red bold underline")
        elif op == 'insert':
            new_text.append(new_line[j1:j2], style="green bold underline")
        elif op == 'replace':
            old_text.append(old_line[i1:i2], style="red bold underline")
            new_text.append(new_line[j1:j2], style="green bold underline")
    
    return old_text, new_text


def summarize_diff(raw_diff: str) -> str:
    """
    Create a summary of changes in a diff.
    
    Args:
        raw_diff: Raw diff string
    
    Returns:
        Human-readable summary
    """
    files_changed = set()
    additions = 0
    deletions = 0
    
    for line in raw_diff.split('\n'):
        if line.startswith('diff --git'):
            header = parse_diff_header(line)
            if header:
                files_changed.add(header[1])
        elif line.startswith('+') and not line.startswith('+++'):
            additions += 1
        elif line.startswith('-') and not line.startswith('---'):
            deletions += 1
    
    files_str = f"{len(files_changed)} file{'s' if len(files_changed) != 1 else ''}"
    
    return f"{files_str} changed, {additions} insertion{'s' if additions != 1 else ''}, {deletions} deletion{'s' if deletions != 1 else ''}"


__all__ = ['format_diff', 'format_inline_diff', 'summarize_diff', 'parse_diff_header']