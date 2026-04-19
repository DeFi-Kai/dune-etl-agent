# Leaf Skill Template

Use this as a starting point when adding a new chain or API leaf. Copy the frontmatter + structure into `.claude/skills/<chain-X | api-X>/SKILL.md` and fill in the specifics. Without the frontmatter, Claude Code's skill discovery will skip the file.

## For a new chain (`chain-<name>`)

```markdown
---
name: chain-<name>
description: Per-chain leaf for <Name>. Core tables, partitioning windows, address format, and pitfalls. Pairs with chain-references.
usage: Load when the data spec declares `<name>` as a chain. Load alongside chain-references.
---

# <Name>

Leaf skill for <Name> tables on Dune. Use alongside `chain-references` (shared chain techniques) and `dune-sql-best-practices` (SQL + verify).

## 1) Core tables

| Use case | Table | Notes |
|---|---|---|
| Transactions | `<chain>.transactions` | Partition on `block_time`. |
| Token transfers | `tokens_<chain>.transfers` | Retention window if any. |
| Decoded calls | `<chain>.traces` or `<chain>.instruction_calls` | |
| Prices | `prices.usd` | Filter `blockchain = '<name>'`. |

## 2) Partition filters

Describe required partition columns and typical time bounds.

## 3) Address format

Hex/base58/other. Case sensitivity. How to normalize.

## 4) Common pitfalls

List of known gotchas: table retention limits, expensive operations, quirks.

## 5) Templates

Two or three canonical query patterns: DAU, volume, balance snapshot.

## 6) Further reading

Links to Dune docs for this chain.
```

## For a new API (`api-<name>`)

```markdown
---
name: api-<name>
description: Per-API leaf for <Name>. Key endpoints, auth, rate limits, and response schemas. Pairs with api-references.
usage: Load when the data spec declares `<name>`. Load alongside api-references.
---

# <Name>

Leaf skill for <Name>'s API. Use alongside `api-references` (shared LiveFetch techniques) and `dune-sql-best-practices`.

## 1) Base URLs

| Surface | Base |
|---|---|
| Main | `https://api.<name>.com` |

## 2) Auth

Keyless / bearer / query-param. If the key goes in the URL, **flag that queries must be private in Dune**.

## 3) Rate limits

Per-tier limits. Note the 80 req/s LiveFetch throttle and how it interacts.

## 4) Key endpoints

One heading per endpoint with:
- The URL pattern
- A LiveFetch SQL example (`http_get(...)` + `json_extract_scalar` / `UNNEST`)
- Response size warning if it risks the 4 MB cap

## 5) When to materialize

Explicit list of endpoints/patterns that don't fit inline. Reference the materialize flow in `api-references` §5.

## 6) Response schema quick reference

Shape of the important fields so the agent can write SQL without re-reading the API docs.

## 7) Further reading

Link to the official API docs.
```

## Checklist

Before the leaf is usable:

1. File lives at `.claude/skills/<chain-X | api-X>/SKILL.md` — exact filename, exact directory pattern
2. Frontmatter has `name`, `description`, `usage`
3. Data spec declares the leaf name in `chains:` or `apis:`
4. Restart Claude Code (or reload skills) so discovery picks up the new file
