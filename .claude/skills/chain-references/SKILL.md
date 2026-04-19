---
name: chain-references
description: Shared techniques for querying chain tables on Dune (partition filters, table selection, decoded calls). Pairs with per-chain files for schema specifics.
usage: Load when the data spec declares one or more chains; then load the matching `chain-<name>` file for schema/quirks.
---

# Chain References

This skill is a **technique library**, not a router. It covers the shared patterns for querying chain tables; pull in the per-chain file (e.g., `chain-solana`) for concrete table lists and quirks when the data spec names that chain.

## 1) Table selection
- **Transfers vs. activity:** Prefer `tokens_<chain>.transfers` for token transfers, `account_activity` for balance deltas, and `instruction_calls` for decoded program calls.
- **Prices:** Use `prices.usd` joins where possible instead of external APIs.
- **Decoded calls:** `instruction_calls` and protocol-specific decoded tables are usually faster than raw transaction parsing.

## 2) Partitioning & time bounds
- Always filter on the partition column first (typically `block_time` or `block_date`).
- Keep expensive tables to recent windows (e.g., 30d for many Solana transfer tables) unless you use lighter pre-aggregated tables.

## 3) Addresses and identifiers
- Use lowercase hex without quotes where possible; quote reserved keywords only (`"from"`, `"to"`).
- Normalize chain-specific address formats in the per-chain file (e.g., Solana base58 helpers).

## 4) Performance guardrails
- Avoid `COUNT(DISTINCT ...)` on raw instruction tables; aggregate upstream or use `account_activity`.
- Cast before arithmetic to avoid overflow (`CAST(x AS DOUBLE) * y`).

## 5) Per-chain specifics
- Load the corresponding `chain-<name>` file for concrete table names, retention notes, and quirks. If it does not exist yet, create it alongside this file when a new chain is added to the data spec.
