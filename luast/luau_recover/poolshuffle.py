"""luast v1.1 runtime constant-pool shuffle.

v1.1 builds the constant pool as a table literal and then, in the very
first state of the top-level dispatcher, permutes it in place:

    local eW = a8
    eW[43], eW[427], ... = eW[43], eW[596], ...    -- parallel assignment
    ...

Every pool read in the program happens after that, so resolving reads
against the literal as written yields the wrong constants. This pass
proves the shuffle is the first thing the program does with the pool,
applies the permutation to the literal, and deletes the shuffle; the
regular pool resolver then sees the runtime layout.

Any check that fails leaves the tree untouched.
"""
from __future__ import annotations

from typing import Any

from .analysis import Analyzer, Binding, binding_for
from .model import Node, children, walk


def _index_slot(node: Node, binding: Binding, analyzer: Analyzer) -> int | None:
    if node.kind != "index":
        return None
    base = node.get("obj")
    key = node.get("key")
    if not (isinstance(base, Node) and base.kind == "name" and binding_for(analyzer, base) is binding):
        return None
    if not (isinstance(key, Node) and key.kind == "number"):
        return None
    value = key.get("value")
    if isinstance(value, float):
        if not value.is_integer():
            return None
        value = int(value)
    return value if isinstance(value, int) else None


def _shuffle_prefix(actions: list[Node], pool: Binding, analyzer: Analyzer) -> tuple[Binding, list[Node]] | None:
    """`local X = pool` followed by parallel `X[i], ... = X[j], ...` runs."""
    if not actions or actions[0].kind != "local":
        return None
    head = actions[0]
    bindings = analyzer.declaration_bindings.get(id(head), [])
    values = head.get("values", [])
    if len(bindings) != 1 or len(values) != 1:
        return None
    value = values[0]
    if not (value.kind == "name" and binding_for(analyzer, value) is pool):
        return None
    alias = bindings[0]
    moves: list[Node] = []
    for statement in actions[1:]:
        if statement.kind != "assign":
            break
        targets = statement.get("targets", [])
        sources = statement.get("values", [])
        if not targets or len(targets) != len(sources):
            break
        if any(_index_slot(item, alias, analyzer) is None for item in targets + sources):
            break
        moves.append(statement)
    if not moves:
        return None
    return alias, moves


def _calls_or_reads(node: Node, pool: Binding, analyzer: Analyzer) -> bool:
    """Does node (outside nested function bodies) call anything or read pool?"""
    stack = [node]
    while stack:
        current = stack.pop()
        if current.kind in {"function", "localfunc", "funcdef"} and current is not node:
            continue
        if current.kind in {"call", "methodcall"}:
            return True
        if current.kind == "name" and binding_for(analyzer, current) is pool:
            return True
        stack.extend(children(current))
    return False


def _pool_literal(body: list[Node], analyzer: Analyzer) -> tuple[Binding, Node, int] | None:
    """The single top-level `P = {...}` / `local P = {...}` constant pool."""
    found: tuple[Binding, Node, int] | None = None
    for index, statement in enumerate(body):
        if statement.kind == "assign" and len(statement.get("targets", [])) == 1 and len(statement.get("values", [])) == 1:
            target = statement.get("targets")[0]
            value = statement.get("values")[0]
            binding = binding_for(analyzer, target) if target.kind == "name" else None
        elif statement.kind == "local" and len(statement.get("values", [])) == 1:
            bindings = analyzer.declaration_bindings.get(id(statement), [])
            binding = bindings[0] if len(bindings) == 1 else None
            value = statement.get("values")[0]
        else:
            continue
        if binding is None or value.kind != "table" or len(value.get("items", [])) < 16:
            continue
        if found is not None:
            return None
        found = (binding, value, index)
    return found


def apply_pool_shuffle(root: Node, analyzer: Analyzer, stats: Any = None) -> bool:
    from .controlflow import DispatcherBail, DispatcherPass
    from .passes import PassStats

    body = root.get("body", [])
    pool_info = _pool_literal(body, analyzer)
    if pool_info is None:
        return False
    pool, table, pool_index = pool_info
    if pool.writes != 1:
        return False
    items = table.get("items", [])
    if any(key is not None for key, _ in items):
        return False
    # top-level dispatcher: the last top-level statement
    if not body or body[-1].kind != "while":
        return False
    dispatch_index = len(body) - 1
    probe = DispatcherPass(root, analyzer, "", stats or PassStats())
    dispatcher = probe.recognize(body, dispatch_index, body[-1])
    if dispatcher is None:
        return False
    # nothing before the dispatcher may run code or touch the pool
    for index, statement in enumerate(body[:dispatch_index]):
        if index == pool_index:
            continue
        if _calls_or_reads(statement, pool, analyzer):
            return False
    # the shuffle must open every path of the initial state
    initial = probe.apply_transform(dispatcher.initial, dispatcher.transform)
    try:
        paths = probe.execute(dispatcher.tree, dispatcher.state, initial, [], [], env=dict(probe.base_env))
    except (DispatcherBail, RecursionError, ValueError, TypeError):
        return False
    if not paths:
        return False
    prefix = _shuffle_prefix(paths[0].actions, pool, analyzer)
    if prefix is None:
        return False
    alias, moves = prefix
    shuffle = [paths[0].actions[0]] + moves
    for path in paths[1:]:
        if len(path.actions) < len(shuffle) or any(a is not b for a, b in zip(path.actions, shuffle)):
            return False
    # `local X = pool` stays: later code in the state keeps reading the
    # (now permuted) pool through it, which the pool resolver follows
    shuffle = moves
    # every shuffle statement must be removable from a statement list
    doomed = {id(statement) for statement in shuffle}
    owners = [statements for statements in probe.statement_lists(root) if any(id(statement) in doomed for statement in statements)]
    if sum(1 for statements in owners for statement in statements if id(statement) in doomed) != len(shuffle):
        return False
    # apply the permutation (Lua evaluates every source before assigning)
    slots = [value for _, value in items]
    for statement in moves:
        targets = [_index_slot(item, alias, analyzer) for item in statement.get("targets", [])]
        sources = [_index_slot(item, alias, analyzer) for item in statement.get("values", [])]
        if any(slot is None or slot < 1 or slot > len(slots) for slot in targets + sources):
            return False
        moved = [slots[slot - 1] for slot in sources]
        for slot, value in zip(targets, moved):
            slots[slot - 1] = value
    table.fields["items"] = [(None, value) for value in slots]
    for statements in owners:
        statements[:] = [statement for statement in statements if id(statement) not in doomed]
    return True
