#!/usr/bin/env python3
"""Build the swarm-trader dashboard as one static page. Usage: python build_dashboard.py [state_dir] [label]"""
import json, os, sys, html
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, "..", "app"))
st = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "state"); label = sys.argv[2] if len(sys.argv) > 2 else "Live"
J = lambda p: json.load(open(p))
acc = {k: J(os.path.join(st, f"{k}.json")) for k in ("playbook", "maxroi")}; bench = J(os.path.join(st, "bench.json"))["curve"]
swarm = J(os.path.join(HERE, "config", "swarm.json")); desk = J(os.path.join(HERE, "..", "app", "desk_notes.json"))
# forecast calls per holding (daily bars, 10 days) from the forecast app
calls = []
try:
    import server
    for h in server.load_holdings():
        if h["assetClass"] == "OPT": continue
        try:
            d = server.api_forecast(h["symbol"], "1d", 10); a = d["analysis"]
            calls.append({"sym": h["symbol"], "name": h["name"], "call": a["topName"], "prob": a["topProb"], "conf": a["confidence"], "px": d["quote"]["price"], "cur": h["currency"]})
        except Exception as e: print("forecast skip", h["symbol"], e)
except Exception as e: print("forecast app unavailable:", e)
def pack(a):
    return {"name": a["name"], "start": a["start"], "cash": a["cash"], "curve": a["curve"], "trades": a["trades"],
            "pos": [{"sym": k, "qty": v["qty"], "entry": v["entry"], "stop": max(v["stop"], v["trail"]), "target": v["target"], "last": a["last_px"].get(k, v["entry"]), "why": v["thesis"]} for k, v in a["pos"].items()],
            "equity": a["cash"] + sum(v["qty"] * a["last_px"].get(k, v["entry"]) for k, v in a["pos"].items())}
DATA = {"label": label, "playbook": pack(acc["playbook"]), "maxroi": pack(acc["maxroi"]), "bench": bench, "swarm": swarm, "desk": desk, "calls": calls}
tpl = open(os.path.join(HERE, "dashboard_template.html")).read()
out = tpl.replace("/*DATA*/", "const DATA=" + json.dumps(DATA, default=float, separators=(",", ":")) + ";")
os.makedirs(os.path.join(HERE, "..", "demo"), exist_ok=True)
open(os.path.join(HERE, "..", "demo", "trader_desk.html"), "w").write(out); print("ok", len(out))
