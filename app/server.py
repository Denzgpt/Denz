#!/usr/bin/env python3
"""Read-only live forecast dashboard. No order placement anywhere. Run: python server.py [port]"""
import json, os, sys, time, threading, urllib.parse
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import data, groups, forecast

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "forecast_log.jsonl")
FC = {}                       # symbol -> (time, result)
FC_TTL = 300                  # recompute forecast at most every 5 min (also on new bar)
fc_lock = threading.Lock()

def load_holdings():
    return json.load(open(os.path.join(HERE, "holdings.json")))["holdings"]

def api_holdings():
    hs, metas = load_holdings(), {}
    for h in hs:
        try: metas[h["yahoo"]] = data.quote(h["yahoo"])
        except Exception: pass
    g = groups.assign(hs, metas)
    out = {}
    for h in hs:
        m = metas.get(h["yahoo"], {})
        out.setdefault(g[h["symbol"]], []).append({**h, "price": m.get("price"), "asof": m.get("asof"), "prevClose": m.get("prevClose")})
    return {"groups": out, "now": int(time.time()), **forecast.engine_status()}

def api_forecast(sym, interval, horizon):
    hs = {h["symbol"]: h for h in load_holdings()}
    h = hs.get(sym) or {"yahoo": sym}
    key = (h["yahoo"], interval, horizon)
    rng = "1mo" if interval == "1h" else "2y"
    bars, meta = data.bars(h["yahoo"], interval, rng, ttl=30)
    with fc_lock:
        hit = FC.get(key)
        if hit and time.time() - hit[0] < FC_TTL and hit[1]["lastBarT"] == bars[-1]["t"]:
            res = hit[1]
        else:
            res = forecast.forecast(bars, horizon=horizon, n=100, step="1h" if interval == "1h" else "1D")
            res["lastBarT"] = bars[-1]["t"]
            FC[key] = (time.time(), res)
            with open(LOG, "a") as f:
                f.write(json.dumps({"sym": h["yahoo"], "interval": interval, "t0": bars[-1]["t"], "last": res["last"],
                                    "p10": res["p10"], "p90": res["p90"], "median": res["median"]}) + "\n")
    q = data.quote(h["yahoo"])
    return {**res, "bars": bars[-120:], "quote": q, "now": int(time.time()), "currency": meta.get("currency"),
            "option": h.get("option"), "marketState": meta.get("currentTradingPeriod") and "see-asof"}

def api_hitrate(sym, interval):
    """Share of past forecasts whose realised path stayed inside the p10-p90 band, per bar."""
    hs = {h["symbol"]: h for h in load_holdings()}
    y = (hs.get(sym) or {"yahoo": sym})["yahoo"]
    if not os.path.exists(LOG): return {"n": 0, "hits": 0}
    bars, _ = data.bars(y, interval, "1mo" if interval == "1h" else "2y", ttl=60)
    by_t = {b["t"]: b["c"] for b in bars}
    ts = sorted(by_t)
    n = hits = 0
    seen = set()
    for line in open(LOG):
        r = json.loads(line)
        if r["sym"] != y or r["interval"] != interval or r["t0"] in seen: continue
        seen.add(r["t0"])
        after = [t for t in ts if t > r["t0"]][:len(r["p10"])]
        for i, t in enumerate(after):
            n += 1; hits += r["p10"][i] <= by_t[t] <= r["p90"][i]
    return {"n": n, "hits": hits}

class H(SimpleHTTPRequestHandler):
    def __init__(s, *a, **k): super().__init__(*a, directory=os.path.join(HERE, "web"), **k)
    def log_message(s, *a): pass
    def _json(s, obj, code=200):
        b = json.dumps(obj).encode(); s.send_response(code)
        s.send_header("Content-Type", "application/json"); s.send_header("Cache-Control", "no-store")
        s.send_header("Content-Length", str(len(b))); s.end_headers(); s.wfile.write(b)
    def do_GET(s):
        u = urllib.parse.urlparse(s.path); q = urllib.parse.parse_qs(u.query)
        try:
            if u.path == "/api/holdings": return s._json(api_holdings())
            if u.path == "/api/forecast":
                return s._json(api_forecast(q["sym"][0], q.get("interval", ["1h"])[0], int(q.get("horizon", ["24"])[0])))
            if u.path == "/api/hitrate": return s._json(api_hitrate(q["sym"][0], q.get("interval", ["1h"])[0]))
        except Exception as e:
            return s._json({"error": str(e)}, 502)
        return super().do_GET()
    def do_POST(s): s._json({"error": "read-only"}, 405)

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"http://localhost:{port}  engine={forecast.engine_status()}")
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
