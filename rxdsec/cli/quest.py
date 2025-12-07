"""
Quest CLI Command for RxDsec CLI
=================================
Autonomous quest execution with progress tracking.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

# Configure module logger
logger = logging.getLogger(__name__)

# Console for output
console = Console()

# Create quest app
quest_app = typer.Typer(
    name="quest",
    help="Run autonomous coding quests"
)


@quest_app.callback(invoke_without_command=True)
def quest_main(
    ctx: typer.Context,
    task: Optional[str] = typer.Argument(
        None,
        help="Task description for the quest"
    ),
    max_iterations: int = typer.Option(
        10,
        "--max-iter", "-n",
        help="Maximum iterations"
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model", "-m",
        help="Path to GGUF model"
    ),
    subagent: Optional[str] = typer.Option(
        None,
        "--agent", "-a",
        help="Sub-agent to use"
    ),
    workspace: Optional[Path] = typer.Option(
        None,
        "--workspace", "-w",
        help="Working directory"
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Plan only, don't execute"
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="Verbose output"
    )
):
    """
    Run an autonomous quest to complete a coding task.
    
    The agent will create a plan and execute it step by step,
    using tools to read, write, and modify code.
    
    Examples:
        rxdsec quest "Add unit tests for auth module"
        rxdsec quest "Refactor the database layer" -n 15
        rxdsec quest "Fix the login bug" --agent debugger
    """
    if ctx.invoked_subcommand is not None:
        return
    
    if not task:
        console.print("[yellow]Please provide a task description.[/yellow]")
        console.print("\nExample: rxdsec quest \"Add unit tests for auth module\"")
        raise typer.Exit(1)
    
    workspace_path = workspace or Path.cwd()
    
    # Find and load model
    from ..agent import create_agent
    
    try:
        agent = create_agent(
            model_path=model,
            workspace=workspace_path,
            verbose=verbose
        )
    except Exception as e:
        console.print(f"[red]Failed to initialize agent: {e}[/red]")
        raise typer.Exit(1)
    
    # Run quest
    run_quest(agent, task, max_iterations, dry_run, verbose)


def run_quest(
    agent,
    task: str,
    max_iterations: int = 10,
    dry_run: bool = False,
    verbose: bool = False
):
    """
    Execute a quest with progress tracking.
    
    Args:
        agent: RxDsec agent instance
        task: Task description
        max_iterations: Maximum iterations
        dry_run: If True, only create plan
        verbose: Verbose output
    """
    console.print(Panel(
        f"[bold]{task}[/bold]",
        title="🚀 Starting Quest",
        border_style="cyan"
    ))
    
    if dry_run:
        # Just create and show plan
        console.print("\n[dim]Dry run mode - creating plan only...[/dim]\n")
        
        with console.status("[bold cyan]Planning...[/bold cyan]", spinner="dots"):
            from ..agent import create_plan
            from ..prompts import format_plan_prompt
            
            plan_prompt = format_plan_prompt(task, str(agent.workspace))
            response = agent._generate_complete([
                {"role": "system", "content": agent._build_system_prompt()},
                {"role": "user", "content": plan_prompt}
            ])
            
            plan = create_plan(response)
        
        console.print(Panel(
            "\n".join(f"  {i+1}. {step.get('description', '')}" for i, step in enumerate(plan)),
            title="Plan",
            border_style="blue"
        ))
        return
    
    # Progress tracking
    steps_completed = 0
    files_modified = []
    tools_used = []
    
    def on_step(message: str, step: int):
        nonlocal steps_completed
        steps_completed = step
        if verbose:
            console.print(f"  [dim]Step {step}:[/dim] {message}")
    
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=console
        ) as progress:
            quest_task = progress.add_task("Running quest...", total=max_iterations)
            
            # Modify on_step to update progress
            def progress_step(message: str, step: int):
                on_step(message, step)
                progress.update(quest_task, completed=step)
            
            result = agent.run_quest(
                task,
                max_iterations=max_iterations,
                on_step=progress_step
            )
        
        # Show results
        if result["success"]:
            console.print("\n")
            console.print(Panel(
                format_quest_summary(result),
                title="✅ Quest Complete",
                border_style="green"
            ))
        else:
            console.print("\n")
            console.print(Panel(
                f"[red]Error:[/red] {result.get('error', 'Unknown error')}\n\n"
                f"Iterations: {result.get('iterations', 0)}\n"
                f"Tools used: {len(set(result.get('tools_used', [])))}",
                title="❌ Quest Failed",
                border_style="red"
            ))
    
    except KeyboardInterrupt:
        console.print("\n[yellow]Quest interrupted by user.[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Quest error: {e}[/red]")
        if verbose:
            console.print_exception()


def format_quest_summary(result: dict) -> str:
    """Format quest result as summary text"""
    lines = []
    
    # Duration
    duration = result.get('duration', 0)
    if duration < 60:
        lines.append(f"Duration: {duration:.1f}s")
    else:
        mins = int(duration // 60)
        secs = int(duration % 60)
        lines.append(f"Duration: {mins}m {secs}s")
    
    # Iterations
    lines.append(f"Iterations: {result.get('iterations', 0)}")
    
    # Tools
    tools = result.get('tools_used', [])
    if tools:
        unique_tools = list(set(tools))
        lines.append(f"Tools used: {', '.join(unique_tools[:5])}")
        if len(unique_tools) > 5:
            lines.append(f"  (+{len(unique_tools) - 5} more)")
    
    # Files
    files = result.get('files_modified', [])
    if files:
        lines.append(f"\nFiles modified ({len(files)}):")
        for f in files[:10]:
            lines.append(f"  • {f}")
        if len(files) > 10:
            lines.append(f"  (+{len(files) - 10} more)")
    
    return "\n".join(lines)


@quest_app.command()
def list():
    """List recent quests"""
    from ..agent import SessionManager
    
    workspace = Path.cwd()
    session_mgr = SessionManager(workspace)
    sessions = session_mgr.list_sessions()
    
    quest_sessions = [s for s in sessions if s.get('quest_task')]
    
    if not quest_sessions:
        console.print("[dim]No recent quests found.[/dim]")
        return
    
    console.print(Panel("Recent Quests", border_style="blue"))
    for session in quest_sessions[:10]:
        console.print(f"  • [cyan]{session['session_id']}[/cyan]")
        console.print(f"    {session.get('quest_task', 'Unknown task')[:50]}")
        console.print(f"    [dim]{session.get('created_at', '')}[/dim]")


@quest_app.command()
def resume(
    session_id: str = typer.Argument(
        ...,
        help="Session ID to resume"
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model", "-m",
        help="Model to use"
    )
):
    """Resume a previous quest"""
    from ..agent import create_agent, SessionManager
    
    workspace = Path.cwd()
    
    try:
        agent = create_agent(model_path=model, workspace=workspace)
    except Exception as e:
        console.print(f"[red]Failed to initialize agent: {e}[/red]")
        raise typer.Exit(1)
    
    # Load session
    sessions = agent.session.list_sessions()
    matching = [s for s in sessions if s['session_id'] == session_id]
    
    if not matching:
        console.print(f"[red]Session not found: {session_id}[/red]")
        raise typer.Exit(1)
    
    session_file = matching[0]['filename']
    if agent.session.load(session_file):
        console.print(f"[green]Loaded session: {session_id}[/green]")
        
        task = agent.session.quest_task
        if task:
            console.print(f"Resuming: {task[:50]}...")
            run_quest(agent, task)
        else:
            console.print("[yellow]No active quest in this session.[/yellow]")
    else:
        console.print(f"[red]Failed to load session: {session_id}[/red]")


__all__ = ['quest_app', 'run_quest']