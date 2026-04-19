"""
Pull query SQL from Dune API for all query IDs in queries.yml.
Saves each as queries/<dashboard>/query_XXXXXXX.sql

Usage:
    python scripts/pull_from_dune.py                  # Pull all dashboards
    python scripts/pull_from_dune.py --dashboard ore  # Pull specific dashboard
"""

import os
import sys
import yaml
import requests
import time


def load_env():
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    env_path = os.path.abspath(env_path)
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())


def main():
    load_env()
    api_key = os.environ.get("DUNE_API_KEY")
    if not api_key:
        print("ERROR: DUNE_API_KEY not found in .env or environment")
        sys.exit(1)

    # Parse args
    dashboard_filter = None
    if "--dashboard" in sys.argv:
        idx = sys.argv.index("--dashboard")
        if idx + 1 < len(sys.argv):
            dashboard_filter = sys.argv[idx + 1]

    # Load query IDs from new structure
    yml_path = os.path.join(os.path.dirname(__file__), "..", "queries.yml")
    yml_path = os.path.abspath(yml_path)
    with open(yml_path, "r") as f:
        data = yaml.safe_load(f)

    dashboards = data.get("dashboards", {})
    if not dashboards:
        # Fallback to old flat structure
        query_ids = data.get("query_ids", [])
        if query_ids:
            dashboards = {"default": {"query_ids": query_ids}}
        else:
            print("No dashboards or query_ids found in queries.yml")
            sys.exit(1)

    # Filter to specific dashboard if requested
    if dashboard_filter:
        if dashboard_filter not in dashboards:
            print(f"ERROR: Dashboard '{dashboard_filter}' not found in queries.yml")
            print(f"Available dashboards: {list(dashboards.keys())}")
            sys.exit(1)
        dashboards = {dashboard_filter: dashboards[dashboard_filter]}

    headers = {"X-Dune-API-Key": api_key}
    project_root = os.path.join(os.path.dirname(__file__), "..")
    project_root = os.path.abspath(project_root)

    total_success = 0
    total_failed = 0

    for dashboard_name, dashboard_config in dashboards.items():
        query_ids = dashboard_config.get("query_ids", [])
        if not query_ids:
            print(f"[{dashboard_name}] No queries to pull")
            continue

        # Create dashboard directory
        queries_dir = os.path.join(project_root, "queries", dashboard_name)
        os.makedirs(queries_dir, exist_ok=True)

        print(f"\n[{dashboard_name}] Pulling {len(query_ids)} queries...")

        success = 0
        failed = 0

        for qid in query_ids:
            url = f"https://api.dune.com/api/v1/query/{qid}"
            resp = requests.get(url, headers=headers)

            if resp.status_code == 200:
                data = resp.json()
                sql = data.get("query_sql", "")
                name = data.get("name", "unnamed")

                if not sql:
                    print(f"  [{qid}] WARNING: empty SQL, skipping")
                    failed += 1
                    continue

                filepath = os.path.join(queries_dir, f"query_{qid}.sql")
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(f"-- {name}\n")
                    f.write(f"-- https://dune.com/queries/{qid}\n\n")
                    f.write(sql)

                print(f"  [{qid}] {name}")
                success += 1
            elif resp.status_code == 429:
                print(f"  [{qid}] Rate limited, waiting 5s...")
                time.sleep(5)
                # Retry once
                resp = requests.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    sql = data.get("query_sql", "")
                    name = data.get("name", "unnamed")
                    if sql:
                        filepath = os.path.join(queries_dir, f"query_{qid}.sql")
                        with open(filepath, "w", encoding="utf-8") as f:
                            f.write(f"-- {name}\n")
                            f.write(f"-- https://dune.com/queries/{qid}\n\n")
                            f.write(sql)
                        print(f"  [{qid}] {name} (retry)")
                        success += 1
                    else:
                        failed += 1
                else:
                    print(f"  [{qid}] FAILED after retry: {resp.status_code}")
                    failed += 1
            else:
                print(f"  [{qid}] FAILED: {resp.status_code} - {resp.text[:100]}")
                failed += 1

            # Small delay to avoid rate limits
            time.sleep(0.5)

        print(f"[{dashboard_name}] Done: {success} pulled, {failed} failed")
        total_success += success
        total_failed += failed

    print(f"\nTotal: {total_success} pulled, {total_failed} failed")


if __name__ == "__main__":
    main()
