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
