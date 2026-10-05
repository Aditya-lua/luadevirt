"""Command-line interface for jnkie-fetch."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .fetcher import fetch, JnkieError


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="jnkie-fetch",
        description="Fetch obfuscated Lua/Luau source from a jnkie URL.",
    )
    p.add_argument("url", help="jnkie share/raw URL (or bare share id, once supported)")
    p.add_argument("-o", "--output", type=Path, help="write the fetched source to this file (default: stdout)")
    p.add_argument("--raw", action="store_true", help="do not unwrap loaders/envelopes; save the response verbatim")
    p.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds (default: 30)")
    p.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = fetch(args.url, timeout=args.timeout, raw=args.raw)
    except JnkieError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if result.note:
        print(f"note: {result.note}", file=sys.stderr)

    if args.output:
        args.output.write_bytes(result.body)
        print(f"wrote {len(result.body)} bytes -> {args.output}", file=sys.stderr)
    else:
        sys.stdout.buffer.write(result.body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
