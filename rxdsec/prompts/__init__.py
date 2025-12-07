"""
Prompt Templates for RxDsec CLI
================================
System prompts, tool prompts, and templates for LLM interaction.
"""

from __future__ import annotations

from typing import Dict, List, Optional

# ============================================================================
# SYSTEM PROMPT TEMPLATE
# ============================================================================

SYSTEM_TEMPLATE = """You are RxDsec Agent, an expert AI coding assistant running locally on the user's machine.
You help with software development tasks: writing code, debugging, refactoring, and explaining concepts.

## ENVIRONMENT
- Workspace: {workspace}
- Current directory: {cwd}
- Platform: {platform}

## PROJECT CONTEXT
{memory_context}

## AVAILABLE TOOLS
You MUST use tools to perform actions. Output tool calls in this EXACT format:
Tool: tool_name(arg1="value1", arg2="value2")

{tool_descriptions}

## HOW TO RESPOND (STRICT!)
1. ONE STEP AT A TIME. Do not chain multiple tools.
2. Explain what you'll do: "I'll find python files..."
3. Call ONE tool: Tool: find(pattern="*.py")
4. STOP. Wait for tool output.

## ERROR HANDLING & ADAPTATION
If a tool fails or returns unexpected results:
1. Explain WHY it failed (based on the error message).
2. Propose an ALTERNATIVE solution.
3. Try the alternative tool.

Example:
"The read tool failed because the file is too large. I'll use grep to search for the specific content instead."
Tool: grep(...)

## CRITICAL RULES
- NEVER call multiple tools in one response
- ALWAYS explain before calling a tool
- STOP immediately after writing a tool call
- Wait for the result before deciding next step
- If a tool fails, DO NOT just retry the same command. ADAPT.
"""

# ============================================================================
# PLAN TEMPLATE
# ============================================================================

PLAN_TEMPLATE = """Create a step-by-step plan to accomplish the following task:

TASK: {task}

CONTEXT:
- Workspace: {workspace}
- Files examined: {files_examined}
{additional_context}

Create a detailed plan with numbered steps. Each step should be:
1. Specific and actionable
2. Include which tool(s) to use
3. Describe expected outcome

Format your response as a numbered list:
1. [Action description] - Tool: tool_name(args)
2. ...

Start with the plan:"""

# ============================================================================
# REVIEW TEMPLATE
# ============================================================================

REVIEW_TEMPLATE = """Review the following code changes and provide feedback:

## CHANGES
```diff
{diff}
```

## CONTEXT
- Repository: {repo}
- Branch: {branch}
- Files changed: {files_changed}

## REVIEW CRITERIA
1. Code quality and readability
2. Potential bugs or issues
3. Performance considerations
4. Security concerns
5. Best practices compliance

Provide your review in this format:

### Summary
[Brief overview of the changes]

### Issues Found
- [ ] [Issue description] (severity: high/medium/low)

### Suggestions
- [Improvement suggestion]

### Verdict
[APPROVE / REQUEST_CHANGES / COMMENT]
"""

# ============================================================================
# TOOL RESPONSE TEMPLATE
# ============================================================================

TOOL_RESULT_TEMPLATE = """Tool execution result:
Tool: {tool_name}
Status: {status}
Duration: {duration_ms:.0f}ms

{output}
"""

# ============================================================================
# ERROR TEMPLATE
# ============================================================================

ERROR_TEMPLATE = """An error occurred:
Type: {error_type}
Message: {error_message}

{traceback}

Please analyze this error and suggest fixes.
"""

# ============================================================================
# QUEST SUMMARY TEMPLATE
# ============================================================================

QUEST_SUMMARY_TEMPLATE = """## Quest Complete

**Task:** {task}
**Duration:** {duration}
**Status:** {status}

### Tools Used
{tools_used}

### Files Modified
{files_modified}

### Summary
{summary}
"""

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def format_system_prompt(
    workspace: str,
    cwd: str,
    platform: str,
    memory_context: str = "",
    tool_descriptions: str = "",
    permissions: str = ""
) -> str:
    """
    Format the system prompt with context.
    
    Args:
        workspace: Workspace path
        cwd: Current working directory
        platform: Operating system
        memory_context: Project memory context
        tool_descriptions: Available tools description
        permissions: Permission rules
    
    Returns:
        Formatted system prompt
    """
    return SYSTEM_TEMPLATE.format(
        workspace=workspace,
        cwd=cwd,
        platform=platform,
        memory_context=memory_context or "No project context loaded.",
        tool_descriptions=tool_descriptions or "No tools available.",
        permissions=permissions or "Default permissions apply."
    )


def format_plan_prompt(
    task: str,
    workspace: str,
    files_examined: List[str] = None,
    additional_context: str = ""
) -> str:
    """
    Format the plan prompt.
    
    Args:
        task: Task description
        workspace: Workspace path
        files_examined: List of files already examined
        additional_context: Additional context
    
    Returns:
        Formatted plan prompt
    """
    files_str = ", ".join(files_examined) if files_examined else "None yet"
    
    return PLAN_TEMPLATE.format(
        task=task,
        workspace=workspace,
        files_examined=files_str,
        additional_context=additional_context
    )


def format_review_prompt(
    diff: str,
    repo: str = ".",
    branch: str = "main",
    files_changed: List[str] = None
) -> str:
    """
    Format the review prompt.
    
    Args:
        diff: Git diff content
        repo: Repository name
        branch: Current branch
        files_changed: List of changed files
    
    Returns:
        Formatted review prompt
    """
    files_str = ", ".join(files_changed) if files_changed else "See diff"
    
    return REVIEW_TEMPLATE.format(
        diff=diff,
        repo=repo,
        branch=branch,
        files_changed=files_str
    )


def format_tool_result(
    tool_name: str,
    status: str,
    output: str,
    duration_ms: float = 0.0
) -> str:
    """
    Format a tool result for the conversation.
    
    Args:
        tool_name: Name of the tool
        status: Execution status
        output: Tool output
        duration_ms: Execution time
    
    Returns:
        Formatted tool result
    """
    return TOOL_RESULT_TEMPLATE.format(
        tool_name=tool_name,
        status=status,
        duration_ms=duration_ms,
        output=output
    )


def format_error(
    error_type: str,
    error_message: str,
    traceback: str = ""
) -> str:
    """
    Format an error for analysis.
    
    Args:
        error_type: Type of error
        error_message: Error message
        traceback: Stack trace
    
    Returns:
        Formatted error prompt
    """
    return ERROR_TEMPLATE.format(
        error_type=error_type,
        error_message=error_message,
        traceback=traceback or "No traceback available."
    )


def format_quest_summary(
    task: str,
    duration: str,
    status: str,
    tools_used: List[str],
    files_modified: List[str],
    summary: str
) -> str:
    """
    Format a quest completion summary.
    
    Args:
        task: Original task
        duration: Time taken
        status: Completion status
        tools_used: List of tools used
        files_modified: List of modified files
        summary: Summary of work done
    
    Returns:
        Formatted summary
    """
    tools_str = "\n".join(f"- {t}" for t in tools_used) if tools_used else "- None"
    files_str = "\n".join(f"- {f}" for f in files_modified) if files_modified else "- None"
    
    return QUEST_SUMMARY_TEMPLATE.format(
        task=task,
        duration=duration,
        status=status,
        tools_used=tools_str,
        files_modified=files_str,
        summary=summary
    )


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Templates
    'SYSTEM_TEMPLATE',
    'PLAN_TEMPLATE',
    'REVIEW_TEMPLATE',
    'TOOL_RESULT_TEMPLATE',
    'ERROR_TEMPLATE',
    'QUEST_SUMMARY_TEMPLATE',
    
    # Formatters
    'format_system_prompt',
    'format_plan_prompt',
    'format_review_prompt',
    'format_tool_result',
    'format_error',
    'format_quest_summary',
]