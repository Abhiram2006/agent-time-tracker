#!/usr/bin/env python3
"""
Build daily Mobilization x Efficiency + fitness data from the work calendar.

Reads TSV (start<TAB>end<TAB>summary) on stdin — produced by fetch_evidence.swift —
and writes data.json / data.js next to the dashboard (index.html).

Everything behavioral lives in the calendar; this script just parses + aggregates:
  - WORK events carry leading stars:   "★★★★ deep work"   -> work_hrs + weighted_hrs
  - GYM/cardio carry trailing stars:   "gym ★★★★★"        -> gym_minutes + gym_stars
        (gym is NOT cognitive work — excluded from Mob/Eff, stays in "awake")
  - MEALS carry a bracketed macro tag: "lunch [675kcal 41P]" -> calories + protein
  - sleep / nap  -> sleep_hrs (counts out of awake)
  - everything else (rest/social/life/etc, no stars) -> awake-non-work, label-only

Metrics per day:
  Mobilization = work_hrs / awake_hrs      (how much of your waking day was work)
  Efficiency   = weighted_hrs / work_hrs   (average star intensity of that work)
  weighted_hrs = sum over work blocks of  hours * (stars / 5)
"""
import json
import sys
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# ============================ CONFIG ============================
# Canonical timezone: ALL metrics are bucketed in this fixed reference zone so
# hour-of-day patterns stay comparable even if you travel. You log in your
# laptop's local clock; the build converts local -> canonical. Set it to your
# home zone (IANA name), e.g. "America/New_York", "Europe/London", "Asia/Kolkata".
CANONICAL_TZ = ZoneInfo("America/New_York")

# First day to include (ISO). Set to when you started tracking.
START_DATE_ISO = "2026-01-01"

# Daily fitness targets (gauges fill toward these).
FITNESS_TARGETS = {'calories': 2500, 'protein_g': 180, 'gym_minutes': 30, 'sleep_hours': 8}

# Optional per-day target overrides, e.g. a planned deficit day:
#   '2026-01-14': {'calories': 1600, 'protein_g': 120},
TARGET_OVERRIDES = {}

# Per-day weighted-hours target shown in the rolling weekly summary header.
WEIGHTED_TARGET = 6.0
# ===============================================================

GYM_RE   = re.compile(r'\b(gym|cardio|lift|workout)\b', re.I)
MACRO_RE = re.compile(r'\[(\d+)\s*kcal\s+(\d+)\s*P\]', re.I)

def strip_marks(s):
    return s.replace('★', '').replace('☆', '').strip()

def is_fitness(summary):
    # gym/cardio carry stars but are NOT cognitive work
    return bool(GYM_RE.search(strip_marks(summary)))

def star_count(summary):
    n = summary.count('★')
    return min(n, 5) if n > 0 else 0

def is_sleep(summary):
    s = summary.strip().lower()
    return s.startswith('nap') or s.startswith('sleep')

def to_canonical(local_naive):
    """System-local naive datetime -> naive datetime in CANONICAL_TZ."""
    aware = local_naive.astimezone()
    return aware.astimezone(CANONICAL_TZ).replace(tzinfo=None)

def split_by_day(start, end):
    cur = start
    while cur < end:
        next_midnight = datetime.combine(cur.date() + timedelta(days=1), datetime.min.time())
        chunk_end = min(end, next_midnight)
        yield cur.date(), (chunk_end - cur).total_seconds() / 3600.0
        cur = chunk_end

raw = sys.stdin.read()
out_dir = sys.argv[1] if len(sys.argv) > 1 else '.'

events = []
for line in raw.split('\n'):
    line = line.rstrip('\r')
    if not line.strip():
        continue
    parts = line.split('\t')
    if len(parts) < 3:
        continue
    start_str, end_str, summary = parts[0], parts[1], '\t'.join(parts[2:])
    try:
        start_local = datetime.strptime(start_str, '%Y-%m-%d %H:%M:%S')
        end_local = datetime.strptime(end_str, '%Y-%m-%d %H:%M:%S')
    except ValueError:
        continue
    if end_local <= start_local:
        continue
    events.append((to_canonical(start_local), to_canonical(end_local), summary))

START_DATE = datetime.strptime(START_DATE_ISO, '%Y-%m-%d').date()
NOW = datetime.now(timezone.utc).astimezone(CANONICAL_TZ).replace(tzinfo=None)
TODAY = NOW.date()

days_data = {}
d = START_DATE
while d <= TODAY:
    days_data[d] = {
        'date': d.isoformat(),
        'work_hrs': 0.0, 'weighted_hrs': 0.0, 'sleep_hrs': 0.0,
        'gym_minutes': 0.0, 'gym_stars': 0, 'calories': 0, 'protein_g': 0,
        '_gym_star_min': 0.0, '_gym_starred_min': 0.0,
    }
    d += timedelta(days=1)

for start, end, summary in events:
    day_key = start.date()

    # --- Gym / cardio (stars = session quality; NOT cognitive work) ---
    if is_fitness(summary):
        if day_key in days_data:
            mins = (end - start).total_seconds() / 60.0
            days_data[day_key]['gym_minutes'] += mins
            st = star_count(summary)
            if st > 0:  # duration-weight across split sessions (e.g. 5★ lift + 3★ cardio)
                days_data[day_key]['_gym_star_min'] += st * mins
                days_data[day_key]['_gym_starred_min'] += mins
        continue

    # --- Macros on meal events: "lunch [675kcal 41P]" ---
    m = MACRO_RE.search(summary)
    if m and day_key in days_data:
        days_data[day_key]['calories'] += int(m.group(1))
        days_data[day_key]['protein_g'] += int(m.group(2))
        # meal is awake-non-work; falls through (no stars -> not counted as work)

    # --- Sleep / work ---
    if is_sleep(summary):
        for date, hrs in split_by_day(start, end):
            if date in days_data:
                days_data[date]['sleep_hrs'] += hrs
    elif '★' in summary:
        score = min(summary.count('★'), 5)
        for date, hrs in split_by_day(start, end):
            if date in days_data:
                days_data[date]['work_hrs'] += hrs
                days_data[date]['weighted_hrs'] += hrs * (score / 5.0)

result_days = []
for date in sorted(days_data.keys(), reverse=True):
    d = days_data[date]
    is_today = (date == TODAY)
    if is_today:
        elapsed = (NOW - datetime.combine(date, datetime.min.time())).total_seconds() / 3600.0
        awake = max(0.0, elapsed - d['sleep_hrs'])
    else:
        awake = max(0.0, 24.0 - d['sleep_hrs'])

    d['awake_hrs'] = round(awake, 2)
    d['work_hrs'] = round(d['work_hrs'], 2)
    d['weighted_hrs'] = round(d['weighted_hrs'], 2)
    d['sleep_hrs'] = round(d['sleep_hrs'], 2)
    d['gym_minutes'] = round(d['gym_minutes'])
    if d['_gym_starred_min'] > 0:
        d['gym_stars'] = round(d['_gym_star_min'] / d['_gym_starred_min'])
    del d['_gym_star_min']; del d['_gym_starred_min']
    d['mobilization'] = round(d['work_hrs'] / awake, 4) if awake > 0 else None
    d['efficiency'] = round(d['weighted_hrs'] / d['work_hrs'], 4) if d['work_hrs'] > 0 else None
    ov = TARGET_OVERRIDES.get(d['date'], {})
    d['cal_target'] = ov.get('calories', FITNESS_TARGETS['calories'])
    d['protein_target'] = ov.get('protein_g', FITNESS_TARGETS['protein_g'])
    d['partial'] = is_today
    result_days.append(d)

# ---- rolling weekly summary: avg weighted hours PER DAY over the last 7 ----
by_date = sorted(result_days, key=lambda r: r['date'])
last7 = by_date[-7:]
complete7 = [d for d in last7 if not d['partial']]   # exclude partial today from diet avgs
diet_src = complete7 if complete7 else last7

days_since_gym = None
for i, d in enumerate(reversed(by_date)):
    if d['gym_minutes'] > 0:
        days_since_gym = i
        break

summary = {
    'window_days': len(last7),
    'start': last7[0]['date'] if last7 else None,
    'end': last7[-1]['date'] if last7 else None,
    'weighted_7d': round(sum(d['weighted_hrs'] for d in last7), 1),
    'weighted_target': WEIGHTED_TARGET,
    'raw_7d': round(sum(d['work_hrs'] for d in last7), 1),
    'sleep_avg': round(sum(d['sleep_hrs'] for d in last7) / len(last7), 1) if last7 else None,
    'sleep_target': FITNESS_TARGETS['sleep_hours'],
    'protein_avg': round(sum(d['protein_g'] for d in diet_src) / len(diet_src)) if diet_src else None,
    'protein_target': FITNESS_TARGETS['protein_g'],
    'cal_avg': round(sum(d['calories'] for d in diet_src) / len(diet_src)) if diet_src else None,
    'cal_target': FITNESS_TARGETS['calories'],
    'days_since_gym': days_since_gym,
}

output = {
    'last_updated': NOW.strftime('%Y-%m-%d %H:%M'),
    'canonical_tz': str(CANONICAL_TZ),
    'fitness_targets': FITNESS_TARGETS,
    'summary': summary,
    'days': result_days,
}

with open(f'{out_dir}/data.json', 'w') as f:
    json.dump(output, f, indent=2)
with open(f'{out_dir}/data.js', 'w') as f:
    f.write('window.DASHBOARD_DATA = ')
    json.dump(output, f, indent=2)
    f.write(';\n')

print(f'Wrote {len(result_days)} days, {len(events)} events parsed.', file=sys.stderr)
