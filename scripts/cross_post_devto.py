#!/usr/bin/env python3
"""Cross-post a cert-depot guide to dev.to with canonical URL set back to us.

Reads static/guides/{slug}.html, extracts the <article> body, converts it to
markdown, and POSTs to dev.to with `canonical_url` pointing at cert-depot.com.
Tracks posted slugs in data/devto_posted.json so re-runs don't duplicate.

Usage:
    cross_post_devto.py [SLUG ...]

If no slugs are supplied, every guide that hasn't been cross-posted yet is sent.

Requires: /home/certdepot/devto_api_key.txt containing the dev.to API key.
"""

import json
import re
import sys
import urllib.error
import urllib.request
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GUIDES_DIR = REPO / "static" / "guides"
POSTED_FILE = REPO / "data" / "devto_posted.json"
API_KEY_FILE = Path("/home/certdepot/devto_api_key.txt")
SITE_BASE = "https://cert-depot.com"
DEVTO_API = "https://dev.to/api/articles"

DEFAULT_TAGS = ["ssl", "tls", "security", "tutorial"]


def load_api_key():
    if not API_KEY_FILE.exists():
        raise SystemExit(
            f"Missing {API_KEY_FILE}. Generate a key at "
            "https://dev.to/settings/extensions and write it to that file."
        )
    return API_KEY_FILE.read_text().strip()


def load_posted():
    if not POSTED_FILE.exists():
        return {}
    try:
        return json.loads(POSTED_FILE.read_text())
    except json.JSONDecodeError:
        return {}


def save_posted(d):
    POSTED_FILE.parent.mkdir(parents=True, exist_ok=True)
    POSTED_FILE.write_text(json.dumps(d, indent=2))


# ---------------- HTML → Markdown ----------------

class _Md(HTMLParser):
    """Minimal HTML→Markdown converter targeting cert-depot guide structure.

    Only handles the tags actually used in the guides: h1/h2/h3, p, pre, code,
    ul/li, blockquote, a, strong, em. Anything unknown is treated as transparent.
    """

    SKIP = {"div", "section", "article", "span", "header", "footer", "main", "nav"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.stack = []
        self.in_pre = False
        self.in_code = False
        self.list_depth = 0
        self.href_stack = []
        self.skip_depth = 0  # for things we want to drop entirely (e.g. guide-cta block)
        self.line_buf = []

    # ---- helpers ----
    def _flush_line(self):
        if self.line_buf:
            self.out.append("".join(self.line_buf))
            self.line_buf = []

    def _emit(self, s):
        if self.skip_depth > 0:
            return
        self.line_buf.append(s)

    def _newline(self, n=1):
        if self.skip_depth > 0:
            return
        self._flush_line()
        self.out.extend([""] * n)

    # ---- tag handlers ----
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        cls = attrs.get("class", "")

        # Drop the on-page CTA, breadcrumb, and Further Reading list — duplicated content
        if "guide-cta" in cls or "guide-breadcrumb" in cls:
            self.skip_depth += 1
            self.stack.append(("__skip__", tag))
            return

        if self.skip_depth > 0:
            self.skip_depth += 1
            self.stack.append(("__skip__", tag))
            return

        if tag == "h1":
            self._newline(); self._emit("# ")
        elif tag == "h2":
            self._newline(); self._emit("## ")
        elif tag == "h3":
            self._newline(); self._emit("### ")
        elif tag == "p":
            self._newline()
        elif tag == "pre":
            self.in_pre = True
            self._flush_line()
            self.out.append("")
            self.out.append("```")
        elif tag == "code":
            if not self.in_pre:
                self.in_code = True
                self._emit("`")
        elif tag == "ul" or tag == "ol":
            self.list_depth += 1
            self._newline()
        elif tag == "li":
            self._flush_line()
            self._emit("- ")
        elif tag == "blockquote":
            self._newline()
            self._emit("> ")
        elif tag == "a":
            self.href_stack.append(attrs.get("href", ""))
            self._emit("[")
        elif tag == "strong" or tag == "b":
            self._emit("**")
        elif tag == "em" or tag == "i":
            self._emit("*")
        elif tag == "br":
            self._flush_line()
        elif tag == "subtitle":
            self._newline(); self._emit("_")
        elif tag in self.SKIP:
            pass
        # all others: ignore opening tag

        self.stack.append((tag, cls))

    def handle_endtag(self, tag):
        if not self.stack:
            return
        last_tag, last_cls = self.stack.pop()

        if last_tag == "__skip__":
            self.skip_depth -= 1
            return

        if tag == "h1" or tag == "h2" or tag == "h3":
            self._newline()
        elif tag == "p":
            self._newline()
        elif tag == "pre":
            self._flush_line()
            self.out.append("```")
            self.out.append("")
            self.in_pre = False
            return
        elif tag == "code":
            if not self.in_pre:
                self._emit("`")
                self.in_code = False
        elif tag == "ul" or tag == "ol":
            self.list_depth -= 1
            self._newline()
        elif tag == "li":
            self._flush_line()
        elif tag == "blockquote":
            self._newline()
        elif tag == "a":
            href = self.href_stack.pop() if self.href_stack else ""
            # Resolve relative URLs back to cert-depot
            if href.startswith("/"):
                href = SITE_BASE + href
            self._emit(f"]({href})")
        elif tag == "strong" or tag == "b":
            self._emit("**")
        elif tag == "em" or tag == "i":
            self._emit("*")

    def handle_data(self, data):
        if self.skip_depth > 0:
            return
        if self.in_pre:
            # preserve verbatim, including newlines
            self.out.append(data.rstrip("\n"))
        else:
            # collapse runs of whitespace; drop whitespace-only data so we don't
            # leave spurious " " lines between block tags.
            collapsed = re.sub(r"\s+", " ", data)
            if collapsed.strip() == "":
                return
            self._emit(collapsed)

    def get_markdown(self):
        self._flush_line()
        text = "\n".join(self.out)
        # collapse 3+ blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip() + "\n"


def html_to_markdown(article_html):
    p = _Md()
    p.feed(article_html)
    return p.get_markdown()


# ---------------- Guide parsing ----------------

ARTICLE_RE = re.compile(r"<article[^>]*>(.*?)</article>", re.IGNORECASE | re.DOTALL)
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)
DESC_RE = re.compile(r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)["\']', re.IGNORECASE)


def parse_guide(slug):
    path = GUIDES_DIR / f"{slug}.html"
    if not path.exists():
        raise SystemExit(f"No such guide: {path}")
    html = path.read_text()
    m = ARTICLE_RE.search(html)
    if not m:
        raise SystemExit(f"Could not find <article> in {path}")
    body_md = html_to_markdown(m.group(1))

    title = unescape((TITLE_RE.search(html) or [None, ""]).__getitem__(1)).strip()
    title = re.sub(r"\s*\|\s*Certificate Depot\s*$", "", title)
    title = re.sub(r"\s*[—-]\s*Certificate Depot\s*$", "", title)
    desc = unescape((DESC_RE.search(html) or [None, ""]).__getitem__(1)).strip()
    canonical = f"{SITE_BASE}/guides/{slug}"

    # Prepend a small canonical-source note for dev.to readers
    body_md = (
        f"> _Originally published on [cert-depot.com]({canonical}). "
        "Free, open-source self-signed certificate generator — no signup, "
        "keys never stored._\n\n" + body_md
    )

    return title, desc, body_md, canonical


# ---------------- Posting ----------------

def post_to_devto(api_key, title, body_md, canonical, tags):
    import re as _re
    import time as _time
    payload = {
        "article": {
            "title": title,
            "body_markdown": body_md,
            "published": True,
            "canonical_url": canonical,
            "tags": tags,
        }
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/vnd.forem.api-v1+json",
        "User-Agent": "cert-depot-cross-poster/1.0 (+https://cert-depot.com)",
    }

    for attempt in range(4):
        req = urllib.request.Request(DEVTO_API, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", "replace")
            # Honour dev.to's "try again in N seconds" on 429s
            if e.code == 429:
                wait = 60
                m = _re.search(r"try again in (\d+) seconds", text, _re.IGNORECASE)
                retry_after = e.headers.get("Retry-After")
                if m:
                    wait = int(m.group(1)) + 5
                elif retry_after and retry_after.isdigit():
                    wait = int(retry_after) + 5
                print(f"  dev.to 429: sleeping {wait}s before retry ({attempt + 1}/4)")
                _time.sleep(wait)
                continue
            # 5xx: short backoff and retry once
            if 500 <= e.code < 600 and attempt < 2:
                print(f"  dev.to {e.code}: short backoff (attempt {attempt + 1}/4)")
                _time.sleep(15)
                continue
            raise SystemExit(f"dev.to HTTP {e.code}: {text[:500]}")
    raise SystemExit("dev.to: gave up after retries")


def main():
    import time

    api_key = load_api_key()
    posted = load_posted()

    slugs = sys.argv[1:]
    if not slugs:
        all_slugs = [p.stem for p in sorted(GUIDES_DIR.glob("*.html"))]
        slugs = [s for s in all_slugs if s not in posted]
        if not slugs:
            print("Nothing to do — every guide has already been cross-posted.")
            return

    first = True
    for slug in slugs:
        if slug in posted:
            print(f"{slug}: already posted ({posted[slug].get('url', '?')})")
            continue
        if not first:
            # dev.to throttles new accounts hard — observed 429 ("retry in 300s")
            # after only a few posts. 90s between posts keeps us well under.
            time.sleep(90)
        first = False
        title, desc, body_md, canonical = parse_guide(slug)
        result = post_to_devto(api_key, title, body_md, canonical, DEFAULT_TAGS)
        url = result.get("url", "?")
        posted[slug] = {"url": url, "id": result.get("id"), "canonical": canonical}
        save_posted(posted)
        print(f"{slug}: posted -> {url}")


if __name__ == "__main__":
    main()
