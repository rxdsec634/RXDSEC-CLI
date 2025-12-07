"""
Advanced Table Formatter for RxDsec CLI
========================================
Parse and render markdown tables with styling.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from rich.table import Table
from rich.text import Text
from rich.box import ROUNDED, SIMPLE, DOUBLE


def parse_markdown_table(raw_table: str) -> Tuple[List[str], List[List[str]]]:
    """
    Parse a markdown table into headers and rows.
    
    Args:
        raw_table: Raw markdown table string
    
    Returns:
        Tuple of (headers, rows)
    """
    lines = [l.strip() for l in raw_table.strip().split('\n') if l.strip()]
    
    if len(lines) < 2:
        return [], []
    
    def parse_row(line: str) -> List[str]:
        """Parse a single table row"""
        # Remove leading/trailing pipes and split
        cells = line.strip('|').split('|')
        return [cell.strip() for cell in cells]
    
    headers = []
    rows = []
    separator_found = False
    
    for i, line in enumerate(lines):
        if not line.startswith('|') and '|' not in line:
            continue
        
        cells = parse_row(line)
        
        # Check if this is the separator row (---, :--:, etc.)
        if all(re.match(r'^:?-+:?$', cell.strip()) for cell in cells if cell.strip()):
            separator_found = True
            continue
        
        if not separator_found:
            # This is a header row
            if not headers:
                headers = cells
        else:
            # This is a data row
            rows.append(cells)
    
    # If no separator found, treat first row as header
    if not separator_found and headers and not rows:
        if len(lines) > 1:
            rows = [parse_row(l) for l in lines[1:] if '|' in l]
    
    return headers, rows


def format_table(
    raw_table: str,
    title: Optional[str] = None,
    style: str = "default"
) -> Table:
    """
    Format a markdown table into a Rich Table.
    
    Args:
        raw_table: Raw markdown table or pre-parsed data
        title: Optional table title
        style: Table style ("default", "simple", "bordered")
    
    Returns:
        Rich Table object
    """
    headers, rows = parse_markdown_table(raw_table)
    
    if not headers and not rows:
        # Return a simple text table if parsing failed
        table = Table(title=title or "Table", box=ROUNDED)
        table.add_column("Content")
        table.add_row(raw_table)
        return table
    
    # Select box style
    box_styles = {
        "default": ROUNDED,
        "simple": SIMPLE,
        "bordered": DOUBLE,
    }
    
    table = Table(
        title=title,
        box=box_styles.get(style, ROUNDED),
        show_header=bool(headers),
        header_style="bold cyan",
        border_style="dim"
    )
    
    # Add columns
    if headers:
        for header in headers:
            table.add_column(header, overflow="fold")
    else:
        # No headers, create generic columns
        if rows:
            for i in range(len(rows[0])):
                table.add_column(f"Col {i+1}", overflow="fold")
    
    # Add rows with proper formatting
    for row in rows:
        formatted_cells = []
        for cell in row:
            formatted_cells.append(format_cell(cell))
        
        # Pad row if needed
        while len(formatted_cells) < len(headers or []) or (not headers and rows and len(formatted_cells) < len(rows[0])):
            formatted_cells.append("")
        
        table.add_row(*formatted_cells)
    
    return table


def format_cell(content: str) -> Text:
    """
    Format a cell with syntax highlighting.
    
    Args:
        content: Cell content
    
    Returns:
        Rich Text with formatting
    """
    text = Text()
    
    # Check for inline code
    code_pattern = r'`([^`]+)`'
    bold_pattern = r'\*\*([^*]+)\*\*'
    italic_pattern = r'\*([^*]+)\*|_([^_]+)_'
    
    last_end = 0
    combined_pattern = f'{code_pattern}|{bold_pattern}|{italic_pattern}'
    
    for match in re.finditer(combined_pattern, content):
        # Add text before match
        if match.start() > last_end:
            text.append(content[last_end:match.start()])
        
        matched = match.group(0)
        
        # Determine type and extract content
        if matched.startswith('`'):
            inner = match.group(1)
            text.append(inner, style="cyan")
        elif matched.startswith('**'):
            inner = match.group(2)
            text.append(inner, style="bold")
        else:
            inner = match.group(3) or match.group(4)
            text.append(inner, style="italic")
        
        last_end = match.end()
    
    # Add remaining text
    if last_end < len(content):
        text.append(content[last_end:])
    
    return text


def format_key_value_table(
    data: dict,
    title: Optional[str] = None,
    key_header: str = "Property",
    value_header: str = "Value"
) -> Table:
    """
    Format a dictionary as a key-value table.
    
    Args:
        data: Dictionary to format
        title: Optional title
        key_header: Header for key column
        value_header: Header for value column
    
    Returns:
        Rich Table
    """
    table = Table(
        title=title,
        box=ROUNDED,
        header_style="bold cyan",
        border_style="dim"
    )
    
    table.add_column(key_header, style="bold")
    table.add_column(value_header)
    
    for key, value in data.items():
        # Format value based on type
        if isinstance(value, bool):
            value_text = Text("✓" if value else "✗", style="green" if value else "red")
        elif isinstance(value, (int, float)):
            value_text = Text(str(value), style="cyan")
        elif isinstance(value, list):
            value_text = Text(", ".join(str(v) for v in value[:5]))
            if len(value) > 5:
                value_text.append(f" +{len(value) - 5} more", style="dim")
        elif value is None:
            value_text = Text("─", style="dim")
        else:
            value_text = Text(str(value))
        
        table.add_row(str(key), value_text)
    
    return table


def format_comparison_table(
    items: List[dict],
    columns: List[str],
    title: Optional[str] = None
) -> Table:
    """
    Format a comparison table.
    
    Args:
        items: List of dictionaries to compare
        columns: Columns to include
        title: Optional title
    
    Returns:
        Rich Table
    """
    table = Table(
        title=title,
        box=ROUNDED,
        header_style="bold cyan"
    )
    
    for col in columns:
        table.add_column(col)
    
    for item in items:
        row = [str(item.get(col, "─")) for col in columns]
        table.add_row(*row)
    
    return table


__all__ = [
    'format_table',
    'format_key_value_table',
    'format_comparison_table',
    'parse_markdown_table',
    'format_cell',
]