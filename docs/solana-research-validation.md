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
