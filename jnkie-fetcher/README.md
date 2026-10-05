# jnkie-fetch

A standalone fetcher for **obfuscated Lua/Luau source hosted on jnkie**. Given a
jnkie URL (or share id), it retrieves the protected script body so it can be fed
into a deobfuscator — e.g. the sibling projects in this monorepo.

> Tool by **@adi.codz** (Discord).

> **Status: starter scaffold.** The raw HTTP fetch works today. The
> jnkie-specific steps — URL/id normalization, loader/redirect/envelope
> unwrapping, and any key/nonce handshake — are stubbed with `TODO`s in
> [`jnkie_fetch/fetcher.py`](jnkie_fetch/fetcher.py) and must be reversed
> against the live service. The full build brief is in
> [`../prompts/jnkie-fetcher.md`](../prompts/jnkie-fetcher.md).

## Scope and authorization

A **protocol-research / analysis** tool for fetching source you are authorized
to retrieve and study. It is not a license bypass and does not attack jnkie
infrastructure — it reads what the delivery chain already serves.

## Usage (current skeleton)

```bash
# fetch and print to stdout
python main.py "https://jnkie.<tld>/<share-or-raw-path>"

# fetch and save, skipping any unwrap step
python main.py "https://jnkie.<tld>/<path>" -o out.lua --raw
```

Python 3.10+, standard library only (no Node, no third-party deps) — matching
`luarmor-fetch`.

## Layout

```
jnkie-fetcher/
├── main.py                 # CLI entry point
├── jnkie_fetch/
│   ├── __init__.py
│   ├── fetcher.py          # transport + unwrap (TODOs for jnkie protocol)
│   └── cli.py              # argparse front end
├── docs/                   # protocol notes (fill in as you reverse it)
├── tests/
├── assets/donate/
├── progress.md             # project memory
└── README.md
```

## Support / Donate

Addresses and QR codes are under [`assets/donate/`](assets/donate/)
(BTC / ETH / BNB / SOL / LTC). — **@adi.codz** (Discord).
