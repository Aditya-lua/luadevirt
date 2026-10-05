# Shared rules (applies to every luadevirt agent prompt)

These rules are inlined into each per-project master prompt. They are the
standing conventions for the `luadevirt` monorepo — do not deviate.

## Repository
- Monorepo: **https://github.com/Aditya-lua/luadevirt** (owner `Aditya-lua`).
- Work **only inside your project's subdirectory** unless a change is
  genuinely cross-cutting. Leave the other projects untouched.
- Branch: develop on your session's designated feature branch (or a feature
  branch off `main`); push that branch to `luadevirt`. Never push to `main`
  or another project's branch without explicit permission. Do **not** open a
  pull request unless asked.

## Authorship & attribution — STRICT
- Author every commit as the user, **without persisting git config**:
  ```
  git -c user.name="Aditya" -c user.email="tiwaribaba3596@gmail.com" commit ...
  ```
  (use `aditya-lua@users.noreply.github.com` instead if privacy is wanted).
- **No AI/Claude attribution anywhere** in the repo: no `Co-Authored-By: Claude`,
  no `Claude-Session:`, no "Generated with Claude Code", no "claude" author — in
  commit messages, PR bodies, code comments, or any pushed artifact.
- The repo must read as the user's own work. Public credit: **@adi.codz** (Discord).

## Engineering workflow (senior-engineer style)
- For a vague ask: requirements → clarifying questions → architecture → module
  breakdown → implementation → optimization → detection/perf review. Ask
  questions first; don't dump a script.
- Debugging: explain the **root cause first** (why it happens + perf/memory
  impact), then a **minimal** fix — don't rewrite everything.
- Code: modular, readable, with sanity checks and error handling; no memory
  leaks, duplicate connections, or needless loops. Match the surrounding style.
- Keep each project **dependency-light** and in the language it already uses.

## Project memory
- Each project keeps a memory file (`progress.md`, `README.md`, or a TECHNICAL
  doc). **Read it first**, and **update it after each change** (Goals /
  Features / Completed / Pending / Bugs / Decisions / Change Log).

## Scope & authorization
- Every tool here is for **protocol research, analysis, and authorized
  reverse-engineering** on code you own or are permitted to study. Honor each
  project's stated scope/limits. Never commit secrets, script keys, HWIDs,
  cookies, or captured payloads (the `.gitignore` files enforce this).
