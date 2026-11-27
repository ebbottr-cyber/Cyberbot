# Solana bounded multi-day research trial

First complete the Windows offline validation and optional native compatibility test. Start a single real-provider research-only cycle under confirmed provider data rights and the active kill switch; verify that its archive, learning and PWA outputs are valid before enabling the disabled Windows task. No real orders or production model fitting are authorized.

## Initial trial

Use at least seven complete UTC calendar days, then review the archived evidence. The new offline assessment accepts 1–14 completed UTC days with up to 500 bridge and 500 exit reports per day. Example (adjust dates to the actual trial):

```powershell
& $py -m tools.solana_trial_assessment --database $researchDb --start '2026-12-01T00:00:00Z' --end '2026-12-08T00:00:00Z'
```

The command does not request market data, fit models, write to the archive, or start a task. Each UTC day uses its own fixed 1,000-USDC hypothetical starting balance, the fixed balanced-exit research policy, and 25/50/100 bps extra cost per direction. It selects data imported and observed within the day. Late imports, cross-day entry/exit pairs and incomplete archive windows are not used to establish sample sufficiency. Run after the scheduled task has stopped to avoid changes during reads.

Provisional research sample thresholds: at least 7 days, 5 days with observations in complete windows, 10 distinct mints, 100 mature entries, 80% exact-quantity quote coverage, 100 closed simulated positions per cost scenario, no unvalued open positions, no truncated days. These deliberately conservative engineering criteria are not calibrated investment thresholds. Report exit 0 means only that these sample gates were met; 2 means insufficient evidence; 1 means invalid input or processing failure. Report per-day realized P/L, closed-only profit factor, realized-only drawdown and unresolved positions separately; do not compound these independent day replays into continuous account returns.

Model sample eligibility is reported separately for each day using the existing 100 earlier / 50 later examples, 15 per class, 5 mints per partition rules. Daily model sample counts are not pooled. No model fit or promotion occurs in assessment. A day with unresolved positions or absent quotes remains uncertain; do not infer liquidation, mark-to-market equity, actual fills, provider uptime or profitability. If gates are unmet, inspect why and collect more suitable observations rather than weaken the criteria.

The suite and real-provider trial have not been executed as part of this commit.
