"""Smoke tests for the jnkie-fetch skeleton (no network)."""
import subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_help_runs():
    out = subprocess.run([sys.executable, "main.py", "-h"], cwd=ROOT,
                         capture_output=True, text=True)
    assert out.returncode == 0
    assert "jnkie" in out.stdout.lower()


def test_bare_id_rejected_until_implemented():
    from jnkie_fetch.fetcher import normalize_url, JnkieError
    import pytest
    with pytest.raises(JnkieError):
        normalize_url("abc123")
