#!/usr/bin/env python3
"""
RxDsec CLI - Direct Entry Point
================================
Run this file directly to start the RxDsec CLI.

Usage:
    python run.py                    # Start interactive TUI
    python run.py quest "Fix bug"    # Run autonomous quest
    python run.py review             # Review code changes
    python run.py --help             # Show all commands
"""

import sys
import os
from pathlib import Path

# Default models folder - auto-detects .gguf files
MODELS_FOLDER = Path(r"D:\rxdsecagent\rxdsec\models")

# Add parent directory to path if running directly
if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)


def find_model():
    """Auto-detect first .gguf model in models folder"""
    if MODELS_FOLDER.exists():
        gguf_files = list(MODELS_FOLDER.glob("*.gguf"))
        if gguf_files:
            return str(gguf_files[0])
    return None


def main():
    """Main entry point"""
    try:
        # If no model specified, auto-detect from models folder
        if not any('--model' in arg or '-m' in arg for arg in sys.argv):
            model_path = find_model()
            if model_path:
                print(f"Auto-detected model: {Path(model_path).name}")
                sys.argv.extend(['--model', model_path])
        
        from rxdsec.cli.main import main_entry
        main_entry()
    except ImportError as e:
        print(f"Import Error: {e}")
        print("\nMake sure you've installed dependencies:")
        print("  pip install -e .")
        print("\nOr install required packages:")
        print("  pip install llama-cpp-python rich prompt-toolkit typer pyyaml requests gitpython pygments")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nGoodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main()
