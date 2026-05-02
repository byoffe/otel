---
name: meeting
description: Generates a realistic spoken conversation for a given topic and participants, posts it through the full OTEL pipeline (gateway → transcription → diarization → indexing → storage), and creates a searchable transcript. Also searches stored transcripts by tag, keyword, or speaker name.
when_to_use: When the user wants to simulate a meeting, generate a conversation on a topic, log it through the observability pipeline, or search/browse stored transcripts.
argument-hint: "topic=<topic> [participants=<name1,name2,...>] | search=<query>"
allowed-tools: "Write Bash(python *)"
---

# /meeting Skill

Two modes. Determine which based on the arguments:

- **Generate** — when `topic` is specified (with or without `participants`)
- **Search** — when `search` is specified (or the user asks to find/list/browse transcripts)

---

## Generate Mode

### Step 1 — Write the conversation

Generate a realistic spoken meeting transcript. Rules:

- Every line is `Speaker Name: their words` — natural speech, contractions, hesitations
- 2–5 speakers; use the provided names or invent realistic ones if none given
- 25–40 exchanges; let participants interrupt, agree, push back, and land on decisions
- Each speaker should have a distinct role or angle on the topic
- Weave in concrete details: numbers, names, dates, action item owners
- End with a clear outcome or next-step summary exchange

After writing the dialogue, compute per-speaker word counts by tallying words in that speaker's lines.

Choose 3–6 lowercase hyphenated `tags` that would help someone find this meeting later (e.g. `q3-budget`, `hiring`, `product-roadmap`, `incident-review`, `sprint-retro`).

Write a 1–2 sentence `summary` capturing the key decision or outcome.

Build a `filename` as `<topic-slug>-YYYY-MM-DD.json` using today's date.

Estimate `duration_seconds` as `total_word_count / 2.5`.

### Step 2 — POST through the pipeline

Write the payload to a temp file and POST it with Python:

```python
import json, urllib.request

payload = {
    "filename": "<topic-slug>-YYYY-MM-DD.json",
    "duration_seconds": <estimated>,
    "content": {
        "text": "<full conversation — newline-separated Speaker: text lines>",
        "speakers": [
            {"name": "Alice", "word_count": 312},
            {"name": "Bob",   "word_count": 189}
        ],
        "tags": ["tag1", "tag2"],
        "summary": "One or two sentences."
    }
}

data = json.dumps(payload).encode()
req = urllib.request.Request(
    "http://localhost:8000/jobs",
    data=data,
    headers={"Content-Type": "application/json"},
)
try:
    resp = urllib.request.urlopen(req, timeout=30)
    print(resp.read().decode())
except Exception as e:
    print(f"Error: {e}")
```

Use the `Write` tool to write this as `/tmp/meeting_post.py` (substituting real values),
then run it with `python /tmp/meeting_post.py`.

### Step 3 — Display

Show the user:

1. **The full conversation** — print it so they can read what was generated
2. **Job result** — `transcript_id`, `job_id`, `status`
3. **Trace** — "Find the distributed trace in Grafana at http://localhost:3000
   (Dashboard → Recent Pipeline Traces) or search Tempo at http://localhost:3200
   for service `gateway-svc`"

---

## Search Mode

Retrieve all transcripts and filter by the query against tags, filename, and summary.

Write and run this Python:

```python
import json, urllib.request

resp = urllib.request.urlopen("http://localhost:8004/transcripts", timeout=10)
transcripts = json.loads(resp.read())

query = "<user query>".lower()
matches = [
    t for t in transcripts
    if query in " ".join(t.get("tags", [])).lower()
    or query in t.get("filename", "").lower()
    or query in t.get("summary", "").lower()
]

if matches:
    for t in matches:
        print(json.dumps(t, indent=2))
else:
    all_tags = sorted({tag for t in transcripts for tag in t.get("tags", [])})
    print("No matches. Available tags:", all_tags)
```

Display results as a clean list. For each match show:
- `id` (the transcript ID)
- `filename`
- `tags`
- `summary`
- `created_at`

Offer to retrieve the full text: "To read the full transcript, ask me:
`/meeting get <transcript_id>`" — or handle `get` inline by calling
`GET http://localhost:8004/transcripts/<id>` and printing the `text` field.

---

## Notes

- The gateway must be running (`docker compose up` or `docker compose ps` to check).
- Storage is in-memory — transcripts reset when the container restarts.
  Run `python scripts/seed.py` to repopulate with demo data.
- The pipeline creates a full distributed OTEL trace for every `/meeting` call —
  all 5 services (gateway → transcription → diarization → indexing → storage)
  appear as child spans under one trace ID in Tempo.
