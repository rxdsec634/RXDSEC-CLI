"""
Professional Visual Formatter for RxDsec CLI
==============================================
Clean, professional output formatting with bullets, tool call styling,
line numbers, and expandable content indicators.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from rich.console import Console, Group
from rich.text import Text
from rich.syntax import Syntax
from rich.panel import Panel
from rich.box import SIMPLE


# Styling constants
BULLET = "●"
TOOL_ARROW = "⎿"
NESTED_LINE = "│"
CHECKBOX_DONE = "[x]"
CHECKBOX_TODO = "[ ]"
ELLIPSIS = "…"


@dataclass
class ToolOutput:
    """Represents a tool call and its output"""
    name: str
    args: str
    output: str
    success: bool = True
    is_nested: bool = False


class VisualFormatter:
    """
    Format agent output in professional CLI style.
    
    Features:
    - Bullet points for agent thoughts (●)
    - Tool call boxes with output (⎿)
    - Line numbers for code/file output
    - Expandable content indicators (… +N lines)
    - Nested agent output with │ prefix
    - Checkboxes for todos [x] [ ]
    """
    
    def __init__(self, console: Optional[Console] = None, max_lines: int = 5):
        self.console = console or Console()
        self.max_lines = max_lines
    
    def format_thought(self, text: str, nested: bool = False) -> Text:
        """Format an agent thought/explanation"""
        result = Text()
        prefix = f"{NESTED_LINE} " if nested else ""
        result.append(f"{prefix}{BULLET} ", style="cyan bold")
        result.append(text)
        return result
    
    def format_tool_call(
        self,
        tool_name: str,
        args: str = "",
        output: str = "",
        success: bool = True,
        nested: bool = False,
        show_all: bool = False
    ) -> Text:
        """
        Format a tool call with its output.
        
        Args:
            tool_name: Name of the tool
            args: Arguments passed to tool
            output: Tool output
            success: Whether tool succeeded
            nested: If this is a nested agent call
            show_all: Show all lines (no truncation)
        """
        result = Text()
        prefix = f"{NESTED_LINE} " if nested else ""
        
        # Tool name line
        color = "green" if success else "red"
        result.append(f"{prefix}{BULLET} ", style=f"{color} bold")
        result.append(tool_name, style=f"{color} bold")
        if args:
            result.append(f" ({args})", style="dim")
        result.append("\n")
        
        # Output if present
        if output:
            lines = output.strip().split('\n')
            
            # Apply truncation
            truncated = False
            hidden_count = 0
            if not show_all and len(lines) > self.max_lines:
                hidden_count = len(lines) - self.max_lines
                lines = lines[:self.max_lines]
                truncated = True
            
            # Format output lines
            for i, line in enumerate(lines):
                result.append(f"{prefix}  {TOOL_ARROW} ", style="dim")
                
                # Add line numbers for multi-line output
                if len(lines) > 1 or truncated:
                    result.append(f"{i+1:02d} ", style="blue dim")
                
                result.append(f"{line}\n")
            
            # Show truncation indicator
            if truncated:
                result.append(f"{prefix}    {ELLIPSIS} +{hidden_count} lines (ctrl+r to expand)\n", style="dim italic")
        else:
            result.append(f"{prefix}  {TOOL_ARROW} ", style="dim")
            result.append("(no content)\n", style="dim italic")
        
        return result
    
    def format_file_content(
        self,
        path: str,
        content: str,
        line_range: Optional[Tuple[int, int]] = None,
        show_all: bool = False
    ) -> Text:
        """Format file read output"""
        lines = content.strip().split('\n')
        
        # Check token limit
        token_estimate = len(content) // 4
        if token_estimate > 25000:
            return self.format_tool_call(
                "Read",
                path,
                f"(File content ({token_estimate} tokens) exceeds maximum allowed tokens (25000). "
                "Please use offset and limit parameters to read specific portions of the file, "
                "or use the GrepTool to search for specific content.)"
            )
        
        line_count = len(lines)
        if line_range:
            output = f"read {line_range[1] - line_range[0]} lines"
        else:
            output = content
        
        return self.format_tool_call("Read", f"{path}", output, show_all=show_all)
    
    def format_grep_results(self, pattern: str, matches: List[str], total: int = 0) -> Text:
        """Format grep search results"""
        if not matches:
            return self.format_tool_call("Grep", pattern, "(No matches found)")
        
        output = f"Found {len(matches)} matching lines:\n\n"
        output += '\n'.join(matches)
        
        return self.format_tool_call("Grep", f'"{pattern}"', output)
    
    def format_bash(
        self,
        command: str,
        output: str,
        exit_code: int = 0,
        background: bool = False
    ) -> Text:
        """Format bash command output"""
        tool_name = "Bash in background" if background else "Bash"
        return self.format_tool_call(
            tool_name,
            command,
            output,
            success=(exit_code == 0)
        )
    
    def format_edit(
        self,
        path: str,
        old_line: str,
        new_line: str,
        line_num: int = 1
    ) -> Text:
        """Format file edit showing before/after"""
        output = f"{line_num:02d} {old_line}\n{line_num:02d} {new_line}"
        return self.format_tool_call("Edit", path, output)
    
    def format_write(self, path: str, content: str, lines_written: int = 0) -> Text:
        """Format file write output"""
        return self.format_tool_call("Write", path, content)
    
    def format_todo_list(self, items: List[Tuple[str, bool]], total: int = 0) -> Text:
        """Format a todo list"""
        result = Text()
        result.append(f"{BULLET} ", style="cyan bold")
        result.append("TodoWrite", style="cyan bold")
        result.append(f" ({total or len(items)} todos)\n", style="dim")
        
        for task, done in items[:self.max_lines]:
            checkbox = CHECKBOX_DONE if done else CHECKBOX_TODO
            result.append(f"  {TOOL_ARROW} {checkbox} ", style="dim" if done else "")
            result.append(f"{task}\n", style="dim strikethrough" if done else "")
        
        if len(items) > self.max_lines:
            hidden = len(items) - self.max_lines
            result.append(f"    {ELLIPSIS} +{hidden} lines (ctrl+r to expand)\n", style="dim italic")
        
        return result
    
    def format_nested_agent(
        self,
        agent_name: str,
        task: str,
        messages: List[Text],
        collapsed_count: int = 0
    ) -> Text:
        """Format nested agent output"""
        result = Text()
        result.append(f"{BULLET} ", style="magenta bold")
        result.append(agent_name, style="magenta bold")
        result.append(f" ({task})\n", style="dim")
        result.append(f"{NESTED_LINE}\n", style="dim")
        
        if collapsed_count > 0:
            result.append(f"{NESTED_LINE} {ELLIPSIS} +{collapsed_count} messages (ctrl+r to expand)\n", style="dim italic")
            result.append(f"{NESTED_LINE}\n", style="dim")
        
        for msg in messages:
            # Prefix each line with nested indicator
            for line in str(msg).split('\n'):
                if line.strip():
                    result.append(f"{NESTED_LINE} {line}\n")
        
        return result
    
    def format_web_fetch(self, url: str, title: str = "", content: str = "") -> Text:
        """Format web fetch output"""
        if title:
            output = f'The title of the page is "{title}".'
        else:
            output = content
        return self.format_tool_call("WebFetch", url, output)
    
    def format_error(self, tool: str, args: str, error: str) -> Text:
        """Format an error message"""
        return self.format_tool_call(tool, args, f"({error})", success=False)
    
    def format_summary(self, items: List[Tuple[str, str]]) -> Text:
        """Format a summary list (numbered items with descriptions)"""
        result = Text()
        
        for i, (title, description) in enumerate(items, 1):
            result.append(f"  {i}. ", style="bold cyan")
            result.append(f"{title}: ", style="bold")
            result.append(f"{description}\n")
        
        return result


def format_agent_output(text: str, console: Optional[Console] = None) -> Text:
    """
    Parse and format raw agent output into professional style.
    
    Args:
        text: Raw agent output text
        console: Rich console
    
    Returns:
        Formatted Rich Text
    """
    formatter = VisualFormatter(console)
    result = Text()
    
    lines = text.split('\n')
    i = 0
    
    while i < len(lines):
        line = lines[i].strip()
        
        if not line:
            result.append('\n')
            i += 1
            continue
        
        # Check for tool call pattern: Tool: name(args)
        tool_match = re.match(r'Tool:\s*(\w+)\s*\((.*?)\)', line)
        if tool_match:
            tool_name = tool_match.group(1)
            tool_args = tool_match.group(2)
            
            # Collect output until next non-indented line
            output_lines = []
            i += 1
            while i < len(lines) and (lines[i].startswith('  ') or lines[i].startswith('\t') or not lines[i].strip()):
                if lines[i].strip():
                    output_lines.append(lines[i].strip())
                i += 1
            
            output = '\n'.join(output_lines)
            result.append_text(formatter.format_tool_call(tool_name, tool_args, output))
            continue
        
        # Default: format as thought
        result.append_text(formatter.format_thought(line))
        result.append('\n')
        i += 1
    
    return result


__all__ = [
    'VisualFormatter',
    'format_agent_output',
    'ToolOutput',
    'BULLET',
    'TOOL_ARROW',
    'NESTED_LINE',
]
