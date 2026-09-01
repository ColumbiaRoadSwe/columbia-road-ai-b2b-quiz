#!/usr/bin/env python3
"""
Generates one self-contained result page per quiz submission, for the follow-up
email. Reads the deployed Apps Script `action=rows` endpoint, rebuilds each
participant's results screen as a static HTML file, and writes a manifest.

    python3 generate-result-pages.py            # fetch live, write result-pages/
    python3 generate-result-pages.py rows.json  # use a saved payload instead

⚠️ Mirrors constants from index.html (STAGES, READY, FIT, DIMS, QCFG,
BOTTLENECK_COPY, DIM_ADVICE, blocker copy, nextSteps). These are parallel
copies, not references — the same cross-file contract CLAUDE.md describes for
quiz-webhook.gs. Change the copy in index.html, change it here.
"""

import csv
import datetime
import json
import math
import pathlib
import re
import sys
import urllib.request

ENDPOINT = ('https://script.google.com/macros/s/AKfycby-Zy07mCjO1Cztm9qpGx61To'
            'DO1JokwzLPhJ3VcN3yS0IZ_wzt0MDoKNzwD_czHlXH/exec?action=rows')
MEET_URL = ('https://www.columbiaroad.com/meetings/simon-fransson/'
            '26-ai-agents-at-scale-event')
OUT_DIR = pathlib.Path(__file__).parent / 'result-pages'

# ── Constants mirrored from index.html ───────────────────────────────────────

DIMS = {
    'Connected tools': {'w': 25, 'c': '#002A3A', 'ids': ['A3', 'A4']},
    'Your data':       {'w': 30, 'c': '#034638', 'ids': ['B1', 'B2']},
    'Ownership':       {'w': 30, 'c': '#651D32', 'ids': ['C1', 'C2']},
    'Your team':       {'w': 15, 'c': '#988873', 'ids': ['D1']},
}
DIM_OF_ID = {i: d for d, v in DIMS.items() for i in v['ids']}
QCFG_N = {'A3': 4, 'A4': 4, 'B1': 4, 'B2': 4, 'C1': 5, 'C2': 4, 'D1': 4}
NA_CREDIT = 0.25

STAGES = [
    {'lv': 'Stage 0: Nothing running yet', 'sub': 'The starting line',
     'bg': '#E5E1DC', 'fg': '#161616',
     'desc': 'No AI is doing work for you yet. Plenty of companies are in the same position, and it means you get to skip the mistakes everyone else made first. Start with one job your team dislikes, not with a tool.'},
    {'lv': 'Stage 1: Testing and pilots', 'sub': 'Where most companies are',
     'bg': '#F7CED7', 'fg': '#161616',
     'desc': 'You have tried things. Nothing has made it into daily use yet. The gap between a pilot and something people rely on is mostly a decision: pick one, set a date, ship it.'},
    {'lv': 'Stage 2: First agents live', 'sub': 'Ahead of most',
     'bg': '#B9D9EB', 'fg': '#161616',
     'desc': 'Something is running and people use it. That already puts you ahead of most B2B companies. Next comes joining up what you have, because two agents that share what they know beat four that do not.'},
    {'lv': 'Stage 3: Several agents live', 'sub': 'At the front',
     'bg': '#034638', 'fg': '#FFFFFF',
     'desc': 'You have more than one thing running across sales and marketing. Very few companies are here. From now on your advantage comes from your own data rather than your tools, because everyone can buy the same tools.'},
]

READY = [
    {'max': 22,  'lv': 'Not there yet'},
    {'max': 32,  'lv': 'Early days'},
    {'max': 41,  'lv': 'Getting there'},
    {'max': 50,  'lv': 'Ready for more'},
    {'max': 100, 'lv': 'Solid ground'},
]

FIT = {
    'ahead': {'t': 'You could be doing more than you are',
              'd': 'Your data, ownership and people are in better shape than what you actually have running. That is an unusual place to be, and an easy one to fix. You do not need to prepare more. Pick something and put it live.'},
    'matched': {'t': 'Your foundations match what you are running',
                'd': 'Nothing is badly out of step. Growing is a question of pace rather than repair. Keep what you have moving and tidy up the weakest area below as you go.'},
    'stretched': {'t': 'You are running ahead of your foundations',
                  'd': 'More is live than your data and ownership can comfortably carry. It works until it does not: the output gets unreliable, nobody can say why, and people stop trusting it. Steady the weakest area below before you add anything else.'},
}

BOTTLENECK_COPY = {
    'Connected tools': 'Your data and your people are further along than your plumbing. Information still has to be carried by hand between systems, which caps how much you can run at once. This is usually the cheapest of the four to fix.',
    'Your data': 'Everything else waits on this. AI can only work with what it can read, and right now that is incomplete or spread out. Buying more tools will not move it.',
    'Ownership': 'You have the pieces but nobody is deciding. Without a clear owner, AI stays a set of side projects that never get a deadline or a budget line.',
    'Your team': 'Your setup is ahead of your people. Tools nobody opens produce nothing, and that is a habit problem rather than a technology one.',
}

DIM_ADVICE = {
    'Connected tools': [
        'Your tools do not talk to each other, so somebody has to move information by hand. Fine for a trial, impossible at any real volume. Pick the two systems that matter most and connect them properly.',
        'The main connections are there. What is missing is one shared source they all read from, so a fix in one place does not have to be repeated in four.',
        'Your tools share what they know. That is the setup that lets you add the next one in days rather than months.'],
    'Your data': [
        'This is what breaks AI fastest. If records are duplicated, half empty or spread across systems, anything built on top will be confidently wrong. A week of tidying saves months of chasing bad output.',
        'Your data sits in one place but the detail is uneven. Fill the gaps your first use case actually depends on rather than trying to clean all of it.',
        'Your data is in good shape. That opens up the harder jobs: full account context, live pipeline signals, scoring people will actually trust.'],
    'Ownership': [
        'Nobody owns this yet. Without a name against it, people quietly use whatever tools they like, spend adds up that nobody tracks, and no one can say what worked. One person and one page of rules is enough to start.',
        'There is ownership but no way to choose between ideas. Agree what you are measuring before you build, so projects compete on results rather than on who asks loudest.',
        'Ownership is clear and decisions have a home. Now show the numbers. Proving one case makes the next five easier to fund.'],
    'Your team': [
        'Interest is low, and no tool survives that. Get four or five people using one thing on a real task every day. The habit matters more than which tool you picked.',
        'People know about it and use it now and then. Training days rarely change how anyone works. Daily use on real work does.',
        'Your team wants to go further. Give them a clear problem and a way to tell whether they solved it, rather than open permission to experiment.'],
}

BLOCKER_OPTS = [
    'Our data is a mess', "We don't have the skills", "We can't prove the ROI",
    'Legal or compliance concerns', 'Too many options, hard to choose',
    'No leadership buy-in or budget', "Our tools don't support it",
]
BLOCKER_MSGS = [
    'Messy data is the most common blocker we see and the most fixable. You do not have to sort all of it first. Clean the part your first use case touches and leave the rest.',
    'Skill gaps close faster than most people expect. Do not wait until you feel ready. One project with a clear goal teaches more than any training course.',
    'It is hard to prove a return before you have shipped anything. Pick something where you already measure the before, and agree the number you are chasing up front.',
    'Compliance worries are the most common brake across European B2B, so you are in good company. Clear rules speed things up. It is the not-knowing that stalls projects.',
    'Too many options is usually a strategy problem rather than a technology one. Look at where your sales process hurts most and start there.',
    'Buy-in follows results, not slides. Find something you can prove in six to eight weeks and let the number do the arguing.',
    'Tool limits are usually data limits in disguise. The question is rarely whether your stack can run agents. It is what you can give them to work with.',
]

NEXT_STEPS = [
    {'headline': 'Start with one job, not a strategy', 'steps': [
        ('1', 'Pick the job people complain about', 'Ask your team what they would hand over tomorrow if they could. Start there. Do not run a tool comparison first.'),
        ('2', 'Get five people using one thing', 'One tool, five people, every day. Five regular users teach you more than fifty licences nobody opens.'),
        ('3', 'Put a name against it', 'Not a working group. One person who decides what gets tried, what gets kept and what it costs. Without that, this dies in the first busy quarter.'),
        ('4', 'Write down how the work is done', 'How your best rep actually works is the raw material any AI needs. Writing it down is the most useful thing you can do before spending anything.')]},
    {'headline': 'Pick one pilot and give it a date', 'steps': [
        ('1', 'Choose one and drop the rest', 'Three experiments that never ship are worth less than one thing people use on Monday. Pick whichever is closest to done.'),
        ('2', 'Agree the number first', 'Decide what you are trying to move before you build. Afterwards, everyone measures whatever makes the result look best.'),
        ('3', 'Give it real users, not reviewers', 'A pilot nobody depends on tells you nothing. Put it in front of people whose week gets worse if it stops working.'),
        ('4', 'Fix only what blocks go-live', 'Data and process problems are endless. Sort out the ones standing between you and launch, and leave the rest for later.')]},
    {'headline': 'Join up what you already have', 'steps': [
        ('1', 'Find where the handovers break', 'Look at every point where your agent passes work to a person or another system. That is where the time you saved goes missing.'),
        ('2', 'Start keeping what you learn', 'Record what the agent did and whether it worked. Almost nobody does this, and it is what makes the next one better.'),
        ('3', 'Build the second one on the first', 'Do not start from scratch. Reuse the data and instructions the first one runs on, or you will end up maintaining two of everything.'),
        ('4', 'Show the numbers while they are fresh', 'You have a working example. Use it now. Budget follows proof faster than it follows plans.')]},
    {'headline': 'Your advantage is your own data now', 'steps': [
        ('1', 'Build the data nobody else has', 'Anyone can buy the same tools. What they cannot buy is your customer history, your deal context and what your market told you last quarter. Capture it on purpose.'),
        ('2', 'Close the loop', 'Track what each agent did and whether the outcome was any good. Without that, they repeat the same mistakes forever.'),
        ('3', 'Decide what keeps them in order', 'Once several are running, something has to sequence them and settle conflicts. Sketch it before you need it. Retrofitting is painful.'),
        ('4', 'Look outside your own walls', 'Agents that work with your partners and customers reach further than anything you automate internally. That is the bigger prize.')]},
]

# ── Data repair ──────────────────────────────────────────────────────────────

# Some numeric cells were date-formatted in the sheet, so the API returns them
# as ISO timestamps near 1900. Google Sheets counts days from 1899-12-30, so
# converting back recovers the original integer exactly.
SHEETS_EPOCH = datetime.datetime(1899, 12, 30, tzinfo=datetime.timezone.utc)


def denumber(v):
    """Return v as an int, undoing date-formatting damage if present."""
    if isinstance(v, str) and 'T' in v and v[:2] == '19':
        dt = datetime.datetime.fromisoformat(v.replace('Z', '+00:00'))
        return round((dt - SHEETS_EPOCH).total_seconds() / 86400)
    if v in ('', None):
        return None
    return int(round(float(v)))


# ── Derivation ───────────────────────────────────────────────────────────────

def band_index(label):
    for i, b in enumerate(READY):
        if b['lv'] == label:
            return i
    return 0


def stage_index(label):
    for i, s in enumerate(STAGES):
        if s['lv'] == label:
            return i
    return 0


def fmt_eur(n):
    if n >= 1_000_000:
        return '€' + str(round(n / 100000) / 10) + 'M'
    if n >= 1000:
        return '€' + str(round(n / 1000)) + 'K'
    return '€' + str(int(n))


def parse_moves(raw):
    """'B1: text | C1: text' -> [{id, text, dim, gain, unknown}]"""
    out = []
    for chunk in (raw or '').split(' | '):
        chunk = chunk.strip()
        if not chunk or ': ' not in chunk:
            continue
        qid, text = chunk.split(': ', 1)
        dim = DIM_OF_ID.get(qid)
        if not dim:
            continue
        per = DIMS[dim]['w'] / len(DIMS[dim]['ids'])
        unknown = text.startswith('Nobody is sure about')
        gain = per * (0.5 - NA_CREDIT) if unknown else per * (1 / (QCFG_N[qid] - 1))
        out.append({'id': qid, 'text': text, 'dim': dim,
                    'gain': gain, 'unknown': unknown})
    return out


def derive(row):
    """Sheet row -> everything the template needs."""
    d = row['dims']
    pct = {
        'Connected tools': denumber(d['connected_tools']) or 0,
        'Your data':       denumber(d['data']) or 0,
        'Ownership':       denumber(d['ownership']) or 0,
        'Your team':       denumber(d['team']) or 0,
    }
    score = denumber(row['readiness_score']) or 0
    band = str(row['readiness_band'])
    bkey = band_index(band)
    skey = stage_index(str(row['stage']))

    # Weakest first; ties break toward the heavier dimension, as in index.html.
    ranked = sorted(pct, key=lambda k: (pct[k], -DIMS[k]['w']))
    weakest, strongest = ranked[0], ranked[-1]
    spread = pct[strongest] - pct[weakest]
    balanced = spread < 15

    fit = str(row['fit']) if str(row['fit']) in FIT else 'matched'
    need = denumber(row['points_to_next_band']) or 0
    moves = parse_moves(row.get('next_moves'))

    plan, acc = [], 0.0
    for m in moves:
        if acc >= need or len(plan) >= 3:
            break
        plan.append(m)
        acc += m['gain']
    if not plan:
        plan = moves[:3]

    blockers = []
    for label in str(row.get('blockers') or '').split(';'):
        label = label.strip()
        if label in BLOCKER_OPTS:
            i = BLOCKER_OPTS.index(label)
            blockers.append((label, BLOCKER_MSGS[i]))

    roi = row.get('roi')
    roi = float(roi) if isinstance(roi, (int, float)) and roi else None

    return {
        'name': str(row.get('name') or '').strip(),
        'email': str(row.get('email') or '').strip(),
        'role': str(row.get('role') or ''),
        'team_size': str(row.get('team_size') or ''),
        'score': score, 'band': band, 'bkey': bkey,
        'stage': STAGES[skey], 'skey': skey,
        'fit': FIT[fit], 'fit_key': fit,
        'pct': pct, 'weakest': weakest, 'strongest': strongest,
        'spread': spread, 'balanced': balanced,
        'need': need, 'plan': plan,
        'next_band': READY[bkey + 1]['lv'] if bkey < len(READY) - 1 else None,
        'crosses': acc >= need and need > 0,
        'blockers': blockers, 'roi': roi,
        'roadmap': NEXT_STEPS[skey],
    }


# ── Rendering ────────────────────────────────────────────────────────────────

def esc(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;').replace('"', '&quot;'))


CSS = """
:root{--navy:#002A3A;--forest:#034638;--burgundy:#651D32;--yellow:#FDD17A;
--light-blue:#B9D9EB;--taupe:#988873;--cream:#F9F6EC;--warm:#E5E1DC;
--black:#161616;--grey-b:#353535;--grey-c:#C0C0C0;--grey-d:#E5E5E5;--white:#fff;
--display:'Playfair Display',Georgia,'Times New Roman',serif;
--body:'Work Sans',-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--cream);color:var(--black);font-family:var(--body);
font-size:15px;line-height:1.5;-webkit-font-smoothing:antialiased}
.app{max-width:600px;margin:0 auto;background:var(--cream)}
.res-hero{background:var(--navy);color:var(--white);padding:36px 20px;text-align:center}
.res-hero .tag{font-size:11px;font-weight:500;text-transform:uppercase;
letter-spacing:.08em;color:var(--yellow);margin-bottom:8px}
.res-hero h2{font-family:var(--display);font-size:1.75rem;font-weight:400;margin-bottom:4px}
.res-hero .who{font-size:13px;opacity:.7;margin-top:6px}
.ring-wrap{display:flex;justify-content:center;margin:24px 0 16px}
.ring{width:160px;height:160px;position:relative}
.ring svg{transform:rotate(-90deg)}
.ring-txt{position:absolute;inset:0;display:flex;flex-direction:column;
align-items:center;justify-content:center}
.ring-num{font-family:var(--display);font-size:2.5rem;color:var(--white)}
.ring-max{font-size:12px;color:var(--light-blue)}
.badge{display:inline-block;font-size:12px;font-weight:600;letter-spacing:.08em;
text-transform:uppercase;padding:6px 20px;border-radius:9999px;margin-bottom:12px}
.stage-sub{font-size:12px;opacity:.7;margin-bottom:10px;letter-spacing:.04em;
text-transform:uppercase;font-weight:500}
.res-desc{font-size:14px;max-width:400px;margin:0 auto;opacity:.85;line-height:1.6}
.cta{display:flex;align-items:center;justify-content:center;gap:8px;
width:calc(100% - 40px);margin:20px 20px 0;background:var(--burgundy);
color:var(--white);font-size:14px;font-weight:600;padding:14px;border-radius:8px;
text-decoration:none}
.bd-grid{padding:0 20px 28px}
.panel{background:var(--white);border-radius:8px;overflow:hidden;margin-top:14px;
box-shadow:0 1px 3px rgba(0,0,0,.08)}
.panel-hdr{padding:14px 16px;background:var(--white);border-bottom:1px solid var(--grey-d);
font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--navy)}
.two-up{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px}
.two-up>div{flex:1;min-width:140px;padding:10px 12px;background:var(--cream)}
.two-up .k{font-size:11px;text-transform:uppercase;letter-spacing:.06em;
color:var(--taupe);margin-bottom:3px}
.two-up .v{font-size:13px;font-weight:600;color:var(--navy)}
.fit-t{font-family:var(--display);font-size:1.2rem;color:var(--navy);
line-height:1.25;margin-bottom:8px}
.fit-d{font-size:13px;color:var(--grey-b);line-height:1.55;margin-bottom:16px}
.callout{padding:12px 14px;background:var(--cream);font-size:13px;
color:var(--grey-b);line-height:1.5}
.callout.warn{border-left:3px solid var(--burgundy)}
.callout.ok{border-left:3px solid var(--forest)}
.callout .ct{font-size:12px;font-weight:600;text-transform:uppercase;
letter-spacing:.06em;color:var(--burgundy);margin-bottom:4px}
.step{display:flex;gap:12px;margin-bottom:14px}
.step .n{min-width:26px;height:26px;border-radius:9999px;background:var(--navy);
color:var(--white);display:flex;align-items:center;justify-content:center;
font-size:10px;font-weight:700;flex-shrink:0;margin-top:1px}
.step .n.na{background:var(--taupe)}
.step .n.fo{background:var(--forest)}
.step .st{font-size:13px;font-weight:600;color:var(--navy);margin-bottom:3px}
.step .sb{font-size:13px;color:var(--grey-b);line-height:1.5}
.step .meta{font-size:11px;color:var(--taupe);margin-top:2px}
.roi-total{padding:14px 16px;display:flex;justify-content:space-between;
align-items:center;background:var(--cream)}
.roi-total .k{font-size:12px;font-weight:600;text-transform:uppercase;
letter-spacing:.06em;color:var(--taupe)}
.roi-total .v{font-family:var(--display);font-size:1.6rem;color:var(--navy)}
.note{font-size:11px;color:var(--grey-c);font-style:italic;padding:10px 16px 14px}
.blk{padding:12px 16px;border-bottom:1px solid var(--grey-d)}
.blk:last-child{border-bottom:none}
.blk .bt{font-size:13px;font-weight:600;color:var(--burgundy);margin-bottom:3px}
.blk .bb{font-size:13px;color:var(--grey-b);line-height:1.5}
.dim{padding:14px 16px;border-bottom:1px solid var(--grey-d)}
.dim:last-child{border-bottom:none}
.dim-row{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.dim-name{font-size:12px;font-weight:600;text-transform:uppercase;
letter-spacing:.06em;color:var(--taupe)}
.dim-sc{display:flex;align-items:baseline;gap:3px}
.dim-sc b{font-family:var(--display);font-size:1.1rem;font-weight:400;color:var(--black)}
.dim-sc s{font-size:11px;color:var(--taupe);text-decoration:none}
.track{height:5px;background:var(--grey-d);border-radius:9999px;
overflow:hidden;margin-bottom:8px}
.track>div{height:100%;border-radius:9999px}
.dim-adv{font-size:12px;color:var(--grey-b);line-height:1.5}
.pad{padding:16px}
.foot{padding:20px;text-align:center;font-size:11px;color:var(--taupe);line-height:1.6}
@media print{
  body{background:#fff}
  .app{max-width:100%}
  .cta{display:none}
  .res-hero{-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .panel{box-shadow:none;border:1px solid #e5e5e5;break-inside:avoid}
  @page{margin:12mm;size:A4}
}
"""


def panel(title, inner):
    return ('<div class="panel"><div class="panel-hdr">' + esc(title)
            + '</div>' + inner + '</div>')


def render(p):
    circ = 2 * math.pi * 66
    off = circ - (max(0, min(100, p['score'])) / 100) * circ
    first = p['name'].split(' ')[0] if p['name'] else 'there'
    st = p['stage']

    h = ['<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">',
         '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
         '<title>AI Maturity Results — ' + esc(p['name']) + '</title>',
         '<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;500'
         '&family=Work+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">',
         '<style>' + CSS + '</style></head><body><div class="app">']

    # Hero
    h.append(
        '<div class="res-hero"><div class="tag">Your Results</div>'
        '<h2>AI Maturity Score</h2>'
        '<div class="who">' + esc(first)
        + (' &middot; ' + esc(p['role']) if p['role'] else '')
        + (' &middot; team of ' + esc(p['team_size']) if p['team_size'] else '')
        + '</div>'
        '<div class="ring-wrap"><div class="ring"><svg width="160" height="160" viewBox="0 0 160 160">'
        '<circle cx="80" cy="80" r="66" fill="none" stroke="rgba(255,255,255,.12)" stroke-width="7"/>'
        '<circle cx="80" cy="80" r="66" fill="none" stroke="#FDD17A" stroke-width="7" '
        'stroke-dasharray="' + f'{circ:.2f}' + '" stroke-dashoffset="' + f'{off:.2f}'
        + '" stroke-linecap="round"/></svg>'
        '<div class="ring-txt"><div class="ring-num">' + str(p['score'])
        + '</div><div class="ring-max">readiness</div></div></div></div>'
        '<div class="badge" style="background:' + st['bg'] + ';color:' + st['fg'] + '">'
        + esc(st['lv']) + '</div>'
        '<div class="stage-sub">' + esc(st['sub']) + '</div>'
        '<p class="res-desc">' + esc(st['desc']) + '</p></div>'
        '<a href="' + MEET_URL + '" class="cta">Book a meeting</a>'
        '<div class="bd-grid">')

    # Where you stand
    if p['balanced']:
        callout = ('<div class="callout ok">Your four areas are within '
                   + str(p['spread']) + ' points of each other, which is not common. '
                   'Nothing is holding you back more than anything else, so this is '
                   'about pace rather than repair.</div>')
    else:
        callout = (
            '<div class="callout warn"><div class="ct">Weakest area &middot; '
            + esc(p['weakest']) + ' (' + str(p['pct'][p['weakest']]) + '%)</div>'
            '<div style="margin-bottom:8px">' + esc(BOTTLENECK_COPY[p['weakest']]) + '</div>'
            '<div><b style="color:#002A3A">Strongest is ' + esc(p['strongest'])
            + ' at ' + str(p['pct'][p['strongest']]) + '%.</b> You are held back by the '
            'weakest of the four rather than the average, so work spent there pays back '
            'more than work spent here.</div></div>')

    h.append(panel('Where you stand',
        '<div class="pad"><div class="two-up">'
        '<div><div class="k">Running today</div><div class="v">'
        + esc(re.sub(r'^Stage \d: ', '', st['lv'])) + '</div></div>'
        '<div><div class="k">Foundations</div><div class="v">' + esc(p['band']) + '</div></div>'
        '</div><div class="fit-t">' + esc(p['fit']['t']) + '</div>'
        '<div class="fit-d">' + esc(p['fit']['d']) + '</div>' + callout + '</div>'))

    # What moves you up
    if p['next_band'] and p['plan']:
        lead = ('You are <b>' + str(p['need']) + ' point'
                + ('' if p['need'] == 1 else 's') + '</b> off <b>' + esc(p['next_band'])
                + '</b>. '
                + (('This one change gets you there:' if len(p['plan']) == 1
                    else 'These changes get you there:') if p['crosses']
                   else 'The biggest things you can move right now:'))
        body = ('<div class="pad"><div style="font-size:13px;color:#353535;'
                'line-height:1.55;margin-bottom:14px">' + lead + '</div>')
        for m in p['plan']:
            body += ('<div class="step"><div class="n '
                     + ('na' if m['unknown'] else 'fo') + '">' + esc(m['id']) + '</div>'
                     '<div><div class="sb">' + esc(m['text']) + '</div>'
                     '<div class="meta">' + esc(m['dim']) + ' &middot; +'
                     + f"{m['gain']:.1f}" + '</div></div></div>')
        h.append(panel('What moves you up', body + '</div>'))

    # ROI — total only; the itemised breakdown needs inputs the sheet does not store.
    if p['roi']:
        h.append(panel('AI Impact Estimate',
            '<div class="roi-total"><div class="k">Estimated annual upside</div>'
            '<div class="v">' + fmt_eur(p['roi']) + '</div></div>'
            '<div class="note">Conservative estimate built from the deal size, close '
            'rate, admin time and lead volume you gave us, assuming gradual adoption '
            'over 12 months. Actual results depend on implementation quality, data '
            'readiness and change management.</div>'))

    # Roadmap
    rm = p['roadmap']
    body = ('<div class="pad"><div class="fit-t" style="margin-bottom:14px">'
            + esc(rm['headline']) + '</div>')
    for n, title, text in rm['steps']:
        body += ('<div class="step"><div class="n">' + n + '</div><div>'
                 '<div class="st">' + esc(title) + '</div>'
                 '<div class="sb">' + esc(text) + '</div></div></div>')
    h.append(panel('Your AI Roadmap', body + '</div>'))

    # Blockers
    if p['blockers']:
        body = ''
        for label, msg in p['blockers']:
            body += ('<div class="blk"><div class="bt">' + esc(label) + '</div>'
                     '<div class="bb">' + esc(msg) + '</div></div>')
        h.append(panel('Your Blockers', body))

    # Score breakdown
    body = ''
    for name in DIMS:
        pc = p['pct'][name]
        w = DIMS[name]['w']
        adv = DIM_ADVICE[name][0 if pc < 50 else 1 if pc < 75 else 2]
        body += ('<div class="dim"><div class="dim-row">'
                 '<div class="dim-name">' + esc(name) + '</div>'
                 '<div class="dim-sc"><b>' + str(round(pc * w / 100))
                 + '</b><s>/ ' + str(w) + '</s></div></div>'
                 '<div class="track"><div style="width:' + str(pc)
                 + '%;background:' + DIMS[name]['c'] + '"></div></div>'
                 '<div class="dim-adv">' + esc(adv) + '</div></div>')
    h.append(panel('Score breakdown', body))

    h.append('</div><div class="foot">Columbia Road &middot; AI in B2B Sales and '
             'Marketing<br>Readiness measures your foundations. Stage is what you '
             'have running today. The two can disagree.</div></div></body></html>')
    return ''.join(h)


# ── Main ─────────────────────────────────────────────────────────────────────

def slug(s):
    s = re.sub(r'[^a-z0-9]+', '-', str(s).lower()).strip('-')
    return s or 'unknown'


def main():
    if len(sys.argv) > 1:
        rows = json.load(open(sys.argv[1]))['rows']
        print(f'Loaded {len(rows)} rows from {sys.argv[1]}')
    else:
        with urllib.request.urlopen(ENDPOINT) as r:
            rows = json.load(r)['rows']
        print(f'Fetched {len(rows)} rows from the Apps Script endpoint')

    OUT_DIR.mkdir(exist_ok=True)
    people = [derive(r) for r in rows if str(r.get('email') or '').strip()]
    for r in rows:
        if not str(r.get('email') or '').strip():
            print(f"  skipped row {r.get('rowIndex')}: no email")

    # Shared first names get the company domain appended — to both, so neither
    # filename is ambiguous.
    counts = {}
    for p in people:
        counts[slug(p['name'])] = counts.get(slug(p['name']), 0) + 1

    manifest = []
    for p in people:
        base = 'ai-readiness-' + slug(p['name'])
        if counts[slug(p['name'])] > 1:
            base += '-' + slug(p['email'].split('@')[-1].rsplit('.', 1)[0])
        fn = base + '.html'

        (OUT_DIR / fn).write_text(render(p), encoding='utf-8')
        manifest.append({
            'name': p['name'], 'email': p['email'], 'file': fn,
            'readiness_score': p['score'], 'readiness_band': p['band'],
            'stage': p['stage']['lv'], 'fit': p['fit_key'],
            'weakest_area': 'none' if p['balanced'] else p['weakest'],
            'roi_estimate_eur': int(p['roi']) if p['roi'] else '',
        })
        print(f"  {fn:<44} {p['score']:>3}  {p['band']}")

    with open(OUT_DIR / 'manifest.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(manifest[0].keys()))
        w.writeheader()
        w.writerows(manifest)

    print(f'\n{len(manifest)} pages + manifest.csv written to {OUT_DIR}/')


if __name__ == '__main__':
    main()
