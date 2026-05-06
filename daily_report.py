#!/usr/bin/env python3
"""Daily cert-depot.com analytics report — sent via agentmail.to"""

import io
import json
import subprocess
import tempfile
import urllib.request
import zipfile
from datetime import date, timedelta

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange,
    Dimension,
    Filter,
    FilterExpression,
    Metric,
    RunRealtimeReportRequest,
    RunReportRequest,
)
from google.oauth2 import service_account
from googleapiclient.discovery import build

GA4_PROPERTY = "properties/531087827"
GA4_KEY_FILE = "/home/certdepot/ga_cc_key_certdepot.json"
GSC_SITE_URL = "https://cert-depot.com/"
COUNTER_FILE = "/home/certdepot/cert-depot/data/counter.txt"

CN_LOG_FILE = "/home/certdepot/cert-depot/data/cn_log.txt"
DEPLOY_LOG_FILE = "/home/certdepot/cert-depot/data/deploy_log.jsonl"

SO_SEEN_FILE = "/home/certdepot/cert-depot/data/so_seen.json"
REDDIT_SEEN_FILE = "/home/certdepot/cert-depot/data/reddit_seen.json"

AGENTMAIL_API = "https://api.agentmail.to/v0/inboxes/certdepot@agentmail.to/messages/send"
AGENTMAIL_KEY = "am_us_inbox_61ea0f71eeafd46fe28e4e1f438bca40088532daebf13b7e1c880e2aaace833a"
TO_EMAIL = "dima@stopel.org"


def ga4_creds():
    return service_account.Credentials.from_service_account_file(
        GA4_KEY_FILE,
        scopes=[
            "https://www.googleapis.com/auth/analytics.readonly",
            "https://www.googleapis.com/auth/webmasters.readonly",
        ],
    )


def get_ga4_client(creds):
    return BetaAnalyticsDataClient(credentials=creds)


def get_gsc_service(creds):
    return build("searchconsole", "v1", credentials=creds)


def ga4_report(client, start_date, end_date, dimensions=None):
    dims = [Dimension(name=d) for d in (dimensions or [])]
    response = client.run_report(
        RunReportRequest(
            property=GA4_PROPERTY,
            date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
            metrics=[
                Metric(name="sessions"),
                Metric(name="activeUsers"),
                Metric(name="screenPageViews"),
            ],
            dimensions=dims,
        )
    )
    return response


def ga4_totals(client, start_date, end_date):
    response = ga4_report(client, start_date, end_date)
    if response.row_count > 0:
        r = response.rows[0]
        return {
            "sessions": int(r.metric_values[0].value),
            "users": int(r.metric_values[1].value),
            "pageviews": int(r.metric_values[2].value),
        }
    return {"sessions": 0, "users": 0, "pageviews": 0}


def ga4_by_dimension(client, start_date, end_date, dimension):
    response = ga4_report(client, start_date, end_date, dimensions=[dimension])
    results = []
    for row in response.rows:
        results.append({
            "key": row.dimension_values[0].value,
            "users": int(row.metric_values[1].value),
            "sessions": int(row.metric_values[0].value),
        })
    results.sort(key=lambda x: x["users"], reverse=True)
    return results


def ga4_realtime(client):
    response = client.run_realtime_report(
        RunRealtimeReportRequest(
            property=GA4_PROPERTY,
            metrics=[Metric(name="activeUsers")],
        )
    )
    if response.row_count > 0:
        return response.rows[0].metric_values[0].value
    return "0"


def gsc_search_data(service, start_date, end_date):
    try:
        response = service.searchanalytics().query(
            siteUrl=GSC_SITE_URL,
            body={
                "startDate": start_date,
                "endDate": end_date,
                "dimensions": ["query"],
                "rowLimit": 10,
            },
        ).execute()
        return response.get("rows", [])
    except Exception:
        return []


def gsc_totals(service, start_date, end_date):
    try:
        response = service.searchanalytics().query(
            siteUrl=GSC_SITE_URL,
            body={"startDate": start_date, "endDate": end_date},
        ).execute()
        rows = response.get("rows", [])
        if rows:
            return {
                "impressions": int(rows[0]["impressions"]),
                "clicks": int(rows[0]["clicks"]),
                "ctr": rows[0]["ctr"],
                "position": rows[0]["position"],
            }
    except Exception:
        pass
    return {"impressions": 0, "clicks": 0, "ctr": 0.0, "position": 0.0}


def get_counter():
    try:
        with open(COUNTER_FILE) as f:
            return f.read().strip()
    except Exception:
        return "unknown"


def get_deployments(days=7):
    """Return deployments from the last N days (most recent first)."""
    try:
        with open(DEPLOY_LOG_FILE) as f:
            entries = [json.loads(line) for line in f if line.strip()]
    except FileNotFoundError:
        return []
    cutoff = (date.today() - timedelta(days=days - 1)).isoformat()
    recent = [e for e in entries if e.get("date", "") >= cutoff]
    recent.sort(key=lambda e: e["date"], reverse=True)
    return recent


def get_cn_log():
    """Read CN log entries since yesterday, then rotate the file."""
    try:
        with open(CN_LOG_FILE) as f:
            lines = f.readlines()
    except FileNotFoundError:
        return []

    entries = []
    for line in lines:
        line = line.strip()
        if line:
            parts = line.split(" ", 1)
            if len(parts) == 2:
                entries.append({"time": parts[0], "cn": parts[1]})
            else:
                entries.append({"time": "", "cn": line})

    # Rotate: clear the file after reading
    try:
        with open(CN_LOG_FILE, "w") as f:
            pass
    except Exception:
        pass

    return entries


SO_QUERIES = [
    "self-signed certificate",
    "generate ssl certificate development",
    "openssl self-signed",
    "self-signed ssl",
    "create test certificate",
]

REDDIT_SUBREDDITS = ["webdev", "devops", "selfhosted", "golang", "homelab", "sysadmin"]
REDDIT_QUERIES = ["self-signed certificate", "self signed ssl", "test certificate", "ssl certificate development"]


def load_seen(path):
    try:
        with open(path) as f:
            return set(json.loads(f.read()))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_seen(path, seen):
    with open(path, "w") as f:
        f.write(json.dumps(list(seen)))


def search_stackoverflow():
    """Find recent SO questions about self-signed certificates."""
    seen = load_seen(SO_SEEN_FILE)
    results = []
    week_ago = int((date.today() - timedelta(days=7)).strftime("%s"))

    for query in SO_QUERIES:
        try:
            encoded = urllib.request.quote(query)
            url = (
                f"https://api.stackexchange.com/2.3/search/advanced"
                f"?order=desc&sort=creation&q={encoded}"
                f"&fromdate={week_ago}&site=stackoverflow"
                f"&filter=!nNPvSNdWme&pagesize=5"
            )
            req = urllib.request.Request(url, headers={"Accept-Encoding": "identity"})
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read())
                for item in data.get("items", []):
                    qid = str(item["question_id"])
                    if qid in seen:
                        continue
                    # Skip if already answered with many answers
                    if item.get("answer_count", 0) > 5:
                        continue
                    title = item.get("title", "")
                    link = item.get("link", "")
                    score = item.get("score", 0)
                    answers = item.get("answer_count", 0)
                    results.append({
                        "id": qid,
                        "title": title,
                        "link": link,
                        "score": score,
                        "answers": answers,
                        "source": "stackoverflow",
                    })
                    seen.add(qid)
        except Exception:
            continue

    save_seen(SO_SEEN_FILE, seen)
    return results


def search_reddit():
    """Find recent Reddit posts about self-signed certificates."""
    seen = load_seen(REDDIT_SEEN_FILE)
    results = []

    for subreddit in REDDIT_SUBREDDITS:
        for query in REDDIT_QUERIES:
            try:
                encoded = urllib.request.quote(query)
                url = (
                    f"https://www.reddit.com/r/{subreddit}/search.json"
                    f"?q={encoded}&restrict_sr=on&sort=new&t=week&limit=5"
                )
                req = urllib.request.Request(url, headers={"User-Agent": "cert-depot-monitor/1.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read())
                    for child in data.get("data", {}).get("children", []):
                        post = child.get("data", {})
                        pid = post.get("id", "")
                        if pid in seen:
                            continue
                        title = post.get("title", "")
                        permalink = post.get("permalink", "")
                        ups = post.get("ups", 0)
                        num_comments = post.get("num_comments", 0)
                        results.append({
                            "id": pid,
                            "title": title,
                            "link": f"https://www.reddit.com{permalink}",
                            "score": ups,
                            "comments": num_comments,
                            "subreddit": subreddit,
                            "source": "reddit",
                        })
                        seen.add(pid)
            except Exception:
                continue

    save_seen(REDDIT_SEEN_FILE, seen)
    return results


def draft_comment(item):
    """Draft a helpful comment that naturally mentions cert-depot."""
    if item["source"] == "stackoverflow":
        return (
            "For a quick self-signed certificate, you can use [cert-depot.com](https://cert-depot.com) — "
            "it generates certs in-browser with SAN support (required by modern browsers). "
            "Supports RSA/ECDSA, outputs ZIP or PFX. Keys are generated in memory and never stored. "
            "It's open source: https://github.com/dimastopel/certdepot\n\n"
            "If you prefer command-line, the equivalent OpenSSL command is:\n\n"
            "```\n"
            "openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes -subj '/CN=localhost'\n"
            "```"
        )
    else:
        return (
            f"If you need a quick self-signed cert, I've been using cert-depot.com — "
            f"free, no signup, open source. Generates certs with SAN support, "
            f"RSA or ECDSA, ZIP or PFX output. Keys are never stored on the server. "
            f"Source: https://github.com/dimastopel/certdepot"
        )


BACKLINK_PRS = [
    {"repo": "sobolevn/awesome-cryptography", "number": 256},
    {"repo": "sbilly/awesome-security", "number": 513},
]


def get_pr_statuses():
    """Check status of backlink PRs via GitHub API."""
    results = []
    for pr in BACKLINK_PRS:
        try:
            url = f"https://api.github.com/repos/{pr['repo']}/pulls/{pr['number']}"
            req = urllib.request.Request(url, headers={"User-Agent": "cert-depot-report"})
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read())
                state = data.get("state", "unknown")
                merged = data.get("merged", False)
                if merged:
                    status = "MERGED"
                elif state == "closed":
                    status = "CLOSED"
                else:
                    status = "OPEN"
                results.append(f"  {pr['repo']}#{pr['number']}: {status}")
        except Exception as e:
            results.append(f"  {pr['repo']}#{pr['number']}: error ({e})")
    return results


def send_email(subject, text):
    payload = json.dumps({"to": [TO_EMAIL], "subject": subject, "text": text}).encode()
    req = urllib.request.Request(
        AGENTMAIL_API,
        data=payload,
        headers={
            "Authorization": f"Bearer {AGENTMAIL_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


SYNTHETIC_BASE = "https://cert-depot.com"
SYNTHETIC_UA = "cert-depot-synthetic/1.0"


def _http_get(path, timeout=15):
    req = urllib.request.Request(SYNTHETIC_BASE + path, headers={"User-Agent": SYNTHETIC_UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.headers, r.read()


def synthetic_test():
    """End-to-end probe of cert-depot.com. Returns (overall_ok, [report_lines])."""
    lines = []
    overall_ok = True

    # 1. Homepage reachable and HTML contains the brand string
    try:
        status, _, body = _http_get("/")
        ok = status == 200 and b"Certificate Depot" in body
        lines.append(f"  Homepage:        {'OK' if ok else 'FAIL'} (HTTP {status})")
        overall_ok = overall_ok and ok
    except Exception as e:
        lines.append(f"  Homepage:        FAIL ({e})")
        overall_ok = False

    # 2. Health endpoint
    try:
        status, _, body = _http_get("/api/health")
        data = json.loads(body)
        ok = status == 200 and data.get("status") == "ok"
        lines.append(f"  /api/health:     {'OK' if ok else 'FAIL'}")
        overall_ok = overall_ok and ok
    except Exception as e:
        lines.append(f"  /api/health:     FAIL ({e})")
        overall_ok = False

    # 3. Full generation flow: POST /api/generate, parse the cert with openssl, verify CN
    cn = f"synthetic-test-{date.today().isoformat()}.local"
    try:
        body = json.dumps({
            "commonName": cn,
            "validityDays": 30,
            "keyType": "rsa2048",
            "outputFormat": "zip",
            "sans": [],
        }).encode()
        req = urllib.request.Request(
            SYNTHETIC_BASE + "/api/generate",
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": SYNTHETIC_UA},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            ct = r.headers.get("Content-Type", "")
            zip_bytes = r.read()

        if "application/zip" not in ct:
            lines.append(f"  /api/generate:   FAIL (unexpected content-type {ct!r})")
            overall_ok = False
        else:
            zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
            names = zf.namelist()
            cert_name = next((n for n in names if n.endswith("certificate.pem")), None)
            if not cert_name:
                lines.append(f"  /api/generate:   FAIL (no certificate.pem in zip; found {names})")
                overall_ok = False
            else:
                pem_bytes = zf.read(cert_name)
                with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as tf:
                    tf.write(pem_bytes)
                    tf_path = tf.name
                proc = subprocess.run(
                    ["openssl", "x509", "-in", tf_path, "-noout", "-subject"],
                    capture_output=True, text=True, timeout=10,
                )
                ok = proc.returncode == 0 and cn in proc.stdout
                subj = proc.stdout.strip() or proc.stderr.strip()
                lines.append(f"  /api/generate:   {'OK' if ok else 'FAIL'} ({subj})")
                overall_ok = overall_ok and ok
    except Exception as e:
        lines.append(f"  /api/generate:   FAIL ({e})")
        overall_ok = False

    # 4. Sample tool + guide pages
    sample = ["/tools/pem-decoder", "/guides/self-signed-cert-nginx", "/guides/why-sans-matter"]
    failures = []
    for path in sample:
        try:
            status, _, _ = _http_get(path)
            if status != 200:
                failures.append(f"{path}={status}")
        except Exception as e:
            failures.append(f"{path}={e}")
    if not failures:
        lines.append(f"  Pages ({len(sample)}/{len(sample)}):     OK")
    else:
        lines.append(f"  Pages:           FAIL ({', '.join(failures)})")
        overall_ok = False

    return overall_ok, lines


def pct_change(current, previous):
    if previous == 0:
        return "+∞" if current > 0 else "flat"
    change = ((current - previous) / previous) * 100
    sign = "+" if change >= 0 else ""
    return f"{sign}{change:.0f}%"


def main():
    creds = ga4_creds()
    ga4 = get_ga4_client(creds)
    gsc = get_gsc_service(creds)

    today = date.today()
    week_ago = today - timedelta(days=7)
    two_weeks_ago = today - timedelta(days=14)

    # GA4 data
    yesterday = ga4_totals(ga4, "yesterday", "yesterday")
    this_week = ga4_totals(ga4, str(week_ago), str(today))
    last_week = ga4_totals(ga4, str(two_weeks_ago), str(week_ago - timedelta(days=1)))
    realtime = ga4_realtime(ga4)
    sources = ga4_by_dimension(ga4, str(week_ago), str(today), "sessionDefaultChannelGroup")
    countries = ga4_by_dimension(ga4, str(week_ago), str(today), "country")

    # GSC data
    gsc_this_week = gsc_totals(gsc, str(week_ago), str(today - timedelta(days=1)))
    top_queries = gsc_search_data(gsc, str(week_ago), str(today - timedelta(days=1)))

    # Community monitoring
    so_opportunities = search_stackoverflow()
    reddit_opportunities = search_reddit()

    certs = get_counter()
    cn_entries = get_cn_log()
    # Filter out synthetic-test CNs so the per-cert section reflects real users
    cn_entries = [e for e in cn_entries if not e["cn"].startswith("synthetic-test-")]
    deployments = get_deployments(days=7)

    # Synthetic end-to-end test (run first so it's the most prominent thing in the email)
    synth_ok, synth_lines = synthetic_test()

    # === Build report ===
    lines = []

    # Synthetic test result — at the top
    lines.append(f"**Synthetic Test — {'PASS' if synth_ok else 'FAIL'}**")
    lines.extend(synth_lines)
    lines.append("")

    # Content Deployments
    lines.append("**Content Deployed (last 7 days)**")
    if deployments:
        for d in deployments:
            lines.append(f"  {d['date']}  [{d['type']}] {d['title']} — {d['url']}")
    else:
        lines.append("  No new content deployed this week.")
    lines.append("")

    # Traffic Summary
    lines.append("**Traffic Summary**")
    lines.append(
        f"Yesterday: {yesterday['users']} users, {yesterday['sessions']} sessions, "
        f"{yesterday['pageviews']} pageviews."
    )
    wow = pct_change(this_week["users"], last_week["users"])
    lines.append(
        f"Week-over-week: {wow} ({this_week['users']} users this week vs. "
        f"{last_week['users']} last week)."
    )
    if realtime != "0":
        lines.append(f"Realtime: {realtime} active users right now.")
    lines.append(f"Total certificates generated: {certs}.")
    lines.append("")

    # Indexing & Organic Search
    lines.append("**Indexing & Organic Search**")
    if gsc_this_week["impressions"] > 0 or gsc_this_week["clicks"] > 0:
        lines.append(
            f"Last 7 days: {gsc_this_week['impressions']} impressions, "
            f"{gsc_this_week['clicks']} clicks, "
            f"CTR {gsc_this_week['ctr']:.1%}, "
            f"avg position {gsc_this_week['position']:.1f}."
        )
    else:
        lines.append("No search impressions or clicks yet. Normal for a new site — Google needs time to index and rank.")

    if top_queries:
        lines.append("Top queries:")
        for row in top_queries[:5]:
            q = row["keys"][0]
            imp = int(row["impressions"])
            clicks = int(row["clicks"])
            pos = row["position"]
            lines.append(f'  "{q}": {imp} imp, {clicks} clicks, pos {pos:.1f}')
    lines.append("")

    # Traffic Sources
    lines.append("**Traffic Sources (7 days)**")
    if sources:
        parts = []
        for s in sources[:5]:
            parts.append(f"{s['key']}: {s['users']} users")
        lines.append(", ".join(parts) + ".")
    else:
        lines.append("No traffic source data.")
    lines.append("")

    # Geo
    if countries:
        lines.append("**Top Countries (7 days)**")
        parts = []
        for c in countries[:5]:
            parts.append(f"{c['key']} ({c['users']})")
        lines.append(", ".join(parts) + ".")
        lines.append("")

    # Comment Opportunities
    all_opportunities = so_opportunities + reddit_opportunities
    if all_opportunities:
        lines.append("**Comment Opportunities (new this week)**")
        for item in all_opportunities[:10]:
            if item["source"] == "stackoverflow":
                lines.append(f'  SO: "{item["title"]}" (score:{item["score"]}, answers:{item["answers"]})')
                lines.append(f'    Link: {item["link"]}')
            else:
                lines.append(f'  r/{item["subreddit"]}: "{item["title"]}" (score:{item["score"]}, comments:{item["comments"]})')
                lines.append(f'    Link: {item["link"]}')
            lines.append(f'    Suggested comment:')
            for cline in draft_comment(item).split("\n"):
                lines.append(f'    {cline}')
            lines.append("")
        lines.append("")

    # Backlink PRs
    pr_statuses = get_pr_statuses()
    has_open = any("OPEN" in s for s in pr_statuses)
    lines.append("**Backlink PRs**")
    for s in pr_statuses:
        lines.append(s)
    if not has_open:
        lines.append("All PRs resolved — this section will stop appearing once none are OPEN.")
    lines.append("")

    # Certificates Issued
    lines.append("**Certificates Issued (since last report)**")
    if cn_entries:
        lines.append(f"{len(cn_entries)} certificate(s):")
        for entry in cn_entries:
            lines.append(f"  {entry['time']}  {entry['cn']}")
    else:
        lines.append("None.")
    lines.append("")

    text = "\n".join(lines)
    subject = f"cert-depot.com — {today}"

    result = send_email(subject, text)
    print(f"Sent: {subject} (message_id: {result.get('message_id', 'unknown')})")


if __name__ == "__main__":
    main()
