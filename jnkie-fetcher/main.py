#!/usr/bin/env python3
"""jnkie-fetch CLI entry point.

Usage:
    python main.py <jnkie-url> [-o out.lua] [--raw]
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jnkie_fetch.cli import main

raise SystemExit(main())
