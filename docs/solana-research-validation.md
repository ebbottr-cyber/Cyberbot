# Solana research validation

Use an isolated checkout of the Solana research branch. Do not run these tests in a production checkout or change the live bot configuration.

From the isolated repository root, use the existing Python environment:

```powershell
& $py -m tools.solana_offline_test_suite
if ($LASTEXITCODE -ne 0) { throw "Solana offline validation failed" }
```

The runner parses source files, discovers the Solana unittest suite, strips Cyberbot/provider configuration from its test environment and blocks Python socket connections and subprocess launches. It is not an OS sandbox. No live provider query or service installation is part of this command. Optional package discovery does not establish native model compatibility.

The new synthetic integration checks write only temporary SQLite databases, validate entry/exit provenance, replay a position, build a blocked learning experiment, publish a report and exercise the read-only API with ASGI transport (no network server).

Acceptance: zero failures and errors; verify the actual discovered test count; then separately validate optional native model dependencies, provider permissions, fresh quote collection and bounded paper-only operation. No promotion or real orders.

## Native model compatibility (separate opt-in)

After the offline unit suite passes, run in the same isolated environment:

```powershell
& $py -m tools.solana_native_model_check --allow-synthetic-fit
if ($LASTEXITCODE -ne 0) { throw "Native model check incomplete" }
```

This command uses 180 synthetic chronological examples and the actual installed LightGBM and River adapters, with Python network calls denied and common numerical thread limits set to one. It never installs dependencies, saves model weights or opens a research database. A pass verifies only synthetic execution compatibility, not trading performance, real-data learning readiness, or independent holdout quality. Gemini remains a manual review packet, with no API call. The unit tests for this check mock optional models and therefore cannot substitute for running the native command.
