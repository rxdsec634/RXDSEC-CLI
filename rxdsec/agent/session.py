"""
Advanced Session Manager for RxDsec CLI
========================================
Conversation management with context pruning, serialization, and quest tracking.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Configure module logger
logger = logging.getLogger(__name__)

# Default session directory
SESSIONS_DIR = ".rxdsec/sessions"

# Maximum messages to keep in context
MAX_CONTEXT_MESSAGES = 30

# Maximum token budget for context (reduced from 6000 to prevent exceeding model limits)
MAX_CONTEXT_TOKENS = 4000


class SessionManager:
    """
    Manage agent conversation sessions.
    
    Features:
    - Message history tracking
    - Context pruning to fit token limits
    - Session persistence
    - Quest lifecycle management
    """
    
    def __init__(self, workspace: Path):
        """
        Initialize the session manager.
        
        Args:
            workspace: Workspace directory
        """
        self.workspace = workspace
        self.sessions_dir = workspace / SESSIONS_DIR
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        
        # Current session state
        self.messages: List[Dict[str, str]] = []
        self.quest_id: Optional[str] = None
        self.quest_task: Optional[str] = None
        self.quest_start: Optional[datetime] = None
        self.session_id: str = str(uuid.uuid4())[:8]
        self.created_at: datetime = datetime.now()
    
    def add_user(self, content: str):
        """Add a user message to the session"""
        self.messages.append({
            "role": "user",
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        logger.debug(f"Added user message ({len(content)} chars)")
    
    def add_assistant(self, content: str):
        """Add an assistant message to the session"""
        self.messages.append({
            "role": "assistant",
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        logger.debug(f"Added assistant message ({len(content)} chars)")
    
    def add_tool_result(self, tool_name: str, success: bool, output: str):
        """Add a tool execution result to the session"""
        status = "success" if success else "error"
        content = f"[Tool: {tool_name}] ({status})\n{output}"
        
        self.messages.append({
            "role": "tool",
            "content": content,
            "tool_name": tool_name,
            "success": success,
            "timestamp": datetime.now().isoformat()
        })
        logger.debug(f"Added tool result: {tool_name} ({status})")
    
    def add_system(self, content: str):
        """Add a system message (not persisted but used in context)"""
        # System messages are handled separately in generate()
        # This is for adding context-specific system notes
        self.messages.append({
            "role": "system",
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
    
    def start_quest(self, task: str) -> str:
        """
        Start a new quest.
        
        Args:
            task: Quest task description
        
        Returns:
            Quest ID
        """
        self.quest_id = str(uuid.uuid4())[:8]
        self.quest_task = task
        self.quest_start = datetime.now()
        
        logger.info(f"Started quest {self.quest_id}: {task[:50]}...")
        
        return self.quest_id
    
    def end_quest(self, success: bool = True):
        """End the current quest"""
        if self.quest_id:
            duration = None
            if self.quest_start:
                duration = (datetime.now() - self.quest_start).total_seconds()
            
            logger.info(f"Quest {self.quest_id} ended: {'success' if success else 'failed'} ({duration:.1f}s)")
        
        self.quest_id = None
        self.quest_task = None
        self.quest_start = None
    
    def prune_context(self, max_tokens: int = MAX_CONTEXT_TOKENS):
        """
        Prune context to fit within token limit.

        Uses a simple character-based estimation (4 chars ≈ 1 token) with better strategy.

        Args:
            max_tokens: Maximum token budget
        """
        # Estimate current size
        current_tokens = self.estimate_tokens()

        if current_tokens <= max_tokens:
            return

        logger.debug(f"Pruning context: {current_tokens} tokens -> {max_tokens}")

        # Keep system messages and recent messages, remove oldest first
        system_messages = [m for m in self.messages if m.get("role") == "system"]
        user_assistant_messages = [m for m in self.messages if m.get("role") in ("user", "assistant")]
        tool_messages = [m for m in self.messages if m.get("role") == "tool"]

        # First, try to remove tool messages (they are often less important for context)
        while self.estimate_tokens() > max_tokens and len(tool_messages) > 2:
            removed = tool_messages.pop(0)
            # Remove the actual message from self.messages
            try:
                self.messages.remove(removed)
            except ValueError:
                pass  # Message already removed

        # If still over the limit, remove older user/assistant messages
        # but keep the most recent 5 conversation turns to maintain context
        while self.estimate_tokens() > max_tokens and len(user_assistant_messages) > 5:
            removed = user_assistant_messages.pop(0)
            # Remove the actual message from self.messages
            try:
                self.messages.remove(removed)
            except ValueError:
                pass  # Message already removed

        # If still over the limit, truncate long individual messages
        if self.estimate_tokens() > max_tokens:
            self._truncate_long_messages(max_tokens)

        logger.info(f"Context pruned to {len(self.messages)} messages ({self.estimate_tokens()} tokens)")

    def _truncate_long_messages(self, target_tokens: int):
        """
        Truncate long individual messages to fit within token budget.
        """
        # Calculate how much we need to reduce
        current_tokens = self.estimate_tokens()
        if current_tokens <= target_tokens:
            return

        # Sort messages by content length (longest first) to optimize truncation
        message_indices = []
        for i, msg in enumerate(self.messages):
            if msg.get("role") in ("user", "assistant", "tool") and len(msg.get("content", "")) > 200:
                message_indices.append((i, len(msg.get("content", ""))))

        # Sort by length descending
        message_indices.sort(key=lambda x: x[1], reverse=True)

        # Truncate the longest messages first
        for idx, length in message_indices:
            if self.estimate_tokens() <= target_tokens:
                break

            msg = self.messages[idx]
            original_content = msg.get("content", "")
            # Reduce to half the size, with minimum of 200 characters
            new_length = max(200, len(original_content) // 2)
            truncated_content = original_content[:new_length] + "\n... (truncated for context)"

            # Update the message content
            self.messages[idx]["content"] = truncated_content

            logger.debug(f"Truncated message from {length} to {len(truncated_content)} chars")
    
    def estimate_tokens(self) -> int:
        """
        Estimate the token count of the current context.

        Uses different character-to-token ratios based on content type for better accuracy.
        User/assistant messages often have more diverse vocabulary (3 chars/token)
        Tool messages often have more repetitive patterns (5 chars/token)
        System messages are often template-like (4 chars/token)

        Returns:
            Estimated token count
        """
        total_tokens = 0
        for m in self.messages:
            content = m.get("content", "")
            role = m.get("role", "")

            if role == "user" or role == "assistant":
                # More diverse text, ~3 chars per token
                total_tokens += len(content) // 3
            elif role == "tool":
                # Often repetitive patterns like file paths, logs, ~5 chars per token
                total_tokens += len(content) // 5
            else:
                # Default system messages, ~4 chars per token
                total_tokens += len(content) // 4

        # Add overhead for role/structure tokens (approximately 1 token per message)
        total_tokens += len(self.messages)

        return total_tokens
    
    def get_messages_for_llm(self) -> List[Dict[str, str]]:
        """
        Get messages formatted for LLM API.
        
        Returns:
            List of message dicts with 'role' and 'content'
        """
        return [
            {"role": m["role"], "content": m["content"]}
            for m in self.messages
            if m.get("role") in ("user", "assistant", "system", "tool")
        ]
    
    def save(self, filename: Optional[str] = None) -> Path:
        """
        Save session to file.
        
        Args:
            filename: Optional custom filename
        
        Returns:
            Path to saved session file
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"session_{self.session_id}_{timestamp}.json"
        
        session_data = {
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "quest_id": self.quest_id,
            "quest_task": self.quest_task,
            "messages": self.messages,
            "saved_at": datetime.now().isoformat()
        }
        
        file_path = self.sessions_dir / filename
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Session saved: {file_path}")
        
        return file_path
    
    def load(self, filename: str) -> bool:
        """
        Load session from file.
        
        Args:
            filename: Session filename
        
        Returns:
            True if loaded successfully
        """
        file_path = self.sessions_dir / filename
        
        if not file_path.exists():
            logger.warning(f"Session file not found: {file_path}")
            return False
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.session_id = data.get("session_id", self.session_id)
            self.messages = data.get("messages", [])
            self.quest_id = data.get("quest_id")
            self.quest_task = data.get("quest_task")
            
            if data.get("created_at"):
                self.created_at = datetime.fromisoformat(data["created_at"])
            
            logger.info(f"Session loaded: {filename} ({len(self.messages)} messages)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load session: {e}")
            return False
    
    def load_most_recent(self) -> bool:
        """
        Load the most recent session.
        
        Returns:
            True if a session was loaded
        """
        sessions = list(self.sessions_dir.glob("session_*.json"))
        
        if not sessions:
            return False
        
        # Sort by modification time
        most_recent = max(sessions, key=lambda p: p.stat().st_mtime)
        
        return self.load(most_recent.name)
    
    def list_sessions(self) -> List[Dict[str, Any]]:
        """
        List available sessions.
        
        Returns:
            List of session info dictionaries
        """
        sessions = []
        
        for file_path in self.sessions_dir.glob("session_*.json"):
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                
                sessions.append({
                    "filename": file_path.name,
                    "session_id": data.get("session_id"),
                    "created_at": data.get("created_at"),
                    "quest_task": data.get("quest_task"),
                    "message_count": len(data.get("messages", []))
                })
            except Exception:
                pass
        
        # Sort by creation date
        sessions.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
        return sessions
    
    def clear(self):
        """Clear the current session"""
        self.messages = []
        self.quest_id = None
        self.quest_task = None
        self.quest_start = None
        self.session_id = str(uuid.uuid4())[:8]
        logger.debug("Session cleared")
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the current session.
        
        Returns:
            Session summary dictionary
        """
        user_msgs = sum(1 for m in self.messages if m.get("role") == "user")
        assistant_msgs = sum(1 for m in self.messages if m.get("role") == "assistant")
        tool_msgs = sum(1 for m in self.messages if m.get("role") == "tool")
        
        return {
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "message_count": len(self.messages),
            "user_messages": user_msgs,
            "assistant_messages": assistant_msgs,
            "tool_results": tool_msgs,
            "estimated_tokens": self.estimate_tokens(),
            "quest_active": self.quest_id is not None,
            "quest_id": self.quest_id,
            "quest_task": self.quest_task
        }


__all__ = ['SessionManager', 'SESSIONS_DIR', 'MAX_CONTEXT_MESSAGES']