# luadevirt

**A unified Lua/Luau devirtualization & deobfuscation toolkit.**

> Tool by **@adi.codz** (Discord).

`luadevirt` brings together several standalone research tools for reversing
protected Roblox Luau scripts into a single monorepo. Each project lives in its
own subdirectory and keeps its own README, dependencies, and run instructions —
this top level is the shared entry point and license.

Per-project **master prompts** for spinning up new session agents live in
[`prompts/`](prompts/).

---

## Projects

| Directory | Project | What it does |
|-----------|---------|--------------|
| [`deobfuscator-luraph-v15/`](deobfuscator-luraph-v15/) | **Luraph v15 Deobfuscator** | Reverse compiler for Luau scripts protected by Luraph v15. Recovers control flow from flattened VM dispatchers, decrypts in-memory constants via a live sandboxed Luau runtime, and bypasses anti-tamper traps. Also ships the shared sandbox harness (`runtime/envlog.luau`), the Luau binary (`bin/`), and the generic devirt core (`src/vmmap`, `core/devirt.py`). |
| [`flowauth-deobfuscator/`](flowauth-deobfuscator/) | **FlowAuth Deobfuscator** | Crack + devirtualization pipeline for `flowauth.net`-protected scripts (FlowAuth v3 protocol / Luraph v15 payload): fresh-loader fetch, envlog patcher, one-process live chain, and payload reassembler. |
| [`luarmor-fetch/`](luarmor-fetch/) | **Luarmor Fetch** | Standalone fetcher and research toolkit for the Luarmor v4 bootstrap chain (loader stub → sephal init → sandbox bootstrap → live auth handshake → session response), plus a static analyzer for captured whitelist clients. |
| [`luast/`](luast/) | **LUAST Deobfuscator** | Deobfuscator for LUAST v1.0.1 obfuscated Luau scripts, including level-3 (state-machine + encrypted payload) support via a static Luau emulator. Recovers control flow, resolves opaque predicates, and statically executes the L3 state machine to recover the payload. |
| [`jnkie-fetcher/`](jnkie-fetcher/) | **jnkie Fetch** | Fetcher for obfuscated Lua/Luau source hosted on jnkie, so a protected script can be pulled and piped into a deobfuscator. **Starter scaffold** — the jnkie-specific unwrap steps are stubbed; see [`prompts/jnkie-fetcher.md`](prompts/jnkie-fetcher.md). |

## How the projects relate

These tools share a lineage, which is why they now live together:

- **`deobfuscator-luraph-v15/`** is the foundation — it owns the sandboxed Luau
  runtime (`runtime/envlog.luau`), the Luau binary (`bin/luau`), and the generic
  devirtualization core.
- **`flowauth-deobfuscator/`** was split out of the Luraph deobfuscator; it holds
  everything FlowAuth-specific while reusing that shared harness and devirt core.
- **`luarmor-fetch/`** drives the Luraph deobfuscator's Luau + envlog sandbox as a
  discovered dependency to resolve the Luarmor client chunk.
- **`luast/`** and **`jnkie-fetcher/`** are the newest additions: `luast/` is a
  self-contained LUAST deobfuscator, and `jnkie-fetcher/` fetches obfuscated
  source that the deobfuscators (here) then consume.

Each subdirectory still references the others by their original repository layout
(e.g. the Luau binary under `deobfuscator-luraph-v15/bin/`). See each project's
own README for exact paths and setup.

## Scope and authorization

Every tool here is for **protocol research, analysis, and authorized
security/reverse-engineering work** on code you own or are permitted to study.
See each project's README for its specific scope notes and known limits.

## Layout

```
luadevirt/
├── deobfuscator-luraph-v15/   # Luraph v15 reverse compiler + shared sandbox/devirt core
├── flowauth-deobfuscator/     # FlowAuth v3 crack + devirt pipeline
├── luarmor-fetch/             # Luarmor v4 bootstrap-chain fetcher & client analyzer
├── luast/                     # LUAST v1.0.1 deobfuscator (+ level-3 static emulator)
├── jnkie-fetcher/             # jnkie obfuscated-source fetcher (starter scaffold)
├── prompts/                   # per-project master prompts for new session agents
├── LICENSE                    # MIT
└── README.md                  # you are here
```

## License

MIT — see [LICENSE](LICENSE).

## Support / Donate

If these tools saved you time, a tip is appreciated — addresses and QR codes are
under each project's `assets/donate/` (BTC / ETH / BNB / SOL / LTC).

Public credit: **@adi.codz** (Discord).
