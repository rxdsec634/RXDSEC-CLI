"""
LPE CLI Command for RxDsec CLI
===============================
Local Protocol Extensions management.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..extensions import ExtensionManager, Extension

# Configure module logger
logger = logging.getLogger(__name__)

# Console for output
console = Console()

# Create LPE app
lpe_app = typer.Typer(
    name="lpe",
    help="Manage Local Protocol Extensions"
)


@lpe_app.command("list")
def lpe_list(
    json_output: bool = typer.Option(
        False,
        "--json", "-j",
        help="Output as JSON"
    )
):
    """List all installed extensions"""
    workspace = Path.cwd()
    manager = ExtensionManager(workspace)
    extensions = manager.load_all()
    
    if not extensions:
        console.print("[dim]No extensions installed.[/dim]")
        console.print("\nAdd one with: [cyan]rxdsec lpe add <name> <command>[/cyan]")
        return
    
    if json_output:
        console.print_json(data={n: e.to_dict() for n, e in extensions.items()})
        return
    
    table = Table(title="Installed Extensions", border_style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Description")
    table.add_column("Source", style="dim")
    table.add_column("Enabled", style="green")
    
    for name, ext in sorted(extensions.items()):
        enabled_str = "✓" if ext.enabled else "○"
        table.add_row(
            name,
            ext.description[:40] if ext.description else "-",
            ext.source,
            enabled_str
        )
    
    console.print(table)


@lpe_app.command("add")
def lpe_add(
    name: str = typer.Argument(
        ...,
        help="Extension name"
    ),
    command: str = typer.Argument(
        ...,
        help="Command to execute (quoted)"
    ),
    description: str = typer.Option(
        "",
        "--description", "-d",
        help="Extension description"
    ),
    global_install: bool = typer.Option(
        False,
        "--global", "-g",
        help="Install globally"
    )
):
    """
    Add a new extension.
    
    Examples:
        rxdsec lpe add mytest "python -m pytest"
        rxdsec lpe add lint "ruff check ." -d "Run linter"
        rxdsec lpe add format "black ." --global
    """
    workspace = Path.cwd()
    manager = ExtensionManager(workspace)
    
    try:
        ext = manager.create_from_command(name, command, description)
        manager.save(ext, local=not global_install, global_=global_install)
        
        location = "globally" if global_install else "locally"
        console.print(Panel(
            f"[green]Extension added {location}![/green]\n\n"
            f"Name: {name}\n"
            f"Command: {command}\n"
            f"Description: {description or 'None'}",
            title="Success",
            border_style="green"
        ))
        
    except Exception as e:
        console.print(f"[red]Failed to add extension: {e}[/red]")
        raise typer.Exit(1)


@lpe_app.command("remove")
def lpe_remove(
    name: str = typer.Argument(
        ...,
        help="Extension name to remove"
    ),
    global_remove: bool = typer.Option(
        False,
        "--global", "-g",
        help="Remove from global storage"
    ),
    force: bool = typer.Option(
        False,
        "--force", "-f",
        help="Skip confirmation"
    )
):
    """Remove an extension"""
    workspace = Path.cwd()
    manager = ExtensionManager(workspace)
    
    ext = manager.get_extension(name)
    if not ext:
        console.print(f"[red]Extension not found: {name}[/red]")
        raise typer.Exit(1)
    
    if not force:
        confirm = typer.confirm(f"Remove extension '{name}'?")
        if not confirm:
            console.print("[dim]Cancelled.[/dim]")
            return
    
    try:
        manager.remove(name, local=not global_remove, global_=global_remove)
        console.print(f"[green]Removed extension: {name}[/green]")
    except Exception as e:
        console.print(f"[red]Failed to remove: {e}[/red]")
        raise typer.Exit(1)


@lpe_app.command("enable")
def lpe_enable(
    name: str = typer.Argument(
        ...,
        help="Extension name to enable"
    )
):
    """Enable an extension"""
    workspace = Path.cwd()
    manager = ExtensionManager(workspace)
    
    ext = manager.get_extension(name)
    if not ext:
        console.print(f"[red]Extension not found: {name}[/red]")
        raise typer.Exit(1)
    
    manager.enable(name, enabled=True)
    console.print(f"[green]Enabled: {name}[/green]")


@lpe_app.command("disable")
def lpe_disable(
    name: str = typer.Argument(
        ...,
        help="Extension name to disable"
    )
):
    """Disable an extension"""
    workspace = Path.cwd()
    manager = ExtensionManager(workspace)
    
    ext = manager.get_extension(name)
    if not ext:
        console.print(f"[red]Extension not found: {name}[/red]")
        raise typer.Exit(1)
    
    manager.enable(name, enabled=False)
    console.print(f"[yellow]Disabled: {name}[/yellow]")


@lpe_app.command("show")
def lpe_show(
    name: str = typer.Argument(
        ...,
        help="Extension name to show"
    )
):
    """Show extension details"""
    workspace = Path.cwd()
    manager = ExtensionManager(workspace)
    
    ext = manager.get_extension(name)
    if not ext:
        console.print(f"[red]Extension not found: {name}[/red]")
        raise typer.Exit(1)
    
    console.print(Panel(
        f"[bold]Name:[/bold] {ext.name}\n"
        f"[bold]Description:[/bold] {ext.description or 'None'}\n"
        f"[bold]Version:[/bold] {ext.version}\n"
        f"[bold]Author:[/bold] {ext.author or 'Unknown'}\n"
        f"[bold]Source:[/bold] {ext.source}\n"
        f"[bold]Enabled:[/bold] {'Yes' if ext.enabled else 'No'}\n"
        f"[bold]Timeout:[/bold] {ext.timeout}s\n\n"
        f"[bold]Command:[/bold]\n  {' '.join(ext.command)}",
        title=f"Extension: {name}",
        border_style="cyan"
    ))


@lpe_app.command("run")
def lpe_run(
    name: str = typer.Argument(
        ...,
        help="Extension name to run"
    ),
    args: Optional[str] = typer.Argument(
        None,
        help="Additional arguments"
    )
):
    """Run an extension directly"""
    import subprocess
    
    workspace = Path.cwd()
    manager = ExtensionManager(workspace)
    
    ext = manager.get_extension(name)
    if not ext:
        console.print(f"[red]Extension not found: {name}[/red]")
        raise typer.Exit(1)
    
    if not ext.enabled:
        console.print(f"[yellow]Warning: Extension '{name}' is disabled[/yellow]")
    
    cmd = ext.command.copy()
    if args:
        cmd.extend(args.split())
    
    console.print(f"[dim]Running: {' '.join(cmd)}[/dim]\n")
    
    try:
        result = subprocess.run(
            cmd,
            cwd=str(workspace),
            timeout=ext.timeout
        )
        
        if result.returncode != 0:
            raise typer.Exit(result.returncode)
            
    except subprocess.TimeoutExpired:
        console.print(f"[red]Command timed out after {ext.timeout}s[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@lpe_app.command("import")
def lpe_import(
    file_path: Path = typer.Argument(
        ...,
        help="JSON file with extensions to import"
    ),
    global_install: bool = typer.Option(
        False,
        "--global", "-g",
        help="Import globally"
    )
):
    """Import extensions from a JSON file"""
    if not file_path.exists():
        console.print(f"[red]File not found: {file_path}[/red]")
        raise typer.Exit(1)
    
    try:
        with open(file_path) as f:
            data = json.load(f)
        
        workspace = Path.cwd()
        manager = ExtensionManager(workspace)
        
        imported = 0
        for name, ext_data in data.items():
            try:
                ext = Extension.from_dict(ext_data)
                ext.name = name
                manager.save(ext, local=not global_install, global_=global_install)
                imported += 1
                console.print(f"  [green]✓[/green] {name}")
            except Exception as e:
                console.print(f"  [red]✗[/red] {name}: {e}")
        
        console.print(f"\n[green]Imported {imported} extension(s).[/green]")
        
    except json.JSONDecodeError:
        console.print("[red]Invalid JSON file[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Import failed: {e}[/red]")
        raise typer.Exit(1)


@lpe_app.command("export")
def lpe_export(
    output: Optional[Path] = typer.Argument(
        None,
        help="Output file (defaults to stdout)"
    )
):
    """Export extensions to JSON"""
    workspace = Path.cwd()
    manager = ExtensionManager(workspace)
    extensions = manager.load_all()
    
    data = {name: ext.to_dict() for name, ext in extensions.items()}
    json_str = json.dumps(data, indent=2)
    
    if output:
        output.write_text(json_str)
        console.print(f"[green]Exported to: {output}[/green]")
    else:
        console.print(json_str)


__all__ = ['lpe_app']