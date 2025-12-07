"""
Advanced TUI for RxDsec CLI
============================
Interactive terminal user interface with Rich rendering and prompt_toolkit input.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Callable, List, Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completer, Completion, PathCompleter, merge_completers
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.application import run_in_terminal
from prompt_toolkit.styles import Style

# Global state for Ctrl+R expansion
_LAST_TOOL_OUTPUT = None
from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.spinner import Spinner as RichSpinner

from ..agent import RxDsecAgent
from ..output import render_output
from ..utils import Spinner

# Configure module logger
logger = logging.getLogger(__name__)


# TUI prompt style
PROMPT_STYLE = Style.from_dict({
    'prompt': '#00aa00 bold',
    'path': '#888888',
})

# Slash commands
SLASH_COMMANDS = {
    '/quest': 'Start an autonomous quest',
    '/review': 'Review git changes',
    '/memory': 'Show/manage project memory',
    '/agents': 'List available sub-agents',
    '/jobs': 'List active worktrees/jobs',
    '/clear': 'Clear the screen',
    '/status': 'Show agent status',
    '/save': 'Save current session',
    '/load': 'Load a previous session',
    '/help': 'Show help',
    '/quit': 'Exit RxDsec',
}


class CommandCompleter(Completer):
    """Completer for slash commands"""
    
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        
        if text.startswith('/'):
            word = text[1:]  # Remove leading slash
            for cmd, desc in SLASH_COMMANDS.items():
                if cmd[1:].startswith(word):
                    yield Completion(
                        cmd,
                        start_position=-len(text),
                        display_meta=desc
                    )


class FileCompleter(Completer):
    """Completer for @ file references"""
    
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self._path_completer = PathCompleter()
    
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        
        # Check for @ prefix
        at_pos = text.rfind('@')
        if at_pos == -1:
            return
        
        path_text = text[at_pos + 1:]
        
        # Find files matching the partial path
        try:
            if path_text:
                search_path = self.workspace / path_text
                parent = search_path.parent
                prefix = search_path.name
            else:
                parent = self.workspace
                prefix = ""
            
            if parent.exists():
                for item in parent.iterdir():
                    if item.name.startswith(prefix):
                        relative = item.relative_to(self.workspace)
                        display = f"@{relative}"
                        yield Completion(
                            display,
                            start_position=-(len(path_text) + 1),
                            display_meta="dir" if item.is_dir() else "file"
                        )
        except Exception:
            pass


class TUICompleter(Completer):
    """Combined completer for TUI"""
    
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.command_completer = CommandCompleter()
        self.file_completer = FileCompleter(workspace)
    
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        
        if text.startswith('/'):
            yield from self.command_completer.get_completions(document, complete_event)
        elif '@' in text:
            yield from self.file_completer.get_completions(document, complete_event)


def print_welcome_banner(console: Console, agent=None, workspace=None):
    """Print customized welcome banner with Indian flag theme"""
    from .. import __version__
    from pathlib import Path
    from rich.align import Align
    from rich.table import Table
    from rich.text import Text
    import os
    
    workspace = workspace or Path.cwd()
    
    # Robust clear
    os.system('cls' if os.name == 'nt' else 'clear')
    console.clear() 
    
    # ASCII Art split into 3 bands for Indian Flag colors
    # Saffron (Top), White (Middle), Green (Bottom)
    
    # Top 2 lines - Saffron (#FF9933)
    art_saffron = (
        "   ██████╗ ██╗  ██╗██████╗ ███████╗███████╗ ██████╗     \n"
        "   ██╔══██╗╚██╗██╔╝██╔══██╗██╔════╝██╔════╝██╔════╝     "
    )
    
    # Middle 2 lines - White (#FFFFFF)
    art_white = (
        "   ██████╔╝ ╚███╔╝ ██║  ██║███████╗█████╗  ██║          \n"
        "   ██╔══██╗ ██╔██╗ ██║  ██║╚════██║██╔══╝  ██║          "
    )
    
    # Bottom 2 lines - Green (#138808)
    art_green = (
        "   ██║  ██║██╔╝ ██╗██████╔╝███████║███████╗╚██████╗     \n"
        "   ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝ ╚══════╝ ╚══════╝ ╚═════╝     "
    )
    
    # Assemble the colored text
    banner_text = Text()
    banner_text.append(art_saffron + "\n", style="#FF9933")
    banner_text.append(art_white + "\n", style="white")
    banner_text.append(art_green + "\n", style="#138808")
    
    # Subtitle
    banner_text.append("\n          Local GGUF-Only Agentic Coding Terminal", style="dim italic")
    banner_text.append("\n          Developed by RxDsec from Telegram,Instagram", style="bold cyan")
    
    # Create Info Block (Right side)
    info_text = Text()
    info_text.append(f"Version:   ", style="bold")
    info_text.append(f"v{__version__}\n", style="green")
    
    info_text.append(f"Directory: ", style="bold")
    info_text.append(f"{workspace.name}\n", style="blue")
    
    if agent:
        model_name = Path(agent.model_path).name if agent.model_path else "Unknown"
        # Truncate model name if too long
        if len(model_name) > 30:
            model_name = model_name[:27] + "..."
            
        tool_count = len(agent.tools.tools) if hasattr(agent, 'tools') else 0
        info_text.append(f"Model:     ", style="bold")
        info_text.append(f"{model_name}\n", style="yellow")
        info_text.append(f"Tools:     ", style="bold")
        info_text.append(f"{tool_count} available\n", style="cyan")
        info_text.append(f"Status:    ", style="bold")
        info_text.append(f"● Ready\n", style="green")
    else:
        info_text.append(f"Status:    ", style="bold")
        info_text.append(f"○ No agent loaded\n", style="yellow")

    # Layout using a grid table (invisible borders)
    grid = Table.grid(padding=5)
    
    # Banner column: justify="left" preserves ASCII art spacing
    grid.add_column(justify="left") 
    grid.add_column(justify="left", vertical="middle") # Info column
    
    grid.add_row(banner_text, info_text)
    
    # Print centered
    console.print()
    console.print(Align.center(grid))
    console.print()
    console.print(Align.center("[dim]Type /help for commands, or just start chatting![/dim]\n"))


def handle_slash_command(
    command: str,
    agent: RxDsecAgent,
    console: Console
) -> bool:
    """
    Handle a slash command.
    
    Args:
        command: The slash command (e.g., "/help")
        agent: The agent instance
        console: Rich console
    
    Returns:
        True if should continue, False to exit
    """
    parts = command.split(maxsplit=1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    
    if cmd == '/quit' or cmd == '/exit' or cmd == '/q':
        console.print("[dim]Goodbye![/dim]")
        return False
    
    elif cmd == '/help' or cmd == '/?':
        console.print(Panel(
            "\n".join(f"  [cyan]{c}[/cyan] - {d}" for c, d in SLASH_COMMANDS.items()),
            title="Commands",
            border_style="blue"
        ))
        console.print("\n[dim]Input prefixes:[/dim]")
        console.print("  [cyan]>[/cyan] message  - Send to agent")
        console.print("  [cyan]![/cyan] command  - Execute shell command")
        console.print("  [cyan]#[/cyan] note     - Add note to memory")
        console.print("  [cyan]@[/cyan] file     - Read file content\n")
    
    elif cmd == '/clear':
        console.clear()
        print_welcome_banner(console)
    
    elif cmd == '/status':
        summary = agent.session.get_summary()
        console.print(Panel(
            f"Session: {summary['session_id']}\n"
            f"Messages: {summary['message_count']}\n"
            f"Tokens: ~{summary['estimated_tokens']}\n"
            f"Quest: {'Active' if summary['quest_active'] else 'None'}",
            title="Status",
            border_style="blue"
        ))
    
    elif cmd == '/memory':
        memory = agent.get_memory()
        console.print(Panel(
            agent.memory.get_context(),
            title="Project Memory",
            border_style="cyan"
        ))
    
    elif cmd == '/agents':
        agent_list = agent.subagents.list_agents()
        if agent_list:
            lines = []
            for a in agent_list:
                lines.append(f"  • [bold]{a['name']}[/bold] - {a.get('description', 'No description')}")
            console.print(Panel("\n".join(lines), title="Available Agents", border_style="cyan"))
        else:
            console.print("[dim]No agents configured.[/dim]")
    
    elif cmd == '/jobs':
        from ..utils import list_worktrees
        worktrees = list_worktrees()
        if worktrees:
            for wt in worktrees:
                console.print(f"  • [cyan]{wt.id}[/cyan] - {wt.path} ({wt.status})")
        else:
            console.print("[dim]No active worktrees.[/dim]")
    
    elif cmd == '/quest':
        if args:
            handle_quest(args, agent, console)
        else:
            console.print("[yellow]Usage: /quest <task description>[/yellow]")
    
    elif cmd == '/review':
        handle_review(agent, console)
    
    elif cmd == '/save':
        path = agent.session.save()
        console.print(f"[green]Session saved: {path.name}[/green]")
    
    elif cmd == '/load':
        sessions = agent.session.list_sessions()
        if sessions:
            console.print("Available sessions:")
            for s in sessions[:10]:
                console.print(f"  • {s['filename']} ({s['message_count']} messages)")
            
            if args:
                if agent.session.load(args):
                    console.print(f"[green]Loaded: {args}[/green]")
                else:
                    console.print(f"[red]Failed to load: {args}[/red]")
        else:
            console.print("[dim]No saved sessions.[/dim]")
    
    else:
        console.print(f"[yellow]Unknown command: {cmd}[/yellow]")
    
    return True


def handle_quest(task: str, agent: RxDsecAgent, console: Console):
    """Handle an autonomous quest"""
    console.print(f"\n[bold cyan]Starting Quest:[/bold cyan] {task}\n")
    
    def on_step(message: str, step: int):
        console.print(f"  [dim]Step {step}:[/dim] {message}")
    
    try:
        with Spinner("Running quest...") as spinner:
            result = agent.run_quest(task, on_step=on_step)
        
        if result["success"]:
            console.print(Panel(
                f"✓ Quest completed in {result.get('duration', 0):.1f}s\n"
                f"Files modified: {len(result.get('files_modified', []))}",
                title="Quest Complete",
                border_style="green"
            ))
        else:
            console.print(Panel(
                f"✗ Quest failed: {result.get('error', 'Unknown error')}",
                title="Quest Failed",
                border_style="red"
            ))
    
    except Exception as e:
        console.print(f"[red]Quest error: {e}[/red]")


def handle_review(agent: RxDsecAgent, console: Console):
    """Handle code review"""
    import subprocess
    
    try:
        result = subprocess.run(
            ["git", "diff", "--staged"],
            capture_output=True,
            text=True,
            cwd=str(agent.workspace)
        )
        
        if not result.stdout.strip():
            result = subprocess.run(
                ["git", "diff"],
                capture_output=True,
                text=True,
                cwd=str(agent.workspace)
            )
        
        if not result.stdout.strip():
            console.print("[dim]No changes to review.[/dim]")
            return
        
        diff = result.stdout
        
        console.print("[bold]Reviewing changes...[/bold]\n")
        
        response = agent.generate(
            f"Please review these code changes:\n\n```diff\n{diff[:5000]}\n```",
            stream=False
        )
        
        console.print(render_output(response))
        
    except Exception as e:
        console.print(f"[red]Review error: {e}[/red]")


def handle_shell_command(command: str, console: Console, workspace: Path):
    """Execute a shell command"""
    import subprocess
    
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=str(workspace)
        )
        
        if result.stdout:
            console.print(result.stdout.rstrip())
        if result.stderr:
            console.print(f"[red]{result.stderr.rstrip()}[/red]")
        
        if result.returncode != 0:
            console.print(f"[dim]Exit code: {result.returncode}[/dim]")
            
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


def handle_file_read(path: str, console: Console, workspace: Path):
    """Read and display a file"""
    try:
        full_path = (workspace / path).resolve()
        
        if not full_path.exists():
            console.print(f"[red]File not found: {path}[/red]")
            return
        
        with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        
        # Detect language for syntax highlighting
        from ..output import highlight_code, detect_language
        language = detect_language(content, str(full_path))
        
        console.print(Panel(
            highlight_code(content[:5000], language),
            title=path,
            border_style="cyan"
        ))
        
        if len(content) > 5000:
            console.print(f"[dim]... ({len(content) - 5000} more characters)[/dim]")
            
    except Exception as e:
        console.print(f"[red]Error reading file: {e}[/red]")


def handle_note(note: str, agent: RxDsecAgent, console: Console):
    """Add a note to memory"""
    agent.add_note(note)
    console.print(f"[green]Note added:[/green] {note[:50]}...")


def handle_chat(message: str, agent: RxDsecAgent, console: Console):
    """Handle regular chat with the agent"""
    import re
    from ..output.visual import VisualFormatter, BULLET
    
    formatter = VisualFormatter(console)
    
    def clean_response(text: str) -> str:
        """Remove prompt tokens and fake user messages from response"""
        # Remove chat template tokens
        text = re.sub(r'<\|im_start\|>(user|assistant|system)', '', text)
        text = re.sub(r'<\|im_end\|>', '', text)
        text = re.sub(r'<\|endoftext\|>', '', text)
        
        # Remove any text that looks like fake user prompts
        # Stop at first occurrence of user-like patterns
        patterns_to_cut = [
            r'\n(User|Human|Question|Q):.*$',
            r'\nCan (I|you|we) .*\?.*$',
            r'\nHow (can|do|would) .*\?.*$',
            r'\nWhat (is|are|would) .*\?.*$',
        ]
        
        for pattern in patterns_to_cut:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                text = text[:match.start()]
        
        return text.strip()
    
    try:
        # ReAct Loop: Run up to 25 turns for complex tasks
        max_turns = 25
        current_message = message
        
        for turn in range(max_turns):
            with console.status("[bold cyan]Thinking...[/bold cyan]", spinner="dots"):
                # Generate response
                response_chunks = []
                for chunk in agent.generate(current_message, stream=True):
                    response_chunks.append(chunk)
            
            full_response = ''.join(response_chunks)
            cleaned = clean_response(full_response)
            
            # Check for tool calls
            # STRICTLY execute only the FIRST tool found to enforce step-by-step
            # This prevents the model from running ahead or getting confused
            all_tool_calls = agent.parse_tools(cleaned)
            tool_results = []
            
            if all_tool_calls:
                # Take only the first tool
                first_tool = all_tool_calls[0]
                
                # Execute it
                result = agent._execute_tool(first_tool)
                tool_results = [(first_tool, result)]
                
                # If there were other tools, we ignore them for this turn.
                # The model will naturally regenerate the next steps in the next turn
                # based on the feedback of this first tool.
            
            if not tool_results:
                # No tools - this is the final answer or just thought
                lines = cleaned.split('\n')
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith('```'):
                        console.print(formatter.format_thought(line))
                break # End loop if no tools called
            
            # If we have tools, display them and execution results
            # Display thoughts (only text BEFORE the tool call)
            # Find the position of the first tool call in the text
            tool_pos = cleaned.find(first_tool.name)
            if tool_pos != -1:
                 # Rough heuristic to get text before tool
                 pre_text = cleaned[:tool_pos].split('Tool:', 1)[0]
                 for line in pre_text.split('\n'):
                    if line.strip():
                        console.print(formatter.format_thought(line.strip()))
            
            # Display execution
            tool_outputs = []
            for tool_call, result in tool_results:
                # Use error message if output is empty and tool failed
                display_output = result.output
                if not display_output and result.error:
                    display_output = f"Error: {result.error}"
                elif not display_output:
                    display_output = "(no output)"
                    
                console.print(formatter.format_tool_call(
                    tool_call.name,
                    ", ".join(f'{k}="{v}"' for k, v in tool_call.args.items()),
                    display_output[:1000],
                    success=result.success
                ))
                tool_outputs.append(f"Tool {tool_call.name} returned: {display_output}")
            
            # Feed result back to agent context for next turn
            # We append the result to conversation history inside agent.generate typically
            # But since we're managing the loop here, we need to invoke agent with the result
            
            output_msg = []
            has_error = False
            for tool_call, result in tool_results:
                status = "successfully" if result.success else "failed"
                output_msg.append(f"Tool '{tool_call.name}' executed {status}.\nOutput:\n{result.output}")
                
                # Update global last output for Ctrl+R
                global _LAST_TOOL_OUTPUT
                _LAST_TOOL_OUTPUT = result.output
                
                if not result.success:
                    has_error = True
            
            combined_output = "\n".join(output_msg)
            
            if has_error:
                current_message = combined_output + "\n\nThe tool execution failed. Please analyze the error above and try a DIFFERENT approach or fix the arguments."
            else:
                current_message = combined_output + "\n\nThe tool succeeded. DO NOT repeat this tool call. Explain what the output means and determine the next step."
            
            # Add result to memory implicitly via generate (which adds user msg)
            if turn == max_turns - 1:
                console.print("[dim]Max turns reached. Stopping.[/dim]")

    except KeyboardInterrupt:
        console.print("\n[dim]Generation interrupted.[/dim]")
        
    except KeyboardInterrupt:
        console.print("\n[dim]Generation interrupted.[/dim]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("Chat error")


def run_tui(agent: RxDsecAgent, console: Optional[Console] = None):
    """
    Run the interactive TUI.
    
    Args:
        agent: The RxDsec agent
        console: Optional Rich console
    """
    console = console or Console()
    workspace = agent.workspace
    
    # Print welcome with agent info
    print_welcome_banner(console, agent=agent, workspace=workspace)
    
    # Set up prompt session
    history_file = workspace / ".rxdsec" / ".history"
    history_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Key bindings
    kb = KeyBindings()
    
    @kb.add('c-r')
    def _(event):
        """Expand last tool output"""
        if _LAST_TOOL_OUTPUT:
            def show_full():
               with console.pager(styles=True):
                   console.print(Panel(_LAST_TOOL_OUTPUT, title="Full Tool Output (Press 'q' or 'ESC' to exit)", border_style="blue"))
            run_in_terminal(show_full)
        else:
            def show_empty():
                console.print("[yellow]No tool recently executed to expand![/yellow]")
            run_in_terminal(show_empty)
    
    session = PromptSession(
        history=FileHistory(str(history_file)),
        auto_suggest=AutoSuggestFromHistory(),
        completer=TUICompleter(workspace),
        style=PROMPT_STYLE,
        key_bindings=kb
    )
    
    # Main loop
    while True:
        try:
            # Get prompt
            cwd = Path.cwd()
            try:
                relative = cwd.relative_to(workspace)
                path_display = str(relative) if str(relative) != '.' else ''
            except ValueError:
                path_display = str(cwd)
            
            prompt_text = [
                ('class:prompt', 'RxDsec'),
                ('class:path', f' {path_display}' if path_display else ''),
                ('class:prompt', ' ❯ '),
            ]
            
            user_input = session.prompt(prompt_text).strip()
            
            if not user_input:
                continue
            
            # Handle different input types
            if user_input.startswith('/'):
                if not handle_slash_command(user_input, agent, console):
                    break
            
            elif user_input.startswith('!'):
                handle_shell_command(user_input[1:].strip(), console, workspace)
            
            elif user_input.startswith('@'):
                handle_file_read(user_input[1:].strip(), console, workspace)
            
            elif user_input.startswith('#'):
                handle_note(user_input[1:].strip(), agent, console)
            
            elif user_input.startswith('>'):
                handle_chat(user_input[1:].strip(), agent, console)
            
            else:
                # Default: send to agent
                handle_chat(user_input, agent, console)
            
        except KeyboardInterrupt:
            console.print("\n[dim]Use /quit to exit[/dim]")
            continue
        except EOFError:
            break
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            logger.exception("TUI error")
    
    console.print("\n[dim]Session ended.[/dim]")


__all__ = ['run_tui', 'print_welcome_banner', 'SLASH_COMMANDS']