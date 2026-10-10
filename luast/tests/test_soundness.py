"""Regression tests for semantic bugs found by differential behaviour
testing on the Ouroboros corpus. Each case reproduces the original
failure mode; programs are executed with the bundled `luau` (when it
runs on this machine) and must print exactly what their input prints."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from luau_recover import junk
from luau_recover.parser import parse
from luau_recover.passes import UNKNOWN, evaluate
from luau_recover.pipeline import Pipeline
from test_v11 import COMPOUND_DISPATCHER, HAVE_LUAU, BehaviourMixin


def verdict(expression: str):
    names = "local gE, gF, gG, gH, gK, gL, eP, eQ, dr, ds, x, s\n"
    root, errors, _ = parse(names + "local probe = " + expression + "\n")
    assert not errors, errors
    node = root.get("body")[1].get("values")[0]
    junk.clear_verdict_cache()
    return junk.junk_truth(node, lambda item: evaluate(item, {}, None) if item.kind in {"number", "binop", "paren"} else UNKNOWN)


class JunkVerdictTests(unittest.TestCase):
    def test_vector_identities_compare_the_same_variables(self):
        self.assertIs(verdict("vector.dot(vector.cross(gE, (vector.cross(gF, gG))), gH) == vector.dot(gF*vector.dot(gE, gG)-gG*vector.dot(gE, gF), gH)"), True)
        self.assertIs(verdict("vector.dot(vector.cross(gE, gF), gG) == vector.dot(vector.cross(gF, gG), gE)"), True)

    def test_constant_offset_decoy_is_false(self):
        self.assertIs(verdict("vector.dot(vector.cross(gK, gL), vector.cross(gE, gF)) == vector.dot(gK, gE)*vector.dot(gL, gF)-vector.dot(gK, gF)*vector.dot(gL, gE)+5"), False)

    def test_correlated_operands_are_not_folded(self):
        # true when eP = cross(dr, ds) and eQ = dot(dr, ds), false otherwise
        self.assertIsNone(verdict("vector.dot(eP, eP)+eQ*eQ == vector.dot(dr, dr)*vector.dot(ds, ds)"))

    def test_mod_shift(self):
        self.assertIs(verdict("(x*3+1)*9%4 == ((x*3+1)*9+10)%4"), False)
        self.assertIs(verdict("(x*3+1)*9%4 == ((x*3+1)*9+8)%4"), True)
        self.assertIs(verdict("(x*3+1)*9%4 ~= ((x*3+1)*9+(8+2))%4"), True)

    def test_string_doubling_direction(self):
        # ("hello"):len() >= ("hello"):gsub("(.)", "%1%1", 1):len() --> false in Luau
        self.assertIs(verdict('s:len() >= s:gsub("(.)", "%1%1", 1):len()'), False)
        self.assertIs(verdict('s:len() < s:gsub("(.)", "%1%1", 1):len()'), True)


class BehaviourTests(BehaviourMixin, unittest.TestCase):

    def test_local_function_parameters_are_renamed(self):
        source = 'local function probe(x)\n  local real = type(x) == "number"\n  return real\nend\nprint(probe(1), probe("s"))\n'
        output = self.recover(source)
        self.assertNotIn("probe(x)", output.replace(" ", ""))
        self.assert_same_behaviour(source, output)

    def test_register_slots_written_in_loops_are_not_constants(self):
        source = (
            "local R = {}\nR[1] = nil\nR[2] = 0\nR[1] = 1\n"
            "while true do\n"
            "  if R[1] == 1 then print(\"a\") R[1] = 2\n"
            "  elseif R[1] == 2 then print(\"b\") R[1] = 3\n"
            "  else break end\n"
            "end\nprint(R[1])\n"
        )
        output = self.recover(source)
        self.assert_same_behaviour(source, output)

    def test_reads_in_elseif_arms_keep_pool_writes(self):
        source = (
            "local P = {}\nP[2] = function() return 5 end\nlocal x = tonumber(\"1\")\n"
            "if x == 0 then print(\"zero\") elseif x == 1 then print(P[2]()) end\n"
        )
        output = self.recover(source)
        self.assert_same_behaviour(source, output)

    def test_multi_assigned_locals_are_not_folded_into_calls(self):
        # the last constant assignment used to stand in for every read
        source = (
            'local P = {"tag", 1}\nlocal ly\nly = 7\n'
            "while true do\n"
            "  print(P[1], bit32.bxor(ly, P[2]))\n"
            "  if ly == 7 then ly = os.time() and 3 else break end\n"
            "end\n"
        )
        output = self.recover(source)
        self.assertIn("bit32.bxor", output)
        self.assert_same_behaviour(source, output)

    def test_state_ifexpr_with_runtime_leaf_is_kept(self):
        # `s = if true then <runtime value> else 6`: the runtime arm was
        # dropped as "junk" and the dead `else` arm taken instead
        source = (
            "local function nxt() return 3 end\n"
            "local function run()\n"
            "  local s, n = nil, 0\n"
            "  s = 8\n"
            "  while true do\n"
            "    if s < 4 then\n"
            "      if s < 2 then\n"
            "        if s < 1 then s = if n < 3 then 7 else 5\n"
            "        else s = if true then nxt() else 6 end\n"
            "      elseif s < 3 then s = 1\n"
            "      else n += 1; print(\"tick\", n); s = 0 end\n"
            "    elseif s < 6 then\n"
            "      if s < 5 then break else print(\"done\"); s = 4 end\n"
            "    elseif s < 7 then s = 4\n"
            "    elseif s < 8 then print(\"seven\"); s = 2\n"
            "    else print(\"start\"); s = 1 end\n"
            "  end\n"
            "end\n"
            "run()\n"
        )
        output = self.recover(source)
        self.assert_same_behaviour(source, output)

    def test_output_is_deterministic(self):
        source = COMPOUND_DISPATCHER
        first, _ = Pipeline().run(source)
        second, _ = Pipeline().run(source)
        self.assertEqual(first, second)


if __name__ == "__main__":
    if not HAVE_LUAU:
        print("note: bundled luau not runnable here; behaviour checks are structural only")
    unittest.main()
