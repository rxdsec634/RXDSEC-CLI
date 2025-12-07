"""
Review CLI Command for RxDsec CLI
==================================
Code review with AI assistance.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

# Configure module logger
logger = logging.getLogger(__name__)

# Console for output
console = Console()

# Create review app
review_app = typer.Typer(
    name="review",
    help="Review code changes"
)


@review_app.callback(invoke_without_command=True)
def review_main(
    ctx: typer.Context,
    target: Optional[str] = typer.Argument(
        None,
        help="File, directory, or git ref to review"
    ),
    staged: bool = typer.Option(
        False,
        "--staged", "-s",
        help="Review only staged changes"
    ),
    branch: Optional[str] = typer.Option(
        None,
        "--branch", "-b",
        help="Compare against branch"
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model", "-m",
        help="Path to GGUF model"
    ),
    workspace: Optional[Path] = typer.Option(
        None,
        "--workspace", "-w",
        help="Working directory"
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="Verbose output"
    )
):
    """
    Review code changes with AI assistance.
    
    By default, reviews all unstaged changes. Use --staged for staged changes,
    or specify a branch to compare against.
    
    Examples:
        rxdsec review                    # Review all changes
        rxdsec review --staged           # Review staged changes
        rxdsec review -b main            # Compare against main branch
        rxdsec review src/auth.py        # Review specific file
    """
    if ctx.invoked_subcommand is not None:
        return
    
    workspace_path = workspace or Path.cwd()
    
    # Get diff
    diff = get_diff(workspace_path, target, staged, branch)
    
    if not diff:
        console.print("[dim]No changes to review.[/dim]")
        return
    
    # Show diff preview
    console.print(Panel(
        Syntax(diff[:2000], "diff", theme="monokai"),
        title="Changes to Review",
        border_style="blue"
    ))
    
    if len(diff) > 2000:
        console.print(f"[dim]... ({len(diff) - 2000} more characters)[/dim]\n")
    
    # Load agent and run review
    from ..agent import create_agent
    
    try:
        agent = create_agent(model_path=model, workspace=workspace_path, verbose=verbose)
    except Exception as e:
        console.print(f"[red]Failed to initialize agent: {e}[/red]")
        raise typer.Exit(1)
    
    run_review(agent, diff)


def get_diff(
    workspace: Path,
    target: Optional[str] = None,
    staged: bool = False,
    branch: Optional[str] = None
) -> str:
    """
    Get git diff for review.
    
    Args:
        workspace: Working directory
        target: Specific file or ref
        staged: Only staged changes
        branch: Branch to compare against
    
    Returns:
        Diff string
    """
    try:
        cmd = ["git", "diff"]
        
        if staged:
            cmd.append("--staged")
        
        if branch:
            cmd.append(branch)
        
        if target:
            cmd.append("--")
            cmd.append(target)
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(workspace)
        )
        
        return result.stdout
        
    except Exception as e:
        logger.error(f"Failed to get diff: {e}")
        return ""


def run_review(agent, diff: str):
    """
    Run AI code review.
    
    Args:
        agent: RxDsec agent
        diff: Diff content to review
    """
    from ..prompts import format_review_prompt
    from ..output import render_output
    
    console.print("\n[bold cyan]Reviewing changes...[/bold cyan]\n")
    
    # Build review prompt
    prompt = format_review_prompt(diff[:10000])  # Truncate very large diffs
    
    try:
        with console.status("[bold cyan]Analyzing...[/bold cyan]", spinner="dots"):
            response = agent.generate(prompt, stream=False)
        
        # Render review output
        console.print(render_output(response))
        
        # Parse verdict
        verdict = parse_verdict(response)
        
        if verdict:
            color = {
                "APPROVE": "green",
                "REQUEST_CHANGES": "yellow",
                "COMMENT": "blue"
            }.get(verdict, "white")
            
            console.print(Panel(
                f"[bold {color}]{verdict}[/bold {color}]",
                title="Verdict",
                border_style=color
            ))
    
    except Exception as e:
        console.print(f"[red]Review error: {e}[/red]")


def parse_verdict(response: str) -> Optional[str]:
    """Extract verdict from review response"""
    import re
    
    # Look for verdict patterns
    patterns = [
        r'\*\*Verdict\*\*[:\s]*(\w+)',
        r'Verdict[:\s]*(\w+)',
        r'\[(APPROVE|REQUEST_CHANGES|COMMENT)\]',
    ]
    
    response_upper = response.upper()
    
    for pattern in patterns:
        match = re.search(pattern, response_upper)
        if match:
            verdict = match.group(1).strip()
            if verdict in ("APPROVE", "REQUEST_CHANGES", "COMMENT"):
                return verdict
    
    # Default detection
    if "APPROVE" in response_upper:
        return "APPROVE"
    elif "REQUEST_CHANGES" in response_upper or "REQUEST CHANGES" in response_upper:
        return "REQUEST_CHANGES"
    
    return None


@review_app.command()
def file(
    path: str = typer.Argument(
        ...,
        help="File to review"
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model", "-m",
        help="Model to use"
    )
):
    """Review a specific file (full content, not just diff)"""
    workspace = Path.cwd()
    file_path = workspace / path
    
    if not file_path.exists():
        console.print(f"[red]File not found: {path}[/red]")
        raise typer.Exit(1)
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        console.print(f"[red]Error reading file: {e}[/red]")
        raise typer.Exit(1)
    
    from ..agent import create_agent
    from ..output import render_output
    
    try:
        agent = create_agent(model_path=model, workspace=workspace)
    except Exception as e:
        console.print(f"[red]Failed to initialize agent: {e}[/red]")
        raise typer.Exit(1)
    
    console.print(f"\n[bold cyan]Reviewing {path}...[/bold cyan]\n")
    
    prompt = f"""Please review this file and provide feedback:

File: {path}

```
{content[:10000]}
```

Analyze for:
1. Code quality and readability
2. Potential bugs
3. Performance issues
4. Security concerns
5. Best practices

Provide specific, actionable feedback."""

    with console.status("[bold cyan]Analyzing...[/bold cyan]", spinner="dots"):
        response = agent.generate(prompt, stream=False)
    
    console.print(render_output(response))


@review_app.command()
def commit(
    ref: str = typer.Argument(
        "HEAD",
        help="Commit ref to review"
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model", "-m",
        help="Model to use"
    )
):
    """Review a specific commit"""
    workspace = Path.cwd()
    
    try:
        result = subprocess.run(
            ["git", "show", ref],
            capture_output=True,
            text=True,
            cwd=str(workspace)
        )
        
        if result.returncode != 0:
            console.print(f"[red]Invalid commit ref: {ref}[/red]")
            raise typer.Exit(1)
        
        diff = result.stdout
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
    
    from ..agent import create_agent
    
    try:
        agent = create_agent(model_path=model, workspace=workspace)
    except Exception as e:
        console.print(f"[red]Failed to initialize agent: {e}[/red]")
        raise typer.Exit(1)
    
    run_review(agent, diff)


__all__ = ['review_app', 'run_review', 'get_diff']