---
description: Generate Dune queries from a data spec. Pass a file path, paste the spec inline, or run with no args to be prompted.
---

Generate Dune queries from the data spec provided as: `$ARGUMENTS`

Follow this workflow exactly:

## 1. Load the spec

Decide how to interpret `$ARGUMENTS`:

- **Empty** — ask the user: "Paste the spec here, or give me a path to one." Wait for their reply. Treat the reply as either a path or pasted content using the rules below.
- **Looks like a path** — a single token ending in `.md`, or matching a file that exists on disk. Read the file with the Read tool.
- **Looks like pasted spec content** — contains `---` frontmatter delimiters or a `## Visualizations` heading. Parse it directly as if it were the file contents.
- **Ambiguous** — ask the user to clarify before proceeding.

Once the spec is loaded, parse the frontmatter for `project`, `chains`, `apis`, and `refresh`. Read the `## Visualizations` section — each numbered item is one query.

If the spec came from a paste (not a file), **ask the user where to save it** (typically `context/<project>.md`) and write it there before continuing, so the canonical flow has a stable file to reference.

## 2. Load the right skills

Always required:
- `dune-sql-best-practices` (SQL patterns + verify.py + 2-retry cap)

Load based on the spec:
- For every chain in `chains:` — load `chain-references` plus the leaf `chain-<name>` (e.g. `chain-solana`)
- For every API in `apis:` — load `api-references` plus the leaf `api-<name>` (e.g. `api-defillama`)

**If a declared leaf does not exist** (e.g. spec says `chains: [avalanche]` but `.claude/skills/chain-avalanche/` is missing): stop before writing any SQL. Tell the user the leaf is missing, show the template at `examples/leaf_skill_template.md`, and ask them to either author the leaf or remove the entry from the spec.

## 3. Confirm the dashboard target

Check `queries.yml` for an entry matching `project`. If it exists, use that dashboard's folder (`queries/<project>/`). If not, ask the user: create a new dashboard entry, or write queries under a different existing dashboard?

## 4. For each visualization, follow the canonical flow

Per the flow in `CLAUDE.md` → Query Workflow:

1. **Write SQL** under `queries/<dashboard>/query_NEW_<slug>.sql`. Pick the right mode:
   - **Pure Dune** if the viz only needs chain tables
   - **User-table reference** if `.github/workflows/<endpoint>.yml` exists for an endpoint the viz depends on
   - **Inline LiveFetch** if the viz pulls from an API and no workflow file exists
2. **Run `verify.py`** on the new file — lint + dry-run. On failure, consult `dune-sql-best-practices` §4 error handling, revise, retry. Cap at **2 revisions**. If still failing, stop and surface the error to the user.
3. **If `verify.py` passes**, run `push_to_dune.py --new-only --verify` to save on Dune and rename the file to `query_<id>.sql`.
4. **If execution returns a LiveFetch payload cap (429 / >4 MB)**, pause and ask the user to confirm materializing per `api-references` §5. Do not auto-generate a workflow.

## 5. Hand back to the user

When all visualizations have been pushed:
- List each query ID and its URL on Dune
- Remind the user to validate in Dune's UI — configure charts, check numbers, make any SQL edits
- Tell them that when they're satisfied, they should ask you to open a PR (you'll run `pull_from_dune.py` first to sync any UI edits, then open the PR)

Do not open a PR automatically. The user validates in Dune first.
