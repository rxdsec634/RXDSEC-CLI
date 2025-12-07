"""
Todo Management Tool for RxDsec CLI
====================================
Manages a TODO list file (todo.md) for task tracking.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .base import tool, ToolResult, ToolStatus

# Configure module logger
logger = logging.getLogger(__name__)


@tool(
    name="todowrite",
    description="Write or update the TODO list to track progress. Provide the full list including checkboxes.",
    category="planning"
)
def todowrite(
    content: str,
    workspace: Optional[Path] = None,
    permissions=None
) -> ToolResult:
    """
    Write to the todo.md file and return the current state.
    
    Args:
        content: The full content of the todo list (e.g. "- [ ] Task 1\n- [x] Task 2")
        workspace: Working directory
        permissions: Permissions engine
    
    Returns:
        ToolResult with the updated list as output
    """
    if not workspace:
        return ToolResult.fail(
            error="Workspace required for todo management",
            status=ToolStatus.SYS_ERROR
        )
    
    try:
        todo_path = (workspace / "todo.md").resolve()
        
        # Ensure it's inside workspace
        try:
            todo_path.relative_to(workspace)
        except ValueError:
             return ToolResult.fail(
                error=f"Access denied: Path {todo_path} is outside workspace",
                status=ToolStatus.PERMISSION_DENIED
            )
            
        # Write content
        with open(todo_path, 'w', encoding='utf-8') as f:
            f.write(content)
            
        # Count items for summary
        lines = content.strip().split('\n')
        total = 0
        done = 0
        
        formatted_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Identify todo items
            if line.startswith('- [ ]') or line.startswith('[ ]'):
                total += 1
                formatted_lines.append(f"  [ ] {line.replace('- [ ]', '').replace('[ ]', '').strip()}")
            elif line.startswith('- [x]') or line.startswith('[x]'):
                total += 1
                done += 1
                formatted_lines.append(f"  [x] {line.replace('- [x]', '').replace('[x]', '').strip()}")
            else:
                # Just a header or note
                formatted_lines.append(f"  {line}")
                
        status_msg = f"{done}/{total} todos" if total > 0 else "Todo list updated"
        
        # We format the output to look like the screenshot request
        output = "\n".join(formatted_lines)
        
        return ToolResult.ok(
            output=output,
            path="todo.md",
            summary=status_msg
        )
        
    except Exception as e:
        logger.exception("Failed to write todo list")
        return ToolResult.fail(
            error=f"Failed to write todo list: {str(e)}",
            status=ToolStatus.FAILURE
        )
