---
name: dune-sql-best-practices
description: Core skill for writing DuneSQL (Trino fork) queries. Covers Trino syntax differences from Postgres/MySQL, CTE query templates, dashboard output shapes, error handling, and optimization.
usage: Load when the project data spec declares a chain or API (any DuneSQL task). Pair with chain-references and api-references technique docs as declared in the spec.
---

# DuneSQL Best Practices

DuneSQL is a Trino fork with blockchain-specific extensions. It is **not** Postgres and **not** Spark. This skill covers syntax, query structure, dashboard output patterns, error handling, and optimization.

**Context:** This skill handles SQL fundamentals. For chain-specific tables, gas models, and decoding, load `chain-references` (technique doc) plus the per-chain file. For external API data, load `api-references` (inline API technique) plus the per-API file. Both are declared in the project data spec.

## 1. Syntax Reference

### 1.1 Timestamps

No implicit string-to-timestamp conversion. Use explicit forms:

```sql
-- Preferred: literal
WHERE block_time >= TIMESTAMP '2025-09-22'

-- Explicit cast
WHERE block_time >= CAST('2025-09-22' AS TIMESTAMP)

-- Defensive: returns NULL on failure (use for untrusted/decoded data)
WHERE block_time >= TRY_CAST('2025-09-22' AS TIMESTAMP)

-- Date comparison (truncates to day)
WHERE block_time >= date('2025-09-22')

-- Relative interval
WHERE block_time >= now() - interval '7' day

-- ❌ Postgres cast syntax — does not work
WHERE block_time >= '2025-09-22'::timestamp
```

Optional end date for bounded ranges:

```sql
AND block_time < TIMESTAMP '2025-10-01'
```

### 1.2 Date Extraction

```sql
-- Grouping by day (keeps timestamp type, best for charts)
SELECT DATE_TRUNC('day', block_time) AS day

-- Pure date type (loses time component)
SELECT DATE(block_time) AS day

-- ❌ Postgres cast syntax
SELECT block_time::date
```

### 1.3 Integer Division & Overflow

Trino truncates integer division. Cast before dividing:

```sql
SELECT CAST(a AS DOUBLE) / b               -- ✅ returns decimal
SELECT a / b                                -- ❌ truncated to integer
```

Large integer multiplication overflows bigint. Cast first:

```sql
SELECT CAST(gas_price AS DOUBLE) * gas_used -- ✅ avoids overflow
SELECT gas_price * gas_used                 -- ⚠️ may overflow
```

### 1.4 Interval Syntax

Unit must be **singular** and **outside** the quotes:

```sql
WHERE block_time >= now() - interval '7' day        -- ✅
WHERE block_time >= date_add('day', -7, now())       -- ✅
WHERE block_time >= now() - interval '7 days'        -- ❌ Postgres-style
```

### 1.5 String Concatenation

Both forms are valid. Choose based on NULL handling needs:

```sql
CONCAT(a, b, c)         -- ✅ multi-arg, NULL in → NULL out
a || b || c              -- ✅ SQL-standard, also NULL-propagating
CONCAT_WS(', ', a, b, c) -- ✅ skips NULLs, joins with separator
```

### 1.6 NULL Handling

```sql
COALESCE(value, 0)                          -- first non-NULL
NULLIF(value, 0)                            -- NULL if value = 0
TRY(risky_expression)                       -- NULL on error
COALESCE(TRY(CAST(raw_value AS DOUBLE)), 0) -- parse with fallback
```

### 1.7 Identifiers & Addresses

```sql
-- Reserved words: double quotes (not backticks, not brackets)
SELECT "from", "to", "value" FROM ethereum.transactions

-- Addresses: bare hex, case-insensitive
WHERE "from" = 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045

-- ❌ Old Postgres V1 syntax
WHERE "from" = '\xd8da...'
```

### 1.8 Type System

No implicit conversions. Always cast explicitly:

```sql
SELECT CAST(number_value AS VARCHAR) || ' ETH' -- ✅
SELECT number_value || ' ETH'                  -- ❌ bigint + varchar fails
```

---

## 2. Query Template

Every query should follow this CTE layering pattern: **base → calculations → presentation**.

```sql
-- Query Title
-- https://dune.com/queries/XXXXXXX
-- Brief description of what this measures

WITH base_data AS (
  SELECT
    DATE_TRUNC('day', block_time) AS day,
    SUM(amount) AS total_amount,
    COUNT(*) AS tx_count
  FROM some_table
  WHERE block_time >= TIMESTAMP '2025-01-01'  -- time filter first (partition pruning)
    AND some_filter = 'value'
  GROUP BY 1
),

calculations AS (
  SELECT
    day,
    total_amount,
    tx_count,
    AVG(total_amount) OVER (
      ORDER BY day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS amount_7d_ma,
    SUM(total_amount) OVER (ORDER BY day) AS cumulative_amount
  FROM base_data
)

SELECT
  day,
  total_amount,
  amount_7d_ma,
  cumulative_amount,
  CASE
    WHEN total_amount > 1000 THEN 'HIGH'
    WHEN total_amount > 500 THEN 'MODERATE'
    WHEN total_amount > 100 THEN 'LOW'
    ELSE 'MINIMAL'
  END AS regime,
  500.0 AS threshold_line
FROM calculations
ORDER BY day
```

**Structure notes:**

- Time filter goes first in WHERE (enables partition pruning).
- `base_data` handles filtering and aggregation.
- `calculations` adds window functions (moving averages, cumulative sums).
- Final SELECT adds presentation logic (CASE labels, reference lines).
- A single query can power multiple dashboard widgets (see section 3.2).

---

## 3. Output Shapes

### 3.1 Widget Patterns

**Time series** (line/bar charts):

```sql
SELECT day, metric_value FROM ... ORDER BY day
```

**Single value** (counters):

```sql
-- Pattern A: Aggregate — simplest, no LIMIT needed
SELECT SUM(amount) AS total_volume
FROM some_table
WHERE block_time >= now() - interval '24' hour

-- Pattern B: Latest row from a time series
SELECT metric_value FROM ... ORDER BY day DESC LIMIT 1
-- ⚠️ Most recent day may have partial data
```

**Regime counters** (text display):

```sql
SELECT
  CASE WHEN ratio > 100 THEN 'DEFLATIONARY' ELSE 'INFLATIONARY' END AS regime
FROM ...
ORDER BY day DESC LIMIT 1
```

**Reference lines** (horizontal lines on charts):

```sql
SELECT day, metric_value, 100.0 AS breakeven_line FROM ...
```

**Pie charts** (keep ≤6 slices, group the long tail):

```sql
SELECT
  CASE WHEN rank <= 5 THEN category ELSE 'Other' END AS category,
  SUM(total) AS total
FROM (
  SELECT category, SUM(amount) AS total,
    ROW_NUMBER() OVER (ORDER BY SUM(amount) DESC) AS rank
  FROM ... GROUP BY 1
)
GROUP BY 1
```

**Tables:**

```sql
SELECT account, inflow, outflow, net_flow
FROM ... ORDER BY ABS(net_flow) DESC LIMIT 20
```

### 3.2 One Query, Multiple Widgets

A single query can power multiple dashboard widgets by selecting different columns:

```sql
SELECT
  day,
  burn_ratio,          -- Line chart: Y-axis
  burn_ratio_7d_ma,    -- Line chart: second series
  breakeven_line,      -- Line chart: reference line (constant 100)
  regime               -- Counter widget: latest value
FROM burn_pressure
ORDER BY day           -- ascending = counter uses last row (most recent)
```

Dashboard setup:

- Line chart widget: X = `day`, Y = `burn_ratio`, `burn_ratio_7d_ma`, `breakeven_line`
- Counter widget: Value = `regime`, uses latest row automatically
- If ORDER BY is changed to DESC, the counter grabs the **oldest** row instead.

### 3.3 Regime Labels

Keep labels short for counter widgets (truncate around ~20 chars):

```sql
-- ✅ Labels that fit
CASE
  WHEN x > 150 THEN 'STRONG DEFLATION'   -- 16 chars
  WHEN x > 100 THEN 'DEFLATIONARY'       -- 12 chars
  WHEN x > 50  THEN 'MILD INFLATION'     -- 14 chars
  ELSE              'INFLATIONARY'        -- 12 chars
END AS regime

-- ❌ Gets cut off in counter widgets
CASE WHEN x > 150 THEN 'STRONGLY DEFLATIONARY (burns exceed 150%)' END
```

Put detailed explanations in text widgets beside the counter, not in the SQL.

---

## 4. Error Handling

### 4.1 Common Errors and Fixes

| Error | Cause | Fix |
|---|---|---|
| Query timeout | No time filter (full table scan) | Add `WHERE block_time >= ...` and `blockchain = '...'` on cross-chain tables |
| "Column not found" | Wrong column name | Check schema in Dune explorer |
| "Function not found" | Postgres syntax in Trino | Use Trino equivalents (see section 1) |
| Push fails 403 | API key doesn't own/access query | Verify key context matches query owner; check private query permissions |
| Credit limit error | Billing cycle limit exceeded | Adjust limits in dune.com settings |
| No data returned | Wrong address, time range, or chain | Verify inputs; confirm you're querying the right chain |

### 4.2 Optimization Checklist

**Select only needed columns** — Dune uses columnar storage; fewer columns = less data scanned:

```sql
SELECT hash, "from", "to", value   -- ✅
SELECT *                           -- ❌ on large tables
```

**Put time filters in JOIN ON clauses** — enables partition pruning on both sides:

```sql
INNER JOIN ethereum.logs l
  ON t.hash = l.tx_hash
  AND t.block_date = l.block_date
  AND l.block_date >= TIMESTAMP '2024-10-01'
  AND l.block_date < TIMESTAMP '2024-10-02'
```

**ORDER BY requires LIMIT on large results:**

```sql
ORDER BY gas_price DESC LIMIT 1000 -- ✅
ORDER BY gas_price DESC            -- ❌ sorts entire table
```

**Use window functions over correlated subqueries:**

```sql
AVG(gas_used) OVER (
  ROWS BETWEEN 99 PRECEDING AND CURRENT ROW
)                                          -- ✅ single pass
(SELECT AVG(gas_used) FROM ... WHERE ...)  -- ❌ runs per row
```

**Use curated tables over raw data:**

```sql
dex.trades, tokens.transfers               -- ✅ pre-decoded, optimized
ethereum.logs + manual topic0 decoding     -- ❌ unless curated table doesn't exist
```

**Diagnose slow queries:**

```sql
EXPLAIN ANALYZE SELECT ... FROM ...        -- shows execution plan + full table scans
```

Further reading: https://docs.dune.com/query-engine/writing-efficient-queries

### 4.3 Revise Budget

When a query fails verification or execution, diagnose using §4.1, rewrite the SQL, and re-run through `verify.py`. **Cap: 2 revisions per query.** After the second failed retry, stop revising and surface to the user:

- The original query and the revised attempts
- The error from each attempt
- Your current best diagnosis of the root cause

This prevents grinding through Dune credits on a query that's structurally wrong (bad table choice, missing data, ambiguous spec). The user is faster than another retry at deciding whether to narrow the spec, change the metric, or accept that the data isn't available.

The cap applies to revisions of the *same* query for the *same* viz. A user follow-up that meaningfully changes the requirement resets the budget.

---

## 5. Technique Docs and Per-Source Leaves

This skill handles DuneSQL syntax and query patterns. For domain-specific knowledge, load the appropriate technique doc:

| I need... | Load this skill |
|---|---|
| Chain-specific tables, gas fees, decoding, daily users, price joins, token balances | `chain-references` (shared chain techniques) → per-chain leaf (e.g. `chain-solana`) |
| External API data via LiveFetch or Python | `api-references` (shared LiveFetch techniques) → per-API leaf (e.g. `api-defillama`) |

Technique docs and their per-source leaves are declared in the project's data spec. Do not load leaves speculatively — let the data spec declare dependencies.

---

## 6. Verification

After writing any SQL file, run the verification script:

```
python .claude/skills/dune-sql-best-practices/verify.py queries/<dashboard>/query_XXXXXXX.sql
```

This will:

- Static lint checks (time filters, SELECT * detection, known-large-table warnings)
- Dry-run via Dune Execute SQL API (requires `DUNE_API_KEY` in `.env`)
