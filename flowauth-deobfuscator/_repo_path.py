#!/usr/bin/env python3
"""Locate the sibling Deobfuscator-Luraph-V15 repo for the root-level probes.

The devirt/lift probes at this repo's root used to hardcode an absolute path to
the sandbox repo (``/home/z/my-project/Deobfuscator-Luraph-V15``), which only
existed on one machine.  This helper delegates discovery to the loader's
``find_repo`` (explicit arg -> ``FLOWAUTH_REPO`` -> sibling/home scan, matching
both the old CamelCase and the monorepo lowercase basename), so the toolchain
works wherever the two repos are checked out.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))


def main_repo(explicit=None):
    """Return the Deobfuscator-Luraph-V15 repo path; add its ``core/`` to sys.path."""
    crack = os.path.join(_HERE, "flowauth_crack")
    if crack not in sys.path:
        sys.path.insert(0, crack)
    from flowauth_loader import find_repo  # noqa: E402

    repo = find_repo(explicit)
    core = os.path.join(repo, "core")
    if core not in sys.path:
        sys.path.insert(0, core)
    return repo
