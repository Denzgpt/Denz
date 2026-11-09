"""Market data: Yahoo chart API (no key). Cached briefly so many tabs don't hammer it."""
import json, time, urllib.request, urllib.error, threading
HOSTS = ["query2.finance.yahoo.com", "query1.finance.yahoo.com"]
_cache, _lock = {}, threading.Lock()

def _get(path, ttl):
    now = time.time()
    with _lock:
        hit = _cache.get(path)
        if hit and now - hit[0] < ttl:
            return hit[1]
    last = None
    for h in HOSTS:
        try:
            req = urllib.request.Request(f"https://{h}{path}", headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=12) as r:
                d = json.load(r)
            with _lock:
                _cache[path] = (now, d)
            return d
        except Exception as e:  # 429 etc -> try next host, then serve stale cache
            last = e
    with _lock:
        hit = _cache.get(path)
    if hit:
        return hit[1]
    raise RuntimeError(f"data fetch failed: {last}")

def bars(sym, interval="1h", rng="1mo", ttl=30):
    d = _get(f"/v8/finance/chart/{sym}?interval={interval}&range={rng}&includePrePost=false", ttl)
    res = d["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    out = []
    for i, t in enumerate(res.get("timestamp") or []):
        o, h, l, c, v = (q[k][i] for k in ("open", "high", "low", "close", "volume"))
        if None in (o, h, l, c):
            continue
        out.append({"t": t, "o": o, "h": h, "l": l, "c": c, "v": v or 0})
    return out, res["meta"]

def quote(sym):
    """Latest price from 1m bars (freshest free data). Returns price, as-of epoch, market state."""
    d = _get(f"/v8/finance/chart/{sym}?interval=1m&range=1d&includePrePost=true", 5)
    res = d["chart"]["result"][0]
    m = res["meta"]
    return {"price": m.get("regularMarketPrice"), "asof": m.get("regularMarketTime"),
            "prevClose": m.get("chartPreviousClose"), "currency": m.get("currency"),
            "type": m.get("instrumentType"), "exchange": m.get("fullExchangeName"),
            "name": m.get("longName") or m.get("shortName")}
