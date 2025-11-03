"""Entry point for CLI module execution.

This allows the CLI to be executed with:
    python3 -m src.cli [command] [options]
"""

from .main import main

if __name__ == "__main__":
    main()