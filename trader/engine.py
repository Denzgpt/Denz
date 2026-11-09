"""Mechanical paper-trading engine. No real orders, ever. Two accounts (Playbook, Max-ROI) run on the same data.
Each run REPLAYS every 5-minute bar since the last run, so resting buy limits, stops and trailing stops are honoured
between hourly runs instead of being missed. Signals at bar t fill no earlier than bar t+1 (no lookahead)."""
import json, os, math, time, datetime as dt, urllib.request
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); CFG = os.path.join(HERE, "config"); ST = os.environ.get("TRADER_STATE") or os.path.join(HERE, "state")
J = lambda p: json.load(open(p))
def cfg(n): return J(os.path.join(CFG, n))

def yahoo(sym, interval, rng):
    last = None
    for h in ("query2", "query1"):
        try:
            u = f"https://{h}.finance.yahoo.com/v8/finance/chart/{sym}?interval={interval}&range={rng}&includePrePost=false"
            r = json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=20))["chart"]["result"][0]
            q = r["indicators"]["quote"][0]; out = []
            for i, t in enumerate(r.get("timestamp") or []):
                if None in (q["open"][i], q["high"][i], q["low"][i], q["close"][i]): continue
                out.append({"t": t, "o": q["open"][i], "h": q["high"][i], "l": q["low"][i], "c": q["close"][i]})
            return out
        except Exception as e: last = e
    raise RuntimeError(f"{sym}: {last}")
day = lambda t: dt.datetime.fromtimestamp(t, dt.UTC).date()

class Ind:
    """Daily indicators as of the close BEFORE a given date."""
    def __init__(s, daily):
        s.d = [day(b["t"]) for b in daily]; c = np.array([b["c"] for b in daily]); h = np.array([b["h"] for b in daily]); l = np.array([b["l"] for b in daily])
        s.rows = []
        for i in range(len(c)):
            if i < 200: s.rows.append(None); continue
            tr = np.maximum(h[i-13:i+1] - l[i-13:i+1], np.maximum(abs(h[i-13:i+1] - c[i-14:i]), abs(l[i-13:i+1] - c[i-14:i])))
            s.rows.append({"close": c[i], "sma50": c[i-49:i+1].mean(), "sma200": c[i-199:i+1].mean(), "atr": tr.mean(), "hi20": h[i-19:i+1].max(), "lo20": l[i-19:i+1].min(),
                           "hi60": h[i-59:i+1].max(), "mom60": c[i] / c[i-60] - 1})
    def at(s, d):
        j = None
        for i in range(len(s.d) - 1, -1, -1):
            if s.d[i] < d: j = i; break
        return s.rows[j] if j is not None else None

class Account:
    def __init__(s, name, equity):
        s.name = name; s.cash = equity; s.start = equity; s.pos = {}; s.orders = {}; s.trades = []; s.curve = []; s.journal = []; s.peak = equity
        s.day = None; s.day_start = equity; s.last_ts = 0; s.last_px = {}; s.cool = {}
    def equity(s): return s.cash + sum(p["qty"] * s.last_px.get(k, p["entry"]) for k, p in s.pos.items())
    def to_json(s): return {k: v for k, v in s.__dict__.items()}
    @staticmethod
    def from_json(d): a = Account(d["name"], d["start"]); a.__dict__.update(d); return a

def log(a, t, text): a.journal.append({"t": iso(t), "text": text})
iso = lambda t: dt.datetime.fromtimestamp(t, dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

def sell(a, sym, px, t, why, U):
    p = a.pos.pop(sym)
    if why.startswith('Stop'): a.cool[sym] = (day(t) + dt.timedelta(days=7)).isoformat()   # no re-buy for a week after a stop-out
    fill = px * (1 - U["slippage_bp"] / 1e4); a.cash += p["qty"] * fill - U["fee_per_order"]
    pnl = p["qty"] * (fill - p["entry"]) - 2 * U["fee_per_order"]
    a.trades.append({"t": iso(t), "side": "SELL", "sym": sym, "qty": round(p["qty"], 4), "px": round(fill, 2), "pnl": round(pnl, 2), "note": why})

def buy(a, sym, o, px, t, U):
    fill = px * (1 + U["slippage_bp"] / 1e4); qty = o["qty"]
    cost = qty * fill + U["fee_per_order"]
    if cost > a.cash: qty = max(0, (a.cash - U["fee_per_order"]) / fill); cost = qty * fill + U["fee_per_order"]
    if qty * fill < 25: return
    a.cash -= cost; a.pos[sym] = {"qty": qty, "entry": fill, "stop": o["stop"], "target": o["target"], "trail": 0, "opened": iso(t), "high": fill, "thesis": o["why"], "rule": o["rule"]}
    a.trades.append({"t": iso(t), "side": "BUY", "sym": sym, "qty": round(qty, 4), "px": round(fill, 2), "pnl": None, "note": o["why"]})

def size(equity, entry, stop, risk, cap_val, cash):
    if entry <= stop: return 0
    return max(0, min(equity * risk / (entry - stop), cap_val / entry, (cash - 1) / entry))

# ---------------- strategies: return desired resting buy orders {sym: order}
def playbook_orders(ctx, a, P, S):
    out = {}; eq = a.equity(); dd = eq / a.peak - 1; dayret = eq / a.day_start - 1
    if dd <= P["dd_stop"] or dayret <= P["day_loss_no_entries"] or S.get("global_pause"): return out, "guard"
    half = 0.5 if dd <= P["dd_half"] else 1.0
    if len(a.pos) >= P["max_positions"]: return out, None
    for sym, x in ctx.items():
        if sym in a.pos or sym in P["excluded"] or sym in S.get("veto", {}) or a.cool.get(sym, "") > day(x["t"]).isoformat(): continue
        i, px, now = x["ind"], x["px"], x["t"]
        if any(0 <= (dt.date.fromisoformat(d) - day(now)).days * 24 + (0 if True else 0) <= 24 and dt.date.fromisoformat(d) >= day(now) for d in x["earn"]): continue
        L = P["lines"].get(sym)
        if L and "gate_lo" in L: lo, hi, abort, tgt = L["gate_lo"], L["gate_hi"], L["abort"], L["target"]
        else:
            if i["close"] < i["sma200"]: continue
            lo, hi = i["lo20"], i["lo20"] + i["atr"]; abort = lo - 0.5 * i["atr"]; tgt = i["hi60"]
            if L and "gate_hi" in L: hi = L["gate_hi"]
        if px < abort or px < lo - 0.5 * i["atr"]: continue          # below the abort line = wait
        if px <= hi: lim = px
        elif px <= hi * 1.06: lim = hi
        else: continue
        rr = (tgt - lim) / (lim - abort) if lim > abort else 0
        if rr < P["min_rr"]: continue
        q = size(eq, lim, abort, P["risk_per_trade"] * half, min(P["starter_cap"], P["max_single"]) * eq, a.cash)
        if q * lim >= 25: out[sym] = {"limit": lim, "stop": abort, "target": tgt, "qty": q, "rule": "gate", "why": f"Gate {lo:.2f}-{hi:.2f}, abort {abort:.2f}, target {tgt:.2f}, R:R {rr:.1f}:1, risk 1% sized ({'half size, drawdown guard' if half < 1 else 'full starter'})."}
    return out, None

def maxroi_orders(ctx, a, M, S):
    out = {}; eq = a.equity(); dd = eq / a.peak - 1; dayret = eq / a.day_start - 1
    if S.get("global_pause") or len(a.pos) >= M["max_positions"] or dd <= -0.12 or dayret <= -0.03: return out, "guard"
    half = 0.5 if dd <= -0.08 else 1.0                      # same drawdown guards as the Playbook
    cands = []
    spy = ctx.get("SPY")
    if spy and not (spy["ind"]["close"] > spy["ind"]["sma50"]): return out, "market below 50d"
    for sym, x in ctx.items():
        if sym in a.pos or sym in M["excluded"] or sym in S.get("veto", {}) or a.cool.get(sym, "") > day(x["t"]).isoformat(): continue
        i, px = x["ind"], x["px"]
        if not (i["close"] > i["sma200"] and i["sma50"] > i["sma200"]): continue
        if px > i["hi20"] - M["pullback_atr"] * i["atr"] or px < i["sma50"] - 0.5 * i["atr"]: continue
        cands.append((i["mom60"], sym, px, i))
    for mom, sym, px, i in sorted(cands, reverse=True)[: M["max_positions"] - len(a.pos)]:
        stop = px - M["stop_atr"] * i["atr"]; tgt = px + M["target_atr"] * i["atr"]
        q = size(eq, px, stop, M["risk_per_trade"] * half, M["max_single"] * eq, a.cash)
        if q * px >= 25: out[sym] = {"limit": px, "stop": stop, "target": tgt, "qty": q, "rule": "pullback", "why": f"Uptrend (50d>200d), pulled back {(i['hi20']-px)/i['atr']:.1f} ATR from the 20-day high; 60d momentum {mom*100:+.0f}%. Stop {stop:.2f} (2 ATR), target {tgt:.2f} (4 ATR)."}
    return out, None

def step(a, kind, t, ctx_bars, ctx_ind_for, earn, S, P, M, U):
    """Process ONE 5-minute timestamp for one account."""
    d = day(t)
    if a.day != d.isoformat(): a.day = d.isoformat(); a.day_start = a.equity()
    for sym, b in ctx_bars.items(): a.last_px[sym] = b["c"]
    # 1) fills of resting orders placed on the previous bar
    for sym, o in list(a.orders.items()):
        b = ctx_bars.get(sym)
        if not b or sym in a.pos: continue
        if b["l"] <= o["limit"]:
            buy(a, sym, o, min(b["o"], o["limit"]), t, U)
    a.orders = {}
    # 2) exits
    for sym, p in list(a.pos.items()):
        b = ctx_bars.get(sym)
        if not b: continue
        p["high"] = max(p["high"], b["h"])
        if kind == "playbook" and p["high"] >= p["entry"] * (1 + P["trail_after"]):
            p["trail"] = max(p["trail"], p["high"] * (1 - P["trail_pct"]))
        stop = max(p["stop"], p["trail"])
        if b["l"] <= stop: sell(a, sym, min(b["o"], stop), t, f"Stop hit ({'trailing' if p['trail'] >= p['stop'] and p['trail'] else 'abort'} {stop:.2f}).", U); continue
        if b["h"] >= p["target"]: sell(a, sym, max(b["o"], p["target"]), t, f"Target {p['target']:.2f} reached.", U); continue
        if kind == "playbook" and b["c"] <= p["entry"] * (1 + P["dead_money"]): sell(a, sym, b["c"], t, "Rule 3: -25% from cost, cut.", U); continue
        if kind == "maxroi" and (d - day(dt.datetime.fromisoformat(p["opened"].replace("Z", "+00:00")).timestamp())).days > M["max_hold_days"]: sell(a, sym, b["c"], t, "Time stop.", U)
    a.peak = max(a.peak, a.equity())
    # 3) new resting orders from this bar's close (fill from the next bar)
    ctx = {s: {"px": b["c"], "ind": ctx_ind_for(s, d), "earn": earn.get(s, []), "t": t} for s, b in ctx_bars.items()}
    ctx = {s: x for s, x in ctx.items() if x["ind"]}
    orders, _ = (playbook_orders if kind == "playbook" else maxroi_orders)(ctx, a, P if kind == "playbook" else M, S)
    a.orders = orders

def run(replay_from=None, reset=False, now_only=False):
    U = cfg("universe.json"); P = cfg("playbook.json"); M = cfg("maxroi.json"); S = J(os.environ["TRADER_SWARM"]) if os.environ.get("TRADER_SWARM") else cfg("swarm.json"); earn = {k: v for k, v in cfg("earnings.json").items() if not k.startswith("_")}
    syms = U["symbols"]; os.makedirs(ST, exist_ok=True)
    bars5 = {s: yahoo(s, "5m", "1mo" if replay_from else "5d") for s in syms}
    inds = {s: Ind(yahoo(s, "1d", "2y")) for s in syms}
    accts = {}
    for k in ("playbook", "maxroi"):
        f = os.path.join(ST, f"{k}.json")
        accts[k] = Account.from_json(J(f)) if (os.path.exists(f) and not reset) else Account(k, U["start_equity"])
    t0 = int(dt.datetime.fromisoformat(replay_from + "T00:00:00+00:00").timestamp()) if replay_from else 0
    ts = sorted({b["t"] for s in syms for b in bars5[s]})
    ts = [t for t in ts if t >= t0 and t > min(a.last_ts for a in accts.values())]
    idx = {s: {b["t"]: b for b in bars5[s]} for s in syms}
    bench = {s: {b["t"]: b["c"] for b in bars5[s]} for s in ("SPY", "QQQ")}
    benchf = os.path.join(ST, "bench.json"); B = J(benchf) if (os.path.exists(benchf) and not reset) else {"curve": []}
    for t in ts:
        cb = {s: idx[s][t] for s in syms if t in idx[s]}
        for k, a in accts.items():
            if t <= a.last_ts: continue
            step(a, k, t, cb, lambda s, d: inds[s].at(d), earn, S, P, M, U); a.last_ts = t
            if not a.curve or t - dt.datetime.fromisoformat(a.curve[-1]["t"].replace("Z", "+00:00")).timestamp() >= 3600 - 1:
                a.curve.append({"t": iso(t), "eq": round(a.equity(), 2)})
        if "SPY" in cb and (not B["curve"] or t - dt.datetime.fromisoformat(B["curve"][-1]["t"].replace("Z", "+00:00")).timestamp() >= 3599):
            B["curve"].append({"t": iso(t), "spy": bench["SPY"].get(t), "qqq": bench["QQQ"].get(t)})
    for k, a in accts.items(): json.dump(a.to_json(), open(os.path.join(ST, f"{k}.json"), "w"), default=float)
    json.dump(B, open(benchf, "w"))
    return accts, B

if __name__ == "__main__":
    import sys
    rf = sys.argv[sys.argv.index("--replay-from") + 1] if "--replay-from" in sys.argv else None
    accts, B = run(rf, reset="--reset" in sys.argv)
    for k, a in accts.items(): print(k, f"equity {a.equity():.2f} cash {a.cash:.2f} positions {list(a.pos)} trades {len(a.trades)} orders {list(a.orders)}")
