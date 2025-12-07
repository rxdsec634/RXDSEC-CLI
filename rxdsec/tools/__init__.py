"""
RxDsec Tools Package
====================
Production-ready tool implementations for the RxDsec CLI agent.

This package provides all built-in tools that the agent can use:
- read: Read file contents with encoding detection and line ranges
- write: Write files with atomic operations and backup
- grep: Search code with ripgrep integration
- find: Find files by name pattern
- localexec: Execute shell commands with sandboxing
- shell: Simple shell command execution
- run_tests: Run project tests with framework detection
- webfetch: Fetch web content with rate limiting
- download: Download files from URLs
- patch: Apply search-replace patches to files
- read_lines: Read specific line ranges
- write_lines: Write/insert lines at specific positions

All tools return ToolResult objects with:
- success: Boolean indicating success/failure
- output: Tool output (stdout, file contents, etc.)
- error: Error message if failed
- status: Detailed ToolStatus enum value
- duration_ms: Execution time
- metadata: Additional context

Example usage:
    from rxdsec.tools import ToolRegistry, ToolResult
    
    registry = ToolRegistry(workspace=Path.cwd())
    result = registry.execute("read", {"path": "src/main.py"})
    
    if result.success:
        print(result.output)
    else:
        print(f"Error: {result.error}")
"""

from .base import (
    tool,
    ToolResult,
    ToolStatus,
    ToolRegistry,
    ToolDefinition,
    ToolParameter,
    TOOL_REGISTRY,
)

# Import all tools to register them
from . import read
from . import write
from . import grep
from . import localexec
from . import web
from . import todo

# Re-export commonly used classes and functions
__all__ = [
    # Core classes
    "ToolRegistry",
    "ToolResult",
    "ToolStatus",
    "ToolDefinition",
    "ToolParameter",
    
    # Decorator
    "tool",
    
    # Global registry
    "TOOL_REGISTRY",
    
    # Tool modules (for direct access if needed)
    "read",
    "write", 
    "grep",
    "localexec",
    "web",
    "todo",
]

# Version
__version__ = "1.0.0"


def get_tool_list() -> list:
    """Get a list of all registered tool names"""
    return list(TOOL_REGISTRY.keys())


def get_tool_help(name: str) -> str:
    """Get help text for a specific tool"""
    if name in TOOL_REGISTRY:
        return TOOL_REGISTRY[name].get_help()
    return f"Tool not found: {name}"


def describe_all_tools() -> str:
    """Get descriptions of all registered tools"""
    registry = ToolRegistry()
    return registry.describe()