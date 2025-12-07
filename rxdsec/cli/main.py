"""
Advanced CLI Main for RxDsec CLI
=================================
Typer-based CLI with global options, subcommands, and configuration.
"""

from __future__ import annotations

import logging
import platform
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from ..agent import RxDsecAgent, create_agent
from ..utils import setup_logging
from .tui import run_tui
from .quest import quest_app
from .review import review_app
from .worktree import worktree_app
from .lpe import lpe_app

# Console for Rich output
console = Console()

# Create Typer app
app = typer.Typer(
    name="rxdsec",
    help="RxDsec CLI - Fully Local GGUF-Only Agentic Coding Terminal",
    no_args_is_help=False,
    add_completion=True,
    rich_markup_mode="rich"
)

# Register subcommands
app.add_typer(quest_app, name="quest", help="Run autonomous quests")
app.add_typer(review_app, name="review", help="Review code changes")
app.add_typer(worktree_app, name="worktree", help="Manage git worktrees")
app.add_typer(lpe_app, name="lpe", help="Manage Local Protocol Extensions")


# Global state
class AppState:
    """Global application state"""
    agent: Optional[RxDsecAgent] = None
    workspace: Path = Path.cwd()
    model_path: Optional[str] = None
    verbose: bool = False


state = AppState()


def version_callback(value: bool):
    """Print version and exit"""
    if value:
        from .. import __version__
        console.print(f"RxDsec CLI v{__version__}")
        raise typer.Exit()


def find_model(model_path: Optional[str], workspace: Path) -> Optional[str]:
    """Auto-detect model if not specified"""
    if model_path:
        if Path(model_path).exists():
            return model_path
        console.print(f"[red]Model not found: {model_path}[/red]")
        raise typer.Exit(1)
    
    # Search paths
    search_paths = [
        workspace / "models",
        workspace / "rxdsec" / "models",
        Path.home() / ".rxdsec" / "models",
        Path.home() / "models"
    ]
    
    for path in search_paths:
        if path.exists():
            gguf_files = list(path.glob("*.gguf"))
            if gguf_files:
                console.print(f"[dim]Auto-detected model: {gguf_files[0].name}[/dim]")
                return str(gguf_files[0])
    
    return None


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    model: Optional[str] = typer.Option(
        None,
        "--model", "-m",
        help="Path to GGUF model file"
    ),
    workspace: Optional[Path] = typer.Option(
        None,
        "--workspace", "-w",
        help="Working directory"
    ),
    gpu_layers: int = typer.Option(
        0,
        "--gpu-layers", "-g",
        help="Number of layers to offload to GPU"
    ),
    ctx_size: int = typer.Option(
        8192,
        "--ctx", "-c",
        help="Context window size"
    ),
    temperature: float = typer.Option(
        0.7,
        "--temperature", "-t",
        help="Sampling temperature"
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="Enable verbose output"
    ),
    version: bool = typer.Option(
        None,
        "--version", "-V",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit"
    )
):
    """
    RxDsec CLI - Your local AI coding assistant.
    
    Run without arguments to start the interactive TUI.
    
    [dim]Examples:[/dim]
        rxdsec                      # Start interactive mode
        rxdsec quest "Add tests"    # Run autonomous quest
        rxdsec review               # Review git changes
        rxdsec --model path.gguf    # Use specific model
    """
    # Set up state
    state.workspace = workspace or Path.cwd()
    state.verbose = verbose
    
    # Set up logging
    setup_logging(verbose=verbose)
    logger = logging.getLogger(__name__)
    
    # Find model
    state.model_path = find_model(model, state.workspace)
    
    # If no subcommand, start TUI
    if ctx.invoked_subcommand is None:
        if not state.model_path:
            console.print(Panel(
                "[yellow]No model found![/yellow]\n\n"
                "Please provide a model using one of these options:\n"
                "  • [cyan]--model path/to/model.gguf[/cyan]\n"
                "  • Place a .gguf file in ./models/\n"
                "  • Place a .gguf file in ~/.rxdsec/models/",
                title="Model Required",
                border_style="yellow"
            ))
            raise typer.Exit(1)
        
        try:
            # Initialize agent
            state.agent = RxDsecAgent(
                model_path=state.model_path,
                workspace=state.workspace,
                n_gpu_layers=gpu_layers,
                n_ctx=ctx_size,
                temperature=temperature,
                verbose=verbose,
                load_immediately=True  # Load model immediately for CLI
            )

            # Run TUI
            run_tui(state.agent, console=console)
            
        except Exception as e:
            if verbose:
                console.print_exception()
            else:
                console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1)


@app.command()
def status():
    """Show current status and configuration"""
    from .. import __version__
    
    info = {
        "Version": __version__,
        "Platform": platform.system(),
        "Python": platform.python_version(),
        "Workspace": str(state.workspace),
        "Model": state.model_path or "Not loaded"
    }
    
    # Check for CUDA
    try:
        import torch
        if torch.cuda.is_available():
            info["GPU"] = torch.cuda.get_device_name(0)
        else:
            info["GPU"] = "Not available"
    except ImportError:
        info["GPU"] = "PyTorch not installed"
    
    # Format output
    text = Text()
    for key, value in info.items():
        text.append(f"  {key}: ", style="bold")
        text.append(f"{value}\n")
    
    console.print(Panel(
        text,
        title="RxDsec Status",
        border_style="blue"
    ))


@app.command()
def config():
    """Show or edit configuration"""
    config_file = state.workspace / ".rxdsec" / "config.yaml"
    
    if not config_file.exists():
        console.print("[dim]No configuration file found.[/dim]")
        console.print(f"Create one at: {config_file}")
        return
    
    import yaml
    with open(config_file) as f:
        cfg = yaml.safe_load(f)
    
    console.print_json(data=cfg)


@app.command()
def models():
    """List available models"""
    search_paths = [
        state.workspace / "models",
        Path.home() / ".rxdsec" / "models",
    ]
    
    found_models = []
    
    for path in search_paths:
        if path.exists():
            for gguf in path.glob("*.gguf"):
                size_mb = gguf.stat().st_size / (1024 * 1024)
                found_models.append({
                    "name": gguf.name,
                    "path": str(gguf),
                    "size": f"{size_mb:.1f}MB"
                })
    
    if not found_models:
        console.print("[yellow]No models found.[/yellow]")
        console.print("\nPlace .gguf files in:")
        for path in search_paths:
            console.print(f"  • {path}")
        return
    
    console.print(Panel("Available Models", border_style="blue"))
    for model in found_models:
        console.print(f"  • [cyan]{model['name']}[/cyan] ({model['size']})")
        console.print(f"    [dim]{model['path']}[/dim]")


@app.command()
def agents():
    """List available sub-agents"""
    from ..agent import SubAgentLoader
    
    loader = SubAgentLoader(state.workspace)
    agent_list = loader.list_agents()
    
    if not agent_list:
        console.print("[dim]No agents available.[/dim]")
        return
    
    console.print(Panel("Available Agents", border_style="cyan"))
    for agent in agent_list:
        keywords = ", ".join(agent.get("keywords", [])[:3])
        console.print(f"  • [bold]{agent['name']}[/bold] ({agent['source']})")
        console.print(f"    {agent.get('description', 'No description')}")
        if keywords:
            console.print(f"    [dim]Keywords: {keywords}[/dim]")


def main_entry():
    """Entry point for the CLI"""
    try:
        app()
    except KeyboardInterrupt:
        console.print("\n[dim]Goodbye![/dim]")
        sys.exit(0)


if __name__ == "__main__":
    main_entry()