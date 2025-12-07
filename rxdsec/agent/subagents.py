"""
Advanced Sub-Agent Loader for RxDsec CLI
=========================================
Load and manage specialized sub-agents with hot-reloading.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileModifiedEvent
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False
    Observer = None
    FileSystemEventHandler = object
    FileModifiedEvent = object

# Configure module logger
logger = logging.getLogger(__name__)

# Default agents directory
AGENTS_DIR = "agents"


class AgentDefinition:
    """Definition of a sub-agent"""
    
    def __init__(
        self,
        name: str,
        description: str = "",
        system: str = "",
        tools: List[str] = None,
        keywords: List[str] = None,
        source: str = "local"
    ):
        self.name = name
        self.description = description
        self.system = system
        self.tools = tools or []
        self.keywords = keywords or []
        self.source = source
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "system": self.system,
            "tools": self.tools,
            "keywords": self.keywords,
            "source": self.source
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], source: str = "local") -> "AgentDefinition":
        return cls(
            name=data.get("name", "unnamed"),
            description=data.get("description", ""),
            system=data.get("system", data.get("system_prompt", "")),
            tools=data.get("tools", []),
            keywords=data.get("keywords", []),
            source=source
        )


class AgentFileHandler(FileSystemEventHandler if HAS_WATCHDOG else object):
    """File handler for hot-reloading agents"""
    
    def __init__(self, loader: "SubAgentLoader"):
        self.loader = loader
    
    def on_modified(self, event):
        if hasattr(event, 'src_path') and event.src_path.endswith(('.yaml', '.yml')):
            logger.info(f"Agent file changed: {event.src_path}")
            self.loader.reload()


class SubAgentLoader:
    """
    Load and manage specialized sub-agents.
    
    Features:
    - YAML-based agent definitions
    - Local and global agent directories
    - Hot-reloading with watchdog
    - Keyword-based agent resolution
    """
    
    DEFAULT_AGENTS = [
        {
            "name": "coder",
            "description": "Expert code writer and refactorer",
            "system": "You are an expert programmer. Focus on writing clean, efficient, well-documented code. Always follow best practices and coding standards.",
            "keywords": ["code", "program", "function", "class", "implement", "write"]
        },
        {
            "name": "reviewer",
            "description": "Code review specialist",
            "system": "You are a thorough code reviewer. Focus on finding bugs, security issues, and suggesting improvements. Be constructive and specific.",
            "keywords": ["review", "check", "audit", "analyze", "inspect"]
        },
        {
            "name": "debugger",
            "description": "Bug hunting expert",
            "system": "You are an expert debugger. Systematically analyze errors, trace issues, and propose fixes. Explain your reasoning clearly.",
            "keywords": ["debug", "fix", "error", "bug", "issue", "crash", "exception"]
        },
        {
            "name": "architect",
            "description": "System design specialist",
            "system": "You are a software architect. Focus on high-level design, patterns, scalability, and maintainability. Think long-term.",
            "keywords": ["design", "architect", "structure", "pattern", "scalable"]
        },
        {
            "name": "documenter",
            "description": "Documentation writer",
            "system": "You are a technical writer. Create clear, comprehensive documentation. Focus on examples and clarity.",
            "keywords": ["document", "docs", "readme", "explain", "describe", "api"]
        }
    ]
    
    def __init__(self, workspace: Path):
        """
        Initialize the sub-agent loader.
        
        Args:
            workspace: Workspace directory
        """
        self.workspace = workspace
        self.local_dir = workspace / AGENTS_DIR
        self.global_dir = Path.home() / ".rxdsec" / AGENTS_DIR
        
        # Agent registry
        self.registry: Dict[str, AgentDefinition] = {}
        
        # File observer for hot-reloading
        self._observer: Optional[Observer] = None
        
        # Initialize
        self._ensure_directories()
        self._load_default_agents()
        self.reload()
    
    def _ensure_directories(self):
        """Ensure agent directories exist"""
        self.local_dir.mkdir(parents=True, exist_ok=True)
        self.global_dir.mkdir(parents=True, exist_ok=True)
        
        # Create example agent file if directory is empty
        example_file = self.local_dir / "example.yaml"
        if not any(self.local_dir.glob("*.yaml")) and not example_file.exists():
            self._create_example_agent(example_file)
    
    def _create_example_agent(self, file_path: Path):
        """Create an example agent file"""
        example = {
            "name": "example",
            "description": "Example custom agent",
            "system": "You are a helpful assistant specialized in [your domain].",
            "keywords": ["example", "demo"],
            "tools": ["read", "write", "grep"]
        }
        
        with open(file_path, 'w') as f:
            yaml.dump(example, f, default_flow_style=False)
        
        logger.debug(f"Created example agent: {file_path}")
    
    def _load_default_agents(self):
        """Load built-in default agents"""
        for agent_data in self.DEFAULT_AGENTS:
            agent = AgentDefinition.from_dict(agent_data, source="builtin")
            self.registry[agent.name] = agent
    
    def reload(self):
        """Reload all agents from files"""
        # Keep default agents
        self.registry = {
            k: v for k, v in self.registry.items() 
            if v.source == "builtin"
        }
        
        # Load from directories
        for directory, source in [(self.global_dir, "global"), (self.local_dir, "local")]:
            self._load_from_directory(directory, source)
        
        logger.info(f"Loaded {len(self.registry)} sub-agents")
    
    def _load_from_directory(self, directory: Path, source: str):
        """Load agents from a directory"""
        for file_path in directory.glob("*.yaml"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                
                if data:
                    # Handle single agent or list of agents
                    if isinstance(data, list):
                        for agent_data in data:
                            agent = AgentDefinition.from_dict(agent_data, source)
                            self.registry[agent.name] = agent
                    else:
                        agent = AgentDefinition.from_dict(data, source)
                        self.registry[agent.name] = agent
                    
                    logger.debug(f"Loaded agent from: {file_path}")
                    
            except Exception as e:
                logger.warning(f"Failed to load agent from {file_path}: {e}")
    
    def start_watching(self):
        """Start watching for file changes"""
        if not HAS_WATCHDOG:
            logger.warning("watchdog not installed, hot-reloading disabled")
            return
        
        if self._observer:
            return
        
        handler = AgentFileHandler(self)
        self._observer = Observer()
        
        for directory in [self.local_dir, self.global_dir]:
            if directory.exists():
                self._observer.schedule(handler, str(directory), recursive=False)
        
        self._observer.start()
        logger.info("Started watching agent directories for changes")
    
    def stop_watching(self):
        """Stop watching for file changes"""
        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._observer = None
    
    def resolve(self, name_or_keyword: str) -> Optional[Dict[str, Any]]:
        """
        Resolve an agent by name or keyword.
        
        Args:
            name_or_keyword: Agent name or keyword to match
        
        Returns:
            Agent definition dictionary or None
        """
        # Exact name match
        if name_or_keyword in self.registry:
            return self.registry[name_or_keyword].to_dict()
        
        # Keyword match
        name_lower = name_or_keyword.lower()
        
        for agent in self.registry.values():
            if name_lower in [k.lower() for k in agent.keywords]:
                return agent.to_dict()
            
            if name_lower in agent.description.lower():
                return agent.to_dict()
        
        return None
    
    def list_agents(self) -> List[Dict[str, Any]]:
        """
        List all available agents.
        
        Returns:
            List of agent info dictionaries
        """
        return [
            {
                "name": agent.name,
                "description": agent.description,
                "keywords": agent.keywords,
                "source": agent.source
            }
            for agent in sorted(self.registry.values(), key=lambda a: a.name)
        ]
    
    def get_agent(self, name: str) -> Optional[AgentDefinition]:
        """Get an agent by name"""
        return self.registry.get(name)
    
    def add_agent(
        self,
        name: str,
        description: str,
        system: str,
        keywords: List[str] = None,
        tools: List[str] = None,
        local: bool = True
    ) -> AgentDefinition:
        """
        Add a new agent.
        
        Args:
            name: Agent name
            description: Agent description
            system: System prompt
            keywords: Keywords for matching
            tools: Allowed tools
            local: Save to local directory
        
        Returns:
            Created AgentDefinition
        """
        agent = AgentDefinition(
            name=name,
            description=description,
            system=system,
            keywords=keywords or [],
            tools=tools or [],
            source="local" if local else "global"
        )
        
        # Save to file
        directory = self.local_dir if local else self.global_dir
        file_path = directory / f"{name}.yaml"
        
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(agent.to_dict(), f, default_flow_style=False)
        
        # Add to registry
        self.registry[name] = agent
        
        logger.info(f"Added agent: {name}")
        return agent
    
    def remove_agent(self, name: str) -> bool:
        """
        Remove an agent.
        
        Args:
            name: Agent name
        
        Returns:
            True if removed
        """
        if name not in self.registry:
            return False
        
        agent = self.registry[name]
        
        if agent.source == "builtin":
            logger.warning(f"Cannot remove builtin agent: {name}")
            return False
        
        # Remove file
        for directory in [self.local_dir, self.global_dir]:
            file_path = directory / f"{name}.yaml"
            if file_path.exists():
                file_path.unlink()
        
        # Remove from registry
        del self.registry[name]
        
        logger.info(f"Removed agent: {name}")
        return True


__all__ = ['SubAgentLoader', 'AgentDefinition', 'AgentFileHandler', 'AGENTS_DIR']