# deploy/

Snapshot of production scheduling state on `beefcake`, kept in git so the repo
records what actually runs.

## crontab

`deploy/crontab` is a snapshot of `crontab -l` for the `certdepot` user.

It is a **snapshot, not a source of truth** — cron reads the real crontab, not
this file. After changing the schedule on the server, re-snapshot and commit:

    crontab -l > deploy/crontab

To restore the schedule onto a fresh machine:

    crontab deploy/crontab

Disabled jobs are kept commented rather than deleted, with a dated reason, so
history is visible and re-enabling is a one-line change.

## Current state (2026-09-13)

Only the health monitor is active. All content and marketing automation is
paused:

| Job | Status |
|-----|--------|
| `scripts/synthetic_monitor.py` | **active** — daily probe, emails only on failure |
| `daily_report.py` | disabled — daily analytics email, SO/Reddit discovery, backlink PR tracking |
| `scripts/deploy_content.py` | disabled — content deploy + IndexNow + GSC sitemap ping |
| `scripts/cross_post_devto.py` | disabled — dev.to cross-posting |

Notes:

- `synthetic_monitor.py` imports `synthetic_test()` and `send_email()` from
  `daily_report.py`. That file must stay in place even though its cron is off.
- Re-enabling `deploy_content.py` or `cross_post_devto.py` should also restore
  the matching entries in `SIBLING_LOGS` in `scripts/synthetic_monitor.py`, so
  a silently dead cron is noticed.
