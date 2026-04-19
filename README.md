# Dune ETL Agent

An agent-driven ETL pipeline for Dune Analytics dashboards. You fill out a data spec, the agent writes, tests, and pushes DuneSQL queries to Dune, with GitHub for version control and optional GitHub Actions for materializing heavy API endpoints.

Designed to run under [Claude Code](https://claude.com/claude-code) — the `.claude/skills/` tree contains the agent's knowledge modules.

## What's in here

```
.
├── CLAUDE.md                        # Always-loaded agent instructions + canonical flow
├── queries.yml                      # Registry of dashboards and query IDs (starts empty)
├── .env.example                     # Copy to .env and fill in your Dune API key
├── .gitignore
├── .claude/
│   ├── commands/
│   │   └── run-spec.md              # Slash command: /run-spec <path> — orchestrates a full run
│   └── skills/
│       ├── dune-sql-best-practices/ # SQL patterns + verify.py; loads on any DuneSQL task
│       ├── api-references/          # Technique doc; loads when spec declares APIs
│       ├── chain-references/        # Technique doc; loads when spec declares chains
│       ├── api-defillama/           # Leaf — example API leaf (DefiLlama)
│       ├── chain-solana/            # Leaf — example chain leaf (Solana)
│       └── dune-actions-csv-upload/ # Loads only when materializing an endpoint
├── examples/
│   ├── data_spec_example.md         # Sample data spec to copy from
│   └── leaf_skill_template.md       # Template for adding new chain/API leaves
├── context/                         # Gitignored. Drop your own specs/notes here.
├── scripts/
│   ├── push_to_dune.py              # repo → Dune (uses Dune API)
│   ├── pull_from_dune.py            # Dune → repo (uses Dune API)
│   └── requirements.txt             # Python deps: requests, pyyaml
├── queries/                         # One folder per dashboard; starts empty
└── .github/workflows/               # One YAML per materialized endpoint; starts empty
```

## Requirements & Costs

| Service     | Tier    | Cost       |
| ----------- | ------- | ---------- |
| Dune        | Analyst | $75/mo     |
| GitHub      | Free    | $0         |
| Claude Code | Pro     | $17/mo     |
| **Total**   |         | **$92/mo** |

## Setup

1. **Clone and install**
   ```bash
   git clone <this-repo> && cd <this-repo>
   pip install -r scripts/requirements.txt
   ```

2. **Get a Dune API key and configure `.env`**

   Grab an API key at https://dune.com/settings/api, then:
   ```bash
   cp .env.example .env
   ```
   Fill in `DUNE_API_KEY` — it's required for `push_to_dune.py`, `pull_from_dune.py`, and `verify.py`'s dry-run.

   Add any other API keys your data spec will use (DefiLlama, etc.) to the same `.env`. `.env` is gitignored — never commit it.

3. **Authenticate with GitHub (for `gh pr create` and `git push`)**

   Create a **fine-grained PAT** at https://github.com/settings/personal-access-tokens — scoped to *only* this repo so the blast radius is contained if it leaks:

   - **Repository access:** *Only select repositories* → pick this repo
   - **Expiration:** 90 days (forces rotation)
   - **Repository permissions:**
     - `Contents`: Read and write — for `git push` / `git pull`
     - `Pull requests`: Read and write — for `gh pr create`
     - `Workflows`: Read and write — only if the agent should edit `.github/workflows/*.yml`
     - `Metadata`: Read (auto-included)

   Leave everything else off. No account perms, no other repos.

   Then authenticate `gh` with the token:
   ```bash
   gh auth login
   # → GitHub.com
   # → HTTPS
   # → Paste an authentication token
   # → paste your PAT
   ```
   `gh` stores the token and configures git's credential helper so `git push` works over HTTPS without further setup.

## Usage

1. **Write a data spec** in `context/<project>.md`. `context/` is gitignored — your specs and notes stay local. Copy the format from `examples/data_spec_example.md`.
2. **Run it** in Claude Code:
   - `/run-spec context/<project>.md` — pass a file path
   - `/run-spec <pasted spec content>` — paste the spec inline
   - `/run-spec` — run with no args and the agent will prompt you

   The slash command at `.claude/commands/run-spec.md` orchestrates the full workflow:
   - Loads `dune-sql-best-practices` + the technique docs and leaves matching your `chains:` / `apis:`
   - Writes SQL, runs `verify.py` (lint + dry-run, 2-retry cap on errors)
   - Pushes to Dune via `push_to_dune.py --verify`
   - Pauses for 429/payload-cap confirmations before materializing anything
3. **Validate in Dune's UI** — configure charts, check numbers, make any SQL edits.
4. **Ask the agent to open a PR** when satisfied. It runs `pull_from_dune.py` first so the PR diff reflects any UI edits, then opens the PR.
5. **Merge when ready.**

See `CLAUDE.md` for skill-loading rules and the canonical flow in detail.

## Adding a new chain or API leaf

The starter ships `chain-solana` and `api-defillama` as worked examples. To add another:

1. **Create the folder** — `.claude/skills/chain-<name>/` or `.claude/skills/api-<name>/`. The directory name is the token the data spec will reference (e.g. `chains: [ethereum]` → `.claude/skills/chain-ethereum/`).
2. **Create `SKILL.md`** inside it, copying the structure from `examples/leaf_skill_template.md`. The YAML frontmatter (`name`, `description`, `usage`) is required — without it, Claude Code's skill discovery skips the file.
3. **Reference the leaf from your data spec** — add the leaf name to `chains:` or `apis:`.
4. **Restart Claude Code** (or reload skills) so discovery picks up the new file.

The existing leaves (`chain-solana/SKILL.md`, `api-defillama/SKILL.md`) are the reference implementations — mirror their structure for consistency.

## License

MIT — adapt freely.
