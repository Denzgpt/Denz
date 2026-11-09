"""Isolated TTWO study: (1) earnings-day reactions, (2) behaviour around major game launches, incl. 6 months after.
Earnings reaction day is INFERRED (not from a calendar): in each usual reporting window the day with the largest volume
spike vs its 20-day average is taken as the reaction day (TTWO reports after the close). Release dates are from memory: verify."""
import json, math, statistics as st, datetime as dt
import numpy as np
D = {s: json.load(open(f"{s}_daily.json")) for s in ("TTWO", "SPY")}
def clean(d):
    rows = [(dt.datetime.fromtimestamp(t, dt.UTC).date(), o, c, v, a) for t, o, c, v, a in zip(d["t"], d["o"], d["c"], d["v"], d["adj"]) if c and a]
    return rows
T = clean(D["TTWO"]); S = {r[0]: r[4] for r in clean(D["SPY"])}
dates = [r[0] for r in T]; idx = {d: i for i, d in enumerate(dates)}
adj = np.array([r[4] for r in T]); cl = np.array([r[2] for r in T]); op = np.array([r[1] for r in T]); vol = np.array([r[3] for r in T], float)
ret = np.diff(np.log(adj), prepend=np.nan)
def spy_ret(i0, i1):
    a, b = S.get(dates[i0]), S.get(dates[i1]); return (b / a - 1) if a and b else float("nan")
# ---------- earnings
WIN = [(2, 1, 2, 14), (5, 10, 5, 31), (8, 1, 8, 14), (11, 1, 11, 14)]       # (m0,d0,m1,d1)
ev = []
for y in range(2001, 2027):
    for m0, d0, m1, d1 in WIN:
        a, b = dt.date(y, m0, d0), dt.date(y, m1, d1)
        cand = [i for i, d in enumerate(dates) if a <= d <= b and i > 25]
        if not cand: continue
        score = [vol[i] / vol[i - 20:i].mean() for i in cand]
        k = cand[int(np.argmax(score))]
        if max(score) < 1.6: continue                       # no clear volume spike -> skip (date not trusted)
        ev.append(k)
# anchor the recent reports to IBKR earnings records (after-close reports -> reaction is the next session); drop false positives
ANCHOR = {"2025-11-07", "2026-02-04", "2026-05-22", "2026-08-07"}
ev = [k for k in ev if str(dates[k]) < "2025-10-01"] + [idx[dt.date.fromisoformat(a)] for a in sorted(ANCHOR) if dt.date.fromisoformat(a) in idx]
rows = []
for k in ev:
    if k + 1 >= len(dates) or k < 1: continue
    gap = op[k] / cl[k - 1] - 1; day = cl[k] / cl[k - 1] - 1
    d5 = adj[min(k + 5, len(adj) - 1)] / adj[k] - 1
    rows.append({"date": str(dates[k]), "gap": gap, "day": day, "after5": d5, "volx": vol[k] / vol[k - 20:k].mean()})
print(f"EARNINGS: {len(rows)} events detected ({rows[0]['date']} to {rows[-1]['date']})")
def summ(rs, lab):
    d = np.array([r["day"] for r in rs]); g = np.array([r["gap"] for r in rs]); a5 = np.array([r["after5"] for r in rs])
    print(f"{lab:>12} n={len(rs):2d} avg|move|={np.mean(abs(d))*100:4.1f}% median|move|={np.median(abs(d))*100:4.1f}% up={np.mean(d>0)*100:3.0f}% "
          f"avg={d.mean()*100:+5.1f}% worst={d.min()*100:+5.1f}% best={d.max()*100:+5.1f}% P90|move|={np.percentile(abs(d),90)*100:4.1f}% gap|avg|={np.mean(abs(g))*100:3.1f}% next5d avg={a5.mean()*100:+4.1f}%")
summ(rows, "all"); summ(rows[-12:], "last 12"); summ(rows[-6:], "last 6")
print("last 8:", [(r["date"], f"{r['day']*100:+.1f}%") for r in rows[-8:]])
# ---------- releases
REL = {"GTA IV": "2008-04-29", "Red Dead Redemption": "2010-05-18", "Borderlands 2": "2012-09-18", "GTA V": "2013-09-17",
       "GTA V next-gen": "2014-11-18", "Civ VI": "2016-10-21", "Red Dead 2": "2018-10-26", "Borderlands 3": "2019-09-13",
       "GTA Trilogy DE": "2021-11-11", "Borderlands 4": "2025-09-12"}
def rv(i, n=20): return np.nanstd(ret[i - n + 1:i + 1]) * math.sqrt(252)
out = []
for name, ds in REL.items():
    r = dt.date.fromisoformat(ds); i = next(i for i, d in enumerate(dates) if d >= r)
    if i + 126 >= len(dates) and name != "Borderlands 4": continue
    base_vol = rv(i - 25, 60)
    def R(a, b): return adj[min(b, len(adj) - 1)] / adj[a] - 1
    n = len(dates); e126 = min(i + 126, n - 1); path = adj[i:e126 + 1] / adj[i] - 1
    mdd = float(np.min(path)); mup = float(np.max(path))
    # stabilised: first day after release where trailing-20d realised vol <= 1.25x pre-release baseline
    stab = None
    for j in range(i + 20, e126 + 1):
        if rv(j) <= 1.25 * base_vol: stab = j - i; break
    out.append({"name": name, "date": ds, "runup20": R(i - 20, i), "runup20_vs_spy": R(i - 20, i) - spy_ret(i - 20, i),
                "d1": R(i, i + 1), "d5": R(i, i + 5), "m1": R(i, i + 21), "m3": R(i, i + 63), "m6": R(i, e126),
                "m6_vs_spy": R(i, e126) - spy_ret(i, e126), "low": mdd, "high": mup, "days": e126 - i, "stab": stab,
                "vol_pre": base_vol, "vol_post20": rv(min(i + 40, n - 1))})
pct = lambda x: f"{x*100:+6.1f}%"
print("\nRELEASES (adjusted close; run-up = 20 trading days before launch day close; m1/m3/m6 = after launch day close)")
print(f"{'game':20}{'date':12}{'run-up20':>9}{'vsSPY':>8}{'d+1':>8}{'d+5':>8}{'m+1':>8}{'m+3':>8}{'m+6':>8}{'m6 vsSPY':>9}{'6m low':>8}{'6m high':>8}{'vol settles':>12}")
for o in out:
    print(f"{o['name']:20}{o['date']:12}{pct(o['runup20']):>9}{pct(o['runup20_vs_spy']):>8}{pct(o['d1']):>8}{pct(o['d5']):>8}{pct(o['m1']):>8}{pct(o['m3']):>8}{pct(o['m6']):>8}{pct(o['m6_vs_spy']):>9}{pct(o['low']):>8}{pct(o['high']):>8}{(str(o['stab'])+'d' if o['stab'] else 'not in 6m'):>12}")
full = [o for o in out if o["days"] >= 120]
for k, lab in (("runup20", "run-up 20d"), ("d1", "launch d+1"), ("m1", "+1m"), ("m3", "+3m"), ("m6", "+6m"), ("m6_vs_spy", "+6m vs SPY"), ("low", "worst dip in 6m"), ("high", "best peak in 6m")):
    v = np.array([o[k] for o in full]); print(f"avg {lab:16} {v.mean()*100:+6.1f}%  median {np.median(v)*100:+6.1f}%  positive in {np.mean(v>0)*100:3.0f}% of {len(v)} launches")
print("vol settled within 6m:", sum(1 for o in full if o["stab"]), "of", len(full), "median days:", st.median([o["stab"] for o in full if o["stab"]]))
# earnings that fall within 30 days of a launch
near = []
for r in rows:
    d = dt.date.fromisoformat(r["date"])
    for name, ds in REL.items():
        if abs((d - dt.date.fromisoformat(ds)).days) <= 45: near.append((r, name)); break
print("\nEARNINGS within 45 days of a launch:", [(r["date"], n, f"{r['day']*100:+.1f}%") for r, n in near])
if near: summ([r for r, _ in near], "near-launch")
json.dump({"earn": rows, "rel": out}, open("ttwo_results.json", "w"), default=float)
print("last close", dates[-1], cl[-1])
