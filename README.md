# Agentic pipeline for onchain data analysis

Use this pipeline in Claude Code to generate, test, and publish DuneSQL queries from a data specification. Optionally, ingest data from external APIs to create custom datasets in [Dune](https://dune.com/). Save queries in GitHub for version control and review.

The original pipeline was used by the research team at [Blocmates](https://x.com/blocmates). This version recreates the workflow without Blocmates' company data. 

## Features

- **Automated DuneSQL development:** Generate, test, and publish DuneSQL queries from a data specification using reusable skills for blockchain data and external APIs.
- **External API integration:** Combine blockchain data with external API data using Dune LiveFetch or Python scripts to create custom datasets in Dune.
- **Scheduled dataset refreshes:** Use GitHub Actions to run Python ingestion scripts on a schedule and update datasets created from external APIs.
- **GitHub version control:** Store SQL queries in GitHub, synchronize changes from Dune, and open pull requests for team review. Use the repository's version history to restore previous query versions.

## How it works

Start with a data specification that describes the visualizations you want to create. When you run `/run-spec` in Claude Code, the agent selects the relevant skill files and Python scripts based on the blockchains and APIs in your specification.

The agent generates and tests SQL queries and calls external APIs when required. It publishes queries to your Dune account and saves them locally as `.sql` files. Inspect the queries in Dune and request changes in Claude Code to update them in real time.

After validating the queries in Dune, ask the agent to open a pull request (PR). The agent pulls any SQL edits you made in Dune, commits the synchronized files, and pushes them to your configured GitHub repository for review and version control.

Configure dashboard visualizations manually in Dune.

The workflow includes reference material for the Solana blockchain and the DefiLlama API. To use other blockchains and APIs, first [create additional context files](#extend-the-agent).

![Pipeline architecture](onchain-analysis-architecture.svg)

## Example dashboards

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

| Service     | Tier    | Estimated monthly cost (USD) |
| ----------- | ------- | ---------------------------- |
| Dune        | Analyst | $75                          |
| GitHub      | Free    | $0                           |
| Claude Code | Pro     | $17                          |
| **Total**   |         | **$92**                      |

Actual costs depend on your plan, billing cycle, and usage. Consult the providers' current documentation for pricing, model authentication, and API availability.

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

### 3. Configure API credentials

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

If you don't have Dune API access, you can still install the dependencies and run local static checks. Live query execution and API synchronization won't be available.

### 4. Configure Claude Code

Install [Claude Code](https://claude.com/claude-code) and configure a supported authentication method or model provider.

Open a terminal in the repository directory and start Claude Code:

```bash
claude
```

The `.claude/` directory contains the agent instructions, commands, and skills used by the workflow.

Claude Code needs access to a working model to run the workflow.

### 5. Configure the destination repository

The agent saves SQL files in a dashboard subfolder determined by the `project` field in your data specification. Configure Git's `origin` remote to push these files to your fork.

1. Open [DeFi-Kai/dune-etl-agent](https://github.com/DeFi-Kai/dune-etl-agent) on GitHub and select **Fork** to create a copy under your account.
2. In your local `dune-etl-agent` folder, run the following commands. Replace `<OWNER>` with your GitHub username and `<REPO>` with your fork's repository name (usually `dune-etl-agent`).

   ```bash
   git remote set-url origin "https://github.com/<OWNER>/<REPO>.git"
   git remote set-url --push origin "https://github.com/<OWNER>/<REPO>.git"
   ```

3. Verify the destination before running `/run-spec`.

   ```bash
   git remote -v
   git remote get-url --push --all origin
   ```

   Check that every `origin` push URL points to your intended `<OWNER>/<REPO>`. If multiple push URLs are listed, remove unintended destinations before proceeding.

In step 6, set GitHub CLI's default repository to the same destination.

### 6. Authenticate with GitHub

1. In GitHub, [create a fine-grained personal access token (PAT)](https://github.com/settings/personal-access-tokens). Restrict it to the destination repository from step 5 to limit access if the token is exposed.

2. Configure the token's access and permissions.

   - **Repository access:** Choose **Only select repositories**, and select your destination repository.
   - **Expiration:** Set an expiration of 90 days.
   - **Repository permissions:**
     - **Contents:** Read and write, for `git push` and `git pull`.
     - **Pull requests:** Read and write, for `gh pr create`.
     - **Workflows:** Read and write, only if the agent needs to edit `.github/workflows/*.yml`.
     - **Metadata:** Read access is included automatically.

   Leave all other permissions disabled.

3. In your terminal, start GitHub CLI authentication.

   ```bash
   gh auth login
   ```

   Choose **GitHub.com**, then **HTTPS**. When asked how to authenticate, choose **Paste an authentication token** and paste your PAT. If prompted to authenticate Git with your GitHub credentials, choose **Yes** to use them for HTTPS operations such as `git push`.

4. Verify authentication.

   ```bash
   gh auth status
   ```

5. In your local `dune-etl-agent` folder, set and verify GitHub CLI's default repository. Use the same `<OWNER>/<REPO>` as `origin`.

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

Open Claude Code in the repository directory and run:

```text
/run-spec context/<project>.md
```

Replace `<project>.md` with your specification's filename.

The agent reads the specification, loads the relevant skills and reference files, and generates DuneSQL queries.

### 3. Verify and publish queries

The workflow uses `verify.py` for SQL checks and Dune API operations for live execution.

The agent stores generated queries as `.sql` files for version control and inspection. It uses the provided scripts to synchronize queries with Dune.

Open the queries in Dune to verify the results and configure visualizations.

After validation, ask the agent to open a PR. It pulls the latest SQL from Dune, commits the synchronized files, pushes a feature branch to the verified `origin` destination, and creates a PR in that repository. `/run-spec` doesn't open a PR automatically.

Live execution, synchronization, and the complete `/run-spec` workflow require the external services described in the prerequisites.

## Extend the agent

The repository organizes domain knowledge into reusable skills.

Shared skills contain general instructions. Blockchain and API skills provide references for specific data sources.

Existing examples include:

- `chain-solana`: Solana tables, schemas, and query guidance
- `api-defillama`: DefiLlama endpoints and API guidance

To add support for another blockchain or API:

1. Create a new subfolder under `.claude/skills/` named `chain-<name>` or `api-<name>`. Inside the subfolder, create a `SKILL.md` file using `examples/leaf_skill_template.md` as a template.
2. Document the relevant tables or endpoints, authentication requirements, rate limits, and implementation considerations.
3. Reference the new file through the `chains` or `apis` field in your data specification.
4. Restart Claude Code or reload the relevant references so the agent can access the new file.

Follow the structure of the existing skills, `chain-solana/SKILL.md` and `api-defillama/SKILL.md`, for consistency.
