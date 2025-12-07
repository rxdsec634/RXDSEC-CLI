"""
Advanced Write Tool for RxDsec CLI
===================================
Production-ready file writing with atomic operations, backup management,
diff preview, and comprehensive safety features.
"""

from __future__ import annotations

import difflib
import hashlib
import logging
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from .base import tool, ToolResult, ToolStatus

# Configure module logger
logger = logging.getLogger(__name__)

# Maximum file size to write (50MB)
MAX_WRITE_SIZE = 50 * 1024 * 1024

# Backup directory name
BACKUP_DIR = ".rxdsec/backups"

# Maximum number of backups to keep per file
MAX_BACKUPS_PER_FILE = 10


def get_backup_path(workspace: Path, file_path: Path) -> Path:
    """
    Generate a backup path for a file.
    
    Args:
        workspace: Workspace directory
        file_path: Path to the original file
    
    Returns:
        Path for the backup file
    """
    backup_dir = workspace / BACKUP_DIR
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_hash = hashlib.md5(str(file_path).encode()).hexdigest()[:8]
    backup_name = f"{file_path.name}_{timestamp}_{file_hash}.bak"
    
    return backup_dir / backup_name


def cleanup_old_backups(workspace: Path, file_path: Path, keep: int = MAX_BACKUPS_PER_FILE):
    """
    Clean up old backups for a file, keeping only the most recent ones.
    
    Args:
        workspace: Workspace directory
        file_path: Path to the original file
        keep: Number of backups to keep
    """
    backup_dir = workspace / BACKUP_DIR
    if not backup_dir.exists():
        return
    
    # Find all backups for this file
    file_prefix = file_path.name + "_"
    backups = sorted(
        [f for f in backup_dir.iterdir() if f.name.startswith(file_prefix) and f.name.endswith('.bak')],
        key=lambda x: x.stat().st_mtime,
        reverse=True
    )
    
    # Remove old backups
    for old_backup in backups[keep:]:
        try:
            old_backup.unlink()
            logger.debug(f"Removed old backup: {old_backup}")
        except Exception as e:
            logger.warning(f"Failed to remove old backup {old_backup}: {e}")


def generate_diff(old_content: str, new_content: str, file_path: str) -> str:
    """
    Generate a unified diff between old and new content.
    
    Args:
        old_content: Original file content
        new_content: New file content
        file_path: Path for diff header
    
    Returns:
        Unified diff string
    """
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    
    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        lineterm=''
    )
    
    return ''.join(diff)


def validate_content(content: str) -> tuple[bool, Optional[str]]:
    """
    Validate content before writing.
    
    Args:
        content: Content to validate
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if len(content) > MAX_WRITE_SIZE:
        return False, f"Content too large ({len(content) / 1024 / 1024:.2f}MB). Maximum is {MAX_WRITE_SIZE / 1024 / 1024:.0f}MB."
    
    return True, None


@tool(
    name="write",
    description="Write content to a file with atomic operations, automatic backup, and safety features.",
    category="filesystem"
)
def write(
    path: str,
    content: str,
    append: bool = False,
    create_dirs: bool = True,
    backup: bool = True,
    workspace: Optional[Path] = None,
    permissions=None
) -> ToolResult:
    """
    Write content to a file with production-grade safety features.
    
    Features:
    - Atomic writes using temporary files
    - Automatic backup before overwriting
    - Directory creation
    - Permission checking
    - Content validation
    
    Args:
        path: Path to write to (relative to workspace or absolute)
        content: Content to write
        append: If True, append to existing file instead of overwriting
        create_dirs: If True, create parent directories if they don't exist
        backup: If True, create backup before overwriting existing file
        workspace: Working directory for relative paths
        permissions: Permissions engine for access control
    
    Returns:
        ToolResult with write outcome
    """
    try:
        # Validate content
        valid, error = validate_content(content)
        if not valid:
            return ToolResult.fail(
                error=error,
                status=ToolStatus.VALIDATION_ERROR
            )
        
        # Resolve path
        if workspace:
            full_path = (workspace / path).resolve()
        else:
            full_path = Path(path).resolve()
        
        # Security check: prevent writing outside workspace
        if workspace:
            try:
                full_path.relative_to(workspace.resolve())
            except ValueError:
                return ToolResult.fail(
                    error=f"Cannot write outside workspace: {path}",
                    status=ToolStatus.PERMISSION_DENIED
                )
        
        # Check if path is a directory
        if full_path.exists() and full_path.is_dir():
            return ToolResult.fail(
                error=f"Cannot write to directory: {path}",
                status=ToolStatus.VALIDATION_ERROR
            )
        
        # Create parent directories if needed
        if create_dirs:
            full_path.parent.mkdir(parents=True, exist_ok=True)
        elif not full_path.parent.exists():
            return ToolResult.fail(
                error=f"Parent directory does not exist: {full_path.parent}",
                status=ToolStatus.VALIDATION_ERROR
            )
        
        # Track what we're doing
        is_new_file = not full_path.exists()
        backup_path = None
        old_content = ""
        
        # Create backup if file exists and backup is enabled
        if not is_new_file and backup and not append:
            try:
                ws = workspace or Path.cwd()
                backup_path = get_backup_path(ws, full_path)
                shutil.copy2(full_path, backup_path)
                
                # Read old content for diff
                with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                    old_content = f.read()
                
                # Cleanup old backups
                cleanup_old_backups(ws, full_path)
                
                logger.debug(f"Created backup: {backup_path}")
            except Exception as e:
                logger.warning(f"Failed to create backup: {e}")
                # Continue with write even if backup fails
        
        # Read existing content for append mode
        if append and full_path.exists():
            try:
                with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                    old_content = f.read()
            except Exception:
                old_content = ""
        
        # Perform atomic write using temporary file
        try:
            # Create temp file in same directory for atomic rename
            fd, temp_path = tempfile.mkstemp(
                dir=str(full_path.parent),
                prefix=f".{full_path.name}.",
                suffix=".tmp"
            )
            
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    if append and old_content:
                        f.write(old_content)
                    f.write(content)
                
                # Atomic rename
                os.replace(temp_path, full_path)
                
            except Exception:
                # Clean up temp file on failure
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                raise
                
        except Exception as e:
            return ToolResult.fail(
                error=f"Failed to write file: {str(e)}",
                status=ToolStatus.FAILURE
            )
        
        # Generate diff for non-append operations
        diff = ""
        if not append and old_content:
            diff = generate_diff(old_content, content, path)
        
        # Build result message
        action = "appended to" if append else ("created" if is_new_file else "updated")
        result_msg = f"Successfully {action}: {path}"
        
        if backup_path:
            result_msg += f"\nBackup saved: {backup_path.name}"
        
        if diff and len(diff) < 2000:  # Only include diff if not too long
            result_msg += f"\n\nChanges:\n{diff}"
        
        metadata = {
            "path": str(full_path),
            "bytes_written": len(content),
            "action": action,
            "is_new": is_new_file,
            "backup": str(backup_path) if backup_path else None
        }
        
        logger.info(f"Wrote file: {path} ({len(content)} bytes, {action})")
        
        return ToolResult.ok(
            output=result_msg,
            **metadata
        )
        
    except PermissionError:
        return ToolResult.fail(
            error=f"Permission denied: {path}",
            status=ToolStatus.PERMISSION_DENIED
        )
    except Exception as e:
        logger.exception(f"Unexpected error writing file: {path}")
        return ToolResult.fail(
            error=f"Error writing file: {str(e)}",
            status=ToolStatus.FAILURE
        )


@tool(
    name="write_lines",
    description="Write or insert lines at a specific position in a file.",
    category="filesystem"
)
def write_lines(
    path: str,
    content: str,
    line: int,
    mode: str = "insert",
    workspace: Optional[Path] = None,
    permissions=None
) -> ToolResult:
    """
    Write or insert lines at a specific position.
    
    Args:
        path: Path to the file
        content: Content to write
        line: Line number for insertion (1-indexed)
        mode: "insert" to insert at line, "replace" to replace line, "after" to insert after line
        workspace: Working directory
        permissions: Permissions engine
    
    Returns:
        ToolResult with outcome
    """
    try:
        # Resolve path
        if workspace:
            full_path = (workspace / path).resolve()
        else:
            full_path = Path(path).resolve()
        
        # Read existing content
        if full_path.exists():
            with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
        else:
            lines = []
        
        # Adjust line index (0-indexed)
        idx = max(0, min(line - 1, len(lines)))
        
        # Apply the operation
        content_lines = content.split('\n')
        content_with_newlines = [l + '\n' for l in content_lines[:-1]]
        if content_lines[-1]:
            content_with_newlines.append(content_lines[-1] + '\n')
        
        if mode == "insert":
            lines[idx:idx] = content_with_newlines
        elif mode == "replace":
            lines[idx:idx + 1] = content_with_newlines
        elif mode == "after":
            lines[idx + 1:idx + 1] = content_with_newlines
        else:
            return ToolResult.fail(
                error=f"Invalid mode: {mode}. Use 'insert', 'replace', or 'after'.",
                status=ToolStatus.VALIDATION_ERROR
            )
        
        # Write back
        new_content = ''.join(lines)
        return write(path, new_content, workspace=workspace, permissions=permissions)
        
    except Exception as e:
        return ToolResult.fail(
            error=f"Error modifying file: {str(e)}",
            status=ToolStatus.FAILURE
        )


@tool(
    name="patch",
    description="Apply a patch/diff to a file.",
    category="filesystem"
)
def patch(
    path: str,
    old_text: str,
    new_text: str,
    workspace: Optional[Path] = None,
    permissions=None
) -> ToolResult:
    """
    Apply a search-and-replace patch to a file.
    
    Args:
        path: Path to the file
        old_text: Text to find and replace
        new_text: Replacement text
        workspace: Working directory
        permissions: Permissions engine
    
    Returns:
        ToolResult with outcome
    """
    try:
        # Resolve path
        if workspace:
            full_path = (workspace / path).resolve()
        else:
            full_path = Path(path).resolve()
        
        if not full_path.exists():
            return ToolResult.fail(
                error=f"File not found: {path}",
                status=ToolStatus.NOT_FOUND
            )
        
        # Read existing content
        with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        
        # Check if old_text exists
        if old_text not in content:
            return ToolResult.fail(
                error=f"Pattern not found in file: {path}",
                output=f"Could not find:\n{old_text[:200]}...",
                status=ToolStatus.VALIDATION_ERROR
            )
        
        # Count occurrences
        count = content.count(old_text)
        
        # Apply patch
        new_content = content.replace(old_text, new_text)
        
        # Write back
        result = write(path, new_content, workspace=workspace, permissions=permissions)
        
        if result.success:
            return ToolResult.ok(
                output=f"Patched {count} occurrence(s) in {path}",
                occurrences=count,
                path=str(full_path)
            )
        
        return result
        
    except Exception as e:
        return ToolResult.fail(
            error=f"Error patching file: {str(e)}",
            status=ToolStatus.FAILURE
        )