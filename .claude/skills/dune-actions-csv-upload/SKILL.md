---
name: dune-pipeline
description: Pattern for building Python data pipelines that fetch external API data, produce CSVs, upload to Dune as custom tables, and run via GitHub Actions.
usage: Use this when Dune SQL limitations (API rate limits, stage limits, complex data transforms) require an external Python script to prepare data for Dune dashboards.
---

# Dune Data Pipeline — Python + GitHub Actions

## When to Use This Pattern

- Dune's `http_get()` hits rate limits (DefiLlama allows ~7 concurrent calls max)
- Query exceeds Dune's "too many stages" limit (~30-50 stages)
- Data requires complex transforms that are painful in Trino SQL (CSV parsing, multi-step attribution)
- You need data from multiple APIs combined before loading into Dune

## Architecture

```
GitHub Action (scheduled) → Python script → CSVs to repo → Upload to Dune API
                                                          → Query as normal table
```

The script runs outside Dune, fetches all the data it needs (no rate limit issues), processes it, writes CSVs to the repo, and uploads them to Dune as custom tables.

## 1. Python Script Structure

Place scripts in `scripts/`. Follow this pattern:

```python
#!/usr/bin/env python3
import os
import time
import requests
import pandas as pd
from pathlib import Path

DELAY = 1.5  # seconds between API calls to respect rate limits
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "queries" / "<dashboard>" / "data"

def fetch_json(url: str, label: str = "") -> dict:
    """Fetch with retry and rate-limit delay."""
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            time.sleep(DELAY)
            return resp.json()
        except (requests.RequestException, ValueError) as e:
            print(f"  [retry {attempt+1}/3] {label or url}: {e}")
            time.sleep(DELAY * 2)
    raise RuntimeError(f"Failed to fetch {label or url} after 3 attempts")

def upload_to_dune(csv_path: Path, table_name: str, description: str):
    """Upload CSV to Dune. Requires DUNE_API_KEY env var."""
    api_key = os.environ.get("DUNE_API_KEY")
    if not api_key:
        print(f"  Skipping Dune upload for {table_name} (DUNE_API_KEY not set)")
        return

    print(f"  Uploading {table_name} to Dune...")
    resp = requests.post(
        "https://api.dune.com/api/v1/uploads/csv",
        headers={
            "X-DUNE-API-KEY": api_key,
            "Content-Type": "application/json",
        },
        json={
            "table_name": table_name,
            "description": description,
            "data": csv_path.read_text(),
            "is_private": False,
        },
        timeout=60,
    )
    if resp.ok:
        print(f"  Uploaded: {resp.json()}")
    else:
        print(f"  ERROR: {resp.status_code} {resp.text}")

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # 1. Fetch data (sequential with delays)
    # 2. Transform / merge / aggregate
    # 3. Write CSVs
    # 4. Upload to Dune
    upload_to_dune(csv_path, "my_table", "Description of table")

if __name__ == "__main__":
    main()
```

### Key points:
- **Sequential fetches with delay** (1.5s) to respect API rate limits
- **3 retries** with exponential backoff on failures
- **Graceful skip** when `DUNE_API_KEY` is not set (local dev)
- **Output CSVs** go to `queries/<dashboard>/data/` so they're versioned alongside queries

## 2. Dune Upload API

### Endpoint
```
POST https://api.dune.com/api/v1/uploads/csv
```

**NOT** `/v1/table/upload/csv` — that's deprecated.

### Request
```json
{
  "table_name": "my_table_name",
  "description": "What this data is",
  "data": "col_a,col_b\n1,hello\n2,world",
  "is_private": false
}
```

### Important details:
- **Overwrites** entire table on each upload (fine for pipelines that regenerate all data)
- Dune adds a **`dataset_` prefix** automatically → table becomes `dune.<namespace>.dataset_<table_name>`
- **Namespace** = your Dune username or team (derived from the API key)
- Column names **cannot start with digits or special characters**
- Max file size: **200 MB**
- Storage limits: Free = 100MB, Plus = 15GB, Enterprise = 200GB+
- Costs **3 credits per GB written** (minimum 1 credit)

### Querying uploaded tables
```sql
SELECT * FROM dune.<namespace>.dataset_<table_name> ORDER BY week
```

Example: if namespace is `blocmatesresearch` and table_name is `chaingdp_combined`:
```sql
SELECT * FROM dune.blocmatesresearch.dataset_chaingdp_combined
```

Tables appear in Dune under **My Creations → Data** (or team workspace → Data).

## 3. GitHub Action Workflow

Place in `.github/workflows/<name>.yml`:

```yaml
name: My Data Pipeline

on:
  schedule:
    - cron: '0 6 * * 1'  # Weekly on Monday at 06:00 UTC
  workflow_dispatch:       # Manual trigger from Actions tab

permissions:
  contents: write  # Required for git push to commit CSVs back to repo

jobs:
  update-data:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: pip install pandas requests

      - name: Run pipeline
        env:
          DUNE_API_KEY: ${{ secrets.DUNE_API_KEY }}
        run: python scripts/my_pipeline.py

      - name: Commit and push CSVs
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add queries/<dashboard>/data/
          git diff --cached --quiet && echo "No changes to commit" && exit 0
          git commit -m "[SYNC] Update <dashboard> data"
          git push
```

### Setup steps:
1. Get Dune API key from https://dune.com/settings/api
2. Add as GitHub repo secret: **Settings → Secrets and variables → Actions → New repository secret** → Name: `DUNE_API_KEY`
3. Push the workflow file and script to `main`
4. Trigger manually: **Actions tab → workflow name → Run workflow**

Secrets are available immediately — no merge/deploy needed.

## 4. DefiLlama API Reference

These are the most commonly used endpoints for chain GDP pipelines.

### Chain app revenue time series
```
GET https://api.llama.fi/overview/fees/{Chain}
    ?excludeTotalDataChart=false
    &excludeTotalDataChartBreakdown=true
    &dataType=dailyRevenue
```
Returns `totalDataChart`: array of `[unix_timestamp, revenue_usd]`.

Chains use title case: `Solana`, `Ethereum`, `Base`, `BSC`, `Tron`, `Arbitrum`, `Optimism`, `Hyperliquid`.

### Protocol revenue time series
```
GET https://api.llama.fi/summary/fees/{protocol}?dataType=dailyRevenue
```
Example protocols: `circle`, `tether`.

### Stablecoin supply shares
```
GET https://stablecoins.llama.fi/stablecoins?includePrices=true
```
Returns `peggedAssets[]` with `chainCirculating.{Chain}.current.peggedUSD` and `circulating.peggedUSD`.

### Global fees (all chains in one call)
```
GET https://api.llama.fi/overview/fees
    ?excludeTotalDataChart=true
    &excludeTotalDataChartBreakdown=true
    &dataType=dailyRevenue
```
Returns `protocols[]` with `breakdown30d.{chain}` (lowercase keys). Good for summary/snapshot data but no time series.

## 5. Gotchas & Lessons Learned

- **USDT name**: In the stablecoins API, Tether's name is `"Tether"`, NOT `"Tether USD"`. USDC is `"USD Coin"`.
- **Dune endpoint**: Use `/v1/uploads/csv`, not `/v1/table/upload/csv` (deprecated, removal planned).
- **`dataset_` prefix**: Dune auto-prepends this to your table name. Don't include it yourself.
- **Workflow permissions**: The workflow MUST include `permissions: contents: write` at the top level, otherwise `git push` fails with 403 "Write access to repository not granted".
- **Git remote auth**: If `git push` fails with "repository not found" on a private repo, use `https://<username>@github.com/...` or fix credentials with `gh auth setup-git`.
- **Branch tracking**: When pushing a feature branch, use `git push -u origin <branch>` to set upstream correctly.
- **PR commit scope**: Verify all commits land on the PR before merging. Check with `gh pr view <n> --json commits`.
- **Local dev**: The script works without `DUNE_API_KEY` — it generates CSVs locally and skips the upload step.
- **Incomplete weeks**: Drop the last week in time series aggregation since it's likely partial data.
- **Double-counting stablecoins**: When adding supply-share attribution for Circle/Tether, filter them from DefiLlama's native protocol data (`SKIP_PROTOCOLS = {"circle", "tether"}` in Python, `AND LOWER(key) NOT IN ('circle', 'tether')` in Dune SQL) to prevent counting their revenue twice.
- **Optimism stablecoin key**: The stablecoins API uses `"OP Mainnet"` for Optimism, not `"Optimism"`. Use bracket notation in Dune SQL: `json_extract_scalar(json_extract(coin, '$.chainCirculating'), '$["OP Mainnet"].current.peggedUSD')`.

## 6. Reference Implementation

See `scripts/chaingdp_timeseries.py` and `.github/workflows/chaingdp_timeseries.yml` for a working example that:
- Fetches weekly GDP for 8 chains from DefiLlama (8 sequential API calls)
- Fetches Circle + Tether daily revenue (2 calls)
- Fetches USDC/USDT supply shares per chain (1 call)
- Attributes stablecoin issuer revenue proportionally to each chain
- Aggregates to weekly buckets
- Outputs 3 CSVs (combined + breakdown + categories)
- Uploads all to Dune as custom tables
