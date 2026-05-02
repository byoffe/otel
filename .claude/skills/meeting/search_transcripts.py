"""
search_transcripts.py — reference script for the /meeting skill.

Fetches all stored transcripts from storage-svc and filters them by a
query string matched against tags, filename, and summary.

Usage:
    python .claude/skills/meeting/search_transcripts.py <query>
    python .claude/skills/meeting/search_transcripts.py              # list all
"""

import json
import sys
import urllib.request

STORAGE_URL = "http://localhost:8004/transcripts"


def main() -> None:
    query = sys.argv[1].lower() if len(sys.argv) > 1 else ""

    try:
        resp = urllib.request.urlopen(STORAGE_URL, timeout=10)
        transcripts: list[dict] = json.loads(resp.read())
    except Exception as e:
        print(f"Could not reach storage-svc: {e}", file=sys.stderr)
        sys.exit(1)

    if not transcripts:
        print("No transcripts stored. Run `python scripts/seed.py` to populate demo data.")
        return

    if query:
        matches = [
            t for t in transcripts
            if query in " ".join(t.get("tags", [])).lower()
            or query in t.get("filename", "").lower()
            or query in t.get("summary", "").lower()
        ]
    else:
        matches = transcripts

    if not matches:
        all_tags = sorted({tag for t in transcripts for tag in t.get("tags", [])})
        print(f"No matches for '{query}'.")
        print(f"Available tags: {', '.join(all_tags)}")
        return

    for t in matches:
        print(f"── {t['id']}")
        print(f"   file   : {t['filename']}")
        print(f"   tags   : {', '.join(t.get('tags', []))}")
        print(f"   summary: {t.get('summary', '')}")
        print(f"   stored : {t.get('created_at', '')}")
        print()


if __name__ == "__main__":
    main()
