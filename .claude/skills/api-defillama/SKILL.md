---
name: api-defillama
description: Per-API leaf for DefiLlama. Key endpoints (chain DEX volume, chain fees, chain TVL, protocol detail), auth, rate limits, and response schemas. Pairs with api-references.
usage: Load when the data spec declares `defillama`. Load alongside api-references.
---

# DefiLlama

Leaf skill for DefiLlama's public API. Use alongside `api-references` (shared LiveFetch techniques) and `dune-sql-best-practices` (SQL + verify).

## 1) Base URL

| Surface | Base |
|---|---|
| Protocols / TVL / volumes / fees | `https://api.llama.fi` |

Keyless — no header or query-param auth required on the endpoints below.

## 2) Rate limits

- **Free tier:** ~300 requests / 5 minutes per IP. Hit it and you get `429`.
- LiveFetch from Dune shares a pool of proxy IPs, so multiple concurrent queries can burn the budget fast. If you're iterating over many rows (e.g. per-protocol loops), materialize instead — see `api-references` §5.

## 3) Key endpoints

### Historical DEX volume — `GET /overview/dexs/{chain}`

**Params:** `chain` (path), `excludeTotalDataChart=false` (required to get the chart)
**Data field:** `$.totalDataChart` → `ARRAY<ARRAY<DOUBLE>>` where each point is `[timestamp, volume_usd]`

```sql
WITH raw AS (
  SELECT http_get('https://api.llama.fi/overview/dexs/Ethereum?excludeTotalDataChart=false') AS response
),
chart AS (
  SELECT CAST(json_extract(response, '$.totalDataChart') AS ARRAY<ARRAY<DOUBLE>>) AS arr
  FROM raw
),
unnested AS (
  SELECT point[1] AS ts, point[2] AS volume
  FROM chart
  CROSS JOIN UNNEST(arr) AS t(point)
)
SELECT
  DATE(FROM_UNIXTIME(CAST(ts AS BIGINT))) AS date,
  volume
FROM unnested
ORDER BY date DESC
```

### Historical chain fees — `GET /overview/fees/{chain}`

**Params:** `chain` (path), `excludeTotalDataChart=false`, `excludeTotalDataChartBreakdown=true` (drops the per-protocol breakdown that bloats response size)
**Data field:** `$.totalDataChart` → `ARRAY<ARRAY<DOUBLE>>` where each point is `[timestamp, fees_usd]`

```sql
WITH raw AS (
  SELECT http_get('https://api.llama.fi/overview/fees/Ethereum?excludeTotalDataChart=false&excludeTotalDataChartBreakdown=true') AS response
),
chart AS (
  SELECT CAST(json_extract(response, '$.totalDataChart') AS ARRAY<ARRAY<DOUBLE>>) AS arr
  FROM raw
),
unnested AS (
  SELECT point[1] AS ts, point[2] AS fees
  FROM chart
  CROSS JOIN UNNEST(arr) AS t(point)
)
SELECT
  DATE(FROM_UNIXTIME(CAST(ts AS BIGINT))) AS date,
  fees
FROM unnested
ORDER BY date DESC
```

### Historical chain TVL — `GET /v2/historicalChainTvl/{chain}`

**Params:** `chain` (path)
**Response shape is different from the overview endpoints** — top-level array of `{date, tvl}` maps, so cast to `ARRAY<MAP<VARCHAR, DOUBLE>>` and index by key instead of position.

```sql
WITH raw AS (
  SELECT http_get('https://api.llama.fi/v2/historicalChainTvl/Ethereum') AS response
),
parsed AS (
  SELECT CAST(json_parse(response) AS ARRAY<MAP<VARCHAR, DOUBLE>>) AS arr
  FROM raw
),
unnested AS (
  SELECT point['date'] AS ts, point['tvl'] AS tvl
  FROM parsed
  CROSS JOIN UNNEST(arr) AS t(point)
)
SELECT
  DATE(FROM_UNIXTIME(CAST(ts AS BIGINT))) AS date,
  tvl
FROM unnested
ORDER BY date DESC
```

### Protocol detail — `GET /protocol/{protocol}`

**Params:** `protocol` (slug — e.g. `aave`, `uniswap`)
**Notes:** Lending protocols expose both TVL and borrowed TVL (outstanding debt) under `chainTvls`:
- `chainTvls.<chain>.tvl` — supplied liquidity on that chain
- `chainTvls.<chain>-borrowed.tvl` — outstanding debt on that chain

**Response size warning:** full history for large protocols can exceed the 4 MB LiveFetch cap. Materialize if you need the full series — see `api-references` §5.

## 4) Response shape quick reference

The `/overview/dexs` and `/overview/fees` endpoints return the same envelope:

```
{
  chain, total24h, total48hto24h, total7d, total30d, total1y, totalAllTime,
  change_1d, change_7d, change_1m,
  totalDataChart:           ARRAY<[timestamp, value]>            ← use this for timeseries
  totalDataChartBreakdown:  ARRAY<[timestamp, {protocol: value}]> ← bloats payload, exclude unless needed
  protocols:                ARRAY<protocol object>
  allChains:                ARRAY<chain name>
}
```

**Important:** `totalDataChartBreakdown` is what pushes the `/overview/fees/*` response over the 4 MB cap. Always pass `excludeTotalDataChartBreakdown=true` unless you specifically need the per-protocol split — and if you do, consider materializing.

`/v2/historicalChainTvl/{chain}` returns a **top-level array** of `{date, tvl}` objects — not the envelope above.

`/protocol/{slug}` top-level keys include `name`, `tvl` (timeseries), `chainTvls` (nested per-chain breakdown with `-borrowed` variants for lending protocols), `tokensInUsd`, `tokens`.

## 5) When to materialize

Materialize (Python script + GH Action, pattern in `dune-actions-csv-upload`) when:
- `/protocol/{slug}` full history for large protocols — often >4 MB
- Any per-row loop across >100 rows — 80 req/s throttle + 300/5min rate limit will trip `429`
- You need `totalDataChartBreakdown` and the response exceeds 4 MB inline

## 6) Further reading
- DefiLlama API docs: https://defillama.com/docs/api
