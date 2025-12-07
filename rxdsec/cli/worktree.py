"""
Worktree CLI Command for RxDsec CLI
====================================
Git worktree management for isolated task work.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..utils import create_worktree, list_worktrees, delete_worktree, attach_worktree

# Configure module logger
logger = logging.getLogger(__name__)

# Console for output
console = Console()

# Create worktree app
worktree_app = typer.Typer(
    name="worktree",
    help="Manage git worktrees for isolated tasks"
)


@worktree_app.command("list")
def worktree_list():
    """List all active worktrees"""
    worktrees = list_worktrees()
    
    if not worktrees:
        console.print("[dim]No active worktrees.[/dim]")
        console.print("\nCreate one with: [cyan]rxdsec worktree create <task-name>[/cyan]")
        return
    
    table = Table(title="Active Worktrees", border_style="blue")
    table.add_column("ID", style="cyan")
    table.add_column("Path", style="dim")
    table.add_column("Status", style="green")
    
    for wt in worktrees:
        table.add_row(wt.id, str(wt.path), wt.status)
    
    console.print(table)


@worktree_app.command("create")
def worktree_create(
    task_slug: str = typer.Argument(
        ...,
        help="Task name/slug for the worktree"
    ),
    start_quest: bool = typer.Option(
        False,
        "--quest", "-q",
        help="Start a quest in the new worktree"
    )
):
    """Create a new worktree for a task"""
    console.print(f"[bold]Creating worktree for: {task_slug}[/bold]\n")
    
    try:
        worktree_path = create_worktree(task_slug)
        
        console.print(Panel(
            f"[green]Worktree created![/green]\n\n"
            f"Path: {worktree_path}\n"
            f"Branch: rxdsec-{task_slug}\n\n"
            f"To use: [cyan]rxdsec worktree attach {task_slug}[/cyan]",
            title="Success",
            border_style="green"
        ))
        
        if start_quest:
            console.print("\n[dim]Starting quest in new worktree...[/dim]\n")
            # Change to worktree directory
            attach_worktree(task_slug)
            
            # Start quest
            from .quest import run_quest
            from ..agent import create_agent
            
            agent = create_agent(workspace=worktree_path)
            run_quest(agent, f"Complete task: {task_slug}")
        
    except Exception as e:
        console.print(f"[red]Failed to create worktree: {e}[/red]")
        raise typer.Exit(1)


@worktree_app.command("attach")
def worktree_attach(
    id_or_name: str = typer.Argument(
        ...,
        help="Worktree ID or name to attach to"
    )
):
    """Attach to an existing worktree"""
    try:
        path = attach_worktree(id_or_name)
        console.print(f"[green]Attached to worktree at: {path}[/green]")
        console.print(f"\n[dim]Working directory changed to: {path}[/dim]")
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Failed to attach: {e}[/red]")
        raise typer.Exit(1)


@worktree_app.command("delete")
def worktree_delete(
    id_or_name: str = typer.Argument(
        ...,
        help="Worktree ID or name to delete"
    ),
    force: bool = typer.Option(
        False,
        "--force", "-f",
        help="Force deletion without confirmation"
    )
):
    """Delete a worktree"""
    if not force:
        confirm = typer.confirm(f"Delete worktree '{id_or_name}'?")
        if not confirm:
            console.print("[dim]Cancelled.[/dim]")
            return
    
    try:
        if delete_worktree(id_or_name):
            console.print(f"[green]Deleted worktree: {id_or_name}[/green]")
        else:
            console.print(f"[yellow]Worktree not found: {id_or_name}[/yellow]")
    except Exception as e:
        console.print(f"[red]Failed to delete: {e}[/red]")
        raise typer.Exit(1)


@worktree_app.command("status")
def worktree_status(
    id_or_name: Optional[str] = typer.Argument(
        None,
        help="Worktree ID (defaults to current)"
    )
):
    """Show status of a worktree"""
    import subprocess
    
    worktrees = list_worktrees()
    
    if id_or_name:
        matching = [wt for wt in worktrees if wt.id == id_or_name]
        if not matching:
            console.print(f"[red]Worktree not found: {id_or_name}[/red]")
            raise typer.Exit(1)
        wt = matching[0]
    else:
        # Show current directory status
        cwd = Path.cwd()
        matching = [wt for wt in worktrees if wt.path == cwd]
        if matching:
            wt = matching[0]
        else:
            console.print("[dim]Not in a worktree. Showing main repo status.[/dim]\n")
            wt = None
    
    if wt:
        console.print(Panel(
            f"ID: {wt.id}\n"
            f"Path: {wt.path}\n"
            f"Status: {wt.status}",
            title="Worktree Info",
            border_style="cyan"
        ))
        work_dir = wt.path
    else:
        work_dir = Path.cwd()
    
    # Show git status
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True,
            text=True,
            cwd=str(work_dir)
        )
        
        if result.stdout:
            console.print("\n[bold]Git Status:[/bold]")
            console.print(result.stdout)
        else:
            console.print("\n[dim]Working directory clean.[/dim]")
            
    except Exception as e:
        console.print(f"[red]Error getting git status: {e}[/red]")


@worktree_app.command("clean")
def worktree_clean(
    force: bool = typer.Option(
        False,
        "--force", "-f",
        help="Force cleanup without confirmation"
    )
):
    """Clean up completed/stale worktrees"""
    worktrees = list_worktrees()
    
    if not worktrees:
        console.print("[dim]No worktrees to clean.[/dim]")
        return
    
    rxdsec_worktrees = [wt for wt in worktrees if wt.id.startswith("rxdsec-") or "rxdsec" in str(wt.path)]
    
    if not rxdsec_worktrees:
        console.print("[dim]No RxDsec worktrees found.[/dim]")
        return
    
    console.print(f"Found {len(rxdsec_worktrees)} RxDsec worktree(s):\n")
    for wt in rxdsec_worktrees:
        console.print(f"  • {wt.id} ({wt.status})")
    
    if not force:
        confirm = typer.confirm("\nDelete all these worktrees?")
        if not confirm:
            console.print("[dim]Cancelled.[/dim]")
            return
    
    deleted = 0
    for wt in rxdsec_worktrees:
        try:
            if delete_worktree(str(wt.path)):
                deleted += 1
                console.print(f"  [green]✓[/green] Deleted: {wt.id}")
        except Exception as e:
            console.print(f"  [red]✗[/red] Failed: {wt.id} ({e})")
    
    console.print(f"\n[green]Cleaned {deleted} worktree(s).[/green]")


__all__ = ['worktree_app']