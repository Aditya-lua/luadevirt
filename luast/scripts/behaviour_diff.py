#!/usr/bin/env python3
"""Differential behaviour check: original vs deobfuscated.

Runs both scripts in the bundled fake Roblox environment (ROBLOX_ENV) and
compares the recorded behaviour traces (service lookups, instance edits,
remote calls, HTTP requests, errors). Script line numbers and timings are
normalised away, so an identical trace means the deobfuscated script did
exactly what the original did under the model.

    python scripts/behaviour_diff.py original.lua deobfuscated.luau
    python scripts/behaviour_diff.py --pairs ORIG_DIR DEOB_DIR [--report r.jsonl]

Exit status is 0 when every pair matches.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_ENV = HERE.parent / "download" / "project" / "LUAST" / "extracted" / "LUAST 1.0.1" / "ROBLOX_ENV"

_NOISE = (
    (re.compile(r"Script:\d+"), "Script:N"),
    (re.compile(r"harness\.luau:\d+"), "harness.luau:N"),
    (re.compile(r" in \d+(\.\d+)?s\b"), ""),
)


def prepare_env(env_dir: Path) -> Path:
    """Private copy: build_env writes the harness next to itself."""
    work = Path(tempfile.mkdtemp(prefix="luast-behaviour-"))
    target = work / "env"
    shutil.copytree(env_dir, target)
    (target / "luau").chmod(0o755)
    return target


def trace(env: Path, script: Path, timeout: int) -> str:
    harness = env / "harness.luau"
    build = subprocess.run([sys.executable, str(env / "build_env.py"), str(script), "-o", str(harness)],
                           capture_output=True, text=True)
    if build.returncode != 0:
        return "-- harness build failed: " + build.stderr.strip()[-300:]
    try:
        run = subprocess.run(["./luau", "harness.luau"], cwd=env, capture_output=True, timeout=timeout)
        raw = run.stdout
    except subprocess.TimeoutExpired as exc:
        raw = exc.stdout or b""
    extract = subprocess.run([sys.executable, str(env / "extract_trace.py")], input=raw, capture_output=True)
    text = extract.stdout.decode("utf-8", "replace")
    for pattern, replacement in _NOISE:
        text = pattern.sub(replacement, text)
    return text


def compare(env: Path, original: Path, deobfuscated: Path, timeout: int, cache: Path | None = None) -> dict:
    cached = cache / (original.name + ".trace") if cache else None
    if cached is not None and cached.exists():
        before = cached.read_text(encoding="utf-8")
    else:
        before = trace(env, original, timeout)
        if cached is not None:
            cached.write_text(before, encoding="utf-8")
    after = trace(env, deobfuscated, timeout)
    statements = re.search(r"-- (\d+) statements recorded", before)
    entry = {
        "input": str(original),
        "output": str(deobfuscated),
        "statements": int(statements.group(1)) if statements else 0,
        "match": before == after,
    }
    if not entry["match"]:
        diff = difflib.unified_diff(before.splitlines(), after.splitlines(), "original", "deobfuscated", n=1, lineterm="")
        entry["diff"] = "\n".join(list(diff)[:40])
    return entry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("original", nargs="?", type=Path)
    parser.add_argument("deobfuscated", nargs="?", type=Path)
    parser.add_argument("--pairs", nargs=2, type=Path, metavar=("ORIG_DIR", "DEOB_DIR"))
    parser.add_argument("--list", type=Path, help="file listing original paths (with --pairs DEOB_DIR lookup)")
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--cache", type=Path, help="directory caching original-script traces")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    if not (args.env / "luau").exists():
        parser.error(f"no luau binary in {args.env}")
    pairs: list[tuple[Path, Path]] = []
    if args.pairs:
        originals, outputs = args.pairs
        sources = [Path(line) for line in args.list.read_text().split("\n") if line] if args.list else sorted(originals.iterdir())
        pairs = [(source, outputs / source.name) for source in sources if (outputs / source.name).exists()]
    elif args.original and args.deobfuscated:
        pairs = [(args.original, args.deobfuscated)]
    else:
        parser.error("give ORIGINAL DEOBFUSCATED or --pairs")
    if args.cache:
        args.cache.mkdir(parents=True, exist_ok=True)

    env = prepare_env(args.env)
    report = args.report.open("w", encoding="utf-8") if args.report else None
    matched = 0
    try:
        for original, deobfuscated in pairs:
            entry = compare(env, original, deobfuscated, args.timeout, args.cache)
            matched += entry["match"]
            print(("match   " if entry["match"] else "DIFFERS ") + f"{original.name} ({entry['statements']} statements)")
            if not entry["match"] and len(pairs) == 1:
                print(entry["diff"])
            if report:
                report.write(json.dumps(entry) + "\n")
                report.flush()
    finally:
        if report:
            report.close()
        shutil.rmtree(env.parent, ignore_errors=True)
    print(f"{matched}/{len(pairs)} behaviour-identical")
    return 0 if matched == len(pairs) else 1


if __name__ == "__main__":
    sys.exit(main())
