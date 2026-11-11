#!/usr/bin/env python3
"""Daily forecast refresh: rebuild the snapshot page and the live page, print today's calls (one line per holding)."""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
subprocess.run([sys.executable, os.path.join(HERE, "build_demo.py")], check=True, stdout=subprocess.DEVNULL)
subprocess.run([sys.executable, os.path.join(HERE, "build_live.py")], check=True, stdout=subprocess.DEVNULL)
import server
rows = []
for h in server.load_holdings():
    if h["assetClass"] == "OPT": continue
    try:
        d = server.api_forecast(h["symbol"], "1d", 10); a = d["analysis"]
        rows.append((h["symbol"], a["topName"], round(a["topProb"] * 100), a["confidence"], d["quote"]["price"], h["currency"], [e["label"] for e in a["events"]][:2]))
    except Exception as e: rows.append((h["symbol"], "unavailable", 0, str(e)[:40], None, "", []))
for r in rows: print(f"{r[0]:6} {r[4] if r[4] is None else round(r[4],2)} {r[5]}  {r[1]} {r[2]}% ({r[3]})" + (f"  events: {'; '.join(r[6])}" if r[6] else ""))
