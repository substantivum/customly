"""Root entry point for panel hosts (bot-hosting.net, Pterodactyl, etc.).

Those panels run `python <entry file>` rather than `python -m bot`, which puts
the *script's* folder on sys.path instead of the project root — so pointing them
straight at bot/__main__.py fails with "No module named 'bot'". This file sits at
the project root and re-exports the same entry point. Docker still uses `-m bot`.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bot.__main__ import main  # noqa: E402

if __name__ == "__main__":
    main()
