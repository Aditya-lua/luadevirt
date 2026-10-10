# LUAST Deobfuscator

Deobfuscator for LUAST-obfuscated Roblox Luau scripts — **v1.0.0, v1.0.1 and
v1.1.x** — including **level-3** (state-machine + encrypted payload) support
via a static Luau emulator (`luau_recover/lua_rt.py` + `luau_recover/luast_l3.py`).
Output is checked for *behaviour*, not just syntax: a differential harness runs
input and output side by side in a fake Roblox environment.

## Features

- Full LUAST v1.0.x / v1.1.x control-flow recovery: flattened dispatcher
  reconstruction (structured `if`/`while` with join points), opaque-predicate
  resolution, junk/dead-code elimination, pool cleanup
- Level-3 support: statically executes the obfuscated state machine
  (pool permutation, xxHash-style avalanche + LCG keystream payload decoder)
  and recovers the original payload — including a constrained seed-recovery
  solver when Roblox-shim drift affects runtime accumulators
- Live fetch mode: pulls scripts straight from the Ouroboros raw GitHub repo
- Optional syntax/VM validation against the real Luau binaries
- Differential behaviour check (`scripts/behaviour_diff.py`): original vs
  output in the bundled fake Roblox environment, trace for trace


## What's New (v1.2) — LUAST v1.1.x and behaviour-exact output

Validated on the LUAST samples in
[`joustingmatch/Ouroboros/games`](https://github.com/joustingmatch/Ouroboros/tree/main/games)
(310 × v1.0.1, 11 × v1.0.0, 12 × v1.1.2) by running every input and its
output in the fake Roblox environment and comparing the recorded behaviour.
See [`progress.md`](progress.md) for the numbers and root-cause notes.

**v1.1.x support**
- **Compound assignment** (`s += K`, `x ..= y`) — desugared in the parser so
  every pass sees `x = x op e`; `s += K` dispatchers are recognised.
- **Runtime pool shuffle** — v1.1 permutes the constant pool in the first
  state of the main dispatcher; the permutation is applied statically (only
  when provably first) before constants are resolved.
- **Hashed string compares** — inlined djb2-xor closures
  `(function(f,e,g,c) ... return f==c end)(x, #lit, hash, lit)` fold to
  `x == lit`; decoys with mismatched constants fold to `false`.

**Control-flow recovery**
- Statements that run before a branch are emitted before it (flags were
  tested before being computed).
- Post-dominator join points: if/else diamonds are emitted once instead of
  duplicating every successor (main bodies no longer hit the emit budget).
- Branch facts are truthiness-only, environment merges are sound, state
  if-expressions with runtime values are kept.

**Correctness fixes in the shared passes** (all found by behaviour diffing;
the previous release produced output that behaved differently from its input
on every sampled script)
- Pool slots rewritten in loops/branches/functions (v1.0.1 register tables,
  dispatcher state in `t[k]`) are no longer resolved as constants.
- Opaque-predicate prober: identities compare the *same* variables on both
  sides, `vector*vector` is component-wise, only input-invariant verdicts
  fold (correlated operands are left alone), exact `X%n == (X+d)%n` rule,
  inverted `gsub`-doubling verdict fixed.
- `local function` parameters are renamed consistently; `elseif` bodies are
  visited by liveness/escape analyses; pool declarations stay while reads
  remain; decoder arguments use only unambiguous local values.
- Deterministic output (analyses no longer key on recycled `id()`s).

**L3** results are only accepted when the payload came through the keystream
decoder; anything else falls back to the generic pipeline instead of emitting
a guessed `print(...)`.

## What's New (v1.1)

- **Nested constant pools**: resolves `pool[slot][key]` reads, local aliases of sub-tables
  (`local a = pool[slot]`), and in-place writes through aliases via copy-on-write overlays.
  The pool pass iterates to a fixpoint so slot-to-slot copy chains resolve transitively.
- **Phi symbolic values**: opaque junk predicates built on `if <unknown> then k1 else k2`
  arithmetic collapse to constants during dispatcher recovery instead of forking the search
  exponentially (`phi_apply`/`phi_binop` component-wise evaluation with collapse-on-equal).
- **Path-condition memory**: dispatcher recovery records branch decisions in the path
  environment, so re-tests of the same binding (`if X then A else if X then B`) prune dead
  subtrees instead of duplicating them.
- **Emission budgets**: per-dispatcher graph and emitted-node caps keep DAG-shaped state
  graphs from tree-expanding into gigabyte outputs; oversized dispatchers keep their
  compact original form.
- **Lua-exact semantics**: float `%` uses Lua floor-modulo (not C fmod) so junk arithmetic
  evaluates bit-identically.
- **Huge-input mode hardened**: limited parent maps, lean tree walks, and chain-carrying
  analysis walks cut peak RSS ~35% (a 4.1 MB / 21k-entry-pool script now processes in ~3 GB).

## Requirements

- Python 3.10+ (stdlib only for the core path; `numpy` optional, used by the
  level-3 seed-recovery fallback for faster scanning)
- No other dependencies

## Usage

```bash
# clone
git clone https://github.com/Aditya-lua/Luast.git
cd Luast

# deobfuscate a local file
python deobfuscate.py path/to/obfuscated.lua -o out.luau

# fetch live from the Ouroboros raw GitHub repo and deobfuscate
python deobfuscate.py --fetch <script-name> -o out.luau

# batch mode
python -m luau_recover.batch --help

# run the regression tests
python tests/test_recovery.py
python tests/test_junk_phi.py
python tests/test_v11.py        # behaviour-checked with the bundled luau
python tests/test_soundness.py

# compare behaviour of an input and its output (fake Roblox environment)
python scripts/behaviour_diff.py original.lua out.luau
python scripts/behaviour_diff.py --pairs IN_DIR OUT_DIR --report diff.jsonl

# bisect which pipeline phase changes behaviour
LUAST_MAX_PHASES=6 python deobfuscate.py in.lua -o out.luau
```

Inputs with a luast level-3 header are auto-routed to the L3 static
emulator (status `ok-l3`) when using `deobfuscate.py`; if it cannot recover a
decoder-verified payload the file falls back to the parser/control-flow/
pipeline recovery passes, which handle regular LUAST v1.0.x and v1.1.x
scripts (`luau_recover.batch` always uses the pipeline). If no `-o` is given, results
are written next to the input / into `DEOBFUSCATED/`.

## Layout

- `deobfuscate.py` — CLI entry point
- `luau_recover/` — parser, control-flow recovery, cleanup passes, L3 emulator, CLI
- `tests/` — regression tests (`test_v11.py` / `test_soundness.py` execute
  input and output with the bundled `luau` and compare their output)
- `scripts/behaviour_diff.py` — differential behaviour check
- `progress.md` — project memory (goals, decisions, change log)

## Validation (optional)

Drop the official `luau` / `luau-ast` binaries (from the
[Luau releases](https://github.com/luau-lang/luau/releases)) into a
`ROBLOX_ENV/` folder to enable automatic syntax/VM validation of outputs.

## Credits

- **@adi.codz** on Discord


## Support / Donate

<div align="center">
  <img src="assets/donate/donate_header.png" width="520" alt="Buy me a coffee — fund future projects">
</div>

If these tools are useful to you, you can help fund future projects by sending
crypto to the addresses below. Thank you for the support. — **@adi.codz** (Discord)

| Network | Address | Scan |
|---|---|---|
| **Bitcoin** (BTC) | `bc1q3nprh6e0y4fz88ft4uu5dad7xsx629z498dkay` | <img src="assets/donate/btc.png" width="120" alt="Bitcoin QR"> |
| **Ethereum** (ERC-20) | `0x11369a1d18eb442581D1e675dAdD94eBA1c4bE52` | <img src="assets/donate/eth.png" width="120" alt="Ethereum QR"> |
| **BNB Smart Chain** (BEP-20) | `0x11369a1d18eb442581D1e675dAdD94eBA1c4bE52` | <img src="assets/donate/bnb.png" width="120" alt="BNB Smart Chain QR"> |
| **Solana** (SOL) | `AVKBDNT2PzYDJ7njVrjt7MoVZ1tY4DvNSsADdujiGKTC` | <img src="assets/donate/sol.png" width="120" alt="Solana QR"> |
| **Litecoin** (LTC) | `ltc1qu4ahsjff622xqjlqwafhlgmacd5ea477sqpx9z` | <img src="assets/donate/ltc.png" width="120" alt="Litecoin QR"> |

> Send each asset only on its own network. ETH and BNB share one EVM address —
> use it for ERC-20 on Ethereum and BEP-20 on BNB Smart Chain. Assets sent on the
> wrong network may be lost.
