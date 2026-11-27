# Local research adapters

Experimental, research-only modules.

- Yahoo collector: nine fixed reference symbols.
- Daily runner: bounded local collection.
- Equity AI: historical model comparison.
- Forward learning: observed Futures forecast evaluation.

Requirements:
- Separate yfinance and Chronos runtimes.
- Existing local research databases.
- Existing verified local Chronos weights.
- CYBERBOT_EQUITY_ARCHIVE points to the historical database.

Run from the Cyberbot repository root.
Yahoo data access and storage rights must be reviewed
before enabling collection.

No market data, database, model weights or credentials
are distributed with these modules.

No automatic strategy promotion.
No real orders.
No verified executable equity quotes.
Production engine integration remains pending.

## Paired AI research

Run only after confirming data rights, in an isolated environment with both
LightGBM and River installed. On Linux use the shared heavy job guard:

    python -m tools.local_research.vps_guard --model lightgbm --state /opt/cyberbot/var/ai/heavy-lock -- python -m tools.local_research.paired_ai_review --root /opt/cyberbot

Requires the local settled Futures forecast database. No model or data download.
The chronological holdout uses identical non-overlapping targets and equal UTC-day
weighting. LightGBM is frozen on the holdout; River learns after each scored target.
Both are retrospective reconstructions using the original forecasts as features,
not independently logged live predictions. The holdout rolls with the dataset;
repeated reports are not independent confirmation. Gemini is not a price predictor.
At most 100 aggregate reports are retained locally; source records are untouched.
The read-only ai_status module exposes the latest paired summary. The PWA route
and recurring paired job are not enabled yet. No automatic selection or trading.

## Market-isolated memory

Run from repository root after confirming local data rights. Initialize with
`python -m tools.local_research.market_memory --initialize` and import a reviewed
full-universe-baselines JSON with `--archive-report PATH`. Use `--import-paired`
for the existing Futures paired journal if available. No flags reads inventory
without creating files. Writers require CYBERBOT_LOCAL_RESEARCH_RIGHTS_CONFIRMED=1.
Files live under var/ai/market-memory, one SQLite journal per market. Historical
equity aggregates are UNIVERSE scopes, not per-symbol training results. Futures
paired replay remains retrospective. Solana mint identity is required for future
per-token records; no Solana observations are imported by this adapter yet.
Source/protocol/interval/symbol scopes must not be pooled as independent evidence.
Imports are idempotent per report fingerprint and scope, not globally atomic across
all five files. No source DB writes, model selection or trading. No model weights.

## Persistent LightGBM research candidates

After confirming authorized local data use, run the optional candidate trainer
in the reviewed LightGBM runtime under the shared heavy job guard:

    python -m tools.local_research.vps_guard --model lightgbm --state /opt/cyberbot/var/ai/heavy-lock -- python -m tools.local_research.train_candidate --root /opt/cyberbot

The trainer saves the fitted native model text and validated manifest together
in var/ai/candidate-models.sqlite3 only after round-trip prediction equivalence.
BTCUSDT Futures, 1m and the original source/feature order are fixed in v1.
The candidate has a data fingerprint, model SHA-256, library version and
chronological holdout metrics. The registry caps each model at 2 MiB and keeps
at most 20 candidates, with no automatic deletion or promotion. A full registry
requires manual review. Checksums detect corruption, not a malicious rewrite.
Keep the database private; do not load externally supplied model text or pickle.
No trained candidate is loaded into the live engine. Existing daily training
continues to write research metrics only; candidate training is explicit for now.
River state is still reconstructed via bounded replay, not an exact persistent
online checkpoint. Native library round-trip and deployment tests remain pending.

## Observed-minute regime diagnostics

Shadow decisions now include a separate regime_diagnostic field for 21
validated completed-minute native midpoint observations and the current book.
The original regime, candidate logic, decision version and risk gates are
unchanged. Direction and volatility are independent dimensions: a sideways
instrument can also have high volatility. Provisional log-return thresholds
are 0.5% cumulative direction and 0.2% per-minute population standard deviation;
these are not calibrated by market or annualized. Only one instrument is
classified, never an entire exchange.
Liquidity is a diagnostic of asserted quote depth and spread. Stocks use
venue-specific share sizes, Futures USDT depth, Solana USD depth and separate
pool liquidity. Missing or stale data are unknown, and pool TVL is not depth.
Thresholds are research-only; neither execution nor data provenance is verified.
No changes to automatic entry, strategy selection or execution. Regime-specific
forward outcome scoring and policy calibration remain pending.

## Conditional strategy review

With the existing observed pilot and shadow permissions enabled, run from the
repository root: python -m tools.local_research.conditional_strategy_report.
It reads at most 500 recent outcomes per market in a 30-day window and joins
matching logged decisions. It requires the same scope and diagnostic regime,
nonoverlapping measurement windows, at least 30 measured cases across 10 UTC
days and 80% measurement coverage, with at least 20 development and 10 holdout
cases. Both normal and doubled modeled costs must have positive equal-day
mean outcomes in both segments. These thresholds are provisional research
criteria, not statistical significance or proof of executable profitability.
Only the existing signalled pair may be marked REVIEW_ONLY. The available
outcomes are selectively observed, not a comparison of all possible strategies.
All actual actions remain HOLD; no existing strategy policy is replaced.
Legacy decisions without the new diagnostic are excluded. The report is not
scheduled, and prospective strategy optimization remains pending.

## Three-stage equity parameter review

After confirming local research rights, run from the repository root:

    python -m tools.local_research.equity_parameter_review --market BIST --symbol THYAO.IS

This uses the existing long-only simulator and local daily equity archive,
requiring an exact unique market mapping in the 5m archive and a single daily
source. Both databases are read-only. It evaluates 15 fixed configurations on
the first 50% of observations, shortlists at most three, selects one using the
next 25%, and tests only that frozen configuration on the last 25%. All stages
require positive normal and doubled-cost returns, drawdowns at most 10%, and
at least five closed trades. Each segment begins flat. The result is a JSON
research report to stdout, not a strategy activation or scheduled training job.
The same rolling dataset may reuse previous holdout observations, so results
are not independent evidence. Daily continuity and large price changes are
screened, but exchange sessions and corporate actions remain unverified.
Futures and Solana are deliberately excluded from this equity simulator.
No real orders, automatic promotion, or claims of executable profitability.

## Windows dashboard handoff

Use `python -m tools.local_research.ai_dashboard --root PATH` from the reviewed
checkout, or consume `snapshot(Path(root))` in a future authenticated,
read-only panel handler. Schema: ai-dashboard-1. No HTTP route is installed by
this module; no files are uploaded. Keep access local or behind the existing
authenticated remote panel.

- research: existing ai-status-1 model and market inventory. Forecast counts
  are recorded, not independently revalidated; paired holdout metrics must
  not be mixed with prospective shadow results.
- windows_health: latest bounded watchdog history sample with five task names
  and allowlisted statuses. NOT_AVAILABLE or DATA_REVIEW_REQUIRED is not
  healthy. A sample older than 900 seconds becomes STALE and resource values
  are withheld. Task statuses in a stale sample are historical only.
- windows_health.resources: optional free/total host RAM and disk bytes at the
  sample time. They are not model process usage, hard resource caps or VRAM.
  No sample means unknown, never zero.
- paper_readiness_verified, automatic_promotion, real_orders remain false.
  SCHEDULER_OK describes scheduler exit status, not inference quality or
  profitability. The snapshot is not atomic across the independent journals.

The Windows watchdog must be registered and explicitly enabled before scheduled
samples become available. It retains at most 288 diagnostic snapshots, not
market records. Native runtime and Windows scheduling tests remain separate.
Do not display local file paths, raw forecasts, environment variables, secrets
or model weights in the panel. The PWA team owns frontend and authenticated
route integration; this module does not alter either.
