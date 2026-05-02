---
name: meeting
description: Generates a realistic spoken conversation for a given topic and participants, posts it through the full OTEL pipeline (gateway → transcription → diarization → indexing → storage), and creates a searchable transcript. Also searches stored transcripts by tag, keyword, or speaker name.
when_to_use: When the user wants to simulate a meeting, generate a conversation on a topic, log it through the observability pipeline, or search/browse stored transcripts.
argument-hint: "topic=<topic> [participants=<name1,name2,...>] | search=<query>"
allowed-tools: "Write Bash(python *)"
---

# /meeting Skill

Two modes — determine which from the arguments:

- **Generate** — `topic` is present → create a conversation and log it through the pipeline
- **Search** — `search` is present (or the user asks to find/list/browse) → query stored transcripts

Reference scripts live alongside this file:

| Script | Purpose |
|--------|---------|
| `post_meeting.py` | Template: fill in `PAYLOAD`, run to POST through the gateway |
| `search_transcripts.py` | Fetch and filter stored transcripts from storage-svc |

---

## Generate Mode

### Step 1 — Write the conversation

Create a realistic spoken meeting transcript. Rules:

- Every line: `Speaker Name: their words` — natural speech, contractions, interruptions
- 2–5 speakers; use the provided names or invent realistic ones if none given
- 25–40 exchanges; let participants agree, push back, and land on concrete decisions
- Each speaker should have a distinct role or perspective
- Include specific details: numbers, names, dates, action-item owners
- End with a clear outcome or next-steps summary exchange

After writing the dialogue, count words per speaker by tallying words in that
speaker's lines.

Choose 3–6 lowercase hyphenated `tags` that would help someone find this meeting
later (e.g. `q3-budget`, `hiring`, `product-roadmap`, `incident-review`).

Write a 1–2 sentence `summary` capturing the key decision or outcome.

Build a `filename` as `<topic-slug>-YYYY-MM-DD.json` using today's date.

Estimate `duration_seconds` as `total_word_count / 2.5`.

### Step 2 — POST through the pipeline

Use `.claude/skills/meeting/post_meeting.py` as your template.
Copy it to `/tmp/meeting_post.py`, fill in the `PAYLOAD` dict with the
conversation you generated, then run it:

```
Write  →  /tmp/meeting_post.py   (filled-in copy of post_meeting.py)
Bash   →  python /tmp/meeting_post.py
```

The gateway runs the full five-service pipeline:
`gateway → transcription → diarization → indexing → storage`

Each service still executes and emits OTEL spans — the full distributed trace
appears in Grafana/Tempo even though the content is pre-baked.

### Step 3 — Show the user

1. **The conversation** — print the full dialogue so the user can read it
2. **Result** — `transcript_id`, `job_id`, `status` from the POST response
3. **Trace** — "View the distributed trace in Grafana at http://localhost:3000
   (Recent Pipeline Traces dashboard) or search Tempo at http://localhost:3200"

---

## Search Mode

Use `.claude/skills/meeting/search_transcripts.py` directly:

```
Bash  →  python .claude/skills/meeting/search_transcripts.py "<query>"
```

Display results as a clean list. For each match show: `id`, `filename`, `tags`,
`summary`, `created_at`.

If no query is given, list all stored transcripts.

To retrieve the full text of a specific transcript:

```python
import json, urllib.request
resp = urllib.request.urlopen("http://localhost:8004/transcripts/<id>")
t = json.loads(resp.read())
print(t["text"])
```

---

## Notes

- The gateway must be running. Check with `docker compose ps`.
- Storage is in-memory — transcripts reset on container restart.
  Run `python scripts/seed.py` to repopulate demo data.
- `post_meeting.py` and `search_transcripts.py` can also be run standalone
  outside of this skill, e.g. in a terminal for quick manual testing.
