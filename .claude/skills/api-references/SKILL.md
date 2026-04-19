---
name: api-references
description: Shared techniques for fetching external data into DuneSQL via inline LiveFetch (http_get / http_post), JSON parsing, and unnesting. Pairs with per-API leaf files for endpoints, auth, and rate limits.
usage: Load when the data spec declares one or more APIs; then load the matching `api-<name>` leaf for endpoints/auth/limits.
---

# API References

This is a shared technique doc for fetching external data into DuneSQL using inline LiveFetch functions. Load the per-API leaves for endpoint details, rate limits, and schemas based on the data spec — load only what the spec declares. Inline is the default for every endpoint; if an endpoint hits the payload cap, ask the user to confirm before materializing (see Escalation path below).

Available API skills:
- `api-defillama` — Historical chain DEX volume, fees, TVL, and protocol detail
- *(add more as needed — see `examples/leaf_skill_template.md`)*

---

## 1. LiveFetch Basics

DuneSQL can call external APIs directly inside queries using `http_get()` and `http_post()`. No Python needed for simple cases.

### GET request
```sql
SELECT http_get('https://api.example.com/endpoint')
```

### GET with auth headers
```sql
SELECT http_get(
  'https://api.example.com/endpoint',
  ARRAY['Authorization: Bearer {{api_key}}']
)
```

Use `{{api_key}}` as a Dune query parameter to avoid hardcoding credentials. **Keep the query private if credentials are hardcoded.**

### POST request (e.g., RPC calls)
```sql
SELECT http_post(
  'https://docs-demo.quiknode.pro',
  '{"method":"eth_chainId","params":[],"id":1,"jsonrpc":"2.0"}',
  ARRAY['Content-Type: application/json']
)
```

**Escaping single quotes:** Double them inside varchar strings. `''` renders as `'`.

---

## 2. Parsing JSON Responses

API responses are returned as `varchar`. Parse with Trino JSON functions:

### Extract a single value
```sql
SELECT json_extract_scalar(
  http_get('https://api.example.com/data'),
  '$.result.price'
) AS price
```

### Unnest an array response into rows
```sql
SELECT * FROM UNNEST(
  CAST(
    json_parse(http_get('https://api.example.com/items'))
    AS array(json)
  )
) t(item)
```

### Extract multiple fields from array elements
```sql
SELECT
  json_extract_scalar(item, '$.id')     AS id,
  json_extract_scalar(item, '$.symbol') AS symbol,
  json_extract_scalar(item, '$.name')   AS name
FROM UNNEST(
  CAST(
    json_parse(http_get('https://api.example.com/items'))
    AS array(json)
  )
) t(item)
```

---

## 3. Parametrizing with Dune Data

Use `concat()` to build URLs dynamically from query results:
```sql
SELECT
  contract_address,
  http_get(
    concat(
      'https://coins.llama.fi/prices/current/ethereum:',
      CAST(contract_address AS varchar)
    )
  ) AS price_data
FROM tokens_ethereum.stablecoins
```

### Use a subquery to avoid repeated calls

When using an API result as a filter, wrap in a subquery so it executes once:
```sql
SELECT *
FROM ethereum.transactions t1,
  (SELECT from_hex(
    json_extract_scalar(
      http_get('https://api.ensideas.com/ens/resolve/vitalik.eth'),
      '$.address'
    )
  )) t2(resolved_address)
WHERE t1."from" = t2.resolved_address
  AND t1.block_time >= TIMESTAMP '2025-01-01'
```

---

## 4. LiveFetch Limits

| Constraint | Limit |
|---|---|
| Call timeout | 5 seconds per request |
| Throttle | 80 requests/second per proxy (3 proxies per cluster) |
| Response size | 4 MB max |
| Request body (POST) | 1 MB max |

These limits are **per query execution**, shared across all `http_get()` and `http_post()` calls in the query.

---

## 5. When to Escalate to GitHub Actions

LiveFetch works well for small, bounded API calls. Escalate when:

- **Row count × API calls exceeds throttle limits** — If your query joins API results against a large table (e.g., calling a price endpoint for every row in a 10k+ result set), you'll hit the 80 req/s throttle and the query will timeout.
- **Response data exceeds 4 MB** — Large historical datasets won't fit in a single response.
- **API requires pagination** — LiveFetch has no loop construct. If the data requires multiple sequential paginated calls, SQL can't do it.
- **API rate limits are stricter than Dune's throttle** — Many free-tier APIs (e.g. Etherscan) limit to 5-30 req/min. LiveFetch will blast through that instantly.

### Escalation path

When LiveFetch won't work for a specific endpoint/pattern, the path is:

1. **Pause and ask the user to confirm materializing the endpoint.** Surface:
   - The endpoint URL/path that capped
   - The proposed user-table name (e.g. `dune.<user>.<endpoint>`)
   - The refresh cadence (default `daily 06:00 UTC`)
   - An estimated row count / payload size
2. **Only on approval**, load `dune-actions-csv-upload` and:
   - Write a Python script under `scripts/` that calls the API with proper rate limiting and pagination
   - Output results to CSV under `queries/<dashboard>/data/`
   - Upload to Dune as a custom data source via the Dune API
   - Add a workflow at `.github/workflows/<endpoint>.yml` to schedule recurring refreshes
   - Rewrite the SQL to query the uploaded table
3. **The presence of `.github/workflows/<endpoint>.yml`** is the source of truth that the endpoint is materialized — future runs check for that file before writing SQL and skip inline if it exists.
4. **On decline**, surface the cap error so the user can narrow the query (date range, row filter, fewer per-row API calls).

> **Load the `dune-actions-csv-upload` skill for implementation details — but only after the user confirms.**

---

## 6. Quick Reference: API Skill Selection

| I need... | Load this skill |
|---|---|
| Chain DEX volume, chain fees, chain TVL, protocol detail | `api-defillama` |
| A specific endpoint is too large/rate-limited for inline | `dune-actions-csv-upload` (only after the user confirms materializing it) |

If the API you need isn't listed, the LiveFetch patterns in sections 1-3 above apply to any HTTP endpoint. Add a new API sub-skill when you find yourself repeatedly referencing the same API's endpoints and response schemas.
