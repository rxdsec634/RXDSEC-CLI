"""
Advanced Tool Base Module for RxDsec CLI
=========================================
Production-ready tool registry with decorators, validation, and execution framework.
Supports dynamic tool registration, permission checking, and result handling.
"""

from __future__ import annotations

import inspect
import logging
import time
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from functools import wraps
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    List,
    NamedTuple,
    Optional,
    Protocol,
    Type,
    TypeVar,
    Union,
    runtime_checkable,
)

# Configure module logger
logger = logging.getLogger(__name__)


class ToolStatus(Enum):
    """Status codes for tool execution results"""
    SUCCESS = auto()
    FAILURE = auto()
    PERMISSION_DENIED = auto()
    TIMEOUT = auto()
    VALIDATION_ERROR = auto()
    NOT_FOUND = auto()


@dataclass(frozen=True)
class ToolResult:
    """
    Immutable result of a tool execution.
    
    Attributes:
        success: Whether the tool executed successfully
        output: The output from the tool (stdout, result data, etc.)
        error: Error message if execution failed
        status: Detailed status code for the result
        duration_ms: Execution time in milliseconds
        metadata: Additional metadata about the execution
    """
    success: bool
    output: str
    error: Optional[str] = None
    status: ToolStatus = ToolStatus.SUCCESS
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        # Validate status matches success flag
        if self.success and self.status not in (ToolStatus.SUCCESS,):
            object.__setattr__(self, 'status', ToolStatus.SUCCESS)
        elif not self.success and self.status == ToolStatus.SUCCESS:
            object.__setattr__(self, 'status', ToolStatus.FAILURE)
    
    @classmethod
    def ok(cls, output: str, duration_ms: float = 0.0, **metadata) -> "ToolResult":
        """Create a successful result"""
        return cls(
            success=True,
            output=output,
            error=None,
            status=ToolStatus.SUCCESS,
            duration_ms=duration_ms,
            metadata=metadata
        )
    
    @classmethod
    def fail(
        cls, 
        error: str, 
        output: str = "", 
        status: ToolStatus = ToolStatus.FAILURE,
        duration_ms: float = 0.0,
        **metadata
    ) -> "ToolResult":
        """Create a failed result"""
        return cls(
            success=False,
            output=output,
            error=error,
            status=status,
            duration_ms=duration_ms,
            metadata=metadata
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for serialization"""
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "status": self.status.name,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata
        }


@dataclass
class ToolParameter:
    """Describes a parameter for a tool"""
    name: str
    type_hint: Type
    description: str
    required: bool = True
    default: Any = None
    
    def validate(self, value: Any) -> tuple[bool, Optional[str]]:
        """Validate a value against this parameter spec"""
        if value is None and self.required and self.default is None:
            return False, f"Required parameter '{self.name}' is missing"
        
        if value is not None and not isinstance(value, self.type_hint):
            try:
                # Try type coercion for common types
                if self.type_hint == str:
                    value = str(value)
                elif self.type_hint == int:
                    value = int(value)
                elif self.type_hint == float:
                    value = float(value)
                elif self.type_hint == bool:
                    value = value.lower() in ('true', '1', 'yes') if isinstance(value, str) else bool(value)
            except (ValueError, TypeError):
                return False, f"Parameter '{self.name}' must be of type {self.type_hint.__name__}"
        
        return True, None


@dataclass
class ToolDefinition:
    """Complete definition of a tool"""
    name: str
    function: Callable[..., ToolResult]
    description: str
    parameters: List[ToolParameter] = field(default_factory=list)
    category: str = "general"
    requires_permission: bool = True
    timeout: int = 600  # Default 10 minute timeout
    
    def get_signature(self) -> str:
        """Get a human-readable signature for the tool"""
        params = ", ".join(
            f"{p.name}: {p.type_hint.__name__}" + 
            (f" = {p.default!r}" if not p.required else "")
            for p in self.parameters
        )
        return f"{self.name}({params})"
    
    def get_help(self) -> str:
        """Get full help text for the tool"""
        sig = self.get_signature()
        param_docs = "\n".join(
            f"  - {p.name} ({p.type_hint.__name__}): {p.description}"
            + (" [required]" if p.required else f" [default: {p.default!r}]")
            for p in self.parameters
        )
        return f"{sig}\n\n{self.description}\n\nParameters:\n{param_docs}"


# Global tool registry storage
_TOOL_REGISTRY: Dict[str, ToolDefinition] = {}


def tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    category: str = "general",
    requires_permission: bool = True,
    timeout: int = 600
) -> Callable:
    """
    Decorator to register a function as a tool.
    
    Usage:
        @tool(name="read", description="Read a file")
        def read_file(path: str, lines: Optional[str] = None) -> ToolResult:
            ...
    
    Or simple usage:
        @tool
        def my_tool(arg: str) -> ToolResult:
            ...
    
    Args:
        name: Tool name (defaults to function name)
        description: Tool description (defaults to docstring)
        category: Tool category for grouping
        requires_permission: Whether permission check is required
        timeout: Default timeout in seconds
    
    Returns:
        Decorated function registered as a tool
    """
    def decorator(fn: Callable) -> Callable:
        tool_name = name or fn.__name__
        tool_desc = description or fn.__doc__ or "No description available"
        
        # Extract parameters from function signature
        sig = inspect.signature(fn)
        params = []
        
        for param_name, param in sig.parameters.items():
            # Skip special parameters
            if param_name in ('workspace', 'permissions', 'self', 'cls'):
                continue
            
            # Skip *args and **kwargs
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue
            
            # Determine type hint
            type_hint = param.annotation if param.annotation != inspect.Parameter.empty else str
            if type_hint == inspect.Parameter.empty:
                type_hint = str
            
            # Handle Optional types
            origin = getattr(type_hint, '__origin__', None)
            if origin is Union:
                args = getattr(type_hint, '__args__', ())
                # Filter out NoneType for Optional
                non_none_args = [a for a in args if a is not type(None)]
                type_hint = non_none_args[0] if non_none_args else str
            
            # Determine if required
            required = param.default == inspect.Parameter.empty
            default = None if required else param.default
            
            params.append(ToolParameter(
                name=param_name,
                type_hint=type_hint if isinstance(type_hint, type) else str,
                description=f"Parameter: {param_name}",
                required=required,
                default=default
            ))
        
        # Create tool definition
        tool_def = ToolDefinition(
            name=tool_name,
            function=fn,
            description=tool_desc.strip(),
            parameters=params,
            category=category,
            requires_permission=requires_permission,
            timeout=timeout
        )
        
        # Register the tool
        _TOOL_REGISTRY[tool_name] = tool_def
        logger.debug(f"Registered tool: {tool_name}")
        
        @wraps(fn)
        def wrapper(*args, **kwargs) -> ToolResult:
            start_time = time.time()
            try:
                result = fn(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000
                
                # Ensure result is a ToolResult
                if isinstance(result, ToolResult):
                    return ToolResult(
                        success=result.success,
                        output=result.output,
                        error=result.error,
                        status=result.status,
                        duration_ms=duration_ms,
                        metadata=result.metadata
                    )
                elif isinstance(result, tuple):
                    # Legacy support for (success, output, error) tuples
                    return ToolResult(
                        success=result[0],
                        output=result[1],
                        error=result[2] if len(result) > 2 else None,
                        duration_ms=duration_ms
                    )
                else:
                    return ToolResult.ok(str(result), duration_ms=duration_ms)
                    
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                logger.exception(f"Tool {tool_name} failed with exception")
                return ToolResult.fail(
                    error=str(e),
                    output=traceback.format_exc(),
                    duration_ms=duration_ms
                )
        
        return wrapper
    
    # Handle @tool without parentheses
    if callable(name):
        fn = name
        name = None
        return decorator(fn)
    
    return decorator


@runtime_checkable
class PermissionsProtocol(Protocol):
    """Protocol for permissions engine"""
    def check(self, action: str, target: str) -> bool: ...
    def confirm(self, tool_call: Dict[str, Any]) -> bool: ...


class ToolRegistry:
    """
    Advanced registry for all available tools.
    
    Features:
    - Dynamic tool registration
    - Permission checking integration
    - Execution timing and logging
    - Tool discovery and description
    - Category-based organization
    """
    
    def __init__(
        self, 
        workspace: Optional[Path] = None, 
        permissions: Optional[PermissionsProtocol] = None
    ):
        """
        Initialize the tool registry.
        
        Args:
            workspace: Working directory for file operations
            permissions: Permissions engine for access control
        """
        self.workspace = workspace or Path.cwd()
        self.permissions = permissions
        self._execution_log: List[Dict[str, Any]] = []
        
        # Import all tools to register them
        self._load_builtin_tools()
        
        # Copy global registry
        self.tools: Dict[str, ToolDefinition] = _TOOL_REGISTRY.copy()
        
        logger.info(f"ToolRegistry initialized with {len(self.tools)} tools")
    
    def _load_builtin_tools(self):
        """Load all built-in tools by importing their modules"""
        try:
            from . import read, write, grep, localexec, web
            logger.debug("Built-in tools loaded successfully")
        except ImportError as e:
            logger.warning(f"Failed to load some built-in tools: {e}")
    
    def register(self, tool_def: ToolDefinition):
        """Register a new tool definition"""
        self.tools[tool_def.name] = tool_def
        logger.info(f"Registered tool: {tool_def.name}")
    
    def unregister(self, name: str) -> bool:
        """Unregister a tool by name"""
        if name in self.tools:
            del self.tools[name]
            logger.info(f"Unregistered tool: {name}")
            return True
        return False
    
    def get(self, name: str) -> Optional[ToolDefinition]:
        """Get a tool definition by name"""
        return self.tools.get(name)
    
    def execute(self, name: str, args: Dict[str, Any]) -> ToolResult:
        """
        Execute a tool by name with given arguments.
        
        Args:
            name: Name of the tool to execute
            args: Dictionary of arguments to pass to the tool
        
        Returns:
            ToolResult with execution outcome
        """
        start_time = time.time()
        
        # Check if tool exists
        if name not in self.tools:
            return ToolResult.fail(
                error=f"Tool not found: {name}",
                status=ToolStatus.NOT_FOUND
            )
        
        tool_def = self.tools[name]
        
        # Check permissions if required
        if tool_def.requires_permission and self.permissions:
            # Determine the resource being accessed
            resource = args.get('path', args.get('url', args.get('cmd', str(args))))
            
            if not self.permissions.check(name, resource):
                return ToolResult.fail(
                    error=f"Permission denied for {name} on {resource}",
                    status=ToolStatus.PERMISSION_DENIED
                )
        
        # Validate parameters
        for param in tool_def.parameters:
            value = args.get(param.name, param.default)
            valid, error = param.validate(value)
            if not valid:
                return ToolResult.fail(
                    error=error,
                    status=ToolStatus.VALIDATION_ERROR
                )
        
        try:
            # Inject workspace and permissions if the function accepts them
            sig = inspect.signature(tool_def.function)
            call_args = args.copy()
            
            if 'workspace' in sig.parameters:
                call_args['workspace'] = self.workspace
            if 'permissions' in sig.parameters:
                call_args['permissions'] = self.permissions
            
            # Execute the tool
            result = tool_def.function(**call_args)
            
            # Log execution
            duration_ms = (time.time() - start_time) * 1000
            self._log_execution(name, args, result, duration_ms)
            
            return result
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.exception(f"Tool {name} failed with exception")
            
            result = ToolResult.fail(
                error=str(e),
                output=traceback.format_exc(),
                duration_ms=duration_ms
            )
            self._log_execution(name, args, result, duration_ms)
            return result
    
    def _log_execution(
        self, 
        name: str, 
        args: Dict[str, Any], 
        result: ToolResult, 
        duration_ms: float
    ):
        """Log tool execution for debugging and auditing"""
        log_entry = {
            "tool": name,
            "args": {k: str(v)[:100] for k, v in args.items()},  # Truncate for logging
            "success": result.success,
            "duration_ms": duration_ms,
            "timestamp": time.time()
        }
        self._execution_log.append(log_entry)
        
        # Keep only last 100 entries
        if len(self._execution_log) > 100:
            self._execution_log = self._execution_log[-100:]
        
        logger.debug(f"Tool execution: {name} -> {'success' if result.success else 'failure'} ({duration_ms:.2f}ms)")
    
    def describe(self) -> str:
        """
        Get a formatted description of all available tools.
        
        Returns:
            Multi-line string describing all tools
        """
        descriptions = []
        
        # Group by category
        categories: Dict[str, List[ToolDefinition]] = {}
        for tool_def in self.tools.values():
            cat = tool_def.category
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(tool_def)
        
        for category, tools in sorted(categories.items()):
            descriptions.append(f"## {category.upper()}")
            for tool_def in sorted(tools, key=lambda t: t.name):
                sig = tool_def.get_signature()
                desc = tool_def.description.split('\n')[0]  # First line only
                descriptions.append(f"  {sig}\n    {desc}")
            descriptions.append("")
        
        return "\n".join(descriptions)
    
    def list_tools(self) -> List[str]:
        """List all available tool names"""
        return sorted(self.tools.keys())
    
    def get_tool_help(self, name: str) -> Optional[str]:
        """Get detailed help for a specific tool"""
        tool_def = self.tools.get(name)
        return tool_def.get_help() if tool_def else None
    
    def get_execution_log(self) -> List[Dict[str, Any]]:
        """Get recent tool execution log"""
        return self._execution_log.copy()
    
    def add_dynamic_tool(
        self,
        name: str,
        command: List[str],
        description: str = "Dynamic tool"
    ):
        """
        Add a dynamic tool that executes a shell command.
        
        Used by extensions/LPE system.
        
        Args:
            name: Name for the new tool
            command: Command list to execute
            description: Description of the tool
        """
        import subprocess
        
        def dynamic_tool_fn(**kwargs) -> ToolResult:
            try:
                cmd = command.copy()
                # Add any keyword arguments as command-line options
                for key, value in kwargs.items():
                    if key not in ('workspace', 'permissions'):
                        cmd.extend([f"--{key}", str(value)])
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=600
                )
                
                if result.returncode == 0:
                    return ToolResult.ok(result.stdout + result.stderr)
                else:
                    return ToolResult.fail(
                        error=f"Exit code: {result.returncode}",
                        output=result.stdout + result.stderr
                    )
            except subprocess.TimeoutExpired:
                return ToolResult.fail(error="Command timed out", status=ToolStatus.TIMEOUT)
            except Exception as e:
                return ToolResult.fail(error=str(e))
        
        tool_def = ToolDefinition(
            name=name,
            function=dynamic_tool_fn,
            description=description,
            parameters=[],
            category="dynamic",
            requires_permission=True
        )
        
        self.register(tool_def)


# Type alias for backward compatibility
TOOL_REGISTRY = _TOOL_REGISTRY