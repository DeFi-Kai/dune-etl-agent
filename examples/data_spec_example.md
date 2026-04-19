# Sample Data Spec

```yaml
project: solana-defi-health
chains: [solana]
apis: [defillama]
refresh: daily 06:00 UTC
```

## Visualizations

1. **Solana DEX volume, last 30 days.** Daily stacked area, split by protocol. Add a 7-day rolling mean.
2. **Stablecoin net flow onto Solana.** Weekly bars for the last 12 weeks, USDC + USDT combined. Green for inflow, red for outflow.
3. **Top 10 Solana wallets by DEX volume (30d).** Simple table, sortable by volume.

## Notes

- Declaring a chain or API loads `dune-sql-best-practices` plus the relevant technique docs (`chain-references`, `api-references`) and the per-API/per-chain files underneath.
- **No per-endpoint strategy in the spec.** Inline `http_get` / `http_post` is the default for every endpoint.
- If an endpoint hits `429` / payload cap during execution, the agent **pauses and asks the user to confirm** materializing it via GH Actions + user table. The confirmation surfaces the endpoint, the proposed table name, the refresh cadence, and an estimated row count.
- After approval, the agent generates a Python script under `scripts/` and a workflow under `.github/workflows/<endpoint>.yml`. The presence of that workflow file is what tells future runs to skip inline and query the user table.
- Charting happens in Dune; datasets are not pulled into the agent context.
