#!/usr/bin/env python3
"""Lift the ENTERED protos of the FlowAuth capture (the code that actually ran).

The capture holds ~424k protos, but only the handful the VM actually *entered*
carry real script logic (the Flow Loader UI builders etc.).  Each entered pid's
table sits at ``dump.pid_of_table`` and its capture (W/V state) is keyed one tid
higher (``cap_by_self[table_tid + 1]``), so we can resolve every entered pid to a
cap and lift it in isolation -- one Program build, one process, error-tolerant
(a failing proto does not kill the run).

Env: SRC (payload source), DUMP (protos json/.gz), OUT (assembled Luau).
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from _repo_path import main_repo  # noqa: E402

main_repo()

from obfuscators.luraph_v15 import devirt  # noqa: E402

SRC = os.environ.get("SRC", os.path.join(HERE, "flowauth_crack", "work", "payload_devirt.lua"))
if not os.path.exists(SRC):  # fresh clone: work/ is gitignored, use tracked capture
    SRC = os.path.join(HERE, "flowauth_capture", "payload_devirt.lua")
DUMP = os.environ.get("DUMP", os.path.join(HERE, "flowauth_crack", "work", "payload_full.protos.json.gz"))
OUT = os.environ.get("OUT", os.path.join(HERE, "flowauth_crack", "work", "payload_entered.devirt.luau"))


def entered_pids(dump):
    """pid -> table tid, for every pid the capture recorded (sorted by pid)."""
    inv = {}
    for tid, pid in dump.pid_of_table.items():
        if pid is not None:
            inv.setdefault(pid, tid)  # one table per pid
    return [(pid, inv[pid]) for pid in sorted(inv)]


def main():
    t0 = time.time()
    prog = devirt.Program(SRC, DUMP)
    prog.requests = set()
    dump = prog.dump
    cbs = dump.cap_by_self
    print("[*] Program built %.0fs; %d entered pids" %
          (time.time() - t0, len(entered_pids(dump))), file=sys.stderr)

    fl = devirt.FunctionLifter(prog)
    out = []
    ok = 0
    for pid, ttid in entered_pids(dump):
        cap = cbs.get(ttid + 1)  # the pid's W/V state cap sits one tid higher
        if cap is None:
            out.append("-- pid %s (table t%s): no cap at t%s" % (pid, ttid, ttid + 1))
            continue
        try:
            vm = prog.vm_of(cap)
            proto = vm.proto_of(cap)
            vmobj = vm.vmobj_of(cap)
        except devirt.Unsupported as ex:
            out.append("-- pid %s (cap t%s): not lifted: %s" % (pid, ttid + 1, ex))
            continue
        t1 = time.time()
        try:
            lines = fl.lift(vm, vmobj, proto, devirt.UpList(), {}, 0)
        except devirt.Unsupported as ex:
            print("[!] pid %s lift failed: %s" % (pid, ex), file=sys.stderr)
            out.append("-- pid %s (cap t%s) lift failed: %s" % (pid, ttid + 1, ex))
            continue
        ok += 1
        out.append("-- " + "-" * 60)
        out.append("-- entered proto pid %s (cap t%s, %.0fs)" % (pid, ttid + 1, time.time() - t1))
        out.append("-- " + "-" * 60)
        out.append("local function pid%s(...)" % pid)
        out += ["\t" + l if l else l for l in lines]
        out.append("end")
        out.append("")
    text = devirt.backend.polish("\n".join(out))
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("[*] stats: %s" % fl.stats, file=sys.stderr)
    print("[*] lifted %d/%d entered protos; wrote %s (%d bytes) in %.0fs"
          % (ok, len(entered_pids(dump)), OUT, len(text), time.time() - t0), file=sys.stderr)


if __name__ == "__main__":
    devirt.run_big_stack(main)
