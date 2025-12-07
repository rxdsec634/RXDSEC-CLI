"""
Advanced Planner for RxDsec CLI
================================
Plan creation, tracking, and progress visualization.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Configure module logger
logger = logging.getLogger(__name__)


@dataclass
class PlanStep:
    """A single step in a plan"""
    number: int
    description: str
    tool: Optional[str] = None
    args: Dict[str, str] = field(default_factory=dict)
    completed: bool = False
    result: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "number": self.number,
            "description": self.description,
            "tool": self.tool,
            "args": self.args,
            "completed": self.completed,
            "result": self.result
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlanStep":
        return cls(
            number=data.get("number", 0),
            description=data.get("description", ""),
            tool=data.get("tool"),
            args=data.get("args", {}),
            completed=data.get("completed", False),
            result=data.get("result")
        )


@dataclass
class Plan:
    """A complete plan for a task"""
    task: str
    steps: List[PlanStep] = field(default_factory=list)
    current_step: int = 0
    
    def add_step(self, description: str, tool: Optional[str] = None, **args):
        """Add a step to the plan"""
        step = PlanStep(
            number=len(self.steps) + 1,
            description=description,
            tool=tool,
            args=args
        )
        self.steps.append(step)
    
    def complete_step(self, step_number: int, result: Optional[str] = None):
        """Mark a step as completed"""
        for step in self.steps:
            if step.number == step_number:
                step.completed = True
                step.result = result
                self.current_step = step_number + 1
                break
    
    def get_progress(self) -> float:
        """Get completion percentage"""
        if not self.steps:
            return 0.0
        completed = sum(1 for s in self.steps if s.completed)
        return completed / len(self.steps)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task": self.task,
            "steps": [s.to_dict() for s in self.steps],
            "current_step": self.current_step,
            "progress": self.get_progress()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Plan":
        plan = cls(
            task=data.get("task", ""),
            current_step=data.get("current_step", 0)
        )
        plan.steps = [PlanStep.from_dict(s) for s in data.get("steps", [])]
        return plan


def create_plan(llm_response: str) -> List[Dict]:
    """
    Parse an LLM response into a structured plan.
    
    Supports multiple formats:
    - JSON array
    - Numbered list
    - Markdown list
    
    Args:
        llm_response: Raw LLM response containing plan
    
    Returns:
        List of plan step dictionaries
    """
    steps = []
    
    # Try JSON parsing first
    try:
        # Look for JSON array in response
        json_match = re.search(r'\[[\s\S]*\]', llm_response)
        if json_match:
            parsed = json.loads(json_match.group())
            if isinstance(parsed, list):
                for i, item in enumerate(parsed):
                    if isinstance(item, dict):
                        steps.append({
                            "number": item.get("number", i + 1),
                            "description": item.get("description", item.get("step", str(item))),
                            "tool": item.get("tool"),
                            "completed": False
                        })
                    else:
                        steps.append({
                            "number": i + 1,
                            "description": str(item),
                            "completed": False
                        })
                
                if steps:
                    logger.debug(f"Parsed {len(steps)} steps from JSON")
                    return steps
    except (json.JSONDecodeError, TypeError):
        pass
    
    # Parse numbered list format
    # Matches: 1. Description, 1) Description, Step 1: Description
    numbered_pattern = re.compile(
        r'(?:^|\n)\s*(?:Step\s*)?(\d+)[.\):]\s*(.+?)(?=\n\s*(?:Step\s*)?\d+[.\):]|\n\n|$)',
        re.DOTALL | re.IGNORECASE
    )
    
    for match in numbered_pattern.finditer(llm_response):
        step_num = int(match.group(1))
        description = match.group(2).strip()
        
        # Extract tool if mentioned
        tool_match = re.search(r'Tool:\s*(\w+)', description)
        tool = tool_match.group(1) if tool_match else None
        
        # Clean description
        description = re.sub(r'\s*-\s*Tool:.*$', '', description).strip()
        
        steps.append({
            "number": step_num,
            "description": description,
            "tool": tool,
            "completed": False
        })
    
    if steps:
        logger.debug(f"Parsed {len(steps)} steps from numbered list")
        return steps
    
    # Parse markdown bullet list
    bullet_pattern = re.compile(r'^[\s]*[-*•]\s+(.+)$', re.MULTILINE)
    
    for i, match in enumerate(bullet_pattern.finditer(llm_response)):
        description = match.group(1).strip()
        
        # Skip empty or very short items
        if len(description) < 5:
            continue
        
        tool_match = re.search(r'Tool:\s*(\w+)', description)
        tool = tool_match.group(1) if tool_match else None
        
        description = re.sub(r'\s*-\s*Tool:.*$', '', description).strip()
        
        steps.append({
            "number": i + 1,
            "description": description,
            "tool": tool,
            "completed": False
        })
    
    if steps:
        logger.debug(f"Parsed {len(steps)} steps from bullet list")
        return steps
    
    # Fallback: split by sentences/lines
    lines = [l.strip() for l in llm_response.split('\n') if l.strip() and len(l.strip()) > 10]
    
    for i, line in enumerate(lines[:10]):  # Limit to 10 steps
        if not line.startswith(('#', '```', '---')):
            steps.append({
                "number": i + 1,
                "description": line[:200],  # Truncate long lines
                "completed": False
            })
    
    logger.debug(f"Parsed {len(steps)} steps from fallback")
    return steps


def track_progress(plan: List[Dict], current_step: int = 0) -> str:
    """
    Format a plan with progress indicators.
    
    Args:
        plan: List of plan step dictionaries
        current_step: Index of current step (0-based)
    
    Returns:
        Formatted plan string
    """
    lines = []
    
    for i, step in enumerate(plan):
        number = step.get("number", i + 1)
        description = step.get("description", "")
        completed = step.get("completed", False)
        
        # Determine status indicator
        if completed:
            indicator = "✓"
            style = ""
        elif i == current_step:
            indicator = "⏳"
            style = " (current)"
        elif i < current_step:
            indicator = "✓"
            style = ""
        else:
            indicator = "○"
            style = ""
        
        lines.append(f"  {indicator} {number}. {description}{style}")
    
    return "\n".join(lines)


def estimate_plan_progress(plan: List[Dict]) -> Dict[str, Any]:
    """
    Estimate overall plan progress.
    
    Args:
        plan: List of plan step dictionaries
    
    Returns:
        Progress information dictionary
    """
    if not plan:
        return {
            "total_steps": 0,
            "completed_steps": 0,
            "progress_percent": 0,
            "remaining_steps": 0
        }
    
    completed = sum(1 for s in plan if s.get("completed", False))
    total = len(plan)
    
    return {
        "total_steps": total,
        "completed_steps": completed,
        "progress_percent": (completed / total) * 100,
        "remaining_steps": total - completed
    }


def validate_plan(plan: List[Dict]) -> tuple[bool, List[str]]:
    """
    Validate a plan for completeness and correctness.
    
    Args:
        plan: Plan to validate
    
    Returns:
        Tuple of (is_valid, list of issues)
    """
    issues = []
    
    if not plan:
        issues.append("Plan is empty")
        return False, issues
    
    for i, step in enumerate(plan):
        if not step.get("description"):
            issues.append(f"Step {i + 1} has no description")
        
        desc = step.get("description", "")
        if len(desc) < 5:
            issues.append(f"Step {i + 1} description is too short")
        
        if len(desc) > 500:
            issues.append(f"Step {i + 1} description is too long")
    
    # Check for duplicate steps
    descriptions = [s.get("description", "").lower() for s in plan]
    if len(descriptions) != len(set(descriptions)):
        issues.append("Plan contains duplicate steps")
    
    return len(issues) == 0, issues


__all__ = [
    'Plan',
    'PlanStep',
    'create_plan',
    'track_progress',
    'estimate_plan_progress',
    'validate_plan',
]