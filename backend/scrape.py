#!/usr/bin/env python3
"""
scrape.py - fetch recent Reddit posts via the public .json endpoints and
write them to records.csv in the backend pipeline schema.

Usage:
    pip install requests
    python scrape.py
"""
import csv
import json
import time
import uuid
from datetime import datetime, timezone
import requests

# ----------------------------- config ---------------------------------
SUBREDDITS = ["technology", "startups", "finance", "cybersecurity"]
POSTS_PER_SUBREDDIT = 100          # Reddit caps a single page at 100
OUTPUT_FILE = "records.csv"
REQUEST_DELAY_SECONDS = 2          # be polite between subreddits
MAX_RETRIES = 3

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

COLUMNS = [
    "id", "platform", "target", "record_type", "external_id", "author_id",
    "text", "source_url", "published_at", "metadata", "dedup_key",
]

BAD_TEXT = {"", "[removed]", "[deleted]"}

# ----------------------------- helpers --------------------------------
def fetch_subreddit(subreddit):
    """Return the list of raw post dicts for r/<subreddit>/new."""
    url = f"https://www.reddit.com/r/{subreddit}/new.json"
    params = {"limit": POSTS_PER_SUBREDDIT, "raw_json": 1}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=HEADERS, params=params, timeout=15)
            if resp.status_code == 429:  # rate limited -> back off and retry
                wait = int(resp.headers.get("Retry-After", 5 * attempt))
                print(f"  [r/{subreddit}] rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            children = resp.json().get("data", {}).get("children", [])
            return [c["data"] for c in children if c.get("kind") == "t3"]
        except (requests.RequestException, ValueError) as exc:
            print(f"  [r/{subreddit}] attempt {attempt}/{MAX_RETRIES} failed: {exc}")
            time.sleep(2 * attempt)
    return []

def iso_utc(created_utc):
    """Convert a Reddit created_utc epoch into strict ISO 8601 (Z suffix)."""
    dt = datetime.fromtimestamp(float(created_utc), tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

def build_text(post):
    """Combine title + selftext. Return None if the post should be skipped."""
    title = (post.get("title") or "").strip()
    body = (post.get("selftext") or "").strip()

    if title in BAD_TEXT or body in {"[removed]", "[deleted]"}:
        return None
    if post.get("author") in (None, "", "[deleted]"):
        return None
    if post.get("removed_by_category"):      # removed by mods/admins/author
        return None

    return f"{title}\n\n{body}" if body else title

def to_record(post, subreddit):
    """Map a raw Reddit post to one CSV row (dict), or None to skip."""
    text = build_text(post)
    if text is None:
        return None

    external_id = post.get("name") or f"t3_{post['id']}"   # e.g. t3_abc123
    return {
        "id": str(uuid.uuid4()),
        "platform": "reddit",
        "target": subreddit,
        "record_type": "post",
        "external_id": external_id,
        "author_id": post["author"],
        "text": text,
        "source_url": f"https://www.reddit.com{post['permalink']}",
        "published_at": iso_utc(post["created_utc"]),
        "metadata": json.dumps(
            {
                "score": post.get("score", 0),
                "num_comments": post.get("num_comments", 0),
            },
            separators=(", ", ": "),
        ),
        "dedup_key": f"reddit|post|{external_id}",
    }

# ------------------------------- main ---------------------------------
def main():
    rows, seen = [], set()

    for i, sub in enumerate(SUBREDDITS):
        print(f"Fetching r/{sub} ...")
        posts = fetch_subreddit(sub)
        kept = 0
        for post in posts:
            record = to_record(post, sub)
            if record is None or record["dedup_key"] in seen:
                continue
            seen.add(record["dedup_key"])
            rows.append(record)
            kept += 1
        print(f"  fetched {len(posts)}, kept {kept}")
        if i < len(SUBREDDITS) - 1:
            time.sleep(REQUEST_DELAY_SECONDS)

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nDone. Wrote {len(rows)} records to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
