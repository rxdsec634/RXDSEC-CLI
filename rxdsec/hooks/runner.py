"""
Advanced Hooks Runner for RxDsec CLI
=====================================
Production-ready hook system for lifecycle events with YAML configuration,
multiple script formats, and comprehensive error handling.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

import yaml

# Configure module logger
logger = logging.getLogger(__name__)


class HookEvent(Enum):
    """Standard hook events"""
    # Quest lifecycle
    QUEST_START = "quest_start"
    QUEST_COMPLETE = "quest_complete"
    QUEST_ERROR = "quest_error"
    
    # Review lifecycle
    REVIEW_START = "review_start"
    REVIEW_COMPLETE = "review_complete"
    
    # Tool lifecycle
    TOOL_BEFORE = "tool_before"
    TOOL_AFTER = "tool_after"
    TOOL_ERROR = "tool_error"
    
    # Session lifecycle
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    
    # Memory events
    MEMORY_UPDATE = "memory_update"
    
    # Custom events
    CUSTOM = "custom"


@dataclass
class HookDefinition:
    """Definition of a hook"""
    name: str
    event: str
    script: str  # Script path or inline command
    script_type: str = "shell"  # shell, python, node, inline
    enabled: bool = True
    timeout: int = 30
    async_: bool = False  # Run asynchronously
    condition: Optional[str] = None  # Optional condition expression
    env: Dict[str, str] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HookDefinition":
        """Create from dictionary"""
        return cls(
            name=data.get("name", "unnamed"),
            event=data.get("event", "custom"),
            script=data.get("script", ""),
            script_type=data.get("type", "shell"),
            enabled=data.get("enabled", True),
            timeout=data.get("timeout", 30),
            async_=data.get("async", False),
            condition=data.get("condition"),
            env=data.get("env", {})
        )


@dataclass
class HookResult:
    """Result of hook execution"""
    hook_name: str
    success: bool
    output: str
    error: Optional[str] = None
    duration_ms: float = 0.0
    skipped: bool = False
    skip_reason: Optional[str] = None


class HookRunner:
    """
    Run hooks at specific lifecycle events.
    
    Features:
    - YAML-based hook configuration
    - Multiple script types (shell, python, node)
    - Async hook execution
    - Condition evaluation
    - Context passing via environment/JSON
    - Comprehensive error handling
    """
    
    # Default hooks configuration
    DEFAULT_HOOKS = {
        "hooks": [
            {
                "name": "notify_quest_complete",
                "event": "quest_complete",
                "script": "echo 'Quest completed: $TASK'",
                "type": "shell",
                "enabled": False,  # Disabled by default
                "comment": "Example: Desktop notification on quest complete"
            }
        ]
    }
    
    def __init__(self, workspace: Path):
        """
        Initialize the hook runner.
        
        Args:
            workspace: Workspace directory
        """
        self.workspace = workspace
        self.hooks_file = workspace / ".rxdsec" / "hooks.yaml"
        self.hooks_dir = workspace / ".rxdsec" / "hooks"
        
        # Registered Python hooks (in-memory)
        self._python_hooks: Dict[str, List[Callable]] = {}
        
        # Execution log
        self._execution_log: List[HookResult] = []
        
        # Ensure directories exist
        self._ensure_setup()
    
    def _ensure_setup(self):
        """Ensure hook directories and files exist"""
        self.hooks_dir.mkdir(parents=True, exist_ok=True)
        
        if not self.hooks_file.exists():
            # Create default hooks file
            with open(self.hooks_file, 'w') as f:
                yaml.dump(self.DEFAULT_HOOKS, f, default_flow_style=False)
    
    def load_hooks(self) -> List[HookDefinition]:
        """
        Load hooks from configuration file.
        
        Returns:
            List of HookDefinition objects
        """
        hooks = []
        
        if self.hooks_file.exists():
            try:
                with open(self.hooks_file) as f:
                    data = yaml.safe_load(f) or {}
                
                for hook_data in data.get("hooks", []):
                    try:
                        hooks.append(HookDefinition.from_dict(hook_data))
                    except Exception as e:
                        logger.warning(f"Invalid hook definition: {e}")
                        
            except Exception as e:
                logger.error(f"Failed to load hooks file: {e}")
        
        return hooks
    
    def run(self, event: Union[str, HookEvent], context: Optional[Dict[str, Any]] = None):
        """
        Run all hooks for a given event.
        
        Args:
            event: Event name or HookEvent enum
            context: Context data to pass to hooks
        """
        if isinstance(event, HookEvent):
            event_name = event.value
        else:
            event_name = event
        
        context = context or {}
        
        # Load hooks for this event
        all_hooks = self.load_hooks()
        event_hooks = [h for h in all_hooks if h.event == event_name and h.enabled]
        
        # Also check for Python callbacks
        python_callbacks = self._python_hooks.get(event_name, [])
        
        logger.debug(f"Running {len(event_hooks)} file hooks and {len(python_callbacks)} Python hooks for event: {event_name}")
        
        # Run file-based hooks
        for hook in event_hooks:
            result = self._execute_hook(hook, context)
            self._execution_log.append(result)
            
            if not result.success and not result.skipped:
                logger.warning(f"Hook {hook.name} failed: {result.error}")
        
        # Run Python callbacks
        for callback in python_callbacks:
            try:
                callback(context)
            except Exception as e:
                logger.warning(f"Python hook callback failed: {e}")
    
    def _execute_hook(self, hook: HookDefinition, context: Dict[str, Any]) -> HookResult:
        """
        Execute a single hook.
        
        Args:
            hook: Hook definition
            context: Context data
        
        Returns:
            HookResult with execution outcome
        """
        import time
        start_time = time.time()
        
        # Check condition if specified
        if hook.condition:
            try:
                if not self._evaluate_condition(hook.condition, context):
                    return HookResult(
                        hook_name=hook.name,
                        success=True,
                        output="",
                        skipped=True,
                        skip_reason=f"Condition not met: {hook.condition}"
                    )
            except Exception as e:
                return HookResult(
                    hook_name=hook.name,
                    success=False,
                    output="",
                    error=f"Condition evaluation failed: {e}"
                )
        
        # Build environment
        env = os.environ.copy()
        env.update(hook.env)
        
        # Add context to environment
        for key, value in context.items():
            env_key = key.upper()
            if isinstance(value, (dict, list)):
                env[env_key] = json.dumps(value)
            else:
                env[env_key] = str(value)
        
        # Write context to temp file for complex data
        context_file = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(context, f, default=str)
                context_file = f.name
                env['RXDSEC_CONTEXT_FILE'] = context_file
        except Exception as e:
            logger.warning(f"Failed to create context file: {e}")
        
        try:
            # Execute based on script type
            if hook.script_type == "shell":
                result = self._run_shell(hook.script, env, hook.timeout)
            elif hook.script_type == "python":
                result = self._run_python(hook.script, env, hook.timeout)
            elif hook.script_type == "node":
                result = self._run_node(hook.script, env, hook.timeout)
            elif hook.script_type == "inline":
                result = self._run_inline(hook.script, env, hook.timeout)
            else:
                return HookResult(
                    hook_name=hook.name,
                    success=False,
                    output="",
                    error=f"Unknown script type: {hook.script_type}"
                )
            
            duration_ms = (time.time() - start_time) * 1000
            
            return HookResult(
                hook_name=hook.name,
                success=result[0],
                output=result[1],
                error=result[2] if not result[0] else None,
                duration_ms=duration_ms
            )
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HookResult(
                hook_name=hook.name,
                success=False,
                output="",
                error=str(e),
                duration_ms=duration_ms
            )
        finally:
            # Cleanup context file
            if context_file and Path(context_file).exists():
                try:
                    Path(context_file).unlink()
                except:
                    pass
    
    def _run_shell(self, script: str, env: Dict, timeout: int) -> tuple:
        """Run a shell script"""
        try:
            # Check if script is a file path
            script_path = self.hooks_dir / script
            if script_path.exists():
                cmd = str(script_path)
            else:
                # Inline command
                cmd = script
            
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                cwd=str(self.workspace)
            )
            
            output = result.stdout + result.stderr
            success = result.returncode == 0
            
            return (success, output, None if success else f"Exit code: {result.returncode}")
            
        except subprocess.TimeoutExpired:
            return (False, "", f"Timeout after {timeout}s")
        except Exception as e:
            return (False, "", str(e))
    
    def _run_python(self, script: str, env: Dict, timeout: int) -> tuple:
        """Run a Python script"""
        script_path = self.hooks_dir / script
        
        if script_path.exists():
            cmd = ["python", str(script_path)]
        else:
            # Inline Python code
            cmd = ["python", "-c", script]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                cwd=str(self.workspace)
            )
            
            output = result.stdout + result.stderr
            success = result.returncode == 0
            
            return (success, output, None if success else f"Exit code: {result.returncode}")
            
        except subprocess.TimeoutExpired:
            return (False, "", f"Timeout after {timeout}s")
        except Exception as e:
            return (False, "", str(e))
    
    def _run_node(self, script: str, env: Dict, timeout: int) -> tuple:
        """Run a Node.js script"""
        script_path = self.hooks_dir / script
        
        if script_path.exists():
            cmd = ["node", str(script_path)]
        else:
            cmd = ["node", "-e", script]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                cwd=str(self.workspace)
            )
            
            output = result.stdout + result.stderr
            success = result.returncode == 0
            
            return (success, output, None if success else f"Exit code: {result.returncode}")
            
        except subprocess.TimeoutExpired:
            return (False, "", f"Timeout after {timeout}s")
        except FileNotFoundError:
            return (False, "", "Node.js not found")
        except Exception as e:
            return (False, "", str(e))
    
    def _run_inline(self, script: str, env: Dict, timeout: int) -> tuple:
        """Run an inline shell command"""
        return self._run_shell(script, env, timeout)
    
    def _evaluate_condition(self, condition: str, context: Dict) -> bool:
        """
        Evaluate a condition expression.
        
        Simple evaluation supporting:
        - context.key == "value"
        - context.key != "value"
        - context.key (truthy check)
        """
        # Very basic condition evaluation
        # In production, use a proper expression parser
        
        if "==" in condition:
            parts = condition.split("==", 1)
            left = self._resolve_value(parts[0].strip(), context)
            right = parts[1].strip().strip('"\'')
            return str(left) == right
        
        if "!=" in condition:
            parts = condition.split("!=", 1)
            left = self._resolve_value(parts[0].strip(), context)
            right = parts[1].strip().strip('"\'')
            return str(left) != right
        
        # Truthy check
        value = self._resolve_value(condition.strip(), context)
        return bool(value)
    
    def _resolve_value(self, expr: str, context: Dict) -> Any:
        """Resolve a value expression from context"""
        if expr.startswith("context."):
            key = expr[8:]
            return context.get(key)
        return expr
    
    def register(self, event: Union[str, HookEvent], callback: Callable):
        """
        Register a Python callback for an event.
        
        Args:
            event: Event to hook into
            callback: Callback function that receives context dict
        """
        if isinstance(event, HookEvent):
            event_name = event.value
        else:
            event_name = event
        
        if event_name not in self._python_hooks:
            self._python_hooks[event_name] = []
        
        self._python_hooks[event_name].append(callback)
    
    def unregister(self, event: Union[str, HookEvent], callback: Callable):
        """Unregister a Python callback"""
        if isinstance(event, HookEvent):
            event_name = event.value
        else:
            event_name = event
        
        if event_name in self._python_hooks:
            self._python_hooks[event_name] = [
                cb for cb in self._python_hooks[event_name] if cb != callback
            ]
    
    def get_execution_log(self) -> List[HookResult]:
        """Get recent hook execution log"""
        return self._execution_log.copy()


__all__ = ['HookRunner', 'HookEvent', 'HookDefinition', 'HookResult']