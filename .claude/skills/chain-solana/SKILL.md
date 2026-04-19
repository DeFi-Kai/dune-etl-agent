---
name: chain-solana
description: Per-chain leaf for Solana. Core tables, partitioning windows, address format, and pitfalls. Pairs with chain-references.
usage: Load when the data spec declares `solana` as a chain. Load alongside chain-references.
---

# Solana

Leaf skill for Solana tables on Dune. Use alongside `chain-references` (shared chain techniques) and `dune-sql-best-practices` (SQL + verify).

## 1) Core tables (lighter — prefer these)

| Use case | Table | Notes |
|---|---|---|
| Transaction fees | `gas_solana.fees` | Base + priority fees per tx. Key cols: `block_time`, `tx_hash`, `signer`, `compute_unit_price`, `compute_limit`. Good source for DAU via `signer`. |
| SPL token transfers | `tokens_solana.transfers` | Normalized SPL + native. Key cols: `block_time`, `amount`, `amount_display`, `amount_usd`, `token_mint_address`, `symbol`, `from_owner`, `to_token_account`. `amount_usd` is built in — skip price joins when it's populated. |
| SPL token metadata | `tokens_solana.fungible` | Mint address → symbol, decimals, name. Join on `token_mint_address`. |
| DEX trades | `dex.trades` | Cross-chain DEX trades. Filter `blockchain = 'solana'`. Key cols: `block_time`, `project`, `token_bought_symbol`, `token_sold_symbol`, `token_pair`. |
| Prices | `prices.usd` | Join by `contract_address` (the mint address) + `blockchain = 'solana'`. Only needed if the `tokens_solana.*` table doesn't already expose `amount_usd`. |

## 2) Raw tables (heavier — use when needed, not by default)

| Use case | Table | Notes |
|---|---|---|
| Full transactions | `solana.transactions` | 32 columns. Heavy — always filter on `block_time` + a signer/program. Reach for this when the aggregated tables above don't have what you need. |
| Decoded instructions | `solana.instruction_calls_decoded` | 53 columns of per-instruction decoded calls. Use for protocol-specific analysis (program_name / instruction_identifier). |

Don't shy away from the raw tables when the aggregated ones can't answer the question — just be aware they scan more data and need tighter partition filters.

## 3) Partition filters (required, not optional)

Every Solana query must filter on the partition column first. Without it, scans run across the full table and time out.

```sql
-- good
WHERE block_time >= NOW() - INTERVAL '30' DAY

-- bad — no partition filter
WHERE signer = 'abc123...'
```

For very large scans, also filter on `block_date` or `block_month` where available (e.g., `gas_solana.fees`, `solana.transactions`) — these partition evaluations are cheaper than `block_time` range checks.

## 4) Address format

Solana addresses are **base58**, case-sensitive, typically 32–44 chars. Do *not* lowercase or hex-decode.

```sql
WHERE signer = 'JUP4Fb2cqiRUcaTHdrPC8h2gNsA2ETXiPDD33WcGuJB'  -- literal base58, preserve case
```

## 5) Common pitfalls

- **`solana.transactions` is very large.** Always filter `block_time` *and* a signer/program before doing anything else.
- **`tokens_solana.transfers`** — queries spanning more than ~30 days commonly time out. Aggregate daily upstream or split into multiple queries.
- **Use `amount_usd` when available** on `tokens_solana.transfers` instead of joining `prices.usd` — it's pre-computed and avoids a heavy join.
- **`dex.trades` is multi-chain** — always include `blockchain = 'solana'` or the query will scan every chain.
- **Price joins (when needed):** Solana uses `contract_address` (mint address) as the join key to `prices.usd`, not symbol.
- **`COUNT(DISTINCT signer)` over wide windows** is expensive. Aggregate to daily first, then sum.

## 6) Templates

### Daily active signers (DAU)
```sql
SELECT
  block_date AS day,
  COUNT(DISTINCT signer) AS dau
FROM gas_solana.fees
WHERE block_time >= NOW() - INTERVAL '30' DAY
GROUP BY 1
ORDER BY 1
```

### SPL token transfer volume (uses built-in `amount_usd`)
```sql
SELECT
  date_trunc('day', block_time) AS day,
  symbol,
  SUM(amount_usd) AS volume_usd
FROM tokens_solana.transfers
WHERE block_time >= NOW() - INTERVAL '30' DAY
  AND amount_usd IS NOT NULL
GROUP BY 1, 2
ORDER BY 1, 3 DESC
```

### Solana DEX volume by project (last 30 days)
```sql
SELECT
  date_trunc('day', block_time) AS day,
  project,
  SUM(amount_usd) AS volume_usd
FROM dex.trades
WHERE blockchain = 'solana'
  AND block_time >= NOW() - INTERVAL '30' DAY
GROUP BY 1, 2
ORDER BY 1, 3 DESC
```

### Token metadata lookup
```sql
SELECT token_mint_address, symbol, name, decimals
FROM tokens_solana.fungible
WHERE token_mint_address IN ('<mint1>', '<mint2>')
```

## 7) Further reading
- Dune Solana tables: https://docs.dune.com/data-catalog/solana/overview
