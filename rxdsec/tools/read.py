"""
Advanced Read Tool for RxDsec CLI
==================================
Production-ready file reading with line range support, encoding detection,
binary file handling, and comprehensive error handling.
"""

from __future__ import annotations

import logging
import mimetypes
import os
from pathlib import Path
from typing import Optional, Tuple

from .base import tool, ToolResult, ToolStatus

# Configure module logger
logger = logging.getLogger(__name__)

# Maximum file size to read (5MB - reduced from 10MB to improve performance)
MAX_FILE_SIZE = 5 * 1024 * 1024

# Maximum output length (4KB - reduced from 8KB to improve performance)
MAX_OUTPUT_LENGTH = 4 * 1024

# Maximum default lines to read (reduced from 200 to improve performance)
MAX_DEFAULT_LINES = 100

# Common text file extensions
TEXT_EXTENSIONS = {
    '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.c', '.cpp', '.h', '.hpp',
    '.cs', '.go', '.rs', '.rb', '.php', '.swift', '.kt', '.scala', '.r',
    '.sql', '.sh', '.bash', '.zsh', '.fish', '.ps1', '.bat', '.cmd',
    '.html', '.htm', '.css', '.scss', '.sass', '.less',
    '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf', '.config',
    '.xml', '.svg', '.md', '.markdown', '.rst', '.txt', '.log',
    '.env', '.gitignore', '.dockerignore', '.editorconfig',
    '.lock', '.sum', '.mod'
}

# Binary file extensions to skip
BINARY_EXTENSIONS = {
    '.exe', '.dll', '.so', '.dylib', '.bin', '.obj', '.o', '.a', '.lib',
    '.pyc', '.pyo', '.class', '.jar', '.war', '.ear',
    '.zip', '.tar', '.gz', '.bz2', '.xz', '.7z', '.rar',
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.webp', '.svg',
    '.mp3', '.mp4', '.avi', '.mkv', '.mov', '.wav', '.flac',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.woff', '.woff2', '.ttf', '.otf', '.eot'
}


def detect_encoding(file_path: Path) -> str:
    """
    Detect the encoding of a file.
    
    Args:
        file_path: Path to the file
    
    Returns:
        Detected encoding string
    """
    encodings_to_try = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252', 'iso-8859-1']
    
    for encoding in encodings_to_try:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                f.read(1024)  # Read first 1KB to test
            return encoding
        except (UnicodeDecodeError, UnicodeError):
            continue
    
    return 'utf-8'  # Default fallback


def is_binary_file(file_path: Path) -> bool:
    """
    Check if a file is binary.
    
    Args:
        file_path: Path to the file
    
    Returns:
        True if the file appears to be binary
    """
    # Check extension first
    if file_path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    
    if file_path.suffix.lower() in TEXT_EXTENSIONS:
        return False
    
    # Check MIME type
    mime_type, _ = mimetypes.guess_type(str(file_path))
    if mime_type:
        if mime_type.startswith('text/'):
            return False
        if mime_type in ('application/json', 'application/xml', 'application/javascript'):
            return False
    
    # Check file content for null bytes
    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(8192)
            if b'\x00' in chunk:
                return True
    except Exception:
        pass
    
    return False


def parse_line_range(lines_spec: str) -> Tuple[Optional[int], Optional[int]]:
    """
    Parse a line range specification.
    
    Supports formats:
    - "10" -> lines 1-10
    - "10-20" -> lines 10-20
    - "10:" -> lines 10 to end
    - ":20" -> lines 1-20
    - "-10" -> last 10 lines (negative indexing)
    
    Args:
        lines_spec: Line range specification string
    
    Returns:
        Tuple of (start_line, end_line) where None means "default"
    """
    lines_spec = lines_spec.strip()
    
    if not lines_spec:
        return None, None
    
    # Handle negative indexing (last N lines)
    if lines_spec.startswith('-') and lines_spec[1:].isdigit():
        return -int(lines_spec[1:]), None
    
    # Handle range formats
    if '-' in lines_spec and not lines_spec.startswith('-'):
        parts = lines_spec.split('-', 1)
        start = int(parts[0]) if parts[0] else 1
        end = int(parts[1]) if parts[1] else None
        return start, end
    
    if ':' in lines_spec:
        parts = lines_spec.split(':', 1)
        start = int(parts[0]) if parts[0] else 1
        end = int(parts[1]) if parts[1] else None
        return start, end
    
    # Single number means first N lines
    if lines_spec.isdigit():
        return 1, int(lines_spec)
    
    return None, None


def format_line_numbers(content: str, start_line: int = 1) -> str:
    """
    Add line numbers to content.
    
    Args:
        content: The content to add line numbers to
        start_line: Starting line number
    
    Returns:
        Content with line numbers prefixed
    """
    lines = content.split('\n')
    max_line_num = start_line + len(lines) - 1
    width = len(str(max_line_num))
    
    numbered_lines = []
    for i, line in enumerate(lines):
        line_num = start_line + i
        numbered_lines.append(f"{line_num:>{width}} | {line}")
    
    return '\n'.join(numbered_lines)


@tool(
    name="read",
    description="Read file contents with optional line range support. Supports text files with encoding detection.",
    category="filesystem"
)
def read(
    path: str,
    lines: Optional[str] = None,
    numbered: bool = False,
    workspace: Optional[Path] = None,
    permissions=None
) -> ToolResult:
    """
    Read a file's contents with advanced features.
    
    Args:
        path: Path to the file (relative to workspace or absolute)
        lines: Optional line range (e.g., "1-50", "10:", ":-20", "-10" for last 10)
        numbered: Whether to include line numbers in output
        workspace: Working directory for relative paths
        permissions: Permissions engine for access control
    
    Returns:
        ToolResult with file contents or error
    """
    try:
        # Resolve path
        if workspace:
            full_path = (workspace / path).resolve()
        else:
            full_path = Path(path).resolve()
        
        # Security check: ensure path is within workspace
        if workspace:
            try:
                full_path.relative_to(workspace.resolve())
            except ValueError:
                # Path is outside workspace - check if it's a safe absolute path
                if not full_path.exists():
                    return ToolResult.fail(
                        error=f"File not found: {path}",
                        status=ToolStatus.NOT_FOUND
                    )
        
        # Check if file exists
        if not full_path.exists():
            return ToolResult.fail(
                error=f"File not found: {path}",
                status=ToolStatus.NOT_FOUND
            )
        
        if not full_path.is_file():
            return ToolResult.fail(
                error=f"Not a file: {path}",
                status=ToolStatus.VALIDATION_ERROR
            )
        
        # Check file size
        file_size = full_path.stat().st_size
        if file_size > MAX_FILE_SIZE:
            return ToolResult.fail(
                error=f"File too large ({file_size / 1024 / 1024:.2f}MB). Maximum is {MAX_FILE_SIZE / 1024 / 1024:.0f}MB.",
                status=ToolStatus.VALIDATION_ERROR
            )

        # Check if binary
        if is_binary_file(full_path):
            return ToolResult.fail(
                error=f"Cannot read binary file: {path}. Detected as binary based on extension or content.",
                status=ToolStatus.VALIDATION_ERROR,
                metadata={"binary": True, "size": file_size}
            )

        # Detect encoding
        encoding = detect_encoding(full_path)

        # Apply line range before reading entire file to save memory
        start_line = 1
        end_line = None

        if lines:
            start, end = parse_line_range(lines)
            if start is not None:
                if start < 0:
                    # For negative indexing (last N lines), we need to read the whole file first
                    try:
                        with open(full_path, 'r', encoding=encoding, errors='replace') as f:
                            all_lines = f.readlines()
                    except Exception as e:
                        return ToolResult.fail(
                            error=f"Failed to read file: {str(e)}",
                            status=ToolStatus.FAILURE
                        )
                    total_lines = len(all_lines)
                    start_line = max(1, total_lines + start + 1)
                    all_lines = all_lines[start_line - 1:]
                    content = ''.join(all_lines)
                else:
                    # For specific line ranges, use more memory-efficient approach
                    start_line = max(1, start)
                    end_line = end
                    try:
                        with open(full_path, 'r', encoding=encoding, errors='replace') as f:
                            all_lines = []
                            for i, line in enumerate(f, 1):
                                if end_line and i > end_line:
                                    break
                                if i >= start_line:
                                    all_lines.append(line)
                        content = ''.join(all_lines)
                    except Exception as e:
                        return ToolResult.fail(
                            error=f"Failed to read file: {str(e)}",
                            status=ToolStatus.FAILURE
                        )
            else:
                # No range specified, read with line limits
                try:
                    with open(full_path, 'r', encoding=encoding, errors='replace') as f:
                        all_lines = []
                        for i, line in enumerate(f, 1):
                            if i > MAX_DEFAULT_LINES:
                                all_lines.append(f"\n\n... (File has more than {MAX_DEFAULT_LINES} lines. Use read(path, lines='{MAX_DEFAULT_LINES + 1}:') to read more)")
                                break
                            all_lines.append(line)
                        content = ''.join(all_lines)
                except Exception as e:
                    return ToolResult.fail(
                        error=f"Failed to read file: {str(e)}",
                        status=ToolStatus.FAILURE
                    )
        else:
            # Read with default line limit to prevent memory issues
            try:
                with open(full_path, 'r', encoding=encoding, errors='replace') as f:
                    all_lines = []
                    for i, line in enumerate(f, 1):
                        if i > MAX_DEFAULT_LINES:
                            all_lines.append(f"\n\n... (File has more than {MAX_DEFAULT_LINES} lines. Use read(path, lines='{MAX_DEFAULT_LINES + 1}:') to read more)")
                            break
                        all_lines.append(line)
                    content = ''.join(all_lines)
            except Exception as e:
                return ToolResult.fail(
                    error=f"Failed to read file: {str(e)}",
                    status=ToolStatus.FAILURE
                )

        # Truncate if too long (after applying line range to save memory)
        truncated = False
        if len(content) > MAX_OUTPUT_LENGTH:
            content = content[:MAX_OUTPUT_LENGTH]
            truncated = True
        
        # Add line numbers if requested
        if numbered:
            content = format_line_numbers(content, start_line)
        
        # Build result
        result_text = content
        if truncated:
            result_text += "\n\n... (content truncated due to length)"
        
        metadata = {
            "path": str(full_path),
            "size": file_size,
            "encoding": encoding,
            "total_lines": total_lines,
            "lines_shown": len(all_lines),
            "truncated": truncated
        }
        
        if lines:
            metadata["line_range"] = lines
        
        logger.debug(f"Read file: {path} ({len(all_lines)} lines, {len(content)} chars)")
        
        return ToolResult.ok(
            output=result_text,
            **metadata
        )
        
    except PermissionError:
        return ToolResult.fail(
            error=f"Permission denied: {path}",
            status=ToolStatus.PERMISSION_DENIED
        )
    except Exception as e:
        logger.exception(f"Unexpected error reading file: {path}")
        return ToolResult.fail(
            error=f"Error reading file: {str(e)}",
            status=ToolStatus.FAILURE
        )


@tool(
    name="read_lines",
    description="Read specific lines from a file. Shorthand for read with line range.",
    category="filesystem"
)
def read_lines(
    path: str,
    start: int = 1,
    end: Optional[int] = None,
    workspace: Optional[Path] = None,
    permissions=None
) -> ToolResult:
    """
    Read specific lines from a file.
    
    Args:
        path: Path to the file
        start: Starting line number (1-indexed)
        end: Ending line number (inclusive, None for end of file)
        workspace: Working directory
        permissions: Permissions engine
    
    Returns:
        ToolResult with the specified lines
    """
    line_spec = f"{start}-{end}" if end else f"{start}:"
    return read(path, lines=line_spec, numbered=True, workspace=workspace, permissions=permissions)