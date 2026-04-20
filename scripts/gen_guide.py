#!/usr/bin/env python3
"""Generate a guide HTML page from a markdown-like spec file.

Usage: gen_guide.py <spec.json>
Each spec.json contains:
  slug, title, description, subtitle, body_html (already formatted), related (list)
Output: writes <slug>.html and metadata.json next to the spec file.
"""

import json
import sys
from pathlib import Path

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <script async src="https://www.googletagmanager.com/gtag/js?id=G-9JTD7HTGCG"></script>
    <script src="/static/js/gtag.js"></script>

    <title>{title} | Certificate Depot</title>
    <meta name="description" content="{description}">
    <link rel="canonical" href="https://cert-depot.com/guides/{slug}">

    <meta property="og:type" content="article">
    <meta property="og:url" content="https://cert-depot.com/guides/{slug}">
    <meta property="og:title" content="{title}">
    <meta property="og:description" content="{description}">

    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
    <link rel="stylesheet" href="/static/css/style.css">
    <link rel="stylesheet" href="/static/css/guide.css">
</head>
<body class="bg-slate-50 min-h-screen flex flex-col">

    <header class="cd-header py-8">
        <div class="max-w-4xl mx-auto px-6 text-center">
            <a href="/" class="inline-block">
                <h1 class="text-3xl sm:text-4xl font-extrabold tracking-tight">Certificate Depot</h1>
            </a>
            <p class="mt-2 text-sm sm:text-base font-medium">Guides</p>
        </div>
    </header>

    <main class="flex-1">
        <article class="guide-body">
            <div class="guide-breadcrumb">
                <a href="/">Home</a> &rsaquo; Guides &rsaquo; {breadcrumb}
            </div>

            <h1>{h1}</h1>
            <p class="subtitle">{subtitle}</p>

{body_html}

            <div class="guide-cta">
                <strong>Need a self-signed certificate?</strong> Use our <a href="/">free generator</a> — browser-compatible SANs, RSA or ECDSA, ZIP or PFX. No signup, no ads, keys never stored.
            </div>

{related_html}
        </article>
    </main>

    <footer class="cd-footer py-6">
        <div class="max-w-4xl mx-auto px-6 text-center">
            <p class="cd-footer-warning text-sm font-semibold mb-2">Self-signed certificates are intended for development and testing only. Do not use them in production.</p>
            <p class="cd-footer-sub text-sm"><strong>Certificate Depot</strong> &mdash; Free and open source, forever. No ads, no tracking cookies, no stored keys.</p>
        </div>
    </footer>
</body>
</html>
"""


def render_related(related):
    if not related:
        return ""
    items = "\n".join(f'                <li><a href="/guides/{r["slug"]}">{r["title"]}</a></li>' for r in related)
    return f'''            <h2>Further Reading</h2>
            <ul>
{items}
            </ul>'''


def main():
    spec_path = Path(sys.argv[1])
    with open(spec_path) as f:
        spec = json.load(f)

    html = TEMPLATE.format(
        title=spec["title"],
        description=spec["description"],
        slug=spec["slug"],
        breadcrumb=spec.get("breadcrumb", spec["title"]),
        h1=spec.get("h1", spec["title"]),
        subtitle=spec["subtitle"],
        body_html=spec["body_html"],
        related_html=render_related(spec.get("related", [])),
    )

    out_dir = spec_path.parent
    out_html = out_dir / f"{spec['slug']}.html"
    out_html.write_text(html)

    meta = {
        "type": "guide",
        "slug": spec["slug"],
        "title": spec["title"],
        "priority": spec.get("priority", "0.7"),
    }
    (out_dir / "metadata.json").write_text(json.dumps(meta, indent=2))

    print(f"Generated {out_html}")


if __name__ == "__main__":
    main()
