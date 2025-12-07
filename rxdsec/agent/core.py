"""
Advanced Agent Core for RxDsec CLI
===================================
Production-ready agent orchestration with streaming, tool execution, 
and comprehensive error handling.
"""

from __future__ import annotations

import logging
import platform
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

try:
    from llama_cpp import Llama
    HAS_LLAMA = True
except ImportError:
    HAS_LLAMA = False
    Llama = None

from ..tools import ToolRegistry, ToolResult, ToolStatus
from ..permissions import PermissionsEngine
from ..hooks import HookRunner, HookEvent
from ..extensions import ExtensionManager
from ..prompts import format_system_prompt, format_plan_prompt, format_tool_result
from .memory import MemoryManager
from .session import SessionManager
from .subagents import SubAgentLoader
from .planner import create_plan, track_progress

# Configure module logger
logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration for the RxDsec agent"""
    model_path: str
    workspace: Path
    n_gpu_layers: int = 0
    n_ctx: int = 8192
    temperature: float = 0.7
    max_tokens: int = 2048
    verbose: bool = False
    stream: bool = True


@dataclass
class ToolCall:
    """Parsed tool call from LLM output"""
    name: str
    args: Dict[str, str]
    raw: str
    line_number: int = 0
    
    def __repr__(self):
        args_str = ", ".join(f"{k}={v!r}" for k, v in self.args.items())
        return f"ToolCall({self.name}({args_str}))"


class RxDsecAgent:
    """
    Core agent for RxDsec CLI.
    
    Features:
    - GGUF model loading and inference
    - Tool calling and execution
    - Memory management
    - Session handling
    - Hook integration
    - Permission checking
    """
    
    # Tool call patterns - matches multiple formats:
    # Tool: name(args), $ name(args), name(args) in code blocks
    TOOL_PATTERNS = [
        # Standard format: Tool: name(args)
        re.compile(r'Tool:\s*(\w+)\s*\(\s*((?:[^()]*|\([^()]*\))*)\s*\)', re.DOTALL),
        # Bash-style: $ name(args)
        re.compile(r'\$\s*(\w+)\s*\(\s*((?:[^()]*|\([^()]*\))*)\s*\)', re.DOTALL),
        # Direct call in text: read(path="...) or write(path="...)
        re.compile(r'\b(read|write|grep|find|shell|localexec|webfetch|patch)\s*\(\s*((?:[^()]*|\([^()]*\))*)\s*\)', re.DOTALL),
    ]
    
    # Argument pattern within tool calls
    ARG_PATTERN = re.compile(
        r'(\w+)\s*=\s*(?:"([^"]*?)"|\'([^\']*?)\'|(\S+?)(?=[,\s\)]|$))',
        re.DOTALL
    )
    
    def __init__(
        self,
        model_path: str,
        workspace: Optional[Path] = None,
        n_gpu_layers: int = 0,
        n_ctx: int = 8192,
        temperature: float = 0.7,
        verbose: bool = False,
        load_immediately: bool = False
    ):
        """
        Initialize the RxDsec agent.

        Args:
            model_path: Path to GGUF model file
            workspace: Working directory
            n_gpu_layers: Number of layers to offload to GPU
            n_ctx: Context window size
            temperature: Sampling temperature
            verbose: Enable verbose output
            load_immediately: Whether to load the model immediately or lazily
        """
        self.workspace = workspace or Path.cwd()
        self.model_path = model_path
        self.n_gpu_layers = n_gpu_layers
        self.n_ctx = n_ctx
        self.temperature = temperature
        self.verbose = verbose
        self._llm = None  # Initialize as None for lazy loading

        # Initialize components
        self._init_components()

        logger.info(f"RxDsecAgent initialized with workspace: {self.workspace}")

        # Load model immediately if requested
        if load_immediately:
            self._init_llm()
    
    def _init_llm(self):
        """Initialize the LLM"""
        if not HAS_LLAMA:
            raise ImportError(
                "llama-cpp-python not installed. "
                "Install with: pip install llama-cpp-python"
            )

        if not Path(self.model_path).exists():
            raise FileNotFoundError(f"Model not found: {self.model_path}")

        logger.info(f"Loading model: {self.model_path}")

        self._llm = Llama(
            model_path=self.model_path,
            n_gpu_layers=self.n_gpu_layers,
            n_ctx=self.n_ctx,
            verbose=self.verbose,
            chat_format="chatml"
        )

        logger.info("Model loaded successfully")

    @property
    def llm(self):
        """Lazy load the LLM on first access"""
        if self._llm is None:
            self._init_llm()
        return self._llm
    
    def _init_components(self):
        """Initialize all agent components"""
        # Core components
        self.memory = MemoryManager(self.workspace)
        self.permissions = PermissionsEngine(self.workspace)
        self.tools = ToolRegistry(
            workspace=self.workspace,
            permissions=self.permissions
        )
        self.session = SessionManager(self.workspace)
        self.hooks = HookRunner(self.workspace)
        self.extensions = ExtensionManager(self.workspace)
        self.subagents = SubAgentLoader(self.workspace)
        
        # Inject extensions as tools
        self.extensions.inject_tools(self.tools)
    
    def _build_system_prompt(self, subagent: Optional[str] = None) -> str:
        """Build the system prompt with all context"""
        # Get memory context
        memory_context = self.memory.get_context()
        
        # Get tool descriptions
        tool_descriptions = self.tools.describe()
        
        # Get permission rules
        permissions = self.permissions.rules
        
        # Format system prompt
        system = format_system_prompt(
            workspace=str(self.workspace),
            cwd=str(Path.cwd()),
            platform=platform.system(),
            memory_context=memory_context,
            tool_descriptions=tool_descriptions,
            permissions=permissions
        )
        
        # Add subagent context if specified
        if subagent:
            agent_def = self.subagents.resolve(subagent)
            if agent_def:
                system += f"\n\n## SPECIALIZED ROLE\n{agent_def.get('system', '')}"
        
        return system
    
    def generate(
        self,
        message: str,
        system: Optional[str] = None,
        subagent: Optional[str] = None,
        stream: bool = True
    ) -> Iterator[str] | str:
        """
        Generate a response from the agent.
        
        Args:
            message: User message
            system: Optional custom system prompt
            subagent: Optional subagent to use
            stream: Whether to stream the response
        
        Returns:
            Response text (streamed or complete)
        """
        # Build messages
        system_prompt = system or self._build_system_prompt(subagent)
        
        # Add to session
        self.session.add_user(message)
        
        # Build message list
        messages = [
            {"role": "system", "content": system_prompt}
        ]
        messages.extend(self.session.messages)
        
        # Prune if needed
        self.session.prune_context(max_tokens=self.n_ctx - 2000)
        
        try:
            if stream:
                return self._generate_stream(messages)
            else:
                return self._generate_complete(messages)
        except Exception as e:
            logger.exception("Generation error")
            raise
    
    def _generate_stream(self, messages: List[Dict]) -> Iterator[str]:
        """Generate response with streaming"""
        full_response = []
        
        try:
            response = self.llm.create_chat_completion(
                messages=messages,
                temperature=self.temperature,
                max_tokens=2048,
                stream=True
            )
            
            for chunk in response:
                if 'choices' in chunk and chunk['choices']:
                    delta = chunk['choices'][0].get('delta', {})
                    content = delta.get('content', '')
                    if content:
                        full_response.append(content)
                        yield content
            
            # Add complete response to session
            complete = ''.join(full_response)
            self.session.add_assistant(complete)
            
        except Exception as e:
            logger.exception("Streaming error")
            raise
    
    def _generate_complete(self, messages: List[Dict]) -> str:
        """Generate complete response"""
        try:
            response = self.llm.create_chat_completion(
                messages=messages,
                temperature=self.temperature,
                max_tokens=2048,
                stream=False
            )
            
            content = response['choices'][0]['message']['content']
            self.session.add_assistant(content)
            
            return content
            
        except Exception as e:
            logger.exception("Generation error")
            raise
    
    def run_quest(
        self,
        task: str,
        max_iterations: int = 10,
        on_step: Optional[Callable[[str, int], None]] = None
    ) -> Dict[str, Any]:
        """
        Run an autonomous quest to complete a task.
        
        Args:
            task: Task description
            max_iterations: Maximum number of agent iterations
            on_step: Callback for step updates
        
        Returns:
            Quest result dictionary
        """
        start_time = time.time()
        quest_id = self.session.start_quest(task)
        
        # Run quest start hook
        self.hooks.run(HookEvent.QUEST_START, {"task": task, "quest_id": quest_id})
        
        result = {
            "quest_id": quest_id,
            "task": task,
            "success": False,
            "steps": [],
            "tools_used": [],
            "files_modified": [],
            "iterations": 0,
            "error": None
        }
        
        try:
            # Create initial plan
            plan = self._create_plan(task)
            result["plan"] = plan
            
            if on_step:
                on_step(f"Plan created with {len(plan)} steps", 0)
            
            # Execute plan iteratively
            iteration = 0
            effective_turns = 0
            
            while effective_turns < max_iterations:
                iteration += 1
                result["iterations"] = iteration
                
                # Generate next action
                context = self._build_quest_context(task, plan, result["steps"])
                response = self._generate_complete([
                    {"role": "system", "content": self._build_system_prompt()},
                    {"role": "user", "content": context}
                ])
                
                # Parse and execute tool calls
                tool_calls = self.parse_tools(response)
                
                if not tool_calls:
                    # No tool calls - check if task is complete
                    if self._is_task_complete(response):
                        result["success"] = True
                        result["summary"] = response
                        break
                    else:
                        # Ask for next action
                        result["steps"].append({
                            "iteration": iteration,
                            "response": response,
                            "tools": []
                        })
                        # No tools used, so this is a 'thinking' turn, count it? 
                        # Probably yes to avoid infinite loops
                        effective_turns += 1
                        continue
                
                # Execute tools
                step_result = {
                    "iteration": iteration,
                    "response": response,
                    "tools": []
                }
                
                has_substantive_action = False
                
                for tool_call in tool_calls:
                    tool_result = self._execute_tool(tool_call)
                    
                    # specific check: todowrite is a meta-tool
                    if tool_call.name != 'todowrite':
                        has_substantive_action = True
                    
                    step_result["tools"].append({
                        "name": tool_call.name,
                        "args": tool_call.args,
                        "success": tool_result.success,
                        "output": tool_result.output[:500]  # Truncate
                    })
                    
                    result["tools_used"].append(tool_call.name)
                
                # Only count against limit if real work was done
                if has_substantive_action or not tool_calls:
                    effective_turns += 1
                    
                    # Track file modifications
                    if tool_call.name in ('write', 'write_lines', 'patch'):
                        path = tool_call.args.get('path', '')
                        if path and path not in result["files_modified"]:
                            result["files_modified"].append(path)
                    
                    # Add tool result to session
                    self.session.add_tool_result(
                        tool_call.name,
                        tool_result.success,
                        tool_result.output
                    )
                
                result["steps"].append(step_result)
                
                if on_step:
                    on_step(f"Completed iteration {iteration + 1}", iteration + 1)
            
            # Quest complete
            result["duration"] = time.time() - start_time
            self.session.end_quest(success=result["success"])
            
            # Run completion hook
            self.hooks.run(
                HookEvent.QUEST_COMPLETE if result["success"] else HookEvent.QUEST_ERROR,
                result
            )
            
        except Exception as e:
            result["success"] = False
            result["error"] = str(e)
            result["duration"] = time.time() - start_time
            logger.exception(f"Quest failed: {task}")
            
            self.hooks.run(HookEvent.QUEST_ERROR, {"task": task, "error": str(e)})
        
        return result
    
    def _create_plan(self, task: str) -> List[Dict]:
        """Create a plan for the task"""
        plan_prompt = format_plan_prompt(
            task=task,
            workspace=str(self.workspace)
        )
        
        response = self._generate_complete([
            {"role": "system", "content": self._build_system_prompt()},
            {"role": "user", "content": plan_prompt}
        ])
        
        return create_plan(response)
    
    def _build_quest_context(
        self,
        task: str,
        plan: List[Dict],
        steps_completed: List[Dict]
    ) -> str:
        """Build context for next quest iteration"""
        context_parts = [f"TASK: {task}"]
        
        # Add plan progress
        context_parts.append("\nPLAN PROGRESS:")
        context_parts.append(track_progress(plan, len(steps_completed)))
        
        # Add recent results
        if steps_completed:
            last_step = steps_completed[-1]
            context_parts.append("\nLAST ACTION RESULTS:")
            for tool in last_step.get("tools", []):
                status = "✓" if tool["success"] else "✗"
                context_parts.append(f"{status} {tool['name']}: {tool['output'][:200]}")
        
        context_parts.append("\nWhat is the next action to take?")
        
        return "\n".join(context_parts)
    
    def _is_task_complete(self, response: str) -> bool:
        """Check if the task appears complete based on response"""
        completion_markers = [
            "task is complete",
            "task complete",
            "successfully completed",
            "all steps done",
            "finished",
            "all done",
            "quest complete"
        ]
        
        response_lower = response.lower()
        return any(marker in response_lower for marker in completion_markers)
    
    def parse_tools(self, text: str) -> List[ToolCall]:
        """
        Parse tool calls from LLM response.
        
        Args:
            text: LLM response text
        
        Returns:
            List of ToolCall objects
        """
        tool_calls = []
        seen_positions = set()  # Avoid duplicates
        
        # Try all patterns
        for pattern in self.TOOL_PATTERNS:
            for match in pattern.finditer(text):
                # Skip if we already found a tool at this position
                if match.start() in seen_positions:
                    continue
                seen_positions.add(match.start())
                
                tool_name = match.group(1)
                args_str = match.group(2)
                
                # Skip if tool doesn't exist
                if not self.tools.get(tool_name):
                    continue
                
                # Parse arguments
                args = {}
                for arg_match in self.ARG_PATTERN.finditer(args_str):
                    key = arg_match.group(1)
                    # Value is in group 2 (double quoted), 3 (single quoted), or 4 (unquoted)
                    value = arg_match.group(2) or arg_match.group(3) or arg_match.group(4) or ''
                    # Unescape common sequences
                    value = value.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"').replace("\\'", "'")
                    args[key] = value
                
                # Get line number of tool call
                line_number = text[:match.start()].count('\n') + 1
                
                tool_calls.append(ToolCall(
                    name=tool_name,
                    args=args,
                    raw=match.group(0),
                    line_number=line_number
                ))
        
        logger.debug(f"Parsed {len(tool_calls)} tool calls")
        return tool_calls
    
    def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
        """
        Execute a single tool call.
        
        Args:
            tool_call: Parsed tool call
        
        Returns:
            Tool execution result
        """
        logger.info(f"Executing tool: {tool_call.name}")
        
        # Run before hook
        self.hooks.run(HookEvent.TOOL_BEFORE, {
            "name": tool_call.name,
            "args": tool_call.args
        })
        
        # Check permissions
        resource = tool_call.args.get('path', 
                   tool_call.args.get('url',
                   tool_call.args.get('cmd', str(tool_call.args))))
        
        if not self.permissions.check(tool_call.name, resource):
            result = ToolResult.fail(
                error=f"Permission denied: {tool_call.name} on {resource}",
                status=ToolStatus.PERMISSION_DENIED
            )
        else:
            # Execute the tool
            result = self.tools.execute(tool_call.name, tool_call.args)
        
        # Run after hook
        self.hooks.run(HookEvent.TOOL_AFTER, {
            "name": tool_call.name,
            "args": tool_call.args,
            "success": result.success,
            "output": result.output[:500]
        })
        
        return result
    
    def execute_tools(self, text: str) -> List[Tuple[ToolCall, ToolResult]]:
        """
        Parse and execute all tool calls in text.
        
        Args:
            text: Text containing tool calls
        
        Returns:
            List of (ToolCall, ToolResult) tuples
        """
        tool_calls = self.parse_tools(text)
        results = []
        
        for tool_call in tool_calls:
            result = self._execute_tool(tool_call)
            results.append((tool_call, result))
        
        return results
    
    def add_note(self, note: str):
        """Add a note to project memory"""
        self.memory.append_note(note)
    
    def get_memory(self) -> Dict:
        """Get project memory"""
        return self.memory.load()
    
    def reset_session(self):
        """Reset the current session"""
        self.session = SessionManager(self.workspace)


# Convenience function
def create_agent(
    model_path: Optional[str] = None,
    workspace: Optional[Path] = None,
    load_immediately: bool = False,
    **kwargs
) -> RxDsecAgent:
    """
    Create an RxDsec agent with auto-detection.

    Args:
        model_path: Path to model (auto-detected if not provided)
        workspace: Working directory
        load_immediately: Whether to load the model immediately or lazily
        **kwargs: Additional agent configuration

    Returns:
        Configured RxDsecAgent
    """
    if not model_path:
        # Try to find a model
        models_dir = Path(workspace or Path.cwd()) / "models"
        if models_dir.exists():
            gguf_files = list(models_dir.glob("*.gguf"))
            if gguf_files:
                model_path = str(gguf_files[0])

        if not model_path:
            home_models = Path.home() / ".rxdsec" / "models"
            if home_models.exists():
                gguf_files = list(home_models.glob("*.gguf"))
                if gguf_files:
                    model_path = str(gguf_files[0])

    if not model_path:
        raise ValueError("No model found. Please specify model_path or place a .gguf file in ./models/")

    return RxDsecAgent(
        model_path=model_path,
        workspace=workspace,
        load_immediately=load_immediately,
        **kwargs
    )


__all__ = ['RxDsecAgent', 'AgentConfig', 'ToolCall', 'create_agent']