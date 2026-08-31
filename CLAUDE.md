# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a single-file, self-contained HTML/JS quiz — an **AI Maturity Assessment** built for Columbia Road's *AI in B2B Sales and Marketing* event (Stockholm, September 1 2026). There is no build system, no package manager, no server.

To run: open `index.html` directly in a browser.

## Architecture

Everything lives in `index.html`:

- **CSS** — inline `<style>` block using CSS custom properties. Mobile-first layout capped at 480px, `--navy`/`--forest`/`--burgundy`/`--yellow`/`--cream` colour palette.
- **HTML** — a single `<div class="app">` shell. All content is injected by JS into `<div id="box">`.
- **JS** — one `<script>` block. No frameworks, no imports.

### JS state model

| Variable | Purpose |
|---|---|
| `A` | Global answers object. Keys are question IDs (e.g. `'A1'`, `'P2'`); multi-select stores an array; open text uses `'<id>_open'`; follow-up text uses `'<id>_d'`; rating grid rows use `'<id>_r<rowIndex>'`. |
| `S` | Array of section objects built by `build()`. Rebuilt whenever role changes (question `P1`). |
| `cur` | Current section index (`-1` = gate screen). |
| `GATE_NAME`, `GATE_EMAIL` | Captured from the email gate before the quiz starts. |
| `QUIZ_RESULT` | Flattened snapshot sent to the webhook on results render. |

### Quiz flow

```
Gate (name + email) → S[0] Profile → S[1] Business Snapshot (role-adaptive) → S[2] AI Maturity (scored) → S[3] Opportunities → Results
```

`build()` assembles `S` based on `role()` (derived from `A['P1']`). Navigation via `go(±1)`. The results screen is triggered when `go(1)` is called past the last section.

### Question types

| `m` value | Rendered as |
|---|---|
| `'single'` | Radio list (`.opt` + `.dot`) |
| `'multi'` | Checkbox list with `mx` cap |
| `'rating'` | Grid: rows × columns (`.rg`) |
| `'scale'` | Horizontal 4-segment bar (`.scale-seg`) with optional N/A row |
| `'tooltip'` | Vertical scale list with expandable `i` info bubbles (`.tip-opt`) |
| `'open'` | Freetext `<textarea>` |

Scored questions (Part 3, `scored:true`) drive the maturity calculation in `results()`.

### Scoring

**Two independent axes.** They can disagree, and the disagreement is the point.

**1. Readiness (`tot`, 0–100)** — how solid the foundations are. `results()` walks `DIMS`, four weighted dimensions summing to 100:

| Dimension | Weight | Question IDs |
|---|---|---|
| Connected tools | 25 | A3, A4 |
| Your data | 30 | B1, B2 |
| Ownership | 30 | C1, C2 |
| Your team | 15 | D1 |

Each answer normalises to `raw/(n-1)` of its own scale, scaled by that question's share of the dimension weight. An unanswered or "don't know" answer earns `NA_CREDIT = 0.25` rather than 0 — so **real scores compress into roughly 20–55**, not 0–100. Anything bucketing this on a 0–100 axis will look broken.

`READY` maps the score to a band: ≤22 `Not there yet`, ≤32 `Early days`, ≤41 `Getting there`, ≤50 `Ready for more`, else `Solid ground`.

**2. Stage (`stageKey`, 0–3)** — what's actually running. Derived **only** from A1/A2, independent of the score. A1/A2 carry `scored:true` but are in no `DIMS.ids` array, so they contribute nothing to `tot`.

`FIT` compares the two: `ahead` (foundations better than what's live), `matched`, or `stretched` (running ahead of foundations).

### ROI model

Built inside `results()` from sales/marketing inputs (deal size, close rate, admin time, lead volume). Conservative assumptions: +15% relative close-rate lift, 25% admin-hour recovery, +20% lead-to-conversation lift. Missing inputs are silently skipped.

### Integrations

Two constants at the bottom of the `<script>` block:

```js
const APPS_SCRIPT_URL = 'https://script.google.com/macros/s/.../exec';
const MEET_URL = '...';
```

The webhook fires automatically on results render via `fetch(POST)` with the full `QUIZ_RESULT` payload plus `name`, `email`, `submitted_at`. It uses **`mode:'no-cors'`**, so the response is opaque — **the quiz cannot detect a server-side failure.** Debug via the GAS editor's Executions log, or the `_raw` / `_errors` sheets the webhook writes.

### ⚠️ Cross-file contract

`QUIZ_RESULT` (index.html:968) is the wire format for two other files. **A scoring change is not done until all three agree** — this exact desync silently blanked the Score and category columns for every submission once already:

| index.html | must match |
|---|---|
| `QUIZ_RESULT` keys | `COLUMNS` / `HEADERS` in `quiz-webhook.gs` (one column per key, HEADERS[i] labels COLUMNS[i], then 4 manual columns) |
| `STAGES` `lv` labels | `STAGE_ORDER` in `quiz-webhook.gs` |
| `READY` `lv` labels | `BAND_ORDER` in `quiz-webhook.gs` |
| `DIMS` keys | `DIM_ORDER` in `quiz-webhook.gs` |
| label arrays `_dealLbls`…`_blkLbls` (index.html:947) | the question `opts` they duplicate — parallel copies, not references |

`aggregated-results.html` deliberately holds **no** stage or band label strings; it colours distributions by position from the zero-filled, canonically-ordered objects `doGet` returns. Keep it that way.

After editing `quiz-webhook.gs`: run `resetSheet()` once if HEADERS changed, then `testPost_v2()` / `testDoGet()` from the GAS editor **before** deploying — editor runs use saved code, but `/exec` serves the last *deployed version*. Redeploy via **Manage deployments → Edit → New version** to keep the URL (it's hardcoded in `index.html`, `aggregated-results.html`, and `AppsScript deployment ID.md`).

## Context file

`cr-event-context.md` — event brief used as grounding context for AI-assisted content changes (audience, content pillars, tone). Not loaded by the quiz itself.
