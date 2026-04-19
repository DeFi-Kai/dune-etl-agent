"""
Dune SQL Query Verification Script

Static checks + dry-run via Dune API (create temp query → execute → archive).

Usage:
    python verify.py <path_to_sql_file>
    python verify.py queries/query_6610176.sql
    python verify.py queries/query_NEW_foo.sql --dry-run   # Force dry-run
    python verify.py queries/query_6610176.sql --static     # Static only

Requires DUNE_API_KEY in .env (or environment) for dry-run execution.
"""

import sys
import os
import re
import time

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


def load_env():
    """Load .env file from project root."""
    env_paths = [
        os.path.join(os.getcwd(), ".env"),
        os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"),
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


def static_checks(sql: str, filepath: str) -> list:
    """Run static lint checks on SQL content. Returns list of (level, message)."""
    issues = []
    sql_lower = sql.lower()

    # Check: SELECT * without WHERE
    if re.search(r'select\s+\*\s+from', sql_lower):
        if 'where' not in sql_lower:
            issues.append(("ERROR", "SELECT * without WHERE clause detected"))
        else:
            issues.append(("WARN", "SELECT * detected - consider specifying columns"))

    # Check: Missing time filter on known large tables
    large_tables = ['solana.transactions', 'solana.account_activity',
                    'solana.instruction_calls', 'solana.rewards']
    for table in large_tables:
        if table in sql_lower:
            if not re.search(r'block_time\s*[><=]', sql_lower):
                issues.append(("ERROR",
                    f"Query uses {table} without block_time filter - will timeout"))

    # Check: Has a time filter somewhere
    has_time_filter = any(pattern in sql_lower for pattern in [
        'block_time', 'now()', 'current_timestamp', 'interval',
    ])
    if not has_time_filter:
        issues.append(("WARN", "No time-based filter detected"))

    # Check: Reasonable interval (not scanning too far back)
    year_scan = re.search(r"interval\s+'(\d+)\s+year", sql_lower)
    if year_scan and int(year_scan.group(1)) > 1:
        issues.append(("WARN",
            f"Scanning {year_scan.group(1)} years of data - may be slow"))

    return issues


def extract_query_id(filepath):
    """Extract numeric query ID from filename, or None if NEW."""
    basename = os.path.basename(filepath)
    match = re.match(r"query_(\d+)\.sql", basename)
    return int(match.group(1)) if match else None


def dry_run(sql: str, api_key: str, existing_id=None) -> dict:
    """
    Dry-run a query on Dune.
    - If existing_id: execute that saved query directly via /v1/query/{id}/execute
    - If no existing_id: use /v1/sql/execute to run raw SQL (no temp query needed)
    """
    if not HAS_REQUESTS:
        return {"status": "skipped", "message": "requests library not installed (pip install requests)"}

    headers = {
        "X-Dune-API-Key": api_key,
        "Content-Type": "application/json",
    }

    try:
        if existing_id:
            # Execute saved query by ID
            resp = requests.post(
                f"https://api.dune.com/api/v1/query/{existing_id}/execute",
                headers=headers,
                json={},
            )
        else:
            # Execute raw SQL directly (no temp query needed)
            resp = requests.post(
                "https://api.dune.com/api/v1/sql/execute",
                headers=headers,
                json={"sql": sql, "performance": "medium"},
            )

        if resp.status_code != 200:
            return {"status": "error", "message": f"Execute failed: {resp.status_code} - {resp.text[:200]}"}

        execution_id = resp.json().get("execution_id")

        # Poll for result (max 90s)
        for _ in range(18):
            time.sleep(5)
            sr = requests.get(
                f"https://api.dune.com/api/v1/execution/{execution_id}/status",
                headers=headers,
            )
            if sr.status_code != 200:
                continue

            state = sr.json().get("state", "")
            if state == "QUERY_STATE_COMPLETED":
                # Get column info
                rr = requests.get(
                    f"https://api.dune.com/api/v1/execution/{execution_id}/results?limit=1",
                    headers=headers,
                )
                cols = []
                row_sample = None
                if rr.status_code == 200:
                    meta = rr.json().get("result", {}).get("metadata", {})
                    cols = meta.get("column_names", [])
                    rows = rr.json().get("result", {}).get("rows", [])
                    if rows:
                        row_sample = rows[0]

                return {
                    "status": "success",
                    "execution_id": execution_id,
                    "columns": cols,
                    "sample_row": row_sample,
                }
            elif state == "QUERY_STATE_FAILED":
                error = sr.json().get("error", "Unknown error")
                return {"status": "failed", "message": error, "execution_id": execution_id}
            elif state == "QUERY_STATE_CANCELLED":
                return {"status": "cancelled", "execution_id": execution_id}

        return {"status": "timeout", "message": "Execution did not complete within 90s",
                "execution_id": execution_id}

    except Exception as e:
        return {"status": "error", "message": str(e)}


def main():
    if len(sys.argv) < 2:
        print("Usage: python verify.py <path_to_sql_file> [--dry-run] [--static]")
        sys.exit(1)

    filepath = sys.argv[1]
    static_only = "--static" in sys.argv
    force_dry_run = "--dry-run" in sys.argv

    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        sys.exit(1)

    with open(filepath, "r") as f:
        sql = f.read()

    print(f"=== Verifying: {filepath} ===\n")

    # Static checks
    issues = static_checks(sql, filepath)
    errors = [i for i in issues if i[0] == "ERROR"]

    if not issues:
        print("[STATIC] All checks passed")
    else:
        for level, msg in issues:
            print(f"[STATIC] {level}: {msg}")

    if errors:
        print(f"\n{len(errors)} error(s) found. Fix before committing.")
        sys.exit(1)

    if static_only:
        print("\n=== Verification complete (static only) ===")
        return

    # Dry run
    load_env()
    api_key = os.environ.get("DUNE_API_KEY")

    if not api_key:
        print("\n[DRY-RUN] Skipped (no DUNE_API_KEY in environment)")
    else:
        existing_id = extract_query_id(filepath)

        if existing_id and not force_dry_run:
            print(f"\n[DRY-RUN] Executing existing query {existing_id}...")
        else:
            print(f"\n[DRY-RUN] Creating temp query and executing...")

        result = dry_run(sql, api_key, existing_id if not force_dry_run else None)
        status = result["status"]

        if status == "success":
            cols = result.get("columns", [])
            sample = result.get("sample_row")
            print(f"[DRY-RUN] SUCCESS (execution: {result['execution_id']})")
            if cols:
                print(f"[DRY-RUN] Columns: {', '.join(cols)}")
            if sample:
                print(f"[DRY-RUN] Sample: {sample}")
        elif status == "skipped":
            print(f"[DRY-RUN] {result['message']}")
        else:
            print(f"[DRY-RUN] {status.upper()}: {result.get('message', '')}")
            if status == "failed":
                sys.exit(1)

    print("\n=== Verification complete ===")


if __name__ == "__main__":
    main()
