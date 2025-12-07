"""
Advanced Grep Tool for RxDsec CLI
==================================
Production-ready code search with ripgrep integration, regex support,
context lines, and comprehensive filtering options.
"""

from __future__ import annotations

import fnmatch
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional, Set

from .base import tool, ToolResult, ToolStatus

# Configure module logger
logger = logging.getLogger(__name__)

# Maximum matches to return
MAX_MATCHES = 500

# Maximum file size to search (5MB)
MAX_SEARCH_FILE_SIZE = 5 * 1024 * 1024

# Directories to always exclude
DEFAULT_EXCLUDES = {
    '.git', '.svn', '.hg', '.bzr',
    'node_modules', 'bower_components',
    '__pycache__', '.pytest_cache', '.mypy_cache',
    'venv', 'env', '.venv', '.env',
    '.rxdsec', '.idea', '.vscode',
    'dist', 'build', 'target', 'out',
    'vendor', 'third_party',
    '.tox', '.nox', '.eggs',
    'coverage', 'htmlcov',
}

# File patterns to always exclude
DEFAULT_EXCLUDE_PATTERNS = {
    '*.pyc', '*.pyo', '*.class', '*.o', '*.a', '*.so', '*.dll', '*.exe',
    '*.zip', '*.tar', '*.gz', '*.bz2', '*.xz', '*.7z', '*.rar',
    '*.png', '*.jpg', '*.jpeg', '*.gif', '*.bmp', '*.ico', '*.webp', '*.svg',
    '*.mp3', '*.mp4', '*.avi', '*.mkv', '*.mov', '*.wav', '*.flac',
    '*.pdf', '*.doc', '*.docx', '*.xls', '*.xlsx',
    '*.woff', '*.woff2', '*.ttf', '*.otf', '*.eot',
    '*.min.js', '*.min.css', '*.map',
    '*.lock', 'yarn.lock', 'package-lock.json', 'Cargo.lock',
    '.DS_Store', 'Thumbs.db',
}


@dataclass
class SearchMatch:
    """Represents a single search match"""
    file: Path
    line_number: int
    line_content: str
    match_start: int = 0
    match_end: int = 0
    context_before: List[str] = None
    context_after: List[str] = None
    
    def __post_init__(self):
        self.context_before = self.context_before or []
        self.context_after = self.context_after or []
    
    def format(self, show_context: bool = False) -> str:
        """Format the match for display"""
        result = f"{self.file}:{self.line_number}:{self.line_content.rstrip()}"
        
        if show_context:
            lines = []
            for i, ctx in enumerate(self.context_before):
                lines.append(f"{self.file}:{self.line_number - len(self.context_before) + i}: {ctx.rstrip()}")
            lines.append(f"{self.file}:{self.line_number}:{self.line_content.rstrip()}")
            for i, ctx in enumerate(self.context_after):
                lines.append(f"{self.file}:{self.line_number + 1 + i}: {ctx.rstrip()}")
            result = '\n'.join(lines)
        
        return result


def has_ripgrep() -> bool:
    """Check if ripgrep is available"""
    return shutil.which('rg') is not None


def should_exclude_path(path: Path, excludes: Set[str]) -> bool:
    """Check if a path should be excluded from search"""
    parts = path.parts
    
    # Check directory excludes
    for part in parts:
        if part in excludes or part in DEFAULT_EXCLUDES:
            return True
    
    # Check file pattern excludes
    name = path.name
    for pattern in DEFAULT_EXCLUDE_PATTERNS:
        if fnmatch.fnmatch(name, pattern):
            return True
    
    return False


def search_with_ripgrep(
    pattern: str,
    search_path: Path,
    regex: bool = True,
    case_sensitive: bool = True,
    context: int = 0,
    includes: Optional[List[str]] = None,
    excludes: Optional[List[str]] = None,
    max_matches: int = MAX_MATCHES
) -> List[SearchMatch]:
    """
    Search using ripgrep for better performance.
    
    Args:
        pattern: Search pattern
        search_path: Path to search in
        regex: Whether pattern is a regex
        case_sensitive: Whether search is case-sensitive
        context: Number of context lines
        includes: File patterns to include
        excludes: Additional patterns to exclude
        max_matches: Maximum number of matches
    
    Returns:
        List of SearchMatch objects
    """
    cmd = ['rg', '--json', '--max-count', str(max_matches)]
    
    if not case_sensitive:
        cmd.append('-i')
    
    if not regex:
        cmd.append('-F')  # Fixed strings
    
    if context > 0:
        cmd.extend(['-C', str(context)])
    
    # Add includes
    if includes:
        for inc in includes:
            cmd.extend(['-g', inc])
    
    # Add excludes
    for exc in DEFAULT_EXCLUDES:
        cmd.extend(['-g', f'!{exc}/'])
    
    if excludes:
        for exc in excludes:
            cmd.extend(['-g', f'!{exc}'])
    
    cmd.append(pattern)
    cmd.append(str(search_path))
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        matches = []
        import json
        
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            try:
                data = json.loads(line)
                if data.get('type') == 'match':
                    match_data = data['data']
                    matches.append(SearchMatch(
                        file=Path(match_data['path']['text']),
                        line_number=match_data['line_number'],
                        line_content=match_data['lines']['text'],
                        match_start=match_data['submatches'][0]['start'] if match_data.get('submatches') else 0,
                        match_end=match_data['submatches'][0]['end'] if match_data.get('submatches') else 0
                    ))
            except (json.JSONDecodeError, KeyError):
                continue
        
        return matches[:max_matches]
        
    except subprocess.TimeoutExpired:
        logger.warning("Ripgrep search timed out")
        return []
    except Exception as e:
        logger.warning(f"Ripgrep search failed: {e}")
        return []


def search_python(
    pattern: str,
    search_path: Path,
    regex: bool = True,
    case_sensitive: bool = True,
    context: int = 0,
    includes: Optional[List[str]] = None,
    excludes: Optional[Set[str]] = None,
    max_matches: int = MAX_MATCHES
) -> Iterator[SearchMatch]:
    """
    Python-based search implementation as fallback.
    
    Args:
        pattern: Search pattern
        search_path: Path to search in
        regex: Whether pattern is a regex
        case_sensitive: Whether search is case-sensitive
        context: Number of context lines
        includes: File patterns to include
        excludes: Additional paths to exclude
        max_matches: Maximum number of matches
    
    Yields:
        SearchMatch objects
    """
    excludes = excludes or set()
    flags = 0 if case_sensitive else re.IGNORECASE
    
    if regex:
        try:
            compiled_pattern = re.compile(pattern, flags)
        except re.error as e:
            logger.error(f"Invalid regex pattern: {e}")
            return
    else:
        # Escape special regex characters for literal search
        escaped = re.escape(pattern)
        compiled_pattern = re.compile(escaped, flags)
    
    match_count = 0
    
    def iter_files(path: Path) -> Iterator[Path]:
        """Iterate through files respecting excludes"""
        if path.is_file():
            yield path
            return
        
        try:
            for item in path.iterdir():
                if should_exclude_path(item, excludes):
                    continue
                
                if item.is_file():
                    # Check includes
                    if includes:
                        if not any(fnmatch.fnmatch(item.name, inc) for inc in includes):
                            continue
                    yield item
                elif item.is_dir():
                    yield from iter_files(item)
        except PermissionError:
            pass
    
    for file_path in iter_files(search_path):
        if match_count >= max_matches:
            break
        
        # Skip large files
        try:
            if file_path.stat().st_size > MAX_SEARCH_FILE_SIZE:
                continue
        except OSError:
            continue
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            for i, line in enumerate(lines):
                if match_count >= max_matches:
                    break
                
                match = compiled_pattern.search(line)
                if match:
                    # Get context lines
                    ctx_before = lines[max(0, i - context):i] if context > 0 else []
                    ctx_after = lines[i + 1:i + 1 + context] if context > 0 else []
                    
                    yield SearchMatch(
                        file=file_path,
                        line_number=i + 1,
                        line_content=line,
                        match_start=match.start(),
                        match_end=match.end(),
                        context_before=ctx_before,
                        context_after=ctx_after
                    )
                    match_count += 1
                    
        except Exception as e:
            logger.debug(f"Error searching file {file_path}: {e}")
            continue


@tool(
    name="grep",
    description="Search for patterns in files using regex or literal strings. Uses ripgrep when available for better performance.",
    category="search"
)
def grep(
    pattern: str,
    path_glob: str = ".",
    invert: bool = False,
    regex: bool = True,
    case_sensitive: bool = True,
    context: int = 0,
    includes: Optional[str] = None,
    excludes: Optional[str] = None,
    files_only: bool = False,
    count_only: bool = False,
    workspace: Optional[Path] = None,
    permissions=None
) -> ToolResult:
    """
    Search for patterns in files.
    
    Args:
        pattern: Search pattern (regex by default)
        path_glob: Path or glob pattern to search in
        invert: If True, show lines that don't match
        regex: If True, treat pattern as regex; if False, literal string
        case_sensitive: If True, case-sensitive search
        context: Number of context lines to show around matches
        includes: Comma-separated file patterns to include (e.g., "*.py,*.js")
        excludes: Comma-separated patterns to exclude
        files_only: If True, only show file names (not line content)
        count_only: If True, only show match count per file
        workspace: Working directory
        permissions: Permissions engine
    
    Returns:
        ToolResult with search results
    """
    try:
        # Parse includes/excludes
        include_list = [p.strip() for p in includes.split(',')] if includes else None
        exclude_set = set(p.strip() for p in excludes.split(',')) if excludes else set()
        
        # Resolve search path
        if workspace:
            search_path = (workspace / path_glob).resolve()
            if not search_path.exists():
                # Try as glob pattern
                search_path = workspace
        else:
            search_path = Path(path_glob).resolve()
        
        if not search_path.exists():
            return ToolResult.fail(
                error=f"Path not found: {path_glob}",
                status=ToolStatus.NOT_FOUND
            )
        
        # Perform search
        use_ripgrep = has_ripgrep() and search_path.is_dir()
        
        if use_ripgrep:
            matches = search_with_ripgrep(
                pattern=pattern,
                search_path=search_path,
                regex=regex,
                case_sensitive=case_sensitive,
                context=context,
                includes=include_list,
                excludes=list(exclude_set) if exclude_set else None
            )
        else:
            matches = list(search_python(
                pattern=pattern,
                search_path=search_path,
                regex=regex,
                case_sensitive=case_sensitive,
                context=context,
                includes=include_list,
                excludes=exclude_set
            ))
        
        # Apply invert filter
        if invert:
            # For invert, we need to re-search and show non-matching lines
            # This is complex with ripgrep, so we'll do Python-based for now
            if not use_ripgrep:
                # Create a new search that finds lines that DON'T match the pattern
                inverted_matches = []

                # Need to iterate through all files in the search path rather than just those with matches
                def iter_files(path: Path) -> Iterator[Path]:
                    """Iterate through files respecting excludes"""
                    if path.is_file():
                        yield path
                        return

                    try:
                        for item in path.iterdir():
                            if should_exclude_path(item, set()):
                                continue

                            if item.is_file():
                                # Check includes
                                if includes:
                                    if not any(fnmatch.fnmatch(item.name, inc) for inc in includes):
                                        continue
                                yield item
                            elif item.is_dir():
                                yield from iter_files(item)
                    except PermissionError:
                        pass

                # Rebuild the file search to cover all files
                for file_path in iter_files(search_path):
                    if match_count >= max_matches:
                        break

                    # Skip large files
                    try:
                        if file_path.stat().st_size > MAX_SEARCH_FILE_SIZE:
                            continue
                    except OSError:
                        continue

                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            lines = f.readlines()

                        flags = 0 if case_sensitive else re.IGNORECASE
                        if regex:
                            try:
                                compiled_pattern = re.compile(pattern, flags)
                            except re.error as e:
                                return ToolResult.fail(
                                    error=f"Invalid regex pattern: {e}",
                                    status=ToolStatus.VALIDATION_ERROR
                                )
                        else:
                            escaped = re.escape(pattern)
                            compiled_pattern = re.compile(escaped, flags)

                        for i, line in enumerate(lines):
                            if match_count >= max_matches:
                                break
                            # If line does NOT match, add it
                            if not compiled_pattern.search(line):
                                inverted_matches.append(SearchMatch(
                                    file=file_path,
                                    line_number=i + 1,
                                    line_content=line
                                ))
                                match_count += 1
                    except Exception:
                        continue  # Skip files that can't be read

                matches = inverted_matches
        
        if not matches:
            return ToolResult.ok(
                output="No matches found",
                match_count=0,
                search_method="ripgrep" if use_ripgrep else "python"
            )
        
        # Format output
        if count_only:
            # Group by file and count
            file_counts = {}
            for m in matches:
                file_counts[str(m.file)] = file_counts.get(str(m.file), 0) + 1
            
            output_lines = [f"{f}:{c}" for f, c in sorted(file_counts.items())]
            output = '\n'.join(output_lines)
            
        elif files_only:
            # Unique file names only
            files = sorted(set(str(m.file) for m in matches))
            output = '\n'.join(files)
            
        else:
            # Full output with line numbers
            output_lines = []
            for m in matches:
                output_lines.append(m.format(show_context=context > 0))
            
            output = '\n'.join(output_lines)
            
            # Truncate if too long
            if len(output) > 50000:
                output = output[:50000] + "\n\n... (output truncated)"
        
        return ToolResult.ok(
            output=output,
            match_count=len(matches),
            files_matched=len(set(str(m.file) for m in matches)),
            search_method="ripgrep" if use_ripgrep else "python",
            pattern=pattern
        )
        
    except re.error as e:
        return ToolResult.fail(
            error=f"Invalid regex pattern: {str(e)}",
            status=ToolStatus.VALIDATION_ERROR
        )
    except Exception as e:
        logger.exception(f"Error during grep search")
        return ToolResult.fail(
            error=f"Search error: {str(e)}",
            status=ToolStatus.FAILURE
        )


@tool(
    name="find",
    description="Find files by name or pattern in the workspace.",
    category="search"
)
def find(
    pattern: str = "*",
    path: str = ".",
    type_filter: str = "all",
    max_depth: Optional[int] = None,
    workspace: Optional[Path] = None,
    permissions=None
) -> ToolResult:
    """
    Find files and directories by name pattern.
    
    Args:
        pattern: Glob pattern to match (e.g., "*.py", "test_*")
        path: Path to search in
        type_filter: "file", "dir", or "all"
        max_depth: Maximum directory depth to search
        workspace: Working directory
        permissions: Permissions engine
    
    Returns:
        ToolResult with list of matching paths
    """
    try:
        # Resolve search path
        if workspace:
            search_path = (workspace / path).resolve()
        else:
            search_path = Path(path).resolve()
        
        if not search_path.exists():
            return ToolResult.fail(
                error=f"Path not found: {path}",
                status=ToolStatus.NOT_FOUND
            )
        
        results = []
        current_depth = 0
        
        def search_dir(dir_path: Path, depth: int):
            # Convert max_depth to int if string
            md = int(max_depth) if isinstance(max_depth, str) else max_depth
            if md is not None and depth > md:
                return
            
            try:
                for item in dir_path.iterdir():
                    if should_exclude_path(item, set()):
                        continue
                    
                    # Check if name matches pattern
                    if fnmatch.fnmatch(item.name, pattern):
                        # Apply type filter
                        if type_filter == "file" and item.is_file():
                            results.append(item)
                        elif type_filter == "dir" and item.is_dir():
                            results.append(item)
                        elif type_filter == "all":
                            results.append(item)
                    
                    # Recurse into directories
                    if item.is_dir():
                        search_dir(item, depth + 1)
                        
            except PermissionError:
                pass
        
        search_dir(search_path, 0)
        
        # Format output
        if not results:
            return ToolResult.ok(
                output="No matching files found",
                count=0
            )
        
        # Sort and format
        results.sort()
        output_lines = []
        
        for item in results[:MAX_MATCHES]:
            try:
                rel_path = item.relative_to(search_path)
            except ValueError:
                rel_path = item
            
            item_type = "d" if item.is_dir() else "f"
            size = item.stat().st_size if item.is_file() else 0
            output_lines.append(f"[{item_type}] {rel_path} ({size} bytes)")
        
        output = '\n'.join(output_lines)
        
        if len(results) > MAX_MATCHES:
            output += f"\n\n... ({len(results) - MAX_MATCHES} more matches)"
        
        return ToolResult.ok(
            output=output,
            count=len(results)
        )
        
    except Exception as e:
        logger.exception(f"Error during find")
        return ToolResult.fail(
            error=f"Find error: {str(e)}",
            status=ToolStatus.FAILURE
        )