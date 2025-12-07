"""
Advanced Memory Manager for RxDsec CLI
=======================================
Persistent project memory with YAML storage, compaction, and context building.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# Configure module logger
logger = logging.getLogger(__name__)

# Default memory file name
MEMORY_FILE = "AGENTS.yaml"

# Maximum memory size before compaction (characters)
MAX_MEMORY_SIZE = 25000

# Maximum notes to keep before oldest are removed
MAX_NOTES = 50

# Maximum standards to keep
MAX_STANDARDS = 20

# Maximum files to track
MAX_TRACKED_FILES = 25


class MemoryManager:
    """
    Manage persistent project memory stored in AGENTS.yaml.
    
    Features:
    - Local and global memory storage
    - Notes, standards, and architecture tracking
    - Automatic compaction when size limit exceeded
    - Context formatting for prompts
    """
    
    DEFAULT_MEMORY = {
        "version": "1.0.0",
        "project": {
            "name": "",
            "description": "",
            "type": ""
        },
        "notes": [],
        "standards": [],
        "architecture": {
            "overview": "",
            "components": [],
            "patterns": []
        },
        "files": {},
        "last_updated": ""
    }
    
    def __init__(self, workspace: Path):
        """
        Initialize the memory manager.
        
        Args:
            workspace: Workspace directory
        """
        self.workspace = workspace
        self.local_file = workspace / MEMORY_FILE
        self.global_file = Path.home() / ".rxdsec" / MEMORY_FILE
        
        # Ensure files exist
        self._ensure_files_exist()
    
    def _ensure_files_exist(self):
        """Create memory files if they don't exist"""
        for file_path in [self.local_file, self.global_file]:
            if not file_path.exists():
                file_path.parent.mkdir(parents=True, exist_ok=True)
                self._save(self.DEFAULT_MEMORY.copy(), file_path)
    
    def _save(self, data: Dict, file_path: Path):
        """Save memory to file"""
        data["last_updated"] = datetime.now().isoformat()
        
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    
    def _load(self, file_path: Path) -> Dict:
        """Load memory from file"""
        try:
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    return data if data else self.DEFAULT_MEMORY.copy()
        except Exception as e:
            logger.warning(f"Failed to load memory from {file_path}: {e}")
        
        return self.DEFAULT_MEMORY.copy()
    
    def load(self, include_global: bool = True) -> Dict:
        """
        Load and merge memory from local and global files.
        
        Args:
            include_global: Whether to include global memory
        
        Returns:
            Merged memory dictionary
        """
        local_memory = self._load(self.local_file)
        
        if include_global:
            global_memory = self._load(self.global_file)
            
            # Merge: local takes precedence, but combine lists
            merged = local_memory.copy()
            
            # Merge notes (local first)
            local_notes = local_memory.get("notes", [])
            global_notes = global_memory.get("notes", [])
            merged["notes"] = local_notes + [n for n in global_notes if n not in local_notes]
            
            # Merge standards
            local_standards = local_memory.get("standards", [])
            global_standards = global_memory.get("standards", [])
            merged["standards"] = local_standards + [s for s in global_standards if s not in local_standards]
            
            return merged
        
        return local_memory
    
    def save(self, data: Dict, local: bool = True, global_: bool = False):
        """
        Save memory to file(s).
        
        Args:
            data: Memory data to save
            local: Save to local file
            global_: Save to global file
        """
        if local:
            self._save(data, self.local_file)
        
        if global_:
            self._save(data, self.global_file)
    
    def append_note(self, note: str, local: bool = True):
        """
        Add a note to project memory.
        
        Args:
            note: Note to add
            local: Add to local memory
        """
        file_path = self.local_file if local else self.global_file
        data = self._load(file_path)
        
        # Create note entry
        note_entry = {
            "content": note,
            "timestamp": datetime.now().isoformat()
        }
        
        if "notes" not in data:
            data["notes"] = []
        
        data["notes"].append(note_entry)
        
        # Trim if too many notes
        if len(data["notes"]) > MAX_NOTES:
            data["notes"] = data["notes"][-MAX_NOTES:]
        
        self._save(data, file_path)
        logger.debug(f"Added note to {'local' if local else 'global'} memory")
    
    def add_standard(self, standard: str, local: bool = True):
        """
        Add a coding standard.
        
        Args:
            standard: Standard to add
            local: Add to local memory
        """
        file_path = self.local_file if local else self.global_file
        data = self._load(file_path)
        
        if "standards" not in data:
            data["standards"] = []
        
        if standard not in data["standards"]:
            data["standards"].append(standard)
            self._save(data, file_path)
    
    def get_standards(self) -> List[str]:
        """Get all coding standards"""
        data = self.load()
        return data.get("standards", [])
    
    def update_architecture(
        self,
        overview: Optional[str] = None,
        components: Optional[List[str]] = None,
        patterns: Optional[List[str]] = None
    ):
        """
        Update project architecture information.
        
        Args:
            overview: Architecture overview
            components: List of components
            patterns: Design patterns used
        """
        data = self._load(self.local_file)
        
        if "architecture" not in data:
            data["architecture"] = {}
        
        if overview:
            data["architecture"]["overview"] = overview
        
        if components:
            data["architecture"]["components"] = components
        
        if patterns:
            data["architecture"]["patterns"] = patterns
        
        self._save(data, self.local_file)
    
    def update_project(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        project_type: Optional[str] = None
    ):
        """
        Update project metadata.
        
        Args:
            name: Project name
            description: Project description
            project_type: Project type (e.g., "python", "nodejs")
        """
        data = self._load(self.local_file)
        
        if "project" not in data:
            data["project"] = {}
        
        if name:
            data["project"]["name"] = name
        if description:
            data["project"]["description"] = description
        if project_type:
            data["project"]["type"] = project_type
        
        self._save(data, self.local_file)
    
    def track_file(self, path: str, summary: str):
        """
        Track information about a file.
        
        Args:
            path: File path
            summary: Brief summary of the file's purpose
        """
        data = self._load(self.local_file)
        
        if "files" not in data:
            data["files"] = {}
        
        data["files"][path] = {
            "summary": summary,
            "updated": datetime.now().isoformat()
        }
        
        # Limit tracked files
        if len(data["files"]) > 50:
            # Remove oldest entries
            sorted_files = sorted(
                data["files"].items(),
                key=lambda x: x[1].get("updated", ""),
                reverse=True
            )
            data["files"] = dict(sorted_files[:50])
        
        self._save(data, self.local_file)
    
    def compact_if_needed(self, llm=None) -> bool:
        """
        Compact memory if it exceeds size limit.

        Args:
            llm: Optional LLM for intelligent compaction

        Returns:
            True if compaction was performed
        """
        data = self._load(self.local_file)
        content = yaml.dump(data)

        if len(content) <= MAX_MEMORY_SIZE:
            return False

        logger.info(f"Memory size ({len(content)}) exceeds limit ({MAX_MEMORY_SIZE}), compacting...")

        # Compact notes: keep only the most recent ones
        if "notes" in data and len(data["notes"]) > MAX_NOTES:
            data["notes"] = data["notes"][-MAX_NOTES:]

        # Compact standards: keep only the most recent ones
        if "standards" in data and len(data["standards"]) > MAX_STANDARDS:
            data["standards"] = data["standards"][-MAX_STANDARDS:]

        # Compact tracked files: keep only the most recently updated
        if "files" in data and len(data["files"]) > MAX_TRACKED_FILES:
            sorted_files = sorted(
                data["files"].items(),
                key=lambda x: x[1].get("updated", ""),
                reverse=True
            )
            data["files"] = dict(sorted_files[:MAX_TRACKED_FILES])

        # Also truncate long individual entries
        if "notes" in data:
            for i, note in enumerate(data["notes"]):
                if isinstance(note, dict) and "content" in note:
                    if len(note["content"]) > 1000:  # Truncate long notes
                        note["content"] = note["content"][:1000] + "... (truncated)"
                elif isinstance(note, str) and len(note) > 1000:
                    data["notes"][i] = note[:1000] + "... (truncated)"

        self._save(data, self.local_file)

        new_size = len(yaml.dump(data))
        logger.info(f"Memory compacted: {len(content)} -> {new_size} characters")

        return True
    
    def get_context(self) -> str:
        """
        Get formatted memory context for system prompt.
        
        Returns:
            Formatted context string
        """
        data = self.load()
        context_parts = []
        
        # Project info
        project = data.get("project", {})
        if project.get("name"):
            context_parts.append(f"Project: {project['name']}")
            if project.get("description"):
                context_parts.append(f"Description: {project['description']}")
            if project.get("type"):
                context_parts.append(f"Type: {project['type']}")
        
        # Architecture
        arch = data.get("architecture", {})
        if arch.get("overview"):
            context_parts.append(f"\nArchitecture: {arch['overview']}")
        
        if arch.get("components"):
            context_parts.append("Components: " + ", ".join(arch["components"][:10]))
        
        # Standards
        standards = data.get("standards", [])
        if standards:
            context_parts.append("\nCoding Standards:")
            for std in standards[:5]:
                context_parts.append(f"  - {std}")
        
        # Recent notes
        notes = data.get("notes", [])
        if notes:
            context_parts.append("\nRecent Notes:")
            for note in notes[-5:]:
                content = note.get("content", note) if isinstance(note, dict) else note
                context_parts.append(f"  - {content[:100]}")
        
        # Tracked files
        files = data.get("files", {})
        if files:
            context_parts.append("\nKey Files:")
            for path, info in list(files.items())[:10]:
                summary = info.get("summary", "") if isinstance(info, dict) else info
                context_parts.append(f"  - {path}: {summary[:50]}")
        
        return "\n".join(context_parts) if context_parts else "No project memory loaded."
    
    def clear(self, local: bool = True, global_: bool = False):
        """
        Clear memory.
        
        Args:
            local: Clear local memory
            global_: Clear global memory
        """
        if local:
            self._save(self.DEFAULT_MEMORY.copy(), self.local_file)
        if global_:
            self._save(self.DEFAULT_MEMORY.copy(), self.global_file)


__all__ = ['MemoryManager', 'MEMORY_FILE', 'MAX_MEMORY_SIZE']