"""Regression tests for luast v1.1 support and the control-flow fixes it
needed. Where the bundled `luau` binary runs, each recovered program is
executed next to its input and the printed output must be identical."""
import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from luau_recover.analysis import analyze
from luau_recover.controlflow import DispatcherPass
from luau_recover.emitter import emit
from luau_recover.hashcmp import djb2_xor
from luau_recover.parser import parse
from luau_recover.passes import PassStats
from luau_recover.pipeline import Pipeline

LUAU = ROOT / "download" / "project" / "LUAST" / "extracted" / "LUAST 1.0.1" / "ROBLOX_ENV" / "luau"


def luau_available() -> bool:
    if not LUAU.exists():
        return False
    try:
        os.chmod(LUAU, 0o755)
        with tempfile.NamedTemporaryFile("w", suffix=".lua", delete=False) as handle:
            handle.write("print(1)\n")
        result = subprocess.run([str(LUAU), handle.name], capture_output=True, timeout=20)
        os.unlink(handle.name)
        return result.returncode == 0 and result.stdout.strip() == b"1"
    except (OSError, subprocess.TimeoutExpired):
        return False


HAVE_LUAU = luau_available()

HASH_CLOSURE = (
    "(function(f,e,g,c)if type(f)~=\"string\"then return false end;if#f~=e then return false end;"
    "local a=5381;local j=buffer.fromstring(f);local k=0.;while true do if k<=e-4 then "
    "local l=buffer.readu32(j,k);a=bit32.bxor(a,l);a=bit32.band(a*33.,4294967295.);k=k+4 else break end end;"
    "while true do if k<e then local m=buffer.readu8(j,k);a=bit32.bxor(a,m);a=bit32.band(a*33.,4294967295.);"
    "k=k+1 else break end end;if a~=g then return false end;return f==c end)"
)

# `s += K` dispatcher whose states branch through `s = if c then .. else ..`
# on a flag computed earlier in the same state (statement order matters).
COMPOUND_DISPATCHER = """
local function check(v)
  local s, c = nil, nil
  s = 6
  while true do
    s += 100
    if s < 103 then
      if s < 101 then break
      elseif s == 101 then c = v > 10; s = if c then 2 else 3
      else print("big", v); s = 4 end
    elseif s < 105 then
      if s == 103 then print("small", v); s = 4 else print("done"); s = 0 end
    elseif s == 105 then print("nan"); return "bad"
    else c = type(v) == "number"; s = if c then 1 else 5 end
  end
  return "ok"
end
print(check(20)); print(check(3)); print(check("x"))
"""


def diamond_chain(count: int) -> str:
    """`count` if/else diamonds in a row, flattened into one dispatcher.
    Without join emission each diamond doubles the emitted tree."""
    lines = ["local function run(v)", "  local s, c = nil, nil", "  s = 999", "  while true do", "    s = 1000 - s"]
    branches = []
    for k in range(count):
        test, left, right, after = 3 * k + 1, 3 * k + 2, 3 * k + 3, 3 * k + 4
        branches.append((test, f"c = v % {k + 2} == 0; s = if c then {1000 - left} else {1000 - right}"))
        branches.append((left, f'print("a", {k}); s = {1000 - after}'))
        branches.append((right, f'print("b", {k}); s = {1000 - after}'))
    branches.append((3 * count + 1, 'print("end"); break'))
    for index, (state, body) in enumerate(branches):
        lines.append(f"    {'if' if index == 0 else 'elseif'} s == {state} then {body}")
    lines += ["    end", "  end", "end", "run(6)", "run(35)"]
    return "\n".join(lines) + "\n"


def pool_shuffle_program() -> str:
    pool = ", ".join(f'"k{index}"' for index in range(1, 21))
    return (
        "local P; local s\n"
        f"P = {{{pool}}}\n"
        "s = 1\n"
        "while true do\n"
        "  s = 50 - s\n"
        "  if s == 49 then local X = P; X[1], X[2], X[3] = X[3], X[1], X[2]; X[4], X[1] = X[1], X[4]; print(X[5]); s = 48\n"
        "  elseif s == 2 then print(P[1], P[2], P[3], P[4]); s = 50\n"
        "  else break end\n"
        "end\n"
    )


class V11Tests(unittest.TestCase):
    def parse(self, source):
        root, errors, _ = parse(source)
        self.assertEqual(errors, [])
        return root

    def recover(self, source: str) -> str:
        output, report = Pipeline().run(source)
        self.assertTrue(report.valid_output, report.fallback_reason)
        return output

    def run_luau(self, source: str) -> str:
        with tempfile.NamedTemporaryFile("w", suffix=".lua", delete=False) as handle:
            handle.write(source)
        try:
            result = subprocess.run([str(LUAU), handle.name], capture_output=True, timeout=60)
        finally:
            os.unlink(handle.name)
        return result.stdout.decode("utf-8", "replace") + result.stderr.decode("utf-8", "replace")

    def assert_same_behaviour(self, source: str, output: str) -> None:
        if HAVE_LUAU:
            self.assertEqual(self.run_luau(source), self.run_luau(output))

    def test_compound_assignment_round_trips(self):
        source = "local x = 5\nx += 1\nlocal t = {n = 1}\nt.n ..= \"a\"\nprint(x, t.n)\n"
        root = self.parse(source)
        output = emit(root, source)
        self.assertIn("x += 1", output)
        self.assertIn('t.n ..= "a"', output)
        recovered = self.recover(source)
        self.assertNotIn("x = 1;", recovered)
        self.assert_same_behaviour(source, recovered)

    def test_compound_dispatcher_and_branch_order(self):
        output = self.recover(COMPOUND_DISPATCHER)
        self.assertNotIn("while true", output)
        # the flag is computed before it is tested
        self.assertLess(output.index('"number"'), output.index("if "))
        self.assert_same_behaviour(COMPOUND_DISPATCHER, output)

    def test_join_emission_keeps_diamond_chains_linear(self):
        source = diamond_chain(40)
        root = self.parse(source)
        stats = PassStats()
        DispatcherPass(root, analyze(root), source, stats).apply()
        output = emit(root, source)
        self.assertNotIn("while true", output)
        self.assertEqual(output.count('print("end")'), 1)
        self.assertLess(len(output), 3 * len(source))
        self.assert_same_behaviour(source, output)

    def test_hashed_compare_folds(self):
        literal = "number"
        source = (
            "local function probe(x)\n"
            f"  local real = {HASH_CLOSURE}(type(x), {len(literal)}, {djb2_xor(literal.encode())}, \"{literal}\")\n"
            f"  local decoy = {HASH_CLOSURE}(type(x), \"enabled\", 2851454103, 7143669)\n"
            "  return real, decoy\n"
            "end\n"
            "print(probe(1)); print(probe(\"s\"))\n"
        )
        output = self.recover(source)
        self.assertNotIn("5381", output)
        self.assertIn('== "number"', output)
        self.assert_same_behaviour(source, output)

    def test_pool_shuffle_applied_before_resolution(self):
        source = pool_shuffle_program()
        output = self.recover(source)
        self.assertNotIn("X[1], X[2]", output)
        # (k1..k4) -> (k3, k1, k2, k4) -> swap slots 4/1 -> (k4, k1, k2, k3)
        self.assertIn('"k4", "k1", "k2", "k3"', output.replace("\n", " "))
        self.assert_same_behaviour(source, output)

    def test_unresolved_pool_reads_keep_their_declarations(self):
        pool = ", ".join(f'"v{index}"' for index in range(1, 20))
        source = f"local P = {{function() return 7 end, {pool}}}\nlocal A = P\nprint(A[1](), A[2])\n"
        output = self.recover(source)
        self.assertEqual(parse(output)[1], [])
        self.assert_same_behaviour(source, output)

    def test_l3_rejects_non_l3_dispatcher(self):
        from luau_recover import luast_l3
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "plain.luau"
            path.write_text(pool_shuffle_program())
            with redirect_stdout(io.StringIO()):
                code = luast_l3.main([str(path), "-o", str(Path(work) / "out.luau")])
            self.assertNotEqual(code, 0)
            self.assertFalse((Path(work) / "out.luau").exists())


if __name__ == "__main__":
    unittest.main()
