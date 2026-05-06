#!/home/certdepot/.venv/bin/python
"""Notify search engines that cert-depot.com content has changed.

Pings IndexNow (Bing/Yandex/Naver/Seznam) for the supplied URLs, and asks
Google Search Console to re-fetch our sitemap.

Usage:
    notify_search_engines.py [URL ...]

If no URLs are supplied, only the GSC sitemap submission runs.
"""

import json
import sys
import urllib.error
import urllib.request

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SITE_BASE = "https://cert-depot.com"
HOST = "cert-depot.com"

INDEXNOW_KEY = "e0c2aaae51eec2777f2dbd044bcf8cf4"
INDEXNOW_KEY_LOCATION = f"{SITE_BASE}/{INDEXNOW_KEY}.txt"
INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"

GSC_KEY_FILE = "/home/certdepot/ga_cc_key_certdepot.json"
GSC_SITE_URL = f"{SITE_BASE}/"
GSC_SITEMAP_URL = f"{SITE_BASE}/sitemap.xml"


def ping_indexnow(urls):
    if not urls:
        return "IndexNow: skipped (no URLs)"
    body = json.dumps({
        "host": HOST,
        "key": INDEXNOW_KEY,
        "keyLocation": INDEXNOW_KEY_LOCATION,
        "urlList": urls,
    }).encode()
    req = urllib.request.Request(
        INDEXNOW_ENDPOINT,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return f"IndexNow: HTTP {resp.status} for {len(urls)} URL(s)"
    except urllib.error.HTTPError as e:
        # 200 OK, 202 Accepted, 422 Unprocessable (URLs don't match host) are documented
        return f"IndexNow: HTTP {e.code} ({e.read().decode('utf-8', 'replace')[:200]})"
    except Exception as e:
        return f"IndexNow: ERROR ({e})"


def submit_sitemap_to_gsc():
    try:
        creds = service_account.Credentials.from_service_account_file(
            GSC_KEY_FILE,
            scopes=["https://www.googleapis.com/auth/webmasters"],
        )
        service = build("searchconsole", "v1", credentials=creds, cache_discovery=False)
        service.sitemaps().submit(
            siteUrl=GSC_SITE_URL,
            feedpath=GSC_SITEMAP_URL,
        ).execute()
        return f"GSC sitemap: submitted {GSC_SITEMAP_URL}"
    except HttpError as e:
        # 403 means the service account isn't an Owner in GSC for this property.
        return f"GSC sitemap: HTTP {e.resp.status} ({e.error_details if hasattr(e, 'error_details') else e})"
    except Exception as e:
        return f"GSC sitemap: ERROR ({e})"


def main():
    urls = sys.argv[1:]
    print(ping_indexnow(urls))
    print(submit_sitemap_to_gsc())


if __name__ == "__main__":
    main()
