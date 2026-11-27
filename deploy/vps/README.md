# Low-cost VPS research profile

Target: Ubuntu 24.04 LTS, 12 GB RAM, 6 vCPU, 50 GB disk.
Budget target is 300 TRY/month including taxes. No purchased server yet.
These templates are not enabled automatically.

AI architecture: Chronos 2 Small, LightGBM, River, optional Gemini API.
TimesFM is outside this profile. Real orders and automatic promotion stay off.

## River replay timer

Use a dedicated non-root cyberbot account. Put reviewed source at
/opt/cyberbot, and create a private .venv-river environment with reviewed
River dependencies. Provide the existing authorized local forward database
at var/ai/forward-models-v2.sqlite3. Do not publish data or copy it to a VPS
without confirming the applicable provider rights.

The administrator must create /etc/cyberbot/research.env, owned by root,
mode 0600, containing CYBERBOT_LOCAL_RESEARCH_RIGHTS_CONFIRMED=1 only after
confirming rights. The service has no network access.

Review the unit paths and file ownership before copying units to
/etc/systemd/system. Validate using systemd-analyze verify, run the service
once manually and check journalctl and systemctl status. Enable the timer
only after successful validation. The timer refreshes an aggregate replay
journal; it is not a live trading service or continuous model training daemon.
The journal rebuilds state from up to 10,000 settled records. No pickle files.

Resource policy: River replay is limited to 1 GiB and one CPU equivalent
with a 180-second timeout. Chronos and LightGBM must use the common heavy
job guard; their service scheduling and hard limits remain to be wired.
No Gemini calls are made; free quota and data-sharing policies require review.

The hardware and real workloads have not been benchmarked. Provider CPU
limits, legal data access and disk growth may require adjusting the profile.
No credentials, private databases, raw data or model weights belong in Git.
