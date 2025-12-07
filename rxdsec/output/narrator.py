"""
Advanced Tool Narrator for RxDsec CLI
======================================
Translates raw tool calls into natural, human-readable language
for better user experience and transparency.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# Configure module logger
logger = logging.getLogger(__name__)


@dataclass
class ToolCallInfo:
    """Parsed tool call information"""
    tool_name: str
    args: Dict[str, str]
    raw: str


class ToolNarrator:
    """
    Translate tool calls into natural language narration.
    
    This makes agent actions more transparent and understandable
    to users by converting technical tool syntax into plain English.
    """
    
    # Narration templates for different tools and outcomes
    TEMPLATES = {
        'read': {
            'action': "Reading file: {path}",
            'with_lines': "Reading lines {lines} from {path}",
            'success': "Read {bytes} bytes from {path}",
            'failure': "Failed to read {path}: {error}",
        },
        'write': {
            'action': "Writing to file: {path}",
            'append': "Appending to file: {path}",
            'success': "Wrote {bytes} bytes to {path}",
            'created': "Created new file: {path}",
            'failure': "Failed to write {path}: {error}",
        },
        'grep': {
            'action': 'Searching for "{pattern}" in {path}',
            'success': "Found {count} matches",
            'no_matches': "No matches found",
            'failure': "Search failed: {error}",
        },
        'find': {
            'action': 'Finding files matching "{pattern}"',
            'success': "Found {count} files",
            'failure': "Find failed: {error}",
        },
        'localexec': {
            'action': "Running: {cmd}",
            'success': "Command completed successfully",
            'failure': "Command failed with exit code {code}",
            'timeout': "Command timed out",
        },
        'shell': {
            'action': "Executing: {cmd}",
            'success': "Execution complete",
            'failure': "Execution failed: {error}",
        },
        'webfetch': {
            'action': "Fetching: {url}",
            'success': "Retrieved {bytes} bytes from {url}",
            'failure': "Failed to fetch {url}: {error}",
        },
        'download': {
            'action': "Downloading: {url}",
            'success': "Downloaded to {path}",
            'failure': "Download failed: {error}",
        },
        'patch': {
            'action': "Patching {path}",
            'success': "Applied {count} patch(es) to {path}",
            'failure': "Patch failed: {error}",
        },
        'run_tests': {
            'action': "Running tests",
            'success': "All tests passed ✓",
            'partial': "{passed} passed, {failed} failed",
            'failure': "Tests failed: {error}",
        },
    }
    
    # Patterns for parsing tool calls
    TOOL_CALL_PATTERN = re.compile(
        r'Tool:\s*(\w+)\s*\(\s*(.*?)\s*\)',
        re.DOTALL
    )
    
    ARG_PATTERN = re.compile(
        r'(\w+)\s*=\s*(?:"([^"]*?)"|\'([^\']*?)\'|([^\s,\)]+))',
        re.DOTALL
    )
    
    def __init__(self):
        self._action_verbs = {
            'read': ('Reading', 'Read'),
            'write': ('Writing', 'Wrote'),
            'grep': ('Searching', 'Found'),
            'find': ('Finding', 'Found'),
            'localexec': ('Running', 'Ran'),
            'shell': ('Executing', 'Executed'),
            'webfetch': ('Fetching', 'Fetched'),
            'download': ('Downloading', 'Downloaded'),
            'patch': ('Patching', 'Patched'),
            'run_tests': ('Testing', 'Tested'),
        }
    
    def parse_tool_call(self, line: str) -> Optional[ToolCallInfo]:
        """
        Parse a tool call line into structured data.
        
        Args:
            line: Raw tool call line (e.g., "Tool: read(path='src/main.py')")
        
        Returns:
            ToolCallInfo or None if not a valid tool call
        """
        match = self.TOOL_CALL_PATTERN.search(line)
        if not match:
            return None
        
        tool_name = match.group(1).lower()
        args_str = match.group(2)
        
        # Parse arguments
        args = {}
        for arg_match in self.ARG_PATTERN.finditer(args_str):
            key = arg_match.group(1)
            # Value is in one of groups 2, 3, or 4
            value = arg_match.group(2) or arg_match.group(3) or arg_match.group(4) or ''
            args[key] = value
        
        return ToolCallInfo(
            tool_name=tool_name,
            args=args,
            raw=line
        )
    
    def translate(self, line: str) -> str:
        """
        Translate a tool call into natural language.
        
        Args:
            line: Raw tool call line
        
        Returns:
            Human-readable narration
        """
        info = self.parse_tool_call(line)
        if not info:
            return line  # Return original if can't parse
        
        return self._narrate_action(info)
    
    def _narrate_action(self, info: ToolCallInfo) -> str:
        """Generate narration for a tool action"""
        templates = self.TEMPLATES.get(info.tool_name, {})
        
        if info.tool_name == 'read':
            path = info.args.get('path', 'unknown file')
            lines = info.args.get('lines', '')
            
            if lines:
                return f"📖 Reading lines {lines} from {self._format_path(path)}"
            return f"📖 Reading {self._format_path(path)}"
        
        elif info.tool_name == 'write':
            path = info.args.get('path', 'unknown file')
            append = info.args.get('append', 'false').lower() == 'true'
            
            if append:
                return f"📝 Appending to {self._format_path(path)}"
            return f"📝 Writing to {self._format_path(path)}"
        
        elif info.tool_name == 'grep':
            pattern = info.args.get('pattern', '')
            path = info.args.get('path_glob', '.') or info.args.get('path', '.')
            
            return f"🔍 Searching for \"{self._truncate(pattern, 30)}\" in {self._format_path(path)}"
        
        elif info.tool_name == 'find':
            pattern = info.args.get('pattern', '*')
            path = info.args.get('path', '.')
            
            return f"📂 Finding files matching \"{pattern}\" in {self._format_path(path)}"
        
        elif info.tool_name in ('localexec', 'shell'):
            cmd = info.args.get('cmd', '')
            return f"⚡ Running: {self._truncate(cmd, 50)}"
        
        elif info.tool_name == 'webfetch':
            url = info.args.get('url', '')
            return f"🌐 Fetching: {self._truncate(url, 50)}"
        
        elif info.tool_name == 'download':
            url = info.args.get('url', '')
            path = info.args.get('save_path', '')
            return f"⬇️ Downloading to {self._format_path(path)}"
        
        elif info.tool_name == 'patch':
            path = info.args.get('path', '')
            return f"🔧 Patching {self._format_path(path)}"
        
        elif info.tool_name == 'run_tests':
            framework = info.args.get('framework', '')
            if framework:
                return f"🧪 Running {framework} tests"
            return "🧪 Running tests"
        
        else:
            # Generic fallback
            args_str = ', '.join(f"{k}={v}" for k, v in list(info.args.items())[:3])
            return f"🔧 {info.tool_name}({self._truncate(args_str, 40)})"
    
    def narrate_result(self, info: ToolCallInfo, success: bool, result_data: Dict) -> str:
        """
        Generate narration for a tool result.
        
        Args:
            info: Tool call info
            success: Whether the tool succeeded
            result_data: Result data from tool
        
        Returns:
            Human-readable result narration
        """
        if info.tool_name == 'read':
            if success:
                bytes_read = result_data.get('size', result_data.get('bytes', '?'))
                path = info.args.get('path', 'file')
                return f"✓ Read {bytes_read} bytes from {self._format_path(path)}"
            else:
                error = result_data.get('error', 'Unknown error')
                return f"✗ Failed to read file: {error}"
        
        elif info.tool_name == 'write':
            if success:
                path = info.args.get('path', 'file')
                is_new = result_data.get('is_new', False)
                action = "Created" if is_new else "Updated"
                return f"✓ {action} {self._format_path(path)}"
            else:
                error = result_data.get('error', 'Unknown error')
                return f"✗ Failed to write file: {error}"
        
        elif info.tool_name == 'grep':
            if success:
                count = result_data.get('match_count', 0)
                if count == 0:
                    return "No matches found"
                return f"✓ Found {count} match{'es' if count != 1 else ''}"
            else:
                return f"✗ Search failed: {result_data.get('error', 'Unknown error')}"
        
        elif info.tool_name in ('localexec', 'shell'):
            if success:
                return "✓ Command completed successfully"
            else:
                code = result_data.get('returncode', '?')
                return f"✗ Command failed with exit code {code}"
        
        elif info.tool_name == 'webfetch':
            if success:
                length = result_data.get('content_length', '?')
                return f"✓ Retrieved {length} bytes"
            else:
                return f"✗ Failed to fetch: {result_data.get('error', 'Unknown error')}"
        
        elif info.tool_name == 'run_tests':
            if success:
                return "✓ All tests passed"
            else:
                return f"✗ Tests failed"
        
        else:
            # Generic fallback
            if success:
                return f"✓ {info.tool_name} completed"
            else:
                return f"✗ {info.tool_name} failed: {result_data.get('error', 'Unknown error')}"
    
    def _format_path(self, path: str) -> str:
        """Format a file path for display"""
        if not path:
            return 'unknown'
        
        # Truncate long paths
        if len(path) > 40:
            parts = path.replace('\\', '/').split('/')
            if len(parts) > 3:
                return f".../{'/'.join(parts[-2:])}"
        
        return path
    
    def _truncate(self, text: str, max_len: int) -> str:
        """Truncate text with ellipsis"""
        if len(text) <= max_len:
            return text
        return text[:max_len - 3] + '...'


# Convenience function for backward compatibility
def translate_tool_call(log: str) -> str:
    """
    Translate a tool call log into natural language.
    
    Args:
        log: Raw tool call log line
    
    Returns:
        Human-readable narration
    """
    narrator = ToolNarrator()
    return narrator.translate(log)


__all__ = ['ToolNarrator', 'translate_tool_call', 'ToolCallInfo']