# generate-emails

Generate personalised post-event follow-up email drafts for all quiz participants who don't yet have one. Emails are written directly into the Google Sheet. No Anthropic API key required — Claude Code generates the content in this session.

## Steps

### 1. Get the GAS URL and MEET_URL

Read `aggregated-results.html` and extract `DASHBOARD_DATA_URL`. That is the GAS endpoint used for both fetching and writing.

Read `quiz-webhook.gs` and extract `MEET_URL`. Use this in every email's closing CTA.

### 2. Fetch participants needing drafts

Run:

```bash
curl "<GAS_URL>?action=rows"
```

The response is `{ "rows": [...] }`. Each row contains:

| Field | Description |
|---|---|
| `rowIndex` | Sheet row number — required to write back |
| `name`, `email`, `role`, `team_size` | Participant basics |
| `readiness_score` | Foundations score, 0–100 |
| `readiness_band` | `Not there yet` → `Solid ground` |
| `stage` | What they actually have running today |
| `fit` | `ahead` / `matched` / `stretched` — foundations vs what's live |
| `weakest_category` | Weakest of the four foundations. **May be `'none'`** when all four are even (spread < 15) |
| `strongest_area` | Strongest of the four foundations |
| `dims` | `{connected_tools, data, ownership, team}`, each 0–100 |
| `next_moves` | The quiz's own recommended actions, `"A3: text \| B1: text"` |
| `points_to_next_band` | Points needed to reach the next readiness band |
| `roi` | ROI estimate in € (may be null) |
| `blockers` | Semicolon-separated top blockers (may be null) |
| `roadmap` | Participant's roadmap headline |

**The two scores mean different things and can disagree — that's the interesting part.** `readiness_score` measures foundations (data, ownership, connected tools, team habits). `stage` is what's actually live. `fit` names the relationship: `stretched` means they're running ahead of their foundations; `ahead` means they could be doing more than they are.

If `rows` is an empty array, report "No participants need email drafts yet." and stop.

### 3. Generate emails

For **each row**, generate a personalised email of ~220 words. Produce all emails before moving to step 4 — do not interleave fetching and writing.

**Structure (in this order):**

1. Subject: `Your AI readiness score — [short stage label]`
2. `Hi [first name],`
3. 2-3 sentences: their `readiness_score`/100 and `readiness_band`, their `stage`, one concrete implication for their specific role and team size. Where `fit` is `ahead` or `stretched`, the gap between foundations and what's live *is* the story — lead with it.
4. 1 paragraph on `weakest_category`: what the gap means in practice, one specific action. **If `weakest_category` is `'none'`**, don't invent a weakness — write about what `fit` means for their next step instead.
5. If `blockers` is set: 1-2 sentences on their biggest blocker, concrete counter-move
6. If `roi` is set: 1 sentence — "Based on your inputs, the opportunity is around €[roi]."
7. Closing: reference the roadmap headline, then: "If you want to talk through where to start, book a slot: [MEET_URL]"
8. Sign off: `Columbia Road`

`next_moves` holds the exact recommendations the participant just read on screen. Echoing one of them keeps the email consistent with their results page — don't contradict it.

---

### Tone — apply the humanise-copy rules

These emails must pass the same anti-pattern check as the quiz copy itself. Before writing each email, run through this checklist mentally:

**Banned constructions:**
- `"The X is Y"` / `"The gap to close is…"` / `"The priority is…"` — cut to the directive
- `"compounding"` as a standalone adjective — say what the actual outcome is
- `"agentic commercial engine"`, `"agentic workflows"` unless the distinction matters — use plain language
- `"proprietary data loops"` — say "data only you have" or be concrete about what it means
- `"agent ops muscle"` / `"your agent ops"` — say "running agents in production"
- `"experimenters vs operators"` — too cute, delete or replace with a specific outcome
- Em-dash overload — if a sentence has more than one em-dash, break it into two sentences
- `"dive into"`, `"leverage"`, `"actionable insights"`, `"unlock potential"` — never

**Writing rules:**
- Active voice. Shorter sentences. Fewer abstract nouns.
- Say what to do, not what "the priority" is.
- Specific over abstract: a named tool, a named process, a number — not "significant improvement"
- The audience knows AI. Skip hype, skip definitions, don't over-explain.
- Each email must be meaningfully different. Stage 1 with Ownership as the weakest foundation should read completely differently from Stage 2 with Your data as the gap.
- Use the participant's own vocabulary from the quiz — "Connected tools", "Your data", "Ownership", "Your team" — not invented category names.

**Target voice:** A sharp Columbia Road consultant writing a quick note after a breakfast event — not a content generator producing balanced feedback.

---

### 4. Write emails back to the Sheet

Construct this payload (one entry per participant):

```json
{
  "action": "write_emails",
  "emails": [
    { "rowIndex": 2, "subject": "...", "body": "..." },
    { "rowIndex": 3, "subject": "...", "body": "..." }
  ]
}
```

Post it using Python (curl mishandles the GAS redirect):

```bash
python3 - <<'EOF'
import urllib.request, json
url = "<GAS_URL>"
payload = json.dumps({"action": "write_emails", "emails": [...]}).encode()
req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req) as r:
    print(r.read().decode())
EOF
```

### 5. Report

Tell the user:
- How many email drafts were written
- That they should review the "Email body" column in the Sheet before sending
- That sending is done by running `sendFollowUpEmails()` in the GAS editor once they're happy with the drafts
