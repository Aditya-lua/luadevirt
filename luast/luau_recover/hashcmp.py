"""luast v1.1 hashed string comparisons.

v1.1 replaces `x == "lit"` with an inlined closure call

    (function(f, e, g, c)
        if type(f) ~= "string" then return false end
        if #f ~= e then return false end
        -- djb2-xor over little-endian u32 words, then the tail bytes
        ...
        if a ~= g then return false end
        return f == c
    end)(x, #lit, hash(lit), "lit")

Every exit returns `false` except the final `f == c`, so for literal
arguments the call is exactly `x == c` when `c` itself passes the
type/length/hash checks, and `false` otherwise. The closure is matched by
an alpha-renamed token fingerprint against the known template (a
different template never matches, so nothing is folded), and the hash is
computed natively.
"""
from __future__ import annotations

import struct

from .lexer import lex
from .model import Node

_TEMPLATE = (
    "local _ = function(f,e,g,c)if type(f)~=\"string\"then return false end;"
    "if#f~=e then return false end;local a=5381;local j=buffer.fromstring(f);"
    "local k=0.;while true do if k<=e-4 then local l=buffer.readu32(j,k);"
    "a=bit32.bxor(a,l);a=bit32.band(a*33.,4294967295.);k=k+4 else break end end;"
    "while true do if k<e then local m=buffer.readu8(j,k);a=bit32.bxor(a,m);"
    "a=bit32.band(a*33.,4294967295.);k=k+1 else break end end;"
    "if a~=g then return false end;return f==c end"
)
_GLOBALS = {"type", "buffer", "bit32"}
_signature: tuple | None = None


def _canonical(text: str) -> tuple | None:
    tokens, errors, _ = lex(text)
    if errors:
        return None
    renamed: dict[str, str] = {}
    result = []
    previous = None
    for token in tokens:
        kind, value = token.kind, token.value
        if kind == "eof":
            break
        if kind == "name" and value not in _GLOBALS and not (previous is not None and previous.kind == "symbol" and previous.value == "."):
            value = renamed.setdefault(value, "n%d" % len(renamed))
        elif kind == "number":
            value = float(value)
        result.append((kind, value))
        previous = token
    return tuple(result)


def _template_signature() -> tuple | None:
    global _signature
    if _signature is None:
        from .emitter import emit_expr_cached
        from .parser import parse
        root, errors, _ = parse(_TEMPLATE)
        if errors:
            _signature = ()
        else:
            function = root.get("body", [])[0].get("values", [])[0]
            _signature = _canonical(emit_expr_cached(function)) or ()
    return _signature or None


def djb2_xor(data: bytes) -> int:
    value = 5381
    offset = 0
    length = len(data)
    while offset <= length - 4:
        (word,) = struct.unpack_from("<I", data, offset)
        value = ((value ^ word) * 33) & 0xFFFFFFFF
        offset += 4
    while offset < length:
        value = ((value ^ data[offset]) * 33) & 0xFFFFFFFF
        offset += 1
    return value


def _function_of(node: Node | None) -> Node | None:
    while isinstance(node, Node) and node.kind == "paren":
        node = node.get("expr")
    return node if isinstance(node, Node) and node.kind == "function" else None


def is_hash_closure(function: Node) -> bool:
    if len(function.get("params", [])) != 4 or function.get("vararg"):
        return False
    signature = _template_signature()
    if signature is None:
        return False
    from .emitter import emit_expr_cached
    return _canonical(emit_expr_cached(function)) == signature


def simplify_hash_compare(call: Node, is_pure) -> Node | None:
    """Return the equivalent of a hashed-compare call, or None."""
    if call.kind != "call":
        return None
    function = _function_of(call.get("func"))
    args = call.get("args", [])
    if function is None or len(args) != 4:
        return None
    subject, length, digest, literal = args
    if not all(isinstance(item, Node) for item in args):
        return None
    constants = {"string", "number", "bool", "nil"}
    if length.kind not in constants or digest.kind not in constants or literal.kind not in constants:
        return None
    if not is_hash_closure(function):
        return None
    # the closure is `x == c` gated on c passing its own type/length/hash
    # checks; v1.1 also plants decoys with mismatched constants (always false)
    value = literal.get("value") if literal.kind != "nil" else None
    matches = (
        isinstance(value, bytes)
        and length.kind == "number" and float(len(value)) == float(length.get("value"))
        and digest.kind == "number" and float(djb2_xor(value)) == float(digest.get("value"))
    )
    if matches:
        return Node("binop", call.start, call.end, op="==", left=subject, right=literal)
    if is_pure(subject) or _is_type_probe(subject):
        return Node("bool", call.start, call.end, value=False)
    return None


def _is_type_probe(node: Node) -> bool:
    """`type(x)` / `typeof(x)` over a plain name/index chain: nothing to
    preserve when the comparison folds away."""
    if node.kind != "call" or len(node.get("args", [])) != 1:
        return False
    func = node.get("func")
    if not (isinstance(func, Node) and func.kind == "name" and func.get("name") in {"type", "typeof"}):
        return False
    current = node.get("args")[0]
    while isinstance(current, Node) and current.kind in {"index", "indexname"}:
        key = current.get("key") if current.kind == "index" else None
        if key is not None and key.kind not in {"string", "number", "name"}:
            return False
        current = current.get("obj")
    return isinstance(current, Node) and current.kind in {"name", "string", "number", "bool", "nil"}
