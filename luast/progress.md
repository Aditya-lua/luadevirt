# Progress Log — LUAST Deobfuscator

Project memory for `luast/`. Newest entries on top. Credit: **@adi.codz**.

## Goals
- Deobfuscate LUAST-protected Roblox Luau: v1.0.x, v1.1.x, and level-3
  (state machine + encrypted payload) builds.
- Output must be *behaviour-identical* to the input, not just parseable.
- Stay stdlib-only (numpy optional for the L3 seed solver); keep huge-input
  memory bounded (4.1 MB / 21k-entry pool case: ~3 GB).

## Features
- Parser/emitter round trip for Luau (types, if-expressions, interpolation,
  compound assignment).
- Constant-pool resolution (nested pools, aliases, copy-on-write overlays),
  constant folding, opaque-predicate / junk elimination (phi values).
- Dispatcher (flattened control flow) recovery with path-condition memory,
  emission budgets, and post-dominator join emission.
- v1.1: compound-assign state steps, runtime pool shuffle, hashed string
  compares (incl. decoys).
- L3 static emulator (`luast_l3.py`) with constrained seed solver.
- Differential behaviour check against the bundled fake Roblox environment
  (`scripts/behaviour_diff.py`).

## Completed
- See Change Log.

## Pending
- Nested-loop dispatchers (one emitted loop header per dispatcher today;
  a second cycle bails and keeps the original loop).
- `batch.py` does not auto-route L3 inputs (only `cli.py` / `deobfuscate.py`).
- L3 detection is token-based; real L3 builds are recognised by the result
  gate (decoder observed + clean payload), everything else falls back.

## Bugs (known)
- Redundant re-tests can survive where dispatcher states merge with
  different path knowledge (correct, just noisy).

## Decisions
- **Desugar compound assignments in the parser** (`x op= e` → `x = x op e`,
  tagged `compound`) rather than teaching every pass about `op`; only
  side-effect-free targets are rewritten; the emitter re-sugars.
- **Hash compares are fingerprinted, not executed**: the closure must match
  the known template token-for-token (alpha-renamed); the djb2-xor hash is
  computed natively. An unknown variant is left alone.
- **Pool shuffle is applied only with proof** that it is the first thing the
  top-level dispatcher executes and nothing before it runs code or reads
  the pool.
- **L3 results must be earned**: `luast_l3.main` returns non-zero unless the
  payload came through the buffer keystream decoder (and, for the solver,
  the Z accumulator was tracked or the round function self-checks). The CLI
  then falls back to the generic pipeline instead of emitting garbage.
- Validation = behaviour traces, not reparse: `valid_output` only proves
  syntax; the differential trace proves semantics.

## Change Log

### 2026-10-10 — v1.1.x support, CFG correctness fixes, behaviour validation
Samples: `joustingmatch/Ouroboros/games` (441 files: 310 v1.0.1, 11 v1.0.0,
12 v1.1.2; 108 are other obfuscators/loaders and out of scope).

Root causes found and fixed:
1. **L3 false positives** — `looks_like_luast_l3` matches large v1.0.1 and
   every v1.1.2 script; the emulator then "succeeded" with an empty or
   garbage payload (`print("9H' MpQLy_/")` for squirrelescape) because
   `main()` returned 0 unconditionally. Now gated (see Decisions).
   Also ported the 90 s emulation budget (`LUAST_L3_SECONDS`) from upstream.
2. **Compound assignment ignored everywhere** — `s += K` was evaluated as
   `s = K`, fabricating dispatcher graphs (v1.1 functions came out empty).
   Fixed by parser desugaring + `add` dispatcher transform.
3. **Fork actions emitted after the branch** — paths carried the actions
   that ran before a fork, and the emitter put `if cond` first, so a flag
   was tested before it was computed. Conditions now record the fork's
   action offset; the shared prefix is hoisted above the `if`.
4. **Exponential emission of diamonds** — shared successors were re-emitted
   per predecessor, blowing the emit budget on main bodies. Added
   post-dominator (Cooper–Harvey–Kennedy) join emission, loop-aware
   (`break` when a join lies outside the emitted loop).
5. **v1.1 runtime pool shuffle** — the first top-level state permutes the
   pool with parallel assignments; static resolution used the unshuffled
   literal (wrong constants). New `poolshuffle.py` applies it statically.
6. **Pool declarations deleted while still read** — literal-key reads that
   could not be inlined (slot holds `game`, a closure, a table) did not
   count as references, so cleanup removed `local X = pool` → undefined
   globals at runtime. Now referenced pools keep their declarations.
7. **Renamer skipped `local function` parameters** (`elif` ordering) —
   uses were renamed, the parameter list was not → nil params at runtime.
8. Hashed string compares folded (`hashcmp.py`), repeated nested tests on
   the same local collapsed, flat `elseif` nesting cap raised (100 → 400),
   emission depth decoupled from `max_paths`.

Tests: `tests/test_v11.py` (7 cases, executed with the bundled `luau` when
available and compared output-for-output).
