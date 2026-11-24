#!/usr/bin/env python3
"""Append today's daily-prediction calls (10 trading-day horizon) to logs/predictions.jsonl so they can be scored later.
Run after app/run_daily.py. One line per holding per day; safe to re-run (skips symbols already logged today)."""
import datetime, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import numpy as np
import data, forecast, server
LOG = os.path.join(HERE, "..", "logs", "predictions.jsonl")
utc = lambda t: datetime.datetime.fromtimestamp(t, datetime.timezone.utc)

def main():
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    now = datetime.datetime.now(datetime.timezone.utc); made = now.strftime("%Y-%m-%d")
    seen = set()
    if os.path.exists(LOG):
        for l in open(LOG):
            try: r = json.loads(l); seen.add((r["made"], r["symbol"]))
            except Exception: pass
    n = 0
    with open(LOG, "a") as f:
        for h in server.load_holdings():
            if h["assetClass"] == "OPT" or (made, h["symbol"]) in seen: continue
            try:
                d = server.api_forecast(h["symbol"], "1d", 10); a = d["analysis"]
                bars = data.bars(h["yahoo"], "1d", "2y", ttl=300)[0]
                if utc(bars[-1]["t"]).strftime("%Y-%m-%d") == made: bars = bars[:-1]      # drop today's unfinished bar
                cl = np.array([b["c"] for b in bars])
                rec = {"made": made, "symbol": h["symbol"], "yahoo": h["yahoo"], "interval": "1d", "horizon": 10,
                       "base_date": utc(bars[-1]["t"]).strftime("%Y-%m-%d"), "base_close": float(cl[-1]),
                       "sigma_h": float(forecast._sigma_h(cl, 10)), "top": a["topName"], "topProb": a["topProb"],
                       "confidence": a["confidence"], "probs": {s["name"]: s["prob"] for s in a["scenarios"]}, "src": "run_daily"}
                f.write(json.dumps(rec) + "\n"); n += 1
            except Exception as e:
                print("skip", h["symbol"], str(e)[:60])
    print(f"logged {n} calls for {made} -> {os.path.normpath(LOG)}")

if __name__ == "__main__": main()
