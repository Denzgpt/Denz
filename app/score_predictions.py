#!/usr/bin/env python3
"""Score logged calls against what the market did. A call is FINAL once 10 trading days have passed; before that it is INTERIM
(the realised move so far is classified against the horizon band scaled by sqrt(days elapsed / 10))."""
import datetime, json, math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import numpy as np
import data, forecast
LOG = os.path.join(HERE, "..", "logs", "predictions.jsonl"); SC = forecast.SCEN
grp = lambda k: 0 if k <= 1 else 1 if k == 2 else 2
utc = lambda t: datetime.datetime.fromtimestamp(t, datetime.timezone.utc)

def main():
    recs = [json.loads(l) for l in open(LOG) if l.strip()]
    now = datetime.datetime.now(datetime.timezone.utc); today = now.strftime("%Y-%m-%d")
    cache, rows = {}, []
    for r in recs:
        y = r["yahoo"]
        if y not in cache: cache[y] = data.bars(y, "1d", "2y", ttl=300)[0]
        after = [b for b in cache[y] if utc(b["t"]).strftime("%Y-%m-%d") > r["base_date"]
                 and not (utc(b["t"]).strftime("%Y-%m-%d") == today and now.hour < 22)]   # skip an unfinished bar
        e = min(len(after), r["horizon"])
        if e == 0: continue
        ret = math.log(after[e - 1]["c"] / r["base_close"])
        act = int(np.digitize(ret / (r["sigma_h"] * math.sqrt(e / r["horizon"])), forecast.EDGES)); call = SC.index(r["top"])
        rows.append({**r, "e": e, "ret": ret * 100, "act": act, "call": call, "final": e >= r["horizon"]})
    for label, sel in (("FINAL (10 days elapsed)", [x for x in rows if x["final"]]), ("INTERIM (fewer than 10 days)", [x for x in rows if not x["final"]])):
        print(f"\n== {label}: {len(sel)} calls")
        if not sel: continue
        for x in sel: print(f"{x['made']} {x['symbol']:6} day {x['e']:2}/10  {x['ret']:6.2f}%  called {SC[x['call']]:13} {x['topProb']*100:3.0f}%  actual {SC[x['act']]:13} {'HIT' if x['call']==x['act'] else ''}")
        n = len(sel); ex = sum(x["call"] == x["act"] for x in sel); dr = sum(grp(x["call"]) == grp(x["act"]) for x in sel); sd = sum(x["act"] == 2 for x in sel)
        print(f"exact {ex}/{n} ({ex/n:.0%}) | direction group {dr}/{n} ({dr/n:.0%}) | always-Sideways exact {sd}/{n} ({sd/n:.0%}) | avg stated prob {np.mean([x['topProb'] for x in sel]):.0%}")

if __name__ == "__main__": main()
