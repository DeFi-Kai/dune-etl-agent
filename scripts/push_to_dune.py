"""
Push query SQL files to Dune via API.

Handles three scenarios:
1. Existing queries (query_XXXXXXX.sql) -> Updates the SQL on Dune
2. New queries (query_NEW_*.sql) -> Creates on Dune, renames file, updates queries.yml
3. Execute + verify after push (optional --verify flag)

Usage:
    python scripts/push_to_dune.py                              # Push all changed queries
    python scripts/push_to_dune.py --verify                     # Push + execute to verify
    python scripts/push_to_dune.py --new-only                   # Only push NEW queries
    python scripts/push_to_dune.py --dashboard ore              # Only push queries for specific dashboard
    python scripts/push_to_dune.py --file queries/ore/query_NEW_foo.sql  # Push specific file
"""

import os
import sys
import re
import time
import glob
import yaml
import requests


def load_env():
    env_paths = [
        os.path.join(os.getcwd(), ".env"),
        os.path.join(os.path.dirname(__file__), "..", ".env"),
    ]
    for env_path in env_paths:
        env_path = os.path.abspath(env_path)
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        os.environ.setdefault(key.strip(), value.strip())
            break


def get_headers(api_key):
    return {
        "X-Dune-API-Key": api_key,
        "Content-Type": "application/json",
    }


def read_sql(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def extract_name_from_sql(sql):
    """Extract query name from first comment line."""
    for line in sql.split("\n"):
        line = line.strip()
        if line.startswith("--") and not line.startswith("-- http"):
            return line.lstrip("- ").strip()
    return "Unnamed Query"


def extract_query_id(filename):
    """Extract numeric query ID from filename, or None if it's a NEW query."""
    basename = os.path.basename(filename)
    match = re.match(r"query_(\d+)\.sql", basename)
    if match:
        return int(match.group(1))
    return None


def extract_dashboard_from_path(filepath):
    """Extract dashboard name from file path (e.g., queries/ore/query_123.sql -> ore)."""
    parts = filepath.replace("\\", "/").split("/")
    if "queries" in parts:
        idx = parts.index("queries")
        if idx + 1 < len(parts) - 1:  # There's a subdirectory
            return parts[idx + 1]
    return None


def create_query(headers, name, sql):
    """Create a new query on Dune. Returns query_id."""
    resp = requests.post(
        "https://api.dune.com/api/v1/query",
        headers=headers,
        json={
            "name": name,
            "query_sql": sql,
            "query_engine": "trino",
            "is_private": False,
        },
    )
    if resp.status_code == 200:
        return resp.json().get("query_id")
    else:
        print(f"  CREATE FAILED: {resp.status_code} - {resp.text[:200]}")
        return None


def update_query(headers, query_id, sql, name=None):
    """Update an existing query's SQL on Dune."""
    payload = {"query_sql": sql}
    if name:
        payload["name"] = name
    resp = requests.patch(
        f"https://api.dune.com/api/v1/query/{query_id}",
        headers=headers,
        json=payload,
    )
    if resp.status_code == 200:
        return True
    else:
        print(f"  UPDATE FAILED: {resp.status_code} - {resp.text[:200]}")
        return False


def execute_and_verify(headers, query_id, timeout_secs=90):
    """Execute a query and wait for completion. Returns (success, message)."""
    resp = requests.post(
        f"https://api.dune.com/api/v1/query/{query_id}/execute",
        headers=headers,
        json={},
    )
    if resp.status_code != 200:
        return False, f"Execute failed: {resp.status_code} - {resp.text[:200]}"

    execution_id = resp.json().get("execution_id")
    polls = int(timeout_secs / 5)

    for i in range(polls):
        time.sleep(5)
        sr = requests.get(
            f"https://api.dune.com/api/v1/execution/{execution_id}/status",
            headers=headers,
        )
        if sr.status_code != 200:
            continue

        state = sr.json().get("state", "")
        if state == "QUERY_STATE_COMPLETED":
            # Get row count
            rr = requests.get(
                f"https://api.dune.com/api/v1/execution/{execution_id}/results?limit=1",
                headers=headers,
            )
            rows_info = ""
            if rr.status_code == 200:
                meta = rr.json().get("result", {}).get("metadata", {})
                cols = meta.get("column_names", [])
                rows_info = f", columns: {cols}"
            return True, f"Executed OK (id: {execution_id}{rows_info})"
        elif state == "QUERY_STATE_FAILED":
            error = sr.json().get("error", "Unknown error")
            return False, f"Execution failed: {error}"
        elif state == "QUERY_STATE_CANCELLED":
            return False, "Execution was cancelled"

    return False, f"Execution timed out after {timeout_secs}s (id: {execution_id})"


def load_queries_yml(project_root):
    """Load queries.yml and return the data structure."""
    yml_path = os.path.join(project_root, "queries.yml")
    with open(yml_path, "r") as f:
        return yaml.safe_load(f)


def save_queries_yml(project_root, data):
    """Save data to queries.yml."""
    yml_path = os.path.join(project_root, "queries.yml")
    with open(yml_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def update_queries_yml(project_root, dashboard, new_id):
    """Add a new query ID to queries.yml under the specified dashboard."""
    data = load_queries_yml(project_root)

    if "dashboards" not in data:
        data["dashboards"] = {}

    if dashboard not in data["dashboards"]:
        data["dashboards"][dashboard] = {"name": dashboard, "query_ids": []}

    ids = data["dashboards"][dashboard].get("query_ids", [])
    if new_id not in ids:
        ids.append(new_id)
        data["dashboards"][dashboard]["query_ids"] = ids
        save_queries_yml(project_root, data)
        return True
    return False


def rename_new_file(filepath, query_id):
    """Rename query_NEW_foo.sql to query_XXXXXXX.sql."""
    directory = os.path.dirname(filepath)
    new_path = os.path.join(directory, f"query_{query_id}.sql")
    os.rename(filepath, new_path)
    return new_path


def get_dashboard_query_ids(project_root, dashboard):
    """Get all query IDs for a specific dashboard."""
    data = load_queries_yml(project_root)
    if "dashboards" in data and dashboard in data["dashboards"]:
        return data["dashboards"][dashboard].get("query_ids", [])
    return []


def main():
    load_env()
    api_key = os.environ.get("DUNE_API_KEY")
    if not api_key:
        print("ERROR: DUNE_API_KEY not found")
        sys.exit(1)

    headers = get_headers(api_key)
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    queries_dir = os.path.join(project_root, "queries")

    verify = "--verify" in sys.argv
    new_only = "--new-only" in sys.argv
    dry_run = "--dry-run" in sys.argv

    specific_file = None
    if "--file" in sys.argv:
        idx = sys.argv.index("--file")
        if idx + 1 < len(sys.argv):
            specific_file = sys.argv[idx + 1]

    dashboard_filter = None
    if "--dashboard" in sys.argv:
        idx = sys.argv.index("--dashboard")
        if idx + 1 < len(sys.argv):
            dashboard_filter = sys.argv[idx + 1]

    # Collect files to process (recursive glob for subdirectories)
    if specific_file:
        files = [specific_file]
    elif new_only:
        files = sorted(glob.glob(os.path.join(queries_dir, "**/query_NEW_*.sql"), recursive=True))
    else:
        files = sorted(glob.glob(os.path.join(queries_dir, "**/query_*.sql"), recursive=True))

    # Filter by dashboard if specified
    if dashboard_filter:
        files = [f for f in files if extract_dashboard_from_path(f) == dashboard_filter]

    if not files:
        print("No query files found to push.")
        return

    print(f"Processing {len(files)} query file(s)...\n")

    created = 0
    updated = 0
    verified = 0
    failed = 0

    for filepath in files:
        sql = read_sql(filepath)
        name = extract_name_from_sql(sql)
        query_id = extract_query_id(filepath)
        dashboard = extract_dashboard_from_path(filepath)
        basename = os.path.basename(filepath)

        dashboard_label = f"[{dashboard}]" if dashboard else ""

        if query_id:
            # Existing query -> update
            if new_only:
                continue
            print(f"  {dashboard_label}[{query_id}] Updating: {name}")
            if dry_run:
                print(f"    [DRY RUN] Would update")
                updated += 1
                continue
            if update_query(headers, query_id, sql, name):
                updated += 1
                if verify:
                    print(f"    Verifying execution...")
                    ok, msg = execute_and_verify(headers, query_id)
                    if ok:
                        print(f"    [OK] {msg}")
                        verified += 1
                    else:
                        print(f"    [FAIL] {msg}")
                        failed += 1
            else:
                failed += 1
        else:
            # New query -> create
            print(f"  {dashboard_label}[NEW] Creating: {name}")
            if dry_run:
                print(f"    [DRY RUN] Would create in dashboard: {dashboard or 'unknown'}")
                created += 1
                continue
            new_id = create_query(headers, name, sql)
            if new_id:
                print(f"    Created as query {new_id}")
                created += 1

                # Rename file
                new_path = rename_new_file(filepath, new_id)
                print(f"    Renamed: {basename} -> query_{new_id}.sql")

                # Update header comment with Dune URL
                sql_updated = re.sub(
                    r"-- NEW QUERY.*\n",
                    f"-- https://dune.com/queries/{new_id}\n",
                    sql,
                    count=1,
                )
                with open(new_path, "w", encoding="utf-8") as f:
                    f.write(sql_updated)

                # Add to queries.yml under the appropriate dashboard
                if dashboard:
                    update_queries_yml(project_root, dashboard, new_id)
                    print(f"    Added to queries.yml under '{dashboard}'")
                else:
                    print(f"    WARNING: No dashboard detected, not added to queries.yml")

                if verify:
                    print(f"    Verifying execution...")
                    ok, msg = execute_and_verify(headers, new_id)
                    if ok:
                        print(f"    [OK] {msg}")
                        verified += 1
                    else:
                        print(f"    [FAIL] {msg}")
                        failed += 1

                time.sleep(1)  # Rate limit buffer between creates
            else:
                failed += 1

    print(f"\nDone: {created} created, {updated} updated", end="")
    if verify:
        print(f", {verified} verified, {failed} failed", end="")
    if dry_run:
        print(" (DRY RUN)", end="")
    print()

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
