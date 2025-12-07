"""
RxDsec Agent Package
=====================
Core agent functionality for the RxDsec CLI.
"""

from .core import RxDsecAgent, AgentConfig, ToolCall, create_agent
from .memory import MemoryManager, MEMORY_FILE
from .session import SessionManager
from .planner import Plan, PlanStep, create_plan, track_progress
from .subagents import SubAgentLoader, AgentDefinition

__all__ = [
    # Core
    'RxDsecAgent',
    'AgentConfig',
    'ToolCall',
    'create_agent',
    
    # Memory
    'MemoryManager',
    'MEMORY_FILE',
    
    # Session
    'SessionManager',
    
    # Planner
    'Plan',
    'PlanStep',
    'create_plan',
    'track_progress',
    
    # Sub-agents
    'SubAgentLoader',
    'AgentDefinition',
]

__version__ = "1.0.0"