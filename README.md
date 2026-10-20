# Agentic Pipeline for Onchain Data Analysis

This pipeline automates SQL query development, with optional support for ingesting external data from APIs to load custom datasets in Dune. The agent is designed for Claude Code's CLI. It provides a standardized workflow for generating and testing queries in Dune using AI, managing files, and maintaining version control through Github.

The original pipeline was used by the research team at [Blocmates](https://x.com/blocmates). This version recreates the workflow without Blocmates' company data. 

## Features

- **Automated DuneSQL development:** Generate, test, and publish DuneSQL queries from a data specification using reusable skills for blockchain data and external APIs.
- **External API integration:** Combine blockchain data with external API data using Dune LiveFetch or Python scripts to create custom datasets in Dune.
- **Scheduled dataset refreshes:** Use GitHub Actions to run Python ingestion scripts on a schedule and update datasets created from external APIs.
- **GitHub version control:** Store SQL queries in GitHub, synchronize changes from Dune, and open pull requests for team review. Use the repository's version history to restore previous query versions.

## How it works

The pipeline starts with a data specification defining the desired visualizations. When the user invokes the `/run-spec` command in Claude Code, the agent selects the relevant skill files and Python scripts based on the blockchains and APIs referenced in the dataspec. 

The agent generates and tests SQL queries, and calls external APIs when required. Generated queries are published to the user's Dune account and saved locally as `.sql` files. Users can inspect the queries in Dune and request changes in Claude Code that appear in real-time. After validating in Dune, users ask the agent to open a PR; the agent then pulls any Dune UI edits, commits the synchronized SQL, and pushes it to the configured GitHub repository for review and version control.

Dashboard visualizations must be configured manually in Dune's interface. 

The workflow is pre-loaded with context for the Solana blockchain and the DeFiLlama API. To generate queries with data from other blockchains and APIs you must first [create additional context files](#extending-the-agent).

![Pipeline Architecture](onchain-analysis-architecture.svg)

## Example Dashboards

The following dashboards were created with the original pipeline at Blocmates:
- [MetaDAO Blocmates Pro](https://dune.com/blocmates_research/metadao-blocmates-pro): MetaDAO ICO analytics covering commitments, final raises, oversubscription, contributors, and raise progress.
- [Chain GDP](https://dune.com/blocmatesresearch/chain-gdp): Cross-chain analysis of chain GDP over time and GDP by protocol category.


## Prerequisites

### Local setup

- Git
- Python 3 with `pip` and `venv`

### Full pipeline execution

- A Dune account with API access and sufficient credits for query execution
- [Claude Code](https://claude.com/claude-code) installed and configured with a supported model provider
- GitHub CLI (`gh`) and repository write permissions for automated Git operations and pull requests

### Costs

| Service     | Tier    | Cost       |
| ----------- | ------- | ---------- |
| Dune        | Analyst | $75/mo     |
| GitHub      | Free    | $0         |
| Claude Code | Pro     | $17/mo     |
| **Total**   |         | **$92/mo** |

Consult the providers' current documentation for subscription costs, model authentication, and API availability.

## Setup

The following instructions use a Linux or macOS terminal.

### 1. Clone the repository

```bash
git clone https://github.com/DeFi-Kai/dune-etl-agent.git
cd dune-etl-agent
```

### 2. Install Python dependencies

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the dependencies:

```bash
python -m pip install -r scripts/requirements.txt
```

### 3. Configure environment variables (Dune and other APIs)

Copy the example environment file:

```bash
cp .env.example .env
```

The example file contains:

```dotenv
DUNE_API_KEY=replace_with_your_dune_api_key
```

To execute queries or synchronize files through Dune's API, obtain a key from [Dune API Settings](https://dune.com/settings/api) and replace the placeholder value in `.env`.

Add any credentials required by external APIs used in your data specifications.

**Security:** Never commit `.env` or API credentials to version control. Only `.env.example`, containing placeholder values, should be tracked.

If you do not have Dune API access, you can still install the dependencies and run local static checks. Live query execution and API synchronization will not be available.

### 4. Configure Claude Code

Install [Claude Code](https://claude.com/claude-code) and configure a supported authentication method or model provider.

Open a terminal in the repository directory and start Claude Code:

```bash
claude
```

The `.claude/` directory contains the agent instructions, commands, and skills used by the workflow.

Claude Code must have access to a working model before you can invoke the agent workflow. 

### 5. Configure the destination repository

The agent saves generated SQL files in the local `dune-etl-agent` folder where you run Claude Code. The `project` field in your data specification determines which dashboard subfolder holds those files. When you push them to GitHub, Git sends them to a saved repository address called `origin`. Signing in to GitHub gives you access; configuring `origin` tells Git where to send your files.

Open [DeFi-Kai/dune-etl-agent](https://github.com/DeFi-Kai/dune-etl-agent) on GitHub and click **Fork** to create a copy under your own account. Your fork will store your generated SQL.

Step 1 downloaded the project from the original repository. The next two commands connect that same local folder to your fork, so future pushes go to your GitHub account. Run them in your local `dune-etl-agent` folder, replacing `<OWNER>` with your GitHub username and `<REPO>` with your fork's repository name (usually `dune-etl-agent`):

```bash
git remote set-url origin "https://github.com/<OWNER>/<REPO>.git"
git remote set-url --push origin "https://github.com/<OWNER>/<REPO>.git"
```

Verify the destination before running `/run-spec`:

```bash
git remote -v
git remote get-url --push --all origin
```

Every effective `origin` push URL must identify your intended `<OWNER>/<REPO>`. If multiple push URLs are listed, remove unintended destinations before proceeding. After authenticating in step 6, also set GitHub CLI's default repository to this same destination.

### 6. Authenticate with GitHub (for `gh pr create` and `git push`)

   Create a **fine-grained PAT** at https://github.com/settings/personal-access-tokens — scoped to *only* the repository you intend to push to, so the blast radius is contained if it leaks.

   Scope the token to the destination repository chosen and configured in step 5.

   - **Repository access:** *Only select repositories* → select your repository
   - **Expiration:** 90 days (forces rotation)
   - **Repository permissions:**
     - `Contents`: Read and write — for `git push` / `git pull`
     - `Pull requests`: Read and write — for `gh pr create`
     - `Workflows`: Read and write — only if the agent should edit `.github/workflows/*.yml`
     - `Metadata`: Read (auto-included)

   Leave everything else off. No account permissions, no other repositories.

   Then authenticate `gh` with the token:

   ```bash
   gh auth login
   # → GitHub.com
   # → HTTPS
   # → Paste an authentication token
   # → Paste your PAT
   ```

   Verify authentication:

   ```bash
   gh auth status
   ```

   GitHub CLI can configure Git authentication for HTTPS operations, allowing `git push` without repeating the login process.

   Set and verify GitHub CLI's default repository, using the same `<OWNER>/<REPO>` as `origin`:

   ```bash
   gh repo set-default <OWNER>/<REPO>
   gh repo set-default --view
   ```

## Usage

### 1. Create a data specification

Create a Markdown file under `context/` describing the dataset or dashboard you want to build.

Use `examples/data_spec_example.md` as a template.

The specification identifies:

- Target blockchains
- External APIs, if applicable
- Desired queries and visualizations
- Data refresh requirements

The `context/` directory is excluded from version control so project-specific specifications and working notes remain local.

### 2. Run the agent

Open Claude Code in the repository directory and invoke:

```text
/run-spec context/<project>.md
```

Replace `<project>.md` with your specification's filename.

The agent reads the specification, loads the relevant skills and reference files, and generates DuneSQL queries.

### 3. Verify and publish queries

The workflow uses `verify.py` for SQL checks and Dune API operations for live execution.

Generated queries are stored as `.sql` files for version control and inspection. The workflow can synchronize queries with Dune using the provided scripts.

The final queries can be opened in Dune's interface for manual verification and visualization configuration.

After validation, ask the agent to open a PR. It pulls the latest SQL from Dune before committing, pushing a feature branch to the verified `origin` destination, and creating a PR in that same repository. `/run-spec` does not open a PR automatically.

Live execution, synchronization, and the complete `/run-spec` workflow require the external services described in the prerequisites.

## Extending the Agent

The repository organizes domain knowledge into reusable skills.

Shared skills contain general instructions, while leaf skills provide chain-specific or API-specific references.

Existing examples include:

- `chain-solana`: Solana tables, schemas, and query guidance
- `api-defillama`: DefiLlama endpoints and API guidance

To add support for another blockchain or API:

1. Create a new subfolder under .claude/skills/ named chain-<name> or api-<name>. Inside the subfolder, create a SKILL.md file using examples/leaf_skill_template.md as a template.
2. Document the relevant tables or endpoints, authentication requirements, rate limits, and implementation considerations.
3. Reference the new file through the `chains` or `apis` field in your data specification.
4. Restart Claude Code or reload the relevant references so the agent can access the new file.

The existing leaves (`chain-solana/SKILL.md`, `api-defillama/SKILL.md`) are the reference implementations — mirror their structure for consistency.

