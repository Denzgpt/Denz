#!/usr/bin/env python3
"""Freeze the live app into a single static page (demo/artifact.html) with a data snapshot."""
import json, os, re, time, sys
sys.path.insert(0, os.path.dirname(__file__))
import server

HERE = os.path.dirname(os.path.abspath(__file__))
snap, now = {}, int(time.time())
hold = server.api_holdings(); snap["/api/holdings"] = hold
for g, hs in hold["groups"].items():
    for h in hs:
        for interval, hz in (("1h", 24), ("1d", 10)):
            try:
                url = f"/api/forecast?sym={h['symbol'].replace(' ', '%20')}&interval={interval}&horizon={hz}"
                snap[url] = server.api_forecast(h["symbol"], interval, hz)
                snap[url.replace("sym=" + h["symbol"].replace(" ", "%20"), "sym=" + __import__("urllib.parse").parse.quote(h["symbol"], safe=""))] = snap[url]
                snap[f"/api/hitrate?sym={__import__('urllib.parse').parse.quote(h['symbol'], safe='')}&interval={interval}"] = {"n": 0, "hits": 0}
                print("ok", h["symbol"], interval, flush=True)
            except Exception as e:
                print("FAIL", h["symbol"], interval, e, flush=True)
html = open(os.path.join(HERE, "web", "index.html")).read()
style = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
body = re.search(r"<body>(.*)</body>", html, re.S).group(1)
body = body.replace("<script>", f"<script>window.SNAPSHOT={json.dumps(snap,separators=(',',':'))};window.SNAPSHOT_AT={now};\n", 1)
body = body.replace("setInterval(refreshHoldings,10000);setInterval(()=>{if(tab)loadForecasts()},30000);", "")
style = style.replace("body{margin:0;", "body{margin:0;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));")
out = f'<title>Holdings Forecast</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n<style>{style}\n:root{{color-scheme:dark}}</style>\n{body}'
os.makedirs(os.path.join(HERE, "..", "demo"), exist_ok=True)
open(os.path.join(HERE, "..", "demo", "artifact.html"), "w").write(out)
print("bytes", len(out))
