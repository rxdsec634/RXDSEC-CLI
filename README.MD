# RxDsec CLI - Fully Local GGUF-Only Agentic Coding Terminal

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Status](https://img.shields.io/badge/status-production-green.svg)](https://github.com/rxdsec/rxdsec)

**RxDsec CLI** is a fully local, GGUF-only AI coding assistant that runs entirely on your machine. No internet connection required - it works completely offline using local models for enhanced privacy and security.

rxdsec.png

## Features

### 🧠 Advanced AI Agent
- **Local Processing**: All AI processing happens on your machine using GGUF models
- **Tool Calling**: Sophisticated tool parsing and execution system
- **Memory Management**: Persistent project memory with YAML storage
- **Session Management**: Conversation history with automatic context pruning

### 🛠️ Comprehensive Tool Set
- **File Operations**: Read, write, patch files with safety features
- **Code Search**: Advanced grep and find with ripgrep fallback
- **Shell Execution**: Safe command execution with sandboxing
- **Web Tools**: Controlled web access with domain filtering
- **Todo Management**: Track tasks and progress

### 🔐 Security First
- **Permission System**: YAML-based permission management with category rules
- **Sandboxed Execution**: Safe command execution with path validation
- **Domain Filtering**: Controlled web access to trusted domains only
- **Path Sanitization**: Prevents directory traversal attacks

### 🎨 Rich User Experience
- **Modern TUI**: Interactive terminal interface with rich formatting
- **Multiple Input Modes**: Slash commands, file reading, shell execution, notes
- **Syntax Highlighting**: Code blocks with 80+ language support
- **Visual Formatting**: Professional output with emojis and styling

### 🚀 Extensibility
- **Hooks System**: Event-driven extensibility with lifecycle events
- **Local Protocol Extensions (LPE)**: Custom tool registration system
- **Worktree Management**: Isolated development environments for tasks
- **Sub-Agent Support**: Specialized roles with keyword matching

## Installation

### Prerequisites
- Python 3.8 or higher
- Git (for worktree features)
- A GGUF model file (e.g., from Hugging Face or Ollama)

### Installation Steps

1. **Clone the repository** (optional, if developing):
   ```bash
   git clone https://github.com/rxdsec634/RXDSEC-CLI.git
   cd rxdsec
   ```

2. **Install the package**:
   ```bash
   pip install -e .
   # Or if installing from PyPI when available
   pip install rxdsec-cli
   ```

3. **Install optional dependencies** (recommended):
   ```bash
   pip install llama-cpp-python[server]  # For model support
   pip install requests  # For web tools
   pip install pygments  # For syntax highlighting
   ```

4. **Install ripgrep for better performance** (optional but recommended):
   - **Ubuntu/Debian**: `sudo apt install ripgrep`
   - **macOS**: `brew install ripgrep`
   - **Windows**: Download from [ripgrep releases](https://github.com/BurntSushi/ripgrep/releases)

## Quick Start

### 1. Download a GGUF Model
You'll need a GGUF model file. Some popular options:
- [Mistral 7B Instruct](https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.1-GGUF) (Recommended for coding)
- [CodeLlama 7B](https://huggingface.co/TheBloke/CodeLlama-7B-GGUF)
- [WizardCoder](https://huggingface.co/TheBloke/WizardCoder-15B-1.0-GGUF)

### 2. Run the CLI
```bash
# Start with default settings (auto-detects model in ./models/)
rxdsec

# Or specify model path explicitly
rxdsec --model /path/to/model.gguf

# With GPU acceleration (if available)
rxdsec --model /path/to/model.gguf --gpu-layers 20

# Start a coding quest
rxdsec quest "Refactor the authentication module"
```

### 3. Interactive TUI Commands
Once in the TUI, you can use:

**Chat Commands**:
- `> message` - Send to agent
- `message` - Send to agent (default)

**File Commands**:
- `@filepath` - Read file content
- `#note` - Add a note to memory

**Shell Commands**:
- `!command` - Execute shell command

**Special Commands**:
- `/help` - Show all commands
- `/quest <task>` - Start autonomous coding task
- `/memory` - View project memory
- `/agents` - List available sub-agents
- `/status` - Show agent status
- `/save` - Save current session
- `/load` - Load a previous session
- `/clear` - Clear screen
- `/quit` - Exit

## Advanced Usage

### Model Configuration
RxDsec will auto-detect models in these locations:
- `./models/` (relative to current directory)
- `~/.rxdsec/models/`
- `~/models/`

### Configuration Files
Configuration files are stored in `~/.rxdsec/`:
- `permissions.yaml` - Permission rules
- `hooks.yaml` - Event hooks
- `lpe.json` - Local Protocol Extensions
- `AGENTS.yaml` - Project memory (in project directory)

### Sub-Agents
RxDsec comes with specialized agents:
- **CodeR** - Expert code writer and refactoring
- **Reviewer** - Code review specialist  
- **Debugger** - Bug hunting expert
- **Architect** - System design specialist
- **Documenter** - Documentation writer

Use with: `/quest --agent debugger "Fix the login bug"`

### Worktree Management
Isolate work on different tasks:
```bash
rxdsec worktree create feature-x          # Create isolated worktree
rxdsec worktree attach feature-x          # Switch to worktree
rxdsec worktree list                      # List worktrees
rxdsec worktree delete feature-x          # Delete worktree
```

## Configuration

### Permission Management
Control what the agent can access:
```bash
rxdsec --help  # See all options
rxdsec lpe --help  # Extension management
```

Example permission presets:
- `security` - Maximum restrictions, all writes require confirmation
- `open` - Minimal restrictions, allow everything (not recommended)
- `readonly` - Read-only access to files

### Extensions (LPE)
Add custom tools:
```bash
# Add a custom tool
rxdsec lpe add mytest "python -m pytest tests/" -d "Run project tests"

# List extensions
rxdsec lpe list

# Run an extension
rxdsec lpe run mytest
```

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│     Agent       │    │      CLI        │    │    Tools        │
│  ┌───────────┐  │    │  ┌───────────┐  │    │  ┌───────────┐  │
│  │ Core      │  │    │  │ TUI       │  │    │  │ Read/Write│  │
│  │ Memory    │  │    │  │ Commands  │  │    │  │ Grep      │  │
│  │ Planning  │  │    │  │ Quest     │  │    │  │ Exec      │  │
│  │ Session   │  │    │  │ Review    │  │    │  │ Web       │  │
│  └───────────┘  │    │  └───────────┘  │    │  └───────────┘  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
             ┌───────────────────┴───────────────────┐
             │        Security & Performance         │
             │  ┌─────────────┐  ┌─────────────────┐ │
             │  │ Permissions │  │ Memory Manager  │ │
             │  │   Engine    │  │   Compaction    │ │
             │  └─────────────┘  └─────────────────┘ │
             └───────────────────────────────────────┘
```

## Security & Privacy

RxDsec prioritizes security and privacy:

- **No Network**: Works completely offline (except when using web tools)
- **Permission System**: Granular control over agent capabilities  
- **Path Validation**: Prevents directory traversal and unauthorized access
- **Sandboxed Execution**: Safe command execution with monitoring
- **Local Models**: No data leaves your machine

## Performance Tips

- Use smaller models for faster response times
- Keep projects organized with proper directory structure
- Use line ranges with read tool for large files: `@file.py:10-50`
- Regularly clean up session history to maintain performance
- Use worktrees for isolation when working on multiple features

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- **Issues**: Use the GitHub issue tracker
- **Documentation**: Check the [Wiki](https://github.com/rxdsec/rxdsec/wiki)
- **Community**: Join the discussion in Issues

## Acknowledgments

- [llama-cpp-python](https://github.com/abetlen/llama-cpp-python) for local GGUF model support
- [Rich](https://github.com/Textualize/rich) for beautiful terminal formatting
- [Typer](https://github.com/tiangolo/typer) for excellent CLI framework
- [Pygments](https://pygments.org/) for syntax highlighting
- All contributors and users who help improve RxDsec

---

**RxDsec CLI** - Your privacy-focused, fully local AI coding assistant ✨
