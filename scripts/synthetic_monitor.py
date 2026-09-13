#!/usr/bin/env python3
"""Daily health probe for cert-depot.com — emails only when something is wrong.

Runs the same synthetic test as daily_report.py (homepage, /api/health, full
/api/generate flow validated with openssl, sample tool/guide pages) and also
checks that the sibling daily crons are still firing. Silent on success.
"""
import sys
import time
import traceback
from datetime import date
from pathlib import Path

sys.path.insert(0, "/home/certdepot/cert-depot")

from daily_report import send_email, synthetic_test  # noqa: E402

# Sibling crons that should touch their log every day. If one goes quiet for
# more than this long, cron or the script itself has broken.
SIBLING_LOGS = {
    "deploy_content": "/home/certdepot/cert-depot/logs/deploy_content.log",
    "dev.to drain": "/home/certdepot/cert-depot/logs/devto_post.log",
}
STALE_AFTER_HOURS = 36


def check_sibling_crons():
    """Returns (ok, [report_lines])."""
    lines = []
    ok = True
    now = time.time()
    for name, path in SIBLING_LOGS.items():
        p = Path(path)
        if not p.exists():
            lines.append(f"  {name}: FAIL (log missing: {path})")
            ok = False
            continue
        age_h = (now - p.stat().st_mtime) / 3600
        if age_h > STALE_AFTER_HOURS:
            lines.append(f"  {name}: FAIL (log stale — last write {age_h:.0f}h ago)")
            ok = False
        else:
            lines.append(f"  {name}: OK (last write {age_h:.0f}h ago)")
    return ok, lines


def main():
    today = date.today().isoformat()

    synth_ok, synth_lines = synthetic_test()
    cron_ok, cron_lines = check_sibling_crons()

    report = ["Synthetic test:"] + synth_lines + ["", "Daily crons:"] + cron_lines
    body = "\n".join(report)

    # Always log the full result so history is inspectable without email.
    print(f"[{today}] synthetic={'OK' if synth_ok else 'FAIL'} "
          f"crons={'OK' if cron_ok else 'FAIL'}")
    print(body)

    if synth_ok and cron_ok:
        return 0

    failed = []
    if not synth_ok:
        failed.append("synthetic test")
    if not cron_ok:
        failed.append("daily crons")
    subject = f"[ALERT] cert-depot.com — {' + '.join(failed)} failing ({today})"
    send_email(subject, body + "\n\n-- \ncert-depot synthetic monitor\n")
    print("Alert email sent.")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        tb = traceback.format_exc()
        print(tb, file=sys.stderr)
        try:
            send_email(
                f"[ALERT] cert-depot.com — monitor crashed ({date.today().isoformat()})",
                "synthetic_monitor.py raised an unhandled exception:\n\n" + tb,
            )
        except Exception:
            print("Could not send crash email.", file=sys.stderr)
        sys.exit(2)
