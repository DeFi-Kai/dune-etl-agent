# Dune Analytics Pipeline

## Role
Data Engineer building narrative-driven Dune dashboards. Translate a data spec into DuneSQL queries, push to Dune, and maintain version control via GitHub.

## Project Structure
```
project/
├── queries/
│   ├── <dashboard>/               # One folder per dashboard
│   │   ├── query_XXXXXXX.sql      # Assigned query ID after push_to_dune
│   │   └── query_NEW_<name>.sql   # New queries before Dune assignment
│   └── <dashboard>/data/          # CSVs produced by GH Actions pipelines
├── queries.yml                    # Registry of all dashboards and query IDs
├── scripts/
│   ├── push_to_dune.py            # Push queries to Dune API
│   ├── pull_from_dune.py          # Pull latest from Dune
│   └── <pipeline>.py              # Per-pipeline GH Actions scripts
├── .github/workflows/             # GH Actions workflows for pipelines
├── .claude/skills/                # Agent knowledge modules
│   ├── dune-sql-best-practices/   # Core DuneSQL skill (Trino syntax, templates, output shapes) + verify.py
│   ├── chain-references/          # Technique doc: chain tables, gas models, decoding
│   ├── chain-<name>/              # Per-chain specifics (add as chains are declared)
│   ├── api-references/            # Technique doc: LiveFetch patterns for external APIs
│   ├── api-<name>/                # Per-API endpoint docs (add as APIs are declared)
│   ├── dune-actions-csv-upload/   # GH Actions + CSV upload escalation path
│   └── <protocol>/                # Per-protocol domain knowledge (add as needed)
└── context/                       # Local-only reference material (data specs, notes)
```

## Skills

`CLAUDE.md` is the only always-loaded anchor. Everything else is derived from the data spec. `dune-sql-best-practices` loads when a spec declares *any* chain or API (i.e., any Dune query task). `api-references` and `chain-references` are shared technique docs; load them when the spec mentions APIs or chains, then pull the per-API/per-chain files underneath as needed.

| Skill                     | When it loads                                                                                                                                                                         |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `dune-sql-best-practices` | Spec declares at least one chain or API (any DuneSQL task). Trino syntax, CTE template, widget output shapes, error handling, optimization, `verify.py` dry-run.                      |
| `chain-references`        | Technique doc for querying chain tables. Load when a chain is declared; consult per-chain files (e.g., `chain-<name>`) for specifics.                                                 |
| `api-references`          | Technique doc for inline API calls (`http_get` / `http_post`, JSON parsing, unnesting). Load when an API is declared; pair with per-API files for endpoints/limits.                   |
| `dune-actions-csv-upload` | Escalation path after a quota/429 or obviously too-large payload, **and only after the user confirms materializing**; documents Python + GH Actions CSV upload and user table wiring. |
| `<protocol>`              | Protocol-specific domain context for metrics and narratives. Add per project.                                                                                                         |

**Endpoint state lives in the workflow files.** There is no separate sidecar. If `.github/workflows/<endpoint>.yml` exists, that endpoint is materialized — query the user table it writes to. If no workflow file exists, the endpoint is inline — write LiveFetch SQL. The artifact's existence *is* the state.

## External Data: Inline first, confirm before materializing

Dune supports inline `http_get()` / `http_post()` (**LiveFetch**) inside SQL. **Default to inline.** It keeps logic in one place and avoids Python → CSV → upload. Load `api-references` for the technique (auth headers, JSON parsing, unnesting) plus the relevant per-API file for endpoints/limits.

### LiveFetch limits (per query execution)

| Constraint | Limit |
|---|---|
| Call timeout | 5 s per request |
| Throttle | 80 req/s per proxy (3 proxies per cluster) |
| Response size | 4 MB max |
| POST body | 1 MB max |

### When inline returns `429` / payload cap

**Pause. Do not auto-generate a workflow.** Surface a confirmation to the user containing:

- **Endpoint that capped** — exact URL/path so the user can confirm scope
- **Proposed table name** — e.g., `dune.<user>.<endpoint_slug>`
- **Refresh cadence** — default `daily 06:00 UTC`; flag if the source updates faster/slower
- **Estimated row count / payload size** — so the user can sanity-check before approving a recurring job

**On user approval:** load `dune-actions-csv-upload`, generate the Python script under `scripts/` and the GH Actions workflow under `.github/workflows/<endpoint>.yml`, run it once to seed the table under `queries/<dashboard>/data/`, then rewrite the SQL to query the user table.

**On user decline:** surface the cap error and let the user narrow the query (date range, row filter, fewer per-row API calls). Do not retry materialization without a fresh confirmation.

**Subsequent runs:** check for `.github/workflows/<endpoint>.yml` *before* writing SQL. If present, query the user table directly — never re-attempt inline for that endpoint.

## Query Workflow

### Canonical Flow

`verify.py` only catches *does it execute?* It can't catch *does it return the right answer?* That requires eyes on the chart in Dune. So **Dune is the correctness system; GitHub is the change-management system.** Every query follows this flow:

1. **Write SQL and run `verify.py`** locally — lint + ephemeral dry-run via `/v1/sql/execute`. Nothing is saved on Dune.
2. **`push_to_dune.py --verify`** — query is saved to Dune with an ID, executed once, results checked. The query is now live.
3. **Validate in Dune's UI** — charts, numbers, edge cases. Manual edits to the SQL in the UI are fine; this is where data correctness is confirmed. When satisfied, ask the agent to open a PR.
4. **Agent runs `pull_from_dune.py`, then opens the PR** — sync first, so the PR diff reflects what's actually on Dune (including any UI edits you made). Commit the synced state, push the branch, open the PR, merge when ready.

Because Dune is updated at step 2, queries are live before the PR exists. That ordering is intentional — correctness can only be checked on Dune, so the artifact has to be there first. GitHub records the merged history so any query can be rolled back later.

### Creating a New Query
```bash
# 1. Create feature branch
git checkout -b feat/new-metric

# 2. Write the query in the appropriate dashboard folder
# Save as queries/<dashboard>/query_NEW_<name>.sql

# 3. Push to Dune (creates query, renames file, updates queries.yml)
python scripts/push_to_dune.py --new-only --verify

# 4. Commit and open a PR
git add queries/ queries.yml
git commit -m "[FEAT] Add <description>"
git push -u origin feat/new-metric
gh pr create
```

### Updating Existing Queries
```bash
python scripts/push_to_dune.py --verify
git add queries/
git commit -m "[FIX] Description"
git push -u origin feat/<branch>
gh pr create
```

### Pulling Latest from Dune
```bash
python scripts/pull_from_dune.py
python scripts/pull_from_dune.py --dashboard <dashboard>
```

## Git Workflow
1. Never commit directly to `main`. Use `feat/<task-name>` branches.
2. Commit messages: `[TYPE] Description`
   - `[FEAT]` - New query or feature
   - `[FIX]` - Bug fix
   - `[REFACTOR]` - Code improvement
   - `[SYNC]` - Sync with Dune
3. Dune's GitHub integration auto-syncs from `main` branch.

## Adding a New Dashboard
1. Create folder: `queries/<dashboard>/`
2. Add entry to `queries.yml`:
   ```yaml
   dashboards:
     <dashboard>:
       name: "<Display Name>"
       url: "https://dune.com/<user>/<dashboard-slug>"
       query_ids: []
   ```
3. Create queries as `query_NEW_<name>.sql` in the folder
4. Run `python scripts/push_to_dune.py --new-only --verify`

## Reference
- **Sample data spec:** `examples/data_spec_example.md`
- **Leaf skill template:** `examples/leaf_skill_template.md`
- **Slash command:** `/run-spec <path>` (defined at `.claude/commands/run-spec.md`)
