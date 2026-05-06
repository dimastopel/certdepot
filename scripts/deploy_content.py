#!/usr/bin/env python3
"""Daily content deployer for cert-depot.com.

Picks the lowest-numbered directory in content-queue/, copies its files into the
correct static/ location, updates the sitemap, rebuilds the binary, and restarts
the service. The queue directory is renamed with a `.deployed` suffix on success.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

REPO = Path("/home/certdepot/cert-depot")
QUEUE = REPO / "content-queue"
STATIC = REPO / "static"
SITEMAP = STATIC / "sitemap.xml"
DEPLOY_LOG = REPO / "data" / "deploy_log.jsonl"
SITE_BASE = "https://cert-depot.com"

NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


def next_item():
    """Return the first un-deployed queue directory (sorted alphabetically)."""
    if not QUEUE.exists():
        return None
    items = sorted(
        p for p in QUEUE.iterdir()
        if p.is_dir() and not p.name.endswith(".deployed") and not p.name.startswith(".")
    )
    return items[0] if items else None


def load_metadata(item_dir):
    meta_path = item_dir / "metadata.json"
    if not meta_path.exists():
        raise SystemExit(f"Missing metadata.json in {item_dir}")
    with open(meta_path) as f:
        return json.load(f)


def copy_content(item_dir, meta):
    """Copy HTML and any JS/CSS from queue dir to static/{tools,guides}/."""
    content_type = meta["type"]
    slug = meta["slug"]
    if content_type not in ("tool", "guide"):
        raise SystemExit(f"Invalid type: {content_type}")
    if not re.match(r"^[a-z0-9-]{1,64}$", slug):
        raise SystemExit(f"Invalid slug: {slug}")

    target_dir_name = "tools" if content_type == "tool" else "guides"
    target_dir = STATIC / target_dir_name
    target_dir.mkdir(parents=True, exist_ok=True)

    # Copy the main HTML file (must be named {slug}.html)
    src_html = item_dir / f"{slug}.html"
    if not src_html.exists():
        raise SystemExit(f"Missing {slug}.html in {item_dir}")
    shutil.copy2(src_html, target_dir / f"{slug}.html")

    # Copy any .js/.css into static/js or static/css using the same basename
    for src in item_dir.iterdir():
        if src.suffix == ".js":
            shutil.copy2(src, STATIC / "js" / src.name)
        elif src.suffix == ".css":
            shutil.copy2(src, STATIC / "css" / src.name)

    return f"/{target_dir_name}/{slug}"


def add_to_sitemap(url_path, priority):
    """Insert a new URL entry into sitemap.xml (no duplicates)."""
    ET.register_namespace("", NS)
    tree = ET.parse(SITEMAP)
    root = tree.getroot()

    full_url = SITE_BASE + url_path
    # Skip if already present
    for loc in root.findall(f"{{{NS}}}url/{{{NS}}}loc"):
        if loc.text == full_url:
            return False

    url_el = ET.SubElement(root, f"{{{NS}}}url")
    ET.SubElement(url_el, f"{{{NS}}}loc").text = full_url
    ET.SubElement(url_el, f"{{{NS}}}changefreq").text = "monthly"
    ET.SubElement(url_el, f"{{{NS}}}priority").text = str(priority)

    ET.indent(tree, space="    ")
    tree.write(SITEMAP, xml_declaration=True, encoding="UTF-8")
    return True


def update_homepage_links():
    """Regenerate the Tools & Guides section on index.html from deploy_log.jsonl.

    Reads all deployments (including the one just logged), and writes a unified
    section between the AUTO-LINKS-START and AUTO-LINKS-END markers.
    """
    index_path = STATIC / "index.html"
    index = index_path.read_text()

    # Collect deployments — prefer later entries if a slug is duplicated
    entries_by_slug = {}
    if DEPLOY_LOG.exists():
        with open(DEPLOY_LOG) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                entries_by_slug[e["slug"]] = e

    # Sort: tools first, then guides, each alphabetical by title
    tools = sorted([e for e in entries_by_slug.values() if e["type"] == "tool"], key=lambda e: e["title"])
    guides = sorted([e for e in entries_by_slug.values() if e["type"] == "guide"], key=lambda e: e["title"])
    all_entries = tools + guides

    if not all_entries:
        return

    def card(entry):
        label = "Tool" if entry["type"] == "tool" else "Guide"
        return (
            f'            <a href="{entry["url"].replace("https://cert-depot.com", "")}" '
            f'class="bg-white rounded-xl border border-gray-200 p-4 hover:border-blue-400 transition-colors">\n'
            f'                <h3 class="cd-heading font-semibold text-sm mb-1">{entry["title"]}</h3>\n'
            f'                <p class="text-xs text-gray-600">{label}</p>\n'
            f'            </a>'
        )

    cards_html = "\n".join(card(e) for e in all_entries)

    new_section = (
        "    <!-- AUTO-LINKS-START -->\n"
        "    <section class=\"w-full max-w-2xl mx-auto px-4 sm:px-6 pb-8\">\n"
        "        <h2 class=\"cd-heading text-xl font-bold mb-4 text-center\">Tools &amp; Guides</h2>\n"
        "        <div class=\"grid grid-cols-1 sm:grid-cols-2 gap-3\">\n"
        f"{cards_html}\n"
        "        </div>\n"
        "    </section>\n"
        "    <!-- AUTO-LINKS-END -->"
    )

    # Replace the section between markers
    pattern = re.compile(r"    <!-- AUTO-LINKS-START -->.*?<!-- AUTO-LINKS-END -->", re.DOTALL)
    if not pattern.search(index):
        print("  WARNING: AUTO-LINKS markers not found in index.html — skipping homepage update.")
        return
    new_index = pattern.sub(new_section, index)
    index_path.write_text(new_index)


def rebuild_and_restart():
    """Build the binary and restart both services."""
    env = os.environ.copy()
    env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"

    # Build staging binary
    r = subprocess.run(["go", "build", "-o", "cert-depot-staging", "."], cwd=REPO, env=env)
    if r.returncode != 0:
        raise SystemExit("go build failed")

    # Restart staging
    subprocess.run(["systemctl", "--user", "restart", "cert-depot-staging"], env=env, check=True)

    # Copy to prod binary and restart prod
    subprocess.run(["systemctl", "--user", "stop", "cert-depot"], env=env, check=True)
    shutil.copy2(REPO / "cert-depot-staging", REPO / "cert-depot")
    subprocess.run(["systemctl", "--user", "start", "cert-depot"], env=env, check=True)


def log_deployment(meta, url_path):
    DEPLOY_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "date": date.today().isoformat(),
        "type": meta["type"],
        "slug": meta["slug"],
        "title": meta["title"],
        "url": SITE_BASE + url_path,
    }
    with open(DEPLOY_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def mark_deployed(item_dir):
    deployed_path = item_dir.with_name(item_dir.name + ".deployed")
    item_dir.rename(deployed_path)


def notify_search_engines(urls):
    """Ping IndexNow + re-submit sitemap to GSC. Best-effort, never fails the deploy."""
    notifier = REPO / "scripts" / "notify_search_engines.py"
    if not notifier.exists():
        return
    try:
        proc = subprocess.run(
            [str(notifier)] + urls,
            capture_output=True, text=True, timeout=30,
        )
        for line in (proc.stdout + proc.stderr).splitlines():
            if line.strip():
                print(f"  {line}")
    except Exception as e:
        print(f"  notify_search_engines failed: {e}")


def main():
    item = next_item()
    if not item:
        print("No items in queue — nothing to deploy.")
        return

    print(f"Deploying: {item.name}")
    meta = load_metadata(item)
    url_path = copy_content(item, meta)
    print(f"  Copied to: {url_path}")

    priority = meta.get("priority", "0.7")
    added = add_to_sitemap(url_path, priority)
    print(f"  Sitemap: {'added' if added else 'already present'}")

    # Log before updating homepage so the new entry is included in the links section
    log_deployment(meta, url_path)
    update_homepage_links()
    print("  Homepage links updated")

    # Inject TechArticle JSON-LD into any guides that lack it (idempotent).
    # Only meaningful for guide deploys; safe to run for tools (it's a no-op).
    if meta.get("type") == "guide":
        injector = REPO / "scripts" / "inject_jsonld.py"
        if injector.exists():
            r = subprocess.run(["python3", str(injector)], cwd=REPO, capture_output=True, text=True)
            for line in r.stdout.splitlines():
                if "injected" in line:
                    print(f"  JSON-LD: {line}")

    rebuild_and_restart()
    print("  Service restarted")

    mark_deployed(item)
    print(f"  Deployed: {meta['title']} -> {url_path}")

    # Ping search engines after the new content is actually live
    full_url = SITE_BASE + url_path
    notify_search_engines([full_url, SITE_BASE + "/", SITE_BASE + "/sitemap.xml"])

    # Cross-post guides to dev.to (skipped silently if no API key configured)
    if meta.get("type") == "guide":
        cross_poster = REPO / "scripts" / "cross_post_devto.py"
        devto_key = Path("/home/certdepot/devto_api_key.txt")
        if cross_poster.exists() and devto_key.exists():
            try:
                r = subprocess.run(
                    ["python3", str(cross_poster), meta["slug"]],
                    cwd=REPO, capture_output=True, text=True, timeout=60,
                )
                for line in (r.stdout + r.stderr).splitlines():
                    if line.strip():
                        print(f"  dev.to: {line}")
            except Exception as e:
                print(f"  dev.to cross-post failed: {e}")


if __name__ == "__main__":
    main()
