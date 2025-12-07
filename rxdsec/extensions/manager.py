"""
Advanced Extensions Manager for RxDsec CLI
===========================================
Local Protocol Extensions (LPE) system for custom tool registration.
"""

from __future__ import annotations

import json
import logging
import subprocess
import shlex
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Configure module logger
logger = logging.getLogger(__name__)


@dataclass
class Extension:
    """Definition of a Local Protocol Extension"""
    name: str
    command: List[str]
    description: str = ""
    version: str = "1.0.0"
    author: str = ""
    timeout: int = 300
    enabled: bool = True
    source: str = "local"  # "local" or "global"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    env: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "name": self.name,
            "command": self.command,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "timeout": self.timeout,
            "enabled": self.enabled,
            "source": self.source,
            "created_at": self.created_at,
            "env": self.env
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Extension":
        """Create from dictionary"""
        return cls(
            name=data.get("name", "unnamed"),
            command=data.get("command", []),
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            author=data.get("author", ""),
            timeout=data.get("timeout", 300),
            enabled=data.get("enabled", True),
            source=data.get("source", "local"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            env=data.get("env", {})
        )


class ExtensionManager:
    """
    Manage Local Protocol Extensions (LPE).
    
    Features:
    - Local and global extension storage
    - Dynamic tool registration
    - Version tracking
    - Enable/disable extensions
    """
    
    def __init__(self, workspace: Path):
        """
        Initialize the extension manager.
        
        Args:
            workspace: Workspace directory
        """
        self.workspace = workspace
        self.local_file = workspace / ".rxdsec" / "lpe.json"
        self.global_file = Path.home() / ".rxdsec" / "lpe.json"
        
        # Ensure files exist
        self._ensure_files()
    
    def _ensure_files(self):
        """Ensure extension files exist"""
        for file_path in [self.local_file, self.global_file]:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            if not file_path.exists():
                file_path.write_text(json.dumps({"extensions": {}, "version": "1.0.0"}, indent=2))
    
    def save(
        self,
        extension: Extension,
        local: bool = True,
        global_: bool = False
    ):
        """
        Save an extension.
        
        Args:
            extension: Extension to save
            local: Save to local storage
            global_: Save to global storage
        """
        if local:
            extension.source = "local"
            self._save_to_file(extension, self.local_file)
        
        if global_:
            extension.source = "global"
            self._save_to_file(extension, self.global_file)
        
        logger.info(f"Saved extension: {extension.name}")
    
    def _save_to_file(self, extension: Extension, file_path: Path):
        """Save extension to a specific file"""
        try:
            data = self._load_file(file_path)
            data["extensions"][extension.name] = extension.to_dict()
            
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save extension: {e}")
            raise
    
    def _load_file(self, file_path: Path) -> Dict[str, Any]:
        """Load extensions from a file"""
        try:
            if file_path.exists():
                with open(file_path) as f:
                    return json.load(f)
        except json.JSONDecodeError:
            pass
        return {"extensions": {}, "version": "1.0.0"}
    
    def load_all(self) -> Dict[str, Extension]:
        """
        Load all extensions from both local and global storage.
        
        Returns:
            Dictionary of extension name to Extension
        """
        extensions = {}
        
        # Load global first (local overrides)
        for file_path, source in [(self.global_file, "global"), (self.local_file, "local")]:
            data = self._load_file(file_path)
            
            for name, ext_data in data.get("extensions", {}).items():
                try:
                    ext_data["source"] = source
                    extensions[name] = Extension.from_dict(ext_data)
                except Exception as e:
                    logger.warning(f"Failed to load extension {name}: {e}")
        
        return extensions
    
    def get_extension(self, name: str) -> Optional[Extension]:
        """Get a specific extension by name"""
        extensions = self.load_all()
        return extensions.get(name)
    
    def remove(self, name: str, local: bool = True, global_: bool = False):
        """
        Remove an extension.
        
        Args:
            name: Extension name
            local: Remove from local storage
            global_: Remove from global storage
        """
        if local:
            self._remove_from_file(name, self.local_file)
        
        if global_:
            self._remove_from_file(name, self.global_file)
        
        logger.info(f"Removed extension: {name}")
    
    def _remove_from_file(self, name: str, file_path: Path):
        """Remove extension from a specific file"""
        try:
            data = self._load_file(file_path)
            
            if name in data.get("extensions", {}):
                del data["extensions"][name]
                
                with open(file_path, 'w') as f:
                    json.dump(data, f, indent=2)
                    
        except Exception as e:
            logger.error(f"Failed to remove extension: {e}")
    
    def enable(self, name: str, enabled: bool = True):
        """Enable or disable an extension"""
        ext = self.get_extension(name)
        if ext:
            ext.enabled = enabled
            self.save(ext, local=(ext.source == "local"), global_=(ext.source == "global"))
    
    def inject_tools(self, tool_registry):
        """
        Inject all enabled extensions as tools into a registry.
        
        Args:
            tool_registry: ToolRegistry instance
        """
        extensions = self.load_all()
        
        for name, ext in extensions.items():
            if not ext.enabled:
                continue
            
            # Create a dynamic tool function
            tool_func = self._create_tool_function(ext)
            
            # Register with the tool registry
            tool_registry.add_dynamic_tool(
                name=ext.name,
                command=ext.command,
                description=ext.description
            )
            
            logger.debug(f"Injected extension as tool: {name}")
    
    def _create_tool_function(self, ext: Extension) -> Callable:
        """Create a tool function for an extension"""
        def tool_func(**kwargs):
            try:
                cmd = ext.command.copy()
                
                # Add keyword arguments as command-line options
                for key, value in kwargs.items():
                    if key not in ('workspace', 'permissions'):
                        cmd.extend([f"--{key}", str(value)])
                
                # Prepare environment
                import os
                env = os.environ.copy()
                env.update(ext.env)
                
                # Execute
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=ext.timeout,
                    env=env,
                    cwd=str(self.workspace)
                )
                
                output = result.stdout + result.stderr
                success = result.returncode == 0
                
                # Return ToolResult-like object
                from ..tools.base import ToolResult
                if success:
                    return ToolResult.ok(output)
                else:
                    return ToolResult.fail(
                        error=f"Exit code: {result.returncode}",
                        output=output
                    )
                    
            except subprocess.TimeoutExpired:
                from ..tools.base import ToolResult, ToolStatus
                return ToolResult.fail(
                    error=f"Timeout after {ext.timeout}s",
                    status=ToolStatus.TIMEOUT
                )
            except Exception as e:
                from ..tools.base import ToolResult
                return ToolResult.fail(error=str(e))
        
        return tool_func
    
    def list_extensions(self, pretty: bool = False) -> str:
        """
        List all extensions.
        
        Args:
            pretty: If True, format for display
        
        Returns:
            Formatted string or JSON
        """
        extensions = self.load_all()
        
        if not extensions:
            return "No extensions installed"
        
        if pretty:
            lines = ["Installed Extensions:", "-" * 40]
            for name, ext in sorted(extensions.items()):
                status = "✓" if ext.enabled else "○"
                lines.append(f"  {status} {name} ({ext.source})")
                lines.append(f"      {ext.description or 'No description'}")
                lines.append(f"      Command: {' '.join(ext.command[:3])}...")
            return "\n".join(lines)
        else:
            return json.dumps({n: e.to_dict() for n, e in extensions.items()}, indent=2)
    
    def create_from_command(self, name: str, command: str, description: str = "") -> Extension:
        """
        Create an extension from a command string.
        
        Args:
            name: Extension name
            command: Command string (will be split)
            description: Optional description
        
        Returns:
            Created Extension
        """
        return Extension(
            name=name,
            command=shlex.split(command),
            description=description
        )


__all__ = ['ExtensionManager', 'Extension']