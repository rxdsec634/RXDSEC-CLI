"""
Advanced LocalExec Tool for RxDsec CLI
=======================================
Production-ready shell command execution with sandboxing support,
timeout handling, and comprehensive safety features.
"""

from __future__ import annotations

import logging
import os
import platform
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .base import tool, ToolResult, ToolStatus

# Configure module logger
logger = logging.getLogger(__name__)

# Default timeout (10 minutes)
DEFAULT_TIMEOUT = 600

# Maximum output size (1MB)
MAX_OUTPUT_SIZE = 1024 * 1024

# Dangerous commands that require explicit permission
DANGEROUS_COMMANDS = {
    'rm', 'rmdir', 'del',           # Delete operations
    'mv', 'move', 'ren', 'rename',   # Move/rename (can overwrite)
    'chmod', 'chown', 'chgrp',       # Permission changes
    'sudo', 'su', 'runas',           # Privilege escalation
    'dd', 'mkfs', 'fdisk',           # Disk operations
    'shutdown', 'reboot', 'halt',    # System control
    'kill', 'pkill', 'killall',      # Process killing
    ':(){:|:&};:', 'fork',           # Fork bombs
    'format', 'diskpart',            # Windows disk ops
}

# Safe commands that don't need confirmation
SAFE_COMMANDS = {
    # Read-only operations
    'ls', 'dir', 'cat', 'type', 'head', 'tail', 'less', 'more',
    'pwd', 'cd', 'echo', 'printf', 'date', 'time', 'whoami', 'hostname',
    'grep', 'find', 'which', 'where', 'locate', 'file', 'stat',
    'wc', 'sort', 'uniq', 'diff', 'cmp', 'md5sum', 'sha256sum',
    
    # Development tools (read-only or isolated)
    'git', 'hg', 'svn',
    'python', 'python3', 'py', 'pip', 'pip3',
    'node', 'npm', 'npx', 'yarn', 'pnpm',
    'cargo', 'rustc', 'rustup',
    'go', 'gofmt', 'golint',
    'java', 'javac', 'mvn', 'gradle',
    'make', 'cmake', 'ninja',
    'gcc', 'g++', 'clang', 'clang++',
    
    # Testing frameworks
    'pytest', 'jest', 'mocha', 'npm test', 'cargo test',
    
    # Linters/formatters
    'black', 'flake8', 'pylint', 'mypy', 'ruff',
    'eslint', 'prettier', 'tsc',
    'rustfmt', 'clippy',
}


@dataclass
class CommandResult:
    """Result of command execution"""
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False
    killed: bool = False
    duration_seconds: float = 0.0
    
    @property
    def success(self) -> bool:
        return self.returncode == 0 and not self.timed_out and not self.killed
    
    @property
    def output(self) -> str:
        """Combined stdout and stderr"""
        parts = []
        if self.stdout.strip():
            parts.append(self.stdout)
        if self.stderr.strip():
            parts.append(f"STDERR:\n{self.stderr}")
        return '\n'.join(parts) if parts else "(no output)"


def has_firejail() -> bool:
    """Check if firejail is available for sandboxing (Linux only)"""
    if platform.system() != 'Linux':
        return False
    return shutil.which('firejail') is not None


def has_sandbox() -> bool:
    """Check if any sandboxing is available"""
    return has_firejail()


def parse_command(cmd: str) -> Tuple[str, List[str]]:
    """
    Parse a command string into executable and arguments.
    
    Args:
        cmd: Command string
    
    Returns:
        Tuple of (executable, arguments)
    """
    try:
        parts = shlex.split(cmd)
        if not parts:
            return '', []
        return parts[0], parts[1:]
    except ValueError:
        # Fallback for edge cases
        parts = cmd.split()
        if not parts:
            return '', []
        return parts[0], parts[1:]


def is_safe_command(cmd: str) -> bool:
    """
    Check if a command is considered safe to run.
    
    Args:
        cmd: Command string
    
    Returns:
        True if command is safe
    """
    executable, args = parse_command(cmd)
    base_cmd = os.path.basename(executable).lower()
    
    # Remove extensions for Windows
    if base_cmd.endswith('.exe') or base_cmd.endswith('.cmd') or base_cmd.endswith('.bat'):
        base_cmd = base_cmd.rsplit('.', 1)[0]
    
    # Check dangerous commands
    if base_cmd in DANGEROUS_COMMANDS:
        return False
    
    # Check safe commands
    if base_cmd in SAFE_COMMANDS:
        return True
    
    # Check for dangerous patterns in arguments
    dangerous_patterns = [
        'rm -rf', 'rm -r', 'del /s', 'del /q',
        '> /dev/', '| rm', '| del',
        '; rm', '; del', '&& rm', '&& del',
        'chmod 777', 'chmod -R',
    ]
    
    cmd_lower = cmd.lower()
    for pattern in dangerous_patterns:
        if pattern in cmd_lower:
            return False
    
    return True  # Default to allowing (permissions engine will verify)


def wrap_with_sandbox(cmd: List[str], sandbox: str = "firejail") -> List[str]:
    """
    Wrap command with sandbox.
    
    Args:
        cmd: Command as list of strings
        sandbox: Sandbox type ("firejail" or "none")
    
    Returns:
        Sandboxed command
    """
    if sandbox == "firejail" and has_firejail():
        return [
            'firejail',
            '--noprofile',
            '--quiet',
            '--private-tmp',
            '--noroot',
            '--nosound',
            '--no3d',
            '--noprinters',
            '--nodvd',
            '--notv',
            '--novideo',
            '--nonewprivs',
            '--nogroups',
            '--net=none',  # No network by default
        ] + cmd
    
    return cmd


def run_command(
    cmd: str,
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
    timeout: int = DEFAULT_TIMEOUT,
    sandbox: bool = False,
    capture_output: bool = True
) -> CommandResult:
    """
    Run a command with proper handling.
    
    Args:
        cmd: Command to run
        cwd: Working directory
        env: Environment variables
        timeout: Timeout in seconds
        sandbox: Whether to use sandboxing
        capture_output: Whether to capture stdout/stderr
    
    Returns:
        CommandResult with execution outcome
    """
    import time
    start_time = time.time()
    
    try:
        # Parse command
        if platform.system() == 'Windows':
            # Windows: Use shell for complex commands
            cmd_list = cmd
            use_shell = True
        else:
            # Unix: Parse into list
            cmd_list = shlex.split(cmd)
            use_shell = False
            
            # Apply sandbox if requested
            if sandbox:
                cmd_list = wrap_with_sandbox(cmd_list)
        
        # Prepare environment
        run_env = os.environ.copy()
        if env:
            run_env.update(env)
        
        # Set PAGER to cat to avoid interactive pagers
        run_env['PAGER'] = 'cat'
        run_env['GIT_PAGER'] = 'cat'
        
        # Run command
        process = subprocess.Popen(
            cmd_list,
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
            cwd=str(cwd) if cwd else None,
            env=run_env,
            shell=use_shell,
            text=True
        )
        
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            
            # Truncate output if too long
            if stdout and len(stdout) > MAX_OUTPUT_SIZE:
                stdout = stdout[:MAX_OUTPUT_SIZE] + "\n... (output truncated)"
            if stderr and len(stderr) > MAX_OUTPUT_SIZE:
                stderr = stderr[:MAX_OUTPUT_SIZE] + "\n... (output truncated)"
            
            duration = time.time() - start_time
            
            # Check for common Windows/WSL errors to hint the agent
            if platform.system() == 'Windows' and stderr and "Windows Subsystem for Linux has no installed distributions" in stderr:
                stderr += "\n\n[SYSTEM HINT]: You are running on Windows and 'bash' failed because WSL is not configured. Do not try to install WSL interactively. Instead, use Windows-native commands (PowerShell) or check if there is a Windows installer (e.g. .exe/msi) or package manager (winget/choco) for the tool you are trying to use."
            
            return CommandResult(
                returncode=process.returncode,
                stdout=stdout or '',
                stderr=stderr or '',
                timed_out=False,
                killed=False,
                duration_seconds=duration
            )
            
        except subprocess.TimeoutExpired:
            # Kill process on timeout
            process.kill()
            try:
                stdout, stderr = process.communicate(timeout=5)
            except:
                stdout, stderr = '', ''
            
            duration = time.time() - start_time
            
            # Check for common Windows/WSL errors to hint the agent
            if platform.system() == 'Windows' and "Windows Subsystem for Linux has no installed distributions" in stderr:
                stderr += "\n\n[SYSTEM HINT]: You are running on Windows and 'bash' failed because WSL is not configured. Do not try to install WSL interactively. Instead, use Windows-native commands (PowerShell) or check if there is a Windows installer (e.g. .exe/msi) or package manager (winget/choco) for the tool you are trying to use."

            return CommandResult(
                returncode=-1,
                stdout=stdout or '',
                stderr=stderr or '',
                timed_out=True,
                killed=True,
                duration_seconds=duration
            )
            
    except FileNotFoundError:
        return CommandResult(
            returncode=127,
            stdout='',
            stderr=f"Command not found: {parse_command(cmd)[0]}",
            timed_out=False,
            killed=False,
            duration_seconds=time.time() - start_time
        )
    except Exception as e:
        return CommandResult(
            returncode=-1,
            stdout='',
            stderr=str(e),
            timed_out=False,
            killed=False,
            duration_seconds=time.time() - start_time
        )


@tool(
    name="localexec",
    description="Execute shell commands safely with timeout, sandboxing support, and output capture.",
    category="execution"
)
def localexec(
    cmd: str,
    timeout: int = DEFAULT_TIMEOUT,
    cwd: Optional[str] = None,
    sandbox: bool = False,
    env: Optional[str] = None,
    workspace: Optional[Path] = None,
    permissions=None
) -> ToolResult:
    """
    Execute a shell command.
    
    Features:
    - Timeout protection
    - Optional firejail sandboxing (Linux)
    - Output capture with truncation
    - Safe command detection
    
    Args:
        cmd: Command to execute
        timeout: Timeout in seconds (default: 600)
        cwd: Working directory (default: workspace)
        sandbox: If True, run in firejail sandbox (Linux only)
        env: Additional environment variables as "KEY=VALUE,KEY2=VALUE2"
        workspace: Working directory
        permissions: Permissions engine
    
    Returns:
        ToolResult with command output
    """
    try:
        # Validate command
        if not cmd.strip():
            return ToolResult.fail(
                error="Empty command",
                status=ToolStatus.VALIDATION_ERROR
            )
        
        # Check if command is safe
        if not is_safe_command(cmd):
            logger.warning(f"Potentially dangerous command: {cmd}")
            # We still allow it - permissions engine will handle blocking
        
        # Resolve working directory
        if cwd:
            work_dir = Path(cwd).resolve()
        elif workspace:
            work_dir = workspace
        else:
            work_dir = Path.cwd()
        
        if not work_dir.exists():
            return ToolResult.fail(
                error=f"Working directory not found: {work_dir}",
                status=ToolStatus.NOT_FOUND
            )
        
        # Parse environment variables
        env_dict = None
        if env:
            env_dict = {}
            for pair in env.split(','):
                if '=' in pair:
                    key, value = pair.split('=', 1)
                    env_dict[key.strip()] = value.strip()
        
        # Execute command
        result = run_command(
            cmd=cmd,
            cwd=work_dir,
            env=env_dict,
            timeout=timeout,
            sandbox=sandbox
        )
        
        # Build result
        if result.timed_out:
            return ToolResult.fail(
                error=f"Command timed out after {timeout} seconds",
                output=result.output,
                status=ToolStatus.TIMEOUT,
                duration_ms=result.duration_seconds * 1000
            )
        
        if result.success:
            return ToolResult.ok(
                output=result.output,
                returncode=result.returncode,
                duration_seconds=result.duration_seconds
            )
        else:
            return ToolResult.fail(
                error=f"Command failed with exit code {result.returncode}",
                output=result.output,
                status=ToolStatus.FAILURE,
                returncode=result.returncode,
                duration_ms=result.duration_seconds * 1000
            )
            
    except Exception as e:
        logger.exception(f"Error executing command: {cmd}")
        return ToolResult.fail(
            error=f"Execution error: {str(e)}",
            status=ToolStatus.FAILURE
        )


@tool(
    name="shell",
    description="Execute a simple shell command. Alias for localexec with sensible defaults.",
    category="execution"
)
def shell(
    cmd: str,
    workspace: Optional[Path] = None,
    permissions=None
) -> ToolResult:
    """
    Simple shell command execution.
    
    Args:
        cmd: Command to execute
        workspace: Working directory
        permissions: Permissions engine
    
    Returns:
        ToolResult with command output
    """
    return localexec(cmd, workspace=workspace, permissions=permissions)


@tool(
    name="run_tests",
    description="Run project tests using detected test framework.",
    category="execution"
)
def run_tests(
    path: str = ".",
    framework: Optional[str] = None,
    pattern: Optional[str] = None,
    verbose: bool = False,
    workspace: Optional[Path] = None,
    permissions=None
) -> ToolResult:
    """
    Run tests using the appropriate testing framework.
    
    Auto-detects test framework based on project files.
    
    Args:
        path: Path to test directory or file
        framework: Force specific framework (pytest, jest, cargo, go, etc.)
        pattern: Test name pattern to match
        verbose: Enable verbose output
        workspace: Working directory
        permissions: Permissions engine
    
    Returns:
        ToolResult with test output
    """
    work_dir = workspace or Path.cwd()
    
    # Check for Git Pager
    env_additions = "PAGER=cat,GIT_PAGER=cat"
    
    # Auto-detect framework if not specified
    if not framework:
        if (work_dir / "pytest.ini").exists() or (work_dir / "pyproject.toml").exists():
            framework = "pytest"
        elif (work_dir / "Cargo.toml").exists():
            framework = "cargo"
        elif (work_dir / "package.json").exists():
            framework = "npm"
        elif (work_dir / "go.mod").exists():
            framework = "go"
        elif (work_dir / "pom.xml").exists():
            framework = "maven"
        else:
            # Default to pytest for Python projects
            framework = "pytest"
    
    # Build command based on framework
    if framework == "pytest":
        cmd = f"python -m pytest {path}"
        if verbose:
            cmd += " -v"
        if pattern:
            cmd += f" -k '{pattern}'"
    
    elif framework == "cargo":
        cmd = f"cargo test"
        if pattern:
            cmd += f" -- {pattern}"
        if verbose:
            cmd += " -- --nocapture"
    
    elif framework == "npm" or framework == "jest":
        cmd = "npm test"
        if pattern:
            cmd += f" -- --testNamePattern='{pattern}'"
    
    elif framework == "go":
        cmd = f"go test {path}"
        if verbose:
            cmd += " -v"
        if pattern:
            cmd += f" -run '{pattern}'"
    
    elif framework == "maven":
        cmd = "mvn test"
        if pattern:
            cmd += f" -Dtest='{pattern}'"
    
    else:
        return ToolResult.fail(
            error=f"Unknown test framework: {framework}",
            status=ToolStatus.VALIDATION_ERROR
        )
    
    return localexec(
        cmd=cmd,
        timeout=300,  # 5 minute timeout for tests
        env=env_additions,
        workspace=workspace,
        permissions=permissions
    )