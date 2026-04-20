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

    rebuild_and_restart()
    print("  Service restarted")

    log_deployment(meta, url_path)
    mark_deployed(item)
    print(f"  Deployed: {meta['title']} -> {url_path}")


if __name__ == "__main__":
    main()
