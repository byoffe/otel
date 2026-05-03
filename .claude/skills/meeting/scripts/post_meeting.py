"""
post_meeting.py — reference script for the /meeting skill.

Claude writes the PAYLOAD dict at the top (replacing the placeholders),
then runs this script to POST a pre-baked conversation through the pipeline.

Usage (after filling in PAYLOAD):
    python .claude/skills/meeting/post_meeting.py
"""

import json
import sys
import urllib.request

GATEWAY_URL = "http://localhost:8000/jobs"

# ── Claude fills this in ────────────────────────────────────────────────────
PAYLOAD: dict = {
    "filename": "TOPIC-SLUG-YYYY-MM-DD.json",
    "duration_seconds": 0,  # estimate: total_word_count / 2.5
    "content": {
        "text": "",  # full conversation, "Speaker: text\n" per turn
        "speakers": [
            # {"name": "Alice", "word_count": 312},
            # {"name": "Bob",   "word_count": 189},
        ],
        "tags": [],  # 3-6 lowercase hyphenated strings
        "summary": "",  # 1-2 sentence outcome
    },
}
# ───────────────────────────────────────────────────────────────────────────


def main() -> None:
    data = json.dumps(PAYLOAD).encode()
    req = urllib.request.Request(
        GATEWAY_URL, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read())
        print(json.dumps(result, indent=2))
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
