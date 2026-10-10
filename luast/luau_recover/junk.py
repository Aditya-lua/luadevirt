"""LUAST opaque-predicate evaluation.

The obfuscator pads dispatch trees with junk branches guarded by predicates
that are mathematically decided regardless of runtime values:

  1. self comparisons            x == x / x <= x  (same expression both sides)
  2. vector identities           dot(cross(A,B),C) == dot(cross(B,C),A)
                                 dot(cross(A,cross(B,C)),D) == dot(B*dot(A,C)-C*dot(A,B),D) + K
  3. angle gap                   abs(angle(A,B,C)) - abs(angle(B,A,C)) == K, |K| > pi
  4. string doubling             s:len() >= s:gsub(p, "%1%1", n):len()

Vector operands are seeded from runtime values, so identities are verified by
probing with random concrete vectors: a predicate that evaluates the same way
for several random inputs is folded; anything else is left untouched.
"""
from __future__ import annotations

import math
import random
import time
from typing import Any, Callable

from .model import Node
from .passes import UNKNOWN, is_number, truthy

_PROBE_SEEDS = 4
_MAX_PROBE_NODES = 20000
_PROBE_TIME_BUDGET = 0.05


class Vector3:
    __slots__ = ("x", "y", "z")

    def __init__(self, x, y, z):
        self.x = x
        self.y = y
        self.z = z

    def __add__(self, other):
        return Vector3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other):
        return Vector3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, other):
        # Luau `vector * vector` is component-wise (not a dot product)
        if isinstance(other, Vector3):
            return Vector3(self.x * other.x, self.y * other.y, self.z * other.z)
        return Vector3(self.x * other, self.y * other, self.z * other)

    __rmul__ = __mul__

    def dot(self, other):
        return self.x * other.x + self.y * other.y + self.z * other.z


def _random_vector(rng: random.Random) -> Vector3:
    return Vector3(rng.randrange(1, 1000), rng.randrange(1, 1000), rng.randrange(1, 1000))


def _random_scalar(rng: random.Random) -> Any:
    return rng.randrange(1, 1000)


def vector_call(name: str | None, args: list[Any]) -> Any:
    """Evaluate vector.* calls when all operands are concrete Vector3/numbers."""
    if name == "vector.create":
        if len(args) >= 3 and all(is_number(value) for value in args[:3]):
            return Vector3(args[0], args[1], args[2])
        return UNKNOWN
    if len(args) >= 2 and isinstance(args[0], Vector3) and isinstance(args[1], Vector3):
        a, b = args[0], args[1]
        if name == "vector.dot":
            return a.dot(b)
        if name == "vector.cross":
            return Vector3(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x)
    if len(args) >= 1 and isinstance(args[0], Vector3):
        a = args[0]
        if name == "vector.floor":
            return Vector3(math.floor(a.x), math.floor(a.y), math.floor(a.z))
        if name == "vector.ceil":
            return Vector3(math.ceil(a.x), math.ceil(a.y), math.ceil(a.z))
    if len(args) >= 3 and all(isinstance(value, Vector3) for value in args[:3]):
        a, b, c = args[0], args[1], args[2]
        if name == "vector.angle":
            u = Vector3(a.x - b.x, a.y - b.y, a.z - b.z)
            v = Vector3(c.x - b.x, c.y - b.y, c.z - b.z)
            uu = u.dot(u)
            vv = v.dot(v)
            if uu == 0 or vv == 0:
                return 0.0
            cosine = max(-1.0, min(1.0, u.dot(v) / math.sqrt(uu * vv)))
            return math.acos(cosine)
    return UNKNOWN


def _vector_arith(op: str, left: Any, right: Any) -> Any:
    if isinstance(left, Vector3) and isinstance(right, Vector3):
        if op == "+":
            return left + right
        if op == "-":
            return left - right
        if op == "*":
            return left * right
        return UNKNOWN
    if isinstance(left, Vector3) and is_number(right):
        if op in {"*", "/"}:
            return left * right if op == "*" else Vector3(left.x / right, left.y / right, left.z / right)
        return UNKNOWN
    if is_number(left) and isinstance(right, Vector3):
        if op == "*":
            return right * left
        return UNKNOWN
    return UNKNOWN


def _collect_vector_atoms(node: Node | None, atoms: dict[int, Node], counter: list[int], vector_args: set[str] | None = None) -> None:
    """Collect probe targets: leaf operands (names, index chains) and string
    constants that appear inside arithmetic (junk states compute with
    pooled strings; they are never really strings there).

    Atoms are leaves only; compound vector arguments are evaluated, never
    replaced. `vector_args` collects the rendered keys of leaves used
    directly as vector operands; the prober gives every occurrence of the
    same key the same value (an identity compares the same variables on
    both sides)."""
    if vector_args is None:
        vector_args = set()
    if node is None or counter[0] > _MAX_PROBE_NODES:
        return
    counter[0] += 1
    kind = node.kind
    if kind == "call":
        func = node.get("func")
        name = _dotted(func)
        if name and name.startswith("vector."):
            for arg in node.get("args", []):
                leaf = _strip(arg) if isinstance(arg, Node) else None
                if not isinstance(leaf, Node) or leaf.kind in {"number", "bool", "nil", "string"}:
                    continue
                if leaf.kind in {"name", "index", "indexname"}:
                    atoms.setdefault(id(leaf), leaf)
                    vector_args.add(_render(leaf))
                else:
                    _collect_vector_atoms(leaf, atoms, counter, vector_args)
            return
        if name and (name.startswith("math.") or name in {"tonumber", "tostring"}):
            for arg in node.get("args", []):
                _collect_vector_atoms(arg, atoms, counter, vector_args)
            return
        return
    if kind == "methodcall":
        for arg in node.get("args", []):
            _collect_vector_atoms(arg, atoms, counter, vector_args)
        _collect_vector_atoms(node.get("obj"), atoms, counter, vector_args)
        return
    if kind == "name":
        atoms.setdefault(id(node), node)
        return
    if kind == "string":
        return
    if kind in {"function", "localfunc"}:
        return
    if kind == "binop" and node.get("op") in {"+", "-", "*", "/", "%", "^"}:
        for side in (node.get("left"), node.get("right")):
            if isinstance(side, Node) and side.kind == "string":
                atoms.setdefault(id(side), side)
        _collect_vector_atoms(node.get("left"), atoms, counter, vector_args)
        _collect_vector_atoms(node.get("right"), atoms, counter, vector_args)
        return
    for field in node.fields.values():
        if isinstance(field, Node):
            _collect_vector_atoms(field, atoms, counter, vector_args)
        elif isinstance(field, (list, tuple)):
            for item in field:
                if isinstance(item, Node):
                    _collect_vector_atoms(item, atoms, counter, vector_args)


def _dotted(node: Node | None) -> str | None:
    if not isinstance(node, Node):
        return None
    if node.kind == "name":
        return node.get("name")
    if node.kind == "indexname":
        base = _dotted(node.get("obj"))
        return base + "." + node.get("name", "") if base else None
    return None


class _ProbeAbort(Exception):
    pass


def _probe_eval(node: Node | None, assignment: dict[int, Any], base_eval: Callable[[Node], Any], budget: list, depth: int = 0) -> Any:
    """Evaluate an expression treating atoms in `assignment` as concrete vectors."""
    if node is None or depth > 48:
        return UNKNOWN
    budget[0] -= 1
    if budget[0] <= 0 or time.monotonic() > budget[1]:
        raise _ProbeAbort()
    if id(node) in assignment:
        return assignment[id(node)]
    kind = node.kind
    if kind == "paren":
        return _probe_eval(node.get("expr"), assignment, base_eval, budget, depth + 1)
    if kind == "number" or kind == "string" or kind == "bool":
        return node.get("value")
    if kind == "nil":
        return None
    if kind == "unop":
        value = _probe_eval(node.get("expr"), assignment, base_eval, budget, depth + 1)
        if value is UNKNOWN:
            return UNKNOWN
        op = node.get("op")
        if op == "not":
            return not truthy(value)
        if op == "-" and is_number(value):
            return -value
        if op == "-" and isinstance(value, Vector3):
            return Vector3(-value.x, -value.y, -value.z)
        return UNKNOWN
    if kind == "binop":
        op = node.get("op")
        if op in {"and", "or"}:
            left = _probe_eval(node.get("left"), assignment, base_eval, budget, depth + 1)
            if left is UNKNOWN:
                return UNKNOWN
            if op == "and":
                return _probe_eval(node.get("right"), assignment, base_eval, budget, depth + 1) if truthy(left) else left
            return left if truthy(left) else _probe_eval(node.get("right"), assignment, base_eval, budget, depth + 1)
        left = _probe_eval(node.get("left"), assignment, base_eval, budget, depth + 1)
        right = _probe_eval(node.get("right"), assignment, base_eval, budget, depth + 1)
        if left is UNKNOWN or right is UNKNOWN:
            return UNKNOWN
        if op in {"==", "~=", "<", "<=", ">", ">="}:
            try:
                if op == "==":
                    return left == right
                if op == "~=":
                    return left != right
                if op == "<":
                    return left < right
                if op == "<=":
                    return left <= right
                if op == ">":
                    return left > right
                return left >= right
            except (TypeError, ValueError):
                return UNKNOWN
        vector_result = _vector_arith(op, left, right)
        if vector_result is not UNKNOWN:
            return vector_result
        if is_number(left) and is_number(right):
            try:
                if abs(left) > 2 ** 53 or abs(right) > 2 ** 53 or (op == "^" and abs(right) > 64):
                    return UNKNOWN
                if op == "+":
                    return left + right
                if op == "-":
                    return left - right
                if op == "*":
                    return left * right
                if op == "/":
                    return left / right
                if op == "%":
                    # Lua floor-modulo (Python %), not C fmod
                    return left % right
                if op == "^":
                    return left ** right
                return UNKNOWN
            except (ArithmeticError, ValueError, OverflowError, ZeroDivisionError):
                return UNKNOWN
        return UNKNOWN
    if kind == "call":
        func = node.get("func")
        name = _dotted(func)
        if name == "math.abs":
            args = node.get("args") or [None]
            value = _probe_eval(args[0], assignment, base_eval, budget, depth + 1)
            return abs(value) if is_number(value) else UNKNOWN
        if name == "math.floor":
            args = node.get("args") or [None]
            value = _probe_eval(args[0], assignment, base_eval, budget, depth + 1)
            return math.floor(value) if is_number(value) else UNKNOWN
        if name == "math.ceil":
            args = node.get("args") or [None]
            value = _probe_eval(args[0], assignment, base_eval, budget, depth + 1)
            return math.ceil(value) if is_number(value) else UNKNOWN
        if name and name.startswith("vector."):
            args = [_probe_eval(arg, assignment, base_eval, budget, depth + 1) for arg in node.get("args", [])]
            if any(value is UNKNOWN for value in args):
                return UNKNOWN
            return vector_call(name, args)
        return UNKNOWN
    if kind == "ifexpr":
        condition = _probe_eval(node.get("cond"), assignment, base_eval, budget, depth + 1)
        if condition is UNKNOWN:
            return UNKNOWN
        if truthy(condition):
            return _probe_eval(node.get("then"), assignment, base_eval, budget, depth + 1)
        for branch_condition, branch_value in node.get("elifs", []):
            branch = _probe_eval(branch_condition, assignment, base_eval, budget, depth + 1)
            if branch is UNKNOWN:
                return UNKNOWN
            if truthy(branch):
                return _probe_eval(branch_value, assignment, base_eval, budget, depth + 1)
        return _probe_eval(node.get("else_"), assignment, base_eval, budget, depth + 1)
    if kind == "index":
        return base_eval(node)
    return base_eval(node)


def _dotted_call_shape(node: Node) -> tuple[str, Node, list[Node]] | None:
    """Match `obj:name(args)` / `obj.name(args)` shapes for method probes."""
    if isinstance(node, Node) and node.kind == "methodcall":
        return (node.get("method", ""), node.get("obj"), list(node.get("args", [])))
    if node.kind != "call":
        return None
    func = node.get("func")
    if isinstance(func, Node) and func.kind == "methodname":
        args = node.get("args", [])
        return (func.get("name", ""), func.get("obj"), list(args))
    if isinstance(func, Node) and func.kind == "indexname":
        args = node.get("args", [])
        return (func.get("name", ""), func.get("obj"), list(args))
    return None


def _string_doubling_truth(node: Node) -> bool | None:
    """`s:len() >= s:gsub(p, r, n):len()` where r duplicates each match."""
    if node.kind != "binop" or node.get("op") not in {">=", "<", "<=", ">"}:
        return None
    left = _strip(node.get("left"))
    right = _strip(node.get("right"))
    left_call = _dotted_call_shape(left) if isinstance(left, Node) else None
    right_call = _dotted_call_shape(right) if isinstance(right, Node) else None
    if not left_call or not right_call:
        return None
    if left_call[0] != "len" or right_call[0] != "len":
        return None
    gsub = _dotted_call_shape(right_call[1]) if isinstance(right_call[1], Node) else None
    if not gsub or gsub[0] != "gsub":
        return None
    # both len() calls must measure the SAME subject string
    if _render(left_call[1]) != _render(gsub[1]):
        return None
    args = gsub[2]
    if len(args) < 3:
        return None
    repl = args[1]
    if not isinstance(repl, Node) or repl.kind != "string":
        return None
    pattern = repl.get("value")
    if not isinstance(pattern, (bytes, str)):
        return None
    text = pattern.decode("utf-8", "replace") if isinstance(pattern, bytes) else pattern
    # "%1%1"-style: every match is rewritten strictly longer.
    stripped = text.replace("%1", "").replace("%2", "").replace("%0", "")
    if "%" in stripped or len(text) <= 1:
        return None
    # The rewritten string is strictly longer than the (non-empty) subject,
    # so `len(s) >= len(doubled)` is false and `len(s) < len(doubled)` true
    # (checked against Luau: ("hello"):len() >= ("hello"):gsub("(.)",
    # "%1%1", 1):len() --> false).
    op = node.get("op")
    if op in {">=", ">"}:
        return False
    if op in {"<", "<="}:
        return True
    return None


def _strip(node: Node | None) -> Node | None:
    while isinstance(node, Node) and node.kind == "paren":
        node = node.get("expr")
    return node


def _render(node: Node | None) -> str:
    if not isinstance(node, Node):
        return ""
    try:
        from .emitter import emit_expr_cached
        return emit_expr_cached(node)
    except Exception:
        return f"<{node.kind}@{node.start}:{node.end}>"


def self_compare_truth(node: Node) -> bool | None:
    """Fold `X op X` for pure deterministic comparisons of one expression."""
    if node.kind != "binop":
        return None
    op = node.get("op")
    if op not in {"==", "~=", "<", "<=", ">", ">="}:
        return None
    left = _strip(node.get("left"))
    right = _strip(node.get("right"))
    if left is None or right is None:
        return None
    if _render(left) != _render(right):
        return None
    if op in {"==", "<=", ">="}:
        return True
    return False


def angle_gap_truth(node: Node, base_eval: Callable[[Node], Any]) -> bool | None:
    """`math.abs(angle(A,B,C)) - math.abs(angle(B,A,C)) == K` with |K| > pi.

    Both angle results lie in [0, pi] (radians), so their absolute
    difference can never exceed pi; when the pooled constant K is beyond
    that range the comparison is always false. When K == 0 the predicate
    reduces to angle symmetry, decided by probing."""
    if node.kind != "binop" or node.get("op") not in {"==", "~="}:
        return None
    left = _strip(node.get("left"))
    right = _strip(node.get("right"))
    if not isinstance(left, Node) or not isinstance(right, Node):
        return None
    constant = None
    difference = None
    for candidate, other in ((left, right), (right, left)):
        value = base_eval(candidate)
        if is_number(value):
            constant = value
            difference = other
            break
    if constant is None or not isinstance(difference, Node) or difference.kind != "binop" or difference.get("op") != "-":
        return None
    if _angle_abs(difference.get("left")) is None or _angle_abs(difference.get("right")) is None:
        return None
    op = node.get("op")
    if abs(constant) > math.pi + 1e-9:
        return op == "~="
    if constant == 0:
        return _probe_truth(difference, base_eval)
    return None


def _angle_abs(node: Node | None) -> Node | None:
    """Return the angle call node inside math.abs(...), else None."""
    current = _strip(node)
    if not isinstance(current, Node) or current.kind != "call":
        return None
    func = current.get("func")
    name = _dotted(func)
    if name != "math.abs":
        return None
    args = current.get("args", [])
    if len(args) != 1:
        return None
    inner = _strip(args[0])
    if isinstance(inner, Node) and inner.kind == "paren":
        inner = _strip(inner)
    if not isinstance(inner, Node) or inner.kind != "call":
        return None
    inner_name = _dotted(inner.get("func"))
    if inner_name != "vector.angle":
        return None
    return inner


# id(node) -> (node, verdict); the node is kept so a recycled id is detected
_verdict_cache: dict[int, tuple[Node, bool | None]] = {}


def clear_verdict_cache() -> None:
    """Reset probe verdict cache (node ids are only unique within one AST)."""
    _verdict_cache.clear()


def _is_probeable(node: Node | None) -> bool:
    """True for arithmetic/vector expressions; bare names and constants are
    excluded so equality checks against runtime values are never probed."""
    node = _strip(node)
    if not isinstance(node, Node):
        return False
    kind = node.kind
    if kind == "paren":
        return _is_probeable(node.get("expr"))
    if kind == "binop" and node.get("op") in {"+", "-", "*", "/", "%", "^"}:
        return True
    if kind == "unop" and node.get("op") == "-":
        return True
    if kind == "call":
        name = _dotted(node.get("func"))
        return bool(name) and (name.startswith("vector.") or name.startswith("math."))
    return False


_COMPARISONS = {"==", "~=", "<", "<=", ">", ">="}


def _difference(left: Any, right: Any) -> Any:
    if isinstance(left, Vector3) and isinstance(right, Vector3):
        return Vector3(left.x - right.x, left.y - right.y, left.z - right.z)
    if is_number(left) and is_number(right):
        return left - right
    return None


def _is_zero(value: Any) -> bool:
    if isinstance(value, Vector3):
        return value.x == 0 and value.y == 0 and value.z == 0
    return value == 0


def _same(first: Any, second: Any) -> bool:
    if isinstance(first, Vector3) and isinstance(second, Vector3):
        return first.x == second.x and first.y == second.y and first.z == second.z
    if is_number(first) and is_number(second):
        return first == second
    return type(first) is type(second) and first == second


def _decide(op: str, pairs: list[tuple[Any, Any]]) -> bool | None:
    """Verdict from sampled (left, right) values that holds for *every*
    input, not just the sampled ones: either both sides agree on all
    samples (a polynomial identity, Schwartz-Zippel) or they differ by the
    same constant on all samples. Anything else depends on the actual
    values (operands are often correlated through earlier statements, so
    'false on random inputs' proves nothing)."""
    differences = [_difference(left, right) for left, right in pairs]
    if all(_same(left, right) for left, right in pairs):
        difference: Any = 0
    elif any(item is None for item in differences) or not all(_same(item, differences[0]) for item in differences):
        return None
    else:
        difference = differences[0]
    if _is_zero(difference):
        return {"==": True, "~=": False, "<=": True, ">=": True, "<": False, ">": False}[op]
    if isinstance(difference, Vector3):
        return {"==": False, "~=": True}.get(op)
    return {"==": False, "~=": True, "<": difference < 0, "<=": difference < 0, ">": difference > 0, ">=": difference > 0}[op]


def _mod_shift_truth(node: Node, base_eval: Callable[[Node], Any]) -> bool | None:
    """`X % n == (X + d) % n`: equal exactly when d is a multiple of n
    (Lua floor-modulo); luast's most common arithmetic junk."""
    op = node.get("op")
    if op not in {"==", "~="}:
        return None
    sides = (_strip(node.get("left")), _strip(node.get("right")))
    for plain, shifted in (sides, sides[::-1]):
        if not (isinstance(plain, Node) and isinstance(shifted, Node)):
            continue
        if plain.kind != "binop" or plain.get("op") != "%" or shifted.kind != "binop" or shifted.get("op") != "%":
            continue
        modulus_a = base_eval(plain.get("right"))
        modulus_b = base_eval(shifted.get("right"))
        if not (is_number(modulus_a) and is_number(modulus_b)) or modulus_a != modulus_b or modulus_a == 0:
            continue
        inner = _strip(shifted.get("left"))
        if not (isinstance(inner, Node) and inner.kind == "binop" and inner.get("op") == "+"):
            continue
        if _render(_strip(inner.get("left"))) != _render(_strip(plain.get("left"))):
            continue
        offset = base_eval(_strip(inner.get("right")))
        if not is_number(offset):
            continue
        equal = offset % modulus_a == 0
        return equal if op == "==" else not equal
    return None


def _probe_truth(node: Node, base_eval: Callable[[Node], Any]) -> bool | None:
    """Random-probe a comparison: fold only when truth is input-invariant."""
    cached = _verdict_cache.get(id(node))
    if cached is not None and cached[0] is node:
        return cached[1]
    result: bool | None = None
    op = node.get("op")
    left = _strip(node.get("left"))
    right = _strip(node.get("right"))
    if op in _COMPARISONS and _is_probeable(left) and _is_probeable(right):
        atoms: dict[int, Node] = {}
        vector_args: set[str] = set()
        counter = [0]
        _collect_vector_atoms(node, atoms, counter, vector_args)
        if atoms:
            keys = {identity: _render(atom) for identity, atom in atoms.items()}
            rng = random.Random(0x5EED)
            pairs: list[tuple[Any, Any]] = []
            try:
                for _ in range(_PROBE_SEEDS):
                    values: dict[str, Any] = {}
                    for key in keys.values():
                        if key not in values:
                            values[key] = _random_vector(rng) if key in vector_args else _random_scalar(rng)
                    assignment = {identity: values[keys[identity]] for identity in atoms}
                    budget = [_MAX_PROBE_NODES, time.monotonic() + _PROBE_TIME_BUDGET]
                    left_value = _probe_eval(left, assignment, base_eval, budget)
                    right_value = _probe_eval(right, assignment, base_eval, budget)
                    if left_value is UNKNOWN or right_value is UNKNOWN:
                        pairs = []
                        break
                    pairs.append((left_value, right_value))
                if pairs:
                    result = _decide(op, pairs)
            except _ProbeAbort:
                result = None
            except (RecursionError, ArithmeticError, ValueError, TypeError, OverflowError):
                result = None
    _verdict_cache[id(node)] = (node, result)
    return result


_JUNK_NODE_CAP = 512


def _fast_size(node: Node) -> int:
    """Iterative subtree size; bails out once above _JUNK_NODE_CAP."""
    if not isinstance(node, Node):
        return 0
    count = 0
    stack = [node]
    while stack:
        current = stack.pop()
        count += 1
        if count > _JUNK_NODE_CAP:
            return count
        for value in current.fields.values():
            if isinstance(value, Node):
                stack.append(value)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    if isinstance(item, Node):
                        stack.append(item)
    return count


def junk_truth(node: Node | None, base_eval: Callable[[Node], Any]) -> bool | None:
    """Try every opaque-predicate strategy; None when undecided.

    Only small predicate expressions are considered: LUAST junk
    identities are tiny, and large subtrees here are real payload
    expressions that must neither be probed nor rendered."""
    if not isinstance(node, Node):
        return None
    node = _strip(node) or node
    if node.kind != "binop":
        return None
    if _fast_size(node) > _JUNK_NODE_CAP:
        return None
    verdict = self_compare_truth(node)
    if verdict is not None:
        return verdict
    verdict = _string_doubling_truth(node)
    if verdict is not None:
        return verdict
    verdict = angle_gap_truth(node, base_eval)
    if verdict is not None:
        return verdict
    verdict = _mod_shift_truth(node, base_eval)
    if verdict is not None:
        return verdict
    return _probe_truth(node, base_eval)
