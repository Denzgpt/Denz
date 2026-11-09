"""Daily-bar sanity backtest of the Max-ROI rules, 10 years, today's universe (survivorship-biased: today's winners).
Signal on prior close, fill at next open, stop/target on daily low/high (stop first), 3bp slippage, no fees."""
import json, sys, numpy as np, datetime as dt
sys.path.insert(0, ".")
from engine import yahoo, cfg
U = cfg("universe.json"); syms = U["symbols"]
D = {s: yahoo(s, "1d", "10y") for s in syms}
dates = sorted({b["t"] for b in D["SPY"]}); T = {t: i for i, t in enumerate(dates)}
n = len(dates)
def arr(s, k):
    m = {b["t"]: b[k] for b in D[s]}; a = np.full(n, np.nan)
    for t, v in m.items():
        if t in T: a[T[t]] = v
    return a
O = {s: arr(s, "o") for s in syms}; H = {s: arr(s, "h") for s in syms}; L = {s: arr(s, "l") for s in syms}; C = {s: arr(s, "c") for s in syms}
def sma(a, k): return np.array([np.nanmean(a[max(0, i-k+1):i+1]) if i >= k - 1 else np.nan for i in range(n)])
S50 = {s: sma(C[s], 50) for s in syms}; S200 = {s: sma(C[s], 200) for s in syms}
def atr(s, k=14):
    tr = np.maximum(H[s] - L[s], np.maximum(abs(H[s] - np.roll(C[s], 1)), abs(L[s] - np.roll(C[s], 1)))); return sma(tr, k)
A = {s: atr(s) for s in syms}
HI20 = {s: np.array([np.nanmax(H[s][max(0, i-19):i+1]) for i in range(n)]) for s in syms}
M60 = {s: C[s] / np.roll(C[s], 60) - 1 for s in syms}
def run(pull, regime, stop_atr=2.0, tgt_atr=4.0, hold=15, cooldown=5, maxpos=8, risk=0.01, cap=0.15, start=250):
    eq = 1.0; cash = 1.0; pos = {}; cool = {}; curve = []; trades = []
    for i in range(start, n):
        # exits using today's bar
        for s, p in list(pos.items()):
            o, h, l, c = O[s][i], H[s][i], L[s][i], C[s][i]
            if np.isnan(c): continue
            ex = None
            if l <= p["stop"]: ex = min(o, p["stop"]); cool[s] = i + cooldown
            elif h >= p["tgt"]: ex = max(o, p["tgt"])
            elif i - p["i"] >= hold: ex = c
            if ex is not None: cash += p["q"] * ex * 0.9997; trades.append(p["q"] * (ex * 0.9997 - p["e"])); del pos[s]
        # entries: signal from yesterday's close (index i-1), fill today's open
        eqn = cash + sum(p["q"] * C[s][i] for s, p in pos.items() if not np.isnan(C[s][i]))
        j = i - 1; ok_mkt = (not regime) or (C["SPY"][j] > S50["SPY"][j])
        if ok_mkt and len(pos) < maxpos:
            cands = []
            for s in syms:
                if s in pos or cool.get(s, 0) > i or np.isnan(S200[s][j]) or np.isnan(O[s][i]): continue
                if not (C[s][j] > S200[s][j] and S50[s][j] > S200[s][j]): continue
                if C[s][j] > HI20[s][j] - pull * A[s][j] or C[s][j] < S50[s][j] - .5 * A[s][j]: continue
                cands.append((M60[s][j], s))
            for _, s in sorted(cands, reverse=True)[: maxpos - len(pos)]:
                e = O[s][i] * 1.0003; stp = e - stop_atr * A[s][j]; tg = e + tgt_atr * A[s][j]
                q = min(eqn * risk / (e - stp), cap * eqn / e, cash / e)
                if q * e > 25 / 5000 * eqn: cash -= q * e; pos[s] = {"q": q, "e": e, "stop": stp, "tgt": tg, "i": i}
        curve.append(cash + sum(p["q"] * C[s][i] for s, p in pos.items() if not np.isnan(C[s][i])))
    c = np.array(curve); yrs = len(c) / 252; dd = (c / np.maximum.accumulate(c) - 1).min()
    spy = C["SPY"][start:]; 
    return {"CAGR": (c[-1] ** (1 / yrs) - 1) * 100, "maxDD": dd * 100, "trades": len(trades), "win%": np.mean(np.array(trades) > 0) * 100, "SPY_CAGR": ((spy[-1] / spy[0]) ** (1 / yrs) - 1) * 100,
            "SPY_DD": ((spy / np.maximum.accumulate(spy)) - 1).min() * 100, "yrs": yrs}
for pull in (1.0, 1.5, 2.0):
    for reg in (False, True):
        r = run(pull, reg); print(f"pullback {pull} ATR, market filter {reg!s:5}: CAGR {r['CAGR']:5.1f}% maxDD {r['maxDD']:6.1f}% trades {r['trades']:4d} win {r['win%']:3.0f}%  | SPY CAGR {r['SPY_CAGR']:4.1f}% DD {r['SPY_DD']:5.1f}% ({r['yrs']:.1f}y)")
