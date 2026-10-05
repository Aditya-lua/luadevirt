# jnkie-fetch — Project Memory

## Goals
- Fetch obfuscated Lua/Luau source from a jnkie URL or share id, reliably and
  Node-free, so the output can be piped into a deobfuscator.

## Features (target)
- URL/id normalization to the canonical raw-content endpoint.
- Loader / redirect / JSON-envelope unwrapping to reach the real payload.
- Any required key/nonce handshake, mirroring the delivery chain.
- CLI: `python main.py <url> [-o file] [--raw] [--timeout N]`.

## Completed
- Project skeleton: package layout, argparse CLI, raw HTTP GET, result model.

## Pending
- Reverse the live jnkie delivery chain: capture a real share URL, observe the
  request/response (headers, redirects, any JS/Lua loader), and document it in
  `docs/`.
- Implement `normalize_url()` (bare id → raw URL) and `unwrap()` (strip loader /
  envelope / follow signed CDN redirect).
- Add regression tests against captured fixtures (no live secrets committed).

## Bugs
- _(none yet — skeleton only)_

## Decisions
- Stdlib-only (urllib) to stay dependency-light and Node-free, like
  `luarmor-fetch`.
- No credentials, HWIDs, or captured payloads committed — see `.gitignore`.

## Change Log
- 0.0.1 — initial scaffold added when merged into the `luadevirt` monorepo.
