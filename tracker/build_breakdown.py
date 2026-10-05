#!/usr/bin/env python3
"""
Hour-of-day breakdown with honest uncertainty.

For each hour of the day, averages Mobilization (work% of awake) and Efficiency
(avg star intensity) across all tracked days, Gaussian-smoothed over the clock
(wrap-aware) with a +/-1 SE band. Hours backed by few day-observations get WIDE
bands, so you can't over-read a curve running on 2 days. No raw points.

Reads the same TSV as build_data.py on stdin; writes breakdown_data.{json,js}.
"""
import json
import sys
import re
import math
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from collections import defaultdict

# Keep this in sync with build_data.py.
CANONICAL_TZ = ZoneInfo("America/New_York")

GYM_RE = re.compile(r'\b(gym|cardio|lift|workout)\b', re.I)
def is_fitness(s): return bool(GYM_RE.search(s.replace('★', '').replace('☆', '').strip()))
def star_count(s):
    if is_fitness(s): return 0
    n = s.count('★'); return min(n, 5) if n > 0 else 0
def is_sleep(s):
    t = s.strip().lower()
    return t.startswith('nap') or t.startswith('sleep')

def to_canon(local):
    aw = local.astimezone()
    return aw.astimezone(CANONICAL_TZ).replace(tzinfo=None)

raw = sys.stdin.read()
out_dir = sys.argv[1] if len(sys.argv) > 1 else '.'

# acc[(date, hour)] -> [work_h, wstar_h, covered_h, sleep_h]
acc = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
for line in raw.split('\n'):
    p = line.rstrip('\r').split('\t')
    if len(p) < 3: continue
    try:
        s = datetime.strptime(p[0], '%Y-%m-%d %H:%M:%S'); e = datetime.strptime(p[1], '%Y-%m-%d %H:%M:%S')
    except ValueError: continue
    if e <= s: continue
    summary = '\t'.join(p[2:])
    sc = to_canon(s); ec = to_canon(e)
    rating = star_count(summary); slp = is_sleep(summary); fit = is_fitness(summary)
    cur = sc
    while cur < ec:
        he = cur.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        ce = min(ec, he); hrs = (ce - cur).total_seconds() / 3600.0; h = cur.hour
        key = (cur.date(), h)
        if not fit: acc[key][2] += hrs            # covered (awake-able)
        if slp: acc[key][3] += hrs                # sleep
        if rating > 0:
            acc[key][0] += hrs; acc[key][1] += rating * hrs
        cur = ce

# Per hour: list of per-day observations (work_min, wstar_min, awake_min)
obs = {h: [] for h in range(24)}
days = set()
for (d, h), (work, wstar, cov, sleep) in acc.items():
    awake = max(0.0, cov - sleep)
    obs[h].append((work * 60.0, wstar * 60.0, awake * 60.0))
    days.add(d)

SIGMA = 1.5
def circ(a, b): dd = abs(a - b); return min(dd, 24 - dd)
def kern(a, b): return math.exp(-(circ(a, b) ** 2) / (2 * SIGMA * SIGMA))

def wmean_wstd(vals, ws):
    sw = sum(ws)
    if sw <= 0: return None, None
    m = sum(v * w for v, w in zip(vals, ws)) / sw
    var = sum(w * (v - m) ** 2 for v, w in zip(vals, ws)) / sw
    return m, math.sqrt(max(var, 0.0))

# pooled sigma across all day-hour obs (SE fallback)
eff_v, eff_w, mob_v, mob_w = [], [], [], []
for h in range(24):
    for (wm, wsm, am) in obs[h]:
        if wm > 0: eff_v.append(wsm / wm); eff_w.append(wm)
        if am > 0: mob_v.append(100.0 * wm / am); mob_w.append(am)
_, eff_sigma = wmean_wstd(eff_v, eff_w)
_, mob_sigma = wmean_wstd(mob_v, mob_w)
eff_sigma = eff_sigma or 0.0; mob_sigma = mob_sigma or 0.0

eff_mean = [None]*24; eff_lo = [None]*24; eff_hi = [None]*24
mob_mean = [None]*24; mob_lo = [None]*24; mob_hi = [None]*24
for H in range(24):
    # Efficiency
    num = den = sw = sw2 = 0.0
    for h in range(24):
        k = kern(h, H)
        for (wm, wsm, am) in obs[h]:
            if wm > 0:
                w = k * wm
                num += k * wsm; den += w; sw += w; sw2 += w * w
    if den > 0:
        m = num / den
        effN = (sw * sw / sw2) if sw2 > 0 else 0.0
        se = eff_sigma / math.sqrt(effN) if effN > 0 else eff_sigma
        eff_mean[H] = round(m, 3)
        eff_lo[H] = round(max(0.0, m - se), 3); eff_hi[H] = round(min(5.0, m + se), 3)
    # Mobilization
    num = den = sw = sw2 = 0.0
    for h in range(24):
        k = kern(h, H)
        for (wm, wsm, am) in obs[h]:
            if am > 0:
                w = k * am
                num += w * (100.0 * wm / am); den += w; sw += w; sw2 += w * w
    if den > 0:
        m = num / den
        mobN = (sw * sw / sw2) if sw2 > 0 else 0.0
        se = mob_sigma / math.sqrt(mobN) if mobN > 0 else mob_sigma
        mob_mean[H] = round(m, 2)
        mob_lo[H] = round(max(0.0, m - se), 2); mob_hi[H] = round(min(100.0, m + se), 2)

output = {
    'last_updated': datetime.now(timezone.utc).astimezone(CANONICAL_TZ).replace(tzinfo=None).strftime('%Y-%m-%d %H:%M'),
    'note': 'Gaussian smoothing (sigma=1.5h, wrap-aware). Band = +/-1 SE (pooled_sigma / sqrt(effective N)) — wide where few day-observations.',
    'hours': list(range(24)),
    'n_days': len(days),
    'eff': {'mean': eff_mean, 'lo': eff_lo, 'hi': eff_hi},
    'mob': {'mean': mob_mean, 'lo': mob_lo, 'hi': mob_hi},
}

with open(f'{out_dir}/breakdown_data.json', 'w') as f:
    json.dump(output, f, indent=2)
with open(f'{out_dir}/breakdown_data.js', 'w') as f:
    f.write('window.BREAKDOWN_DATA = '); json.dump(output, f, indent=2); f.write(';\n')

print(f"breakdown: {output['n_days']} days", file=sys.stderr)
