# Master prompts

One self-contained **master prompt per project** in the `luadevirt` monorepo.
Paste the matching file as the opening message when you start a new session
agent to work on that project — each tells the agent its mission, where the
code lives, how to run it, current state, and the standing conventions.

| Project directory | Master prompt |
|-------------------|---------------|
| `deobfuscator-luraph-v15/` | [deobfuscator-luraph-v15.md](deobfuscator-luraph-v15.md) |
| `flowauth-deobfuscator/`   | [flowauth-deobfuscator.md](flowauth-deobfuscator.md) |
| `luarmor-fetch/`           | [luarmor-fetch.md](luarmor-fetch.md) |
| `luast/`                   | [luast.md](luast.md) |
| `jnkie-fetcher/`           | [jnkie-fetcher.md](jnkie-fetcher.md) — build-from-scaffold brief |

Every prompt inherits the shared rules in [`_SHARED.md`](_SHARED.md)
(repo/branch, strict Aditya authorship with **no AI attribution**,
senior-engineer workflow, project-memory upkeep, scope/authorization). Read
that file alongside any individual prompt.
