"""seed.py — populate storage-svc with demo transcripts.

Usage:
    python scripts/seed.py
    STORAGE_URL=http://localhost:8004 python scripts/seed.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
import uuid

STORAGE_URL = os.environ.get("STORAGE_URL", "http://localhost:8004")

TRANSCRIPTS: list[dict] = [
    {
        "transcript_id": str(uuid.uuid4()),
        "filename": "q3-budget-planning-2026-04-15.json",
        "text": (
            "Alice: Let's get through the Q3 budget. Engineering is asking for two net-new headcount.\n"
            "Bob: We already froze hiring in Q2. What's the justification?\n"
            "Alice: Both are ML platform roles — they're tied to the inference cost reduction initiative.\n"
            "Carol: Finance approved those in March. They're in the plan.\n"
            "Bob: Okay, then we protect those two and freeze everything else until Q4 review.\n"
            "Alice: Agreed. Carol, can you own the vendor contract renewals before June 1st?\n"
            "Carol: Yes, I'll have drafts to legal by May 20th.\n"
            "Bob: Perfect. Let's lock this and move to the roadmap.\n"
        ),
        "speakers": [
            {"name": "Alice", "word_count": 48},
            {"name": "Bob", "word_count": 36},
            {"name": "Carol", "word_count": 22},
        ],
        "tags": ["q3-budget", "headcount", "hiring-freeze", "vendor", "finance"],
        "summary": "Team agreed to freeze all non-critical hiring while protecting two approved ML platform roles; Carol to deliver vendor contract drafts to legal by May 20th.",
    },
    {
        "transcript_id": str(uuid.uuid4()),
        "filename": "product-roadmap-review-2026-04-22.json",
        "text": (
            "Dana: We have five features in flight and only bandwidth for three in Q3. We need to cut.\n"
            "Eli: The search overhaul has been on the roadmap for two quarters. We can't cut it again.\n"
            "Dana: I agree. Search stays. The question is mobile notifications vs. bulk export.\n"
            "Fiona: Customer support gets twenty tickets a week on bulk export. That's the one.\n"
            "Eli: Mobile notifications has higher NPS impact according to the survey.\n"
            "Dana: Let's do bulk export now, notifications in Q4. We can A/B test the notification design in the meantime.\n"
            "Fiona: Works for me. I'll update the roadmap doc today.\n"
            "Eli: Ship search by end of July, bulk export by mid-August. That's the plan.\n"
        ),
        "speakers": [
            {"name": "Dana", "word_count": 55},
            {"name": "Eli", "word_count": 44},
            {"name": "Fiona", "word_count": 26},
        ],
        "tags": ["product-roadmap", "prioritization", "q3-features", "search", "mobile"],
        "summary": "Team cut mobile notifications to Q4 to protect the search overhaul and bulk export features; bulk export prioritized based on 20 weekly support tickets.",
    },
    {
        "transcript_id": str(uuid.uuid4()),
        "filename": "incident-review-api-outage-2026-04-28.json",
        "text": (
            "Grace: We had a 47-minute API outage on April 26th. Root cause was a bad deploy at 14:32 UTC.\n"
            "Henry: The deploy changed the connection pool size from 20 to 200. It exhausted database connections within 90 seconds.\n"
            "Grace: Why did it pass CI?\n"
            "Henry: Load test in CI only runs 10 concurrent users. The pool exhaustion requires 50+.\n"
            "Grace: So we need a higher-concurrency load test in CI and a rollback playbook.\n"
            "Iris: I'll add a 50-user load test to the pipeline by Friday.\n"
            "Henry: And I'll write the rollback runbook — should take a day.\n"
            "Grace: Good. We also need a postmortem doc published to the team by end of week.\n"
            "Iris: I'll draft it. Henry, can you review before I send?\n"
            "Henry: Yes. Let's not let this happen again.\n"
        ),
        "speakers": [
            {"name": "Grace", "word_count": 55},
            {"name": "Henry", "word_count": 64},
            {"name": "Iris", "word_count": 30},
        ],
        "tags": ["incident-review", "outage", "postmortem", "reliability", "database", "ci"],
        "summary": "47-minute API outage caused by connection pool misconfiguration in a deploy; remediation includes a 50-user CI load test (Iris, by Friday) and rollback runbook (Henry, 1 day).",
    },
    {
        "transcript_id": str(uuid.uuid4()),
        "filename": "hiring-panel-debrief-2026-04-30.json",
        "text": (
            "Jack: We interviewed four candidates for the senior backend role. I want to debrief on each.\n"
            "Karen: Candidate A had strong distributed systems knowledge but struggled with the system design round.\n"
            "Jack: I noticed that too. The Kafka design was shaky. What about Candidate B?\n"
            "Lena: Candidate B was the strongest by far. Five years at a FAANG, clean code, asked great questions.\n"
            "Karen: My only concern is compensation — they're expecting 180k base.\n"
            "Jack: We can go to 175k with the equity refresh. That might land it.\n"
            "Lena: Candidates C and D were junior-level despite applying to the senior role. Not a fit.\n"
            "Jack: Agreed. Let's move Candidate B to offer stage. Karen, can you prep the comp package today?\n"
            "Karen: Done by 3pm.\n"
        ),
        "speakers": [
            {"name": "Jack", "word_count": 60},
            {"name": "Karen", "word_count": 38},
            {"name": "Lena", "word_count": 34},
        ],
        "tags": ["hiring", "engineering", "candidate-review", "compensation", "backend"],
        "summary": "Panel selected Candidate B for the senior backend role at up to $175k base plus equity refresh; Karen to prepare the offer package by 3pm.",
    },
    {
        "transcript_id": str(uuid.uuid4()),
        "filename": "customer-feedback-synthesis-2026-05-01.json",
        "text": (
            "Mia: I reviewed 200 NPS responses from Q1. Three themes dominate: onboarding complexity, search quality, and API docs.\n"
            "Nate: Onboarding is the one I keep hearing on sales calls. Prospects drop off before the aha moment.\n"
            "Mia: Median time to first successful API call is 4.2 hours. It should be under 30 minutes.\n"
            "Olivia: We fixed three of the top onboarding friction points last sprint. Are those reflected in the data?\n"
            "Mia: No — this data predates the fixes. We'll see the impact in Q2 responses.\n"
            "Nate: Good. Search quality — is that the same ranking issue we already know about?\n"
            "Mia: Yes, and it's the number one detractor. Fixing it would move NPS by an estimated 8 points.\n"
            "Olivia: That's on the roadmap for July. API docs — what specifically?\n"
            "Mia: Missing authentication examples and no SDK quickstart for Python.\n"
            "Nate: I can write the Python quickstart this week. That one's quick.\n"
            "Mia: Perfect. Let's revisit this in four weeks with Q2 data.\n"
        ),
        "speakers": [
            {"name": "Mia", "word_count": 90},
            {"name": "Nate", "word_count": 52},
            {"name": "Olivia", "word_count": 26},
        ],
        "tags": ["customer-feedback", "nps", "onboarding", "search", "api-docs", "product"],
        "summary": "Q1 NPS analysis identified onboarding (4.2h to first API call), search ranking, and missing Python SDK docs as top detractors; Nate to write Python quickstart this week.",
    },
]


def main() -> None:
    print(f"Seeding {STORAGE_URL} with {len(TRANSCRIPTS)} transcripts...\n")
    for t in TRANSCRIPTS:
        data = json.dumps(t).encode()
        req = urllib.request.Request(
            f"{STORAGE_URL}/transcripts",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            result = json.loads(resp.read())
            print(f"  {result['id']}  {t['filename']}")
        except Exception as e:
            print(f"  ERROR seeding {t['filename']}: {e}", file=sys.stderr)
            sys.exit(1)
    print(f"\nDone. {len(TRANSCRIPTS)} transcripts stored.")


if __name__ == "__main__":
    main()
