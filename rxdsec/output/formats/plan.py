"""
Advanced Plan Formatter for RxDsec CLI
=======================================
Beautiful plan/step list rendering with progress indicators.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from rich.console import Group
from rich.panel import Panel
from rich.text import Text
from rich.progress import Progress, BarColumn, TextColumn, TaskProgressColumn
from rich.box import ROUNDED


def parse_plan_items(raw_plan: str) -> List[Tuple[str, str, bool]]:
    """
    Parse plan text into structured items.
    
    Args:
        raw_plan: Raw plan text
    
    Returns:
        List of (number/bullet, text, is_completed) tuples
    """
    items = []
    lines = raw_plan.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Check for completion markers
        is_completed = False
        if line.startswith(('✓', '✅', '[x]', '[X]', '☑')):
            is_completed = True
            line = re.sub(r'^[✓✅☑\[\]xX\s]+', '', line)
        elif line.startswith(('○', '[ ]', '☐', '⏳')):
            line = re.sub(r'^[○☐⏳\[\]\s]+', '', line)
        
        # Match numbered items
        match = re.match(r'^(\d+)[.\)]\s*(.+)$', line)
        if match:
            items.append((match.group(1), match.group(2), is_completed))
            continue
        
        # Match bullet items
        match = re.match(r'^[-*•]\s*(.+)$', line)
        if match:
            items.append(('•', match.group(1), is_completed))
            continue
        
        # Plain text (continuation or standalone)
        if items:
            # Append to previous item
            prev_num, prev_text, prev_done = items[-1]
            items[-1] = (prev_num, prev_text + ' ' + line, prev_done)
        else:
            items.append(('', line, is_completed))
    
    return items


def format_plan(
    raw_plan: str,
    current_step: Optional[int] = None,
    title: str = "Plan"
) -> Panel:
    """
    Format a plan into a beautiful Rich panel with progress.
    
    Features:
    - Numbered/bulleted lists
    - Completion checkmarks (✓)
    - Current step indicator (⏳)
    - Progress bar
    
    Args:
        raw_plan: Raw plan text
        current_step: Index of currently executing step (0-based)
        title: Panel title
    
    Returns:
        Rich Panel with formatted plan
    """
    items = parse_plan_items(raw_plan)
    
    if not items:
        return Panel(Text(raw_plan), title=title, border_style="cyan", box=ROUNDED)
    
    text = Text()
    completed_count = 0
    total_count = len(items)
    
    for i, (marker, content, is_completed) in enumerate(items):
        # Determine status and styling
        if is_completed:
            prefix = "✓"
            style = "green dim"
            completed_count += 1
        elif current_step is not None and i == current_step:
            prefix = "⏳"
            style = "bold yellow"
        elif current_step is not None and i < current_step:
            prefix = "✓"
            style = "green dim"
            completed_count += 1
        else:
            prefix = "○"
            style = "white"
        
        # Format the line
        if marker and marker != '•':
            text.append(f"  {prefix} {marker}. ", style=style)
        else:
            text.append(f"  {prefix} ", style=style)
        
        text.append(f"{content}\n", style=style)
    
    # Calculate progress
    progress_pct = (completed_count / total_count * 100) if total_count > 0 else 0
    
    # Add progress bar
    progress_bar = create_progress_bar(completed_count, total_count)
    
    content = Group(text, Text(""), progress_bar)
    
    return Panel(
        content,
        title=f"{title} ({completed_count}/{total_count})",
        border_style="cyan",
        box=ROUNDED,
        padding=(0, 1)
    )


def create_progress_bar(completed: int, total: int) -> Text:
    """
    Create a simple text-based progress bar.
    
    Args:
        completed: Number of completed items
        total: Total number of items
    
    Returns:
        Text object with progress bar
    """
    if total == 0:
        return Text("")
    
    percentage = completed / total
    bar_width = 30
    filled = int(bar_width * percentage)
    empty = bar_width - filled
    
    text = Text()
    text.append("  Progress: ", style="dim")
    text.append("█" * filled, style="green")
    text.append("░" * empty, style="dim")
    text.append(f" {percentage * 100:.0f}%", style="bold")
    
    return text


def format_checklist(items: List[Tuple[str, bool]], title: str = "Checklist") -> Panel:
    """
    Format a simple checklist.
    
    Args:
        items: List of (item_text, is_completed) tuples
        title: Panel title
    
    Returns:
        Rich Panel with checklist
    """
    text = Text()
    
    for item_text, is_completed in items:
        if is_completed:
            text.append("  ✓ ", style="green")
            text.append(f"{item_text}\n", style="green dim")
        else:
            text.append("  ○ ", style="dim")
            text.append(f"{item_text}\n")
    
    completed = sum(1 for _, c in items if c)
    total = len(items)
    
    return Panel(
        text,
        title=f"{title} ({completed}/{total})",
        border_style="cyan" if completed < total else "green",
        box=ROUNDED
    )


__all__ = ['format_plan', 'format_checklist', 'parse_plan_items', 'create_progress_bar']