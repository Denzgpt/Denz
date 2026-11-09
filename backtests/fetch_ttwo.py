import urllib.request, json, time
def get(sym):
    u=f"https://query2.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&period1=946684800&period2={int(time.time())}&events=div,split"
    r=json.load(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0"}),timeout=25))["chart"]["result"][0]
    q=r["indicators"]["quote"][0]; a=r["indicators"]["adjclose"][0]["adjclose"]
    return {"t":r["timestamp"],"o":q["open"],"c":q["close"],"v":q["volume"],"adj":a}
for s in ("TTWO","SPY"): json.dump(get(s),open(f"{s}_daily.json","w"))
print("ok")
