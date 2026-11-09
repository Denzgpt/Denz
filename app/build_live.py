#!/usr/bin/env python3
"""Assemble demo/live.html: the live forecast page (reads IBKR through the artifact mcp capability)."""
import json, os, re, datetime
HERE = os.path.dirname(os.path.abspath(__file__)); J = lambda p: json.load(open(p))
cal = {k.rsplit("|", 1)[0] + "|" + k.rsplit("|", 1)[1]: v for k, v in J(os.path.join(HERE, "calibration_cache.json")).items() if v}
cal = {k: {**v, "years": v.get("years")} for k, v in cal.items()}
def pool(iv):
    items = [v for k, v in cal.items() if k.split("|")[1] == iv]
    tot = sum(v["n"] for v in items); w = lambda f: sum(v[f] * v["n"] for v in items) / tot
    bands = {}
    for v in items:
        for r in v["reliability"]:
            b = bands.setdefault(r["lo"], {"lo": r["lo"], "hi": r["hi"], "n": 0, "s": 0, "r": 0}); b["n"] += r["n"]; b["s"] += r["stated"] * r["n"]; b["r"] += r["realized"] * r["n"]
    rel = [{"lo": b["lo"], "hi": b["hi"], "n": b["n"], "stated": round(b["s"] / b["n"], 3), "realized": round(b["r"] / b["n"], 3)} for b in sorted(bands.values(), key=lambda x: x["lo"]) if b["n"] >= 30]
    return {"n": tot, "years": round(sum(v["years"] for v in items) / len(items), 1), "realized": round(w("realized"), 3), "stated": round(w("stated"), 3), "bestConstant": round(w("bestConstant"), 3), "skill": round(w("skill"), 4), "reliability": rel, "pooled": True}
POOL = {"1d": pool("1d"), "1h": pool("1h")}
TC = os.path.join(HERE, "..", "trader", "config"); ev = []
for e in J(os.path.join(HERE, "events.json"))["events"]: ev.append({**e, "kind": "macro"})
for s, ds in J(os.path.join(TC, "earnings.json")).items():
    if not s.startswith("_"):
        for d in ds: ev.append({"date": d, "label": f"{s} earnings", "scope": [s], "verified": False, "kind": "earnings"})
sw = J(os.path.join(TC, "swarm.json")); today = datetime.date.today().isoformat()
for s, why in (sw.get("veto") or {}).items(): ev.append({"date": today, "label": f"Swarm veto: {why}", "scope": [s], "verified": True, "kind": "swarm"})
desk = J(os.path.join(HERE, "desk_notes.json")); desk["notes"] = {k: v for k, v in desk["notes"].items()}
DATA = {"cal": cal, "pool": POOL, "events": ev, "desk": desk, "built": today}
html = open(os.path.join(HERE, "web", "index.html")).read(); style = re.search(r"<style>(.*?)</style>", html, re.S).group(1); link = re.search(r"<link[^>]*fonts[^>]*>", html).group(0)
style += ".hdr{min-width:90px}.hdr .px{text-align:right}#status .note{margin-bottom:8px}button.primary{font:600 13px var(--sans);background:var(--ink);color:var(--bg);border:0;border-radius:99px;padding:9px 16px;cursor:pointer}"
body = f'''<div class="wrap">
<header>
 <div class="eyebrow">Live · read-only · reads IBKR positions and prices · no orders</div>
 <h1>Holdings <em>forecast</em></h1>
 <p class="lede">Your actual positions, grouped automatically. Prices refresh every 30 seconds and each forecast is recomputed in your browser from fresh price history. Probabilities are mapped to what each confidence band really delivered in walk-forward tests.</p>
 <div id="status" style="margin-top:12px"></div>
 <p><button class="primary" id="connect">Connect to IBKR (read-only)</button></p>
</header>
<section class="panel swarm" id="swarm"></section>
<div class="bar"><nav id="tabs"></nav><div class="seg ctl"><button data-i="1d" class="on">Daily bars · 10 days</button><button data-i="1h">Hourly bars · 24 hours</button></div></div>
<main id="main"></main>
</div>'''
out = f'<title>Live Holdings Forecast</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n{link}\n<style>{style}</style>\n{body}\n<script>\nconst DATA={json.dumps(DATA, separators=(",", ":"))};\n{open(os.path.join(HERE, "live_app.js")).read()}\n</script>'
os.makedirs(os.path.join(HERE, "..", "demo"), exist_ok=True); open(os.path.join(HERE, "..", "demo", "live.html"), "w").write(out); print("bytes", len(out), "pool 1d", POOL["1d"]["n"], POOL["1d"]["realized"])
