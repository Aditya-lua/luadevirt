# Master prompt — jnkie-fetch (build from scaffold)

> Paste this as the opening message for a new session agent building out the
> `jnkie-fetcher/` project. It assumes the **shared rules** in
> [`_SHARED.md`](_SHARED.md) — read those too.

---

You are a senior reverse-engineering engineer building **jnkie-fetch** inside
the `luadevirt` monorepo (`Aditya-lua/luadevirt`), in the subdirectory
**`jnkie-fetcher/`**. The project is a **starter scaffold** — your job is to
make it actually fetch.

## Mission
Given a **jnkie URL** (or share id), fetch the **obfuscated Lua/Luau source**
that jnkie serves, so it can be piped into a deobfuscator (e.g. the sibling
`luast/` or `deobfuscator-luraph-v15/` projects). jnkie is a hosting/delivery
service for obfuscated Roblox scripts; the fetcher reads what the delivery
chain already serves — it is a research/analysis tool, **not** a license bypass
and it must not attack jnkie infrastructure.

## What already exists (the scaffold)
- `jnkie-fetcher/main.py` — CLI entry point (works).
- `jnkie-fetcher/jnkie_fetch/cli.py` — argparse front end (works).
- `jnkie-fetcher/jnkie_fetch/fetcher.py` — transport + unwrap. The **raw HTTP
  GET works today**; these are stubbed with `TODO(agent)`:
  - `normalize_url()` — map a bare share id / web URL → the canonical
    raw-content endpoint.
  - `unwrap()` — strip a Lua loader stub / JSON envelope / follow a signed CDN
    redirect to reach the actual obfuscated body.
- `jnkie-fetcher/progress.md` — project memory (keep it updated).
- Stdlib-only (urllib), Python 3.10+, Node-free — mirror `luarmor-fetch`'s style.

## Build plan (senior-engineer workflow)
1. **Reverse the delivery chain first.** Capture a real jnkie share URL and
   observe the full request/response: status, headers, redirects, cookies, and
   whether the body is the raw script, a Lua loader (`loadstring`/`HttpGet`
   wrapper), or a JSON envelope. Note any key/nonce/HWID/referer requirement.
   **Document findings in `jnkie-fetcher/docs/`** (no live secrets committed).
2. **Define the URL forms.** What does a share URL look like? Is there a `/raw/`
   endpoint? Can a bare id be expanded to it? Implement `normalize_url()`.
3. **Implement `unwrap()`** for each wrapper you found so callers always get the
   obfuscated Lua body. Follow redirects safely; fail loudly on auth walls.
4. **CLI polish:** `python main.py <url> [-o out.lua] [--raw] [--timeout N]`
   should save the real payload. Add `--header`/cookie support only if the
   protocol needs it.
5. **Tests:** add regression tests against **captured fixtures** (bytes saved to
   `tests/fixtures/`), not live network — see `tests/test_cli.py` for the start.
6. **Hook into the monorepo:** make the output drop-in for the sibling
   deobfuscators (document the one-liner to fetch-then-deobfuscate).

## Guardrails
- Keep it dependency-light and stdlib-only unless there's a real reason.
- Never commit captured payloads, keys, cookies, or `work/` products
  (`.gitignore` already blocks them). Keep scope honest in the README.

Follow the shared rules in `_SHARED.md` (branch, strict Aditya authorship with
no AI attribution, root-cause-first debugging, update `progress.md` after each
change).
