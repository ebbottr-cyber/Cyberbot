# DexTerm independent research probe

Upstream: https://github.com/dexterm-xyz/dexterm
Pinned revision: 235a55e71f90ee5ba32d05ec11d90570ddd079c2 (AGPL-3.0-only).
No upstream code is vendored or modified. Review licensing before redistribution or tighter integration.
Node 22.18+ is required. Install the external checkout separately with npm ci --ignore-scripts.
The Python probe invokes only initialize, tools/list and optionally screener_query (trending, limit 10) over stdio.
No analyst, wallet, Telegram, strategy, real-mode, executor or paper tools are invoked.
A temporary home and an in-memory database are used; this is not an OS sandbox or a complete supply-chain audit.
The child does not receive the parent credential environment. Do not run external software in a credential-bearing account unless you trust and review it.
Use the kill switch and explicit data-use permission. API limits and provider terms still apply.
Default invocation is protocol smoke test, not a market scan. Add --live only for the bounded diagnostic query.
Results are unverified observations; missing values remain missing and no risk authorization is derived.
Native Windows compatibility and live data access require testing. No main integration or PWA changes yet.
