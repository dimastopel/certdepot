#!/usr/bin/env python3
"""Inject TechArticle JSON-LD into every static/guides/*.html that lacks it.

Idempotent: if a guide already has a script tag with @type TechArticle, it is
skipped. Pulls publication dates from data/deploy_log.jsonl so each guide gets
an accurate datePublished / dateModified.
"""

import json
import re
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GUIDES_DIR = REPO / "static" / "guides"
DEPLOY_LOG = REPO / "data" / "deploy_log.jsonl"
SITE_BASE = "https://cert-depot.com"

PUBLISHER = {
    "@type": "Organization",
    "name": "Certificate Depot",
    "url": SITE_BASE,
    "logo": {
        "@type": "ImageObject",
        "url": f"{SITE_BASE}/static/favicon.svg",
    },
}


def slug_dates():
    """Map slug -> (datePublished, dateModified). Falls back to today."""
    by_slug = {}
    if DEPLOY_LOG.exists():
        for line in DEPLOY_LOG.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            slug = e.get("slug")
            d = e.get("date")
            if not slug or not d:
                continue
            if slug not in by_slug:
                by_slug[slug] = [d, d]  # [first_seen, last_seen]
            else:
                by_slug[slug][1] = d  # update last_seen
    today = date.today().isoformat()
    return {s: (v[0], v[1]) for s, v in by_slug.items()} | {}, today


def extract(html, pattern, group=1):
    m = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
    return m.group(group).strip() if m else ""


def has_techarticle(html):
    # Look for a JSON-LD block whose @type is TechArticle.
    for m in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.IGNORECASE | re.DOTALL,
    ):
        try:
            obj = json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            continue
        t = obj.get("@type")
        if t == "TechArticle" or (isinstance(t, list) and "TechArticle" in t):
            return True
    return False


def build_jsonld(slug, title, description, url, date_published, date_modified):
    obj = {
        "@context": "https://schema.org",
        "@type": "TechArticle",
        "headline": title,
        "description": description,
        "url": url,
        "mainEntityOfPage": {"@type": "WebPage", "@id": url},
        "author": PUBLISHER,
        "publisher": PUBLISHER,
        "datePublished": date_published,
        "dateModified": date_modified,
        "inLanguage": "en",
    }
    return (
        '    <script type="application/ld+json">\n'
        + json.dumps(obj, indent=4)
        + "\n    </script>\n"
    )


def inject(path):
    html = path.read_text()
    slug = path.stem

    if has_techarticle(html):
        return f"{slug}: skipped (already has TechArticle)"

    title = extract(html, r"<title>(.*?)</title>")
    # Strip the " | Certificate Depot" suffix for headline cleanliness
    title = re.sub(r"\s*\|\s*Certificate Depot\s*$", "", title)
    description = extract(html, r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)["\']')
    url = f"{SITE_BASE}/guides/{slug}"

    # Pull dates from deploy log (set up below)
    pub, mod = DATES.get(slug, (TODAY, TODAY))

    block = build_jsonld(slug, title, description, url, pub, mod)

    # Insert the new <script> just before </head>. Preserve indentation.
    def _repl(m):
        return "\n" + block + m.group(1) + m.group(2) + "</head>"
    new_html, n = re.subn(r"(\n)(\s*)</head>", _repl, html, count=1)
    if n == 0:
        return f"{slug}: FAILED (no </head> found)"

    path.write_text(new_html)
    return f"{slug}: injected (published {pub}, modified {mod})"


# Loaded once at module level for inject() to use.
DATES, TODAY = slug_dates()


def main():
    if not GUIDES_DIR.exists():
        raise SystemExit(f"No such dir: {GUIDES_DIR}")
    paths = sorted(GUIDES_DIR.glob("*.html"))
    if not paths:
        print("No guides found.")
        return
    for p in paths:
        print(inject(p))


if __name__ == "__main__":
    main()
