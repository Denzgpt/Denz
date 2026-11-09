"""Forecasters. Kronos if installed (see README), otherwise a bootstrapped Monte Carlo fallback.
Both return the same shape: horizon bars x N sampled close paths + OHLC median bars."""
import os, sys, math, numpy as np
KRONOS_DIR = os.path.join(os.path.dirname(__file__), "Kronos")
KRONOS_N = int(os.environ.get('KRONOS_SAMPLES', 60))
_kronos = {"tried": False, "pred": None, "err": None}

def _load_kronos():
    if _kronos["tried"]: return _kronos["pred"]
    _kronos["tried"] = True
    try:
        if not os.environ.get("USE_KRONOS"):
            raise RuntimeError("Kronos is installed but off by default: in a 96-test walk-forward it predicted -5.8% on average against 0.0% realised and was heavily overconfident (see README). Set USE_KRONOS=1 to try it.")
        if not os.path.isdir(KRONOS_DIR): raise RuntimeError("Kronos/ not cloned")
        sys.path.insert(0, KRONOS_DIR)
        from model import Kronos, KronosTokenizer, KronosPredictor  # type: ignore
        tok = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
        mdl = Kronos.from_pretrained("NeoQuasar/Kronos-small")
        _kronos["pred"] = KronosPredictor(mdl, tok, max_context=512)
    except Exception as e:
        _kronos["err"] = str(e)
    return _kronos["pred"]

def engine_status():
    p = _load_kronos()
    return {"engine": "kronos-small" if p else "monte-carlo", "note": None if p else _kronos["err"]}

def _mc(closes, horizon, n):
    r = np.diff(np.log(closes))[-300:]
    r = r - r.mean() * 0.5                      # shrink drift: don't extrapolate trends
    rng = np.random.default_rng()
    vol = np.array([r[-20:].std(), r.std()]).mean()
    # bootstrap returns, rescaled to blended vol; block size 3 keeps some clustering
    idx = rng.integers(0, len(r) - 3, size=(n, math.ceil(horizon / 3)))
    blocks = np.concatenate([r[idx + k][..., None] for k in range(3)], axis=-1).reshape(n, -1)[:, :horizon]
    blocks = blocks / (r.std() or 1) * vol
    return closes[-1] * np.exp(np.cumsum(blocks, axis=1))

def _future_stamps(ts, horizon, step):
    """Future bar times that follow the market's own calendar: business days for daily bars; for intraday bars the
    time-of-day pattern of the latest full session repeated on following business days (no overnight or weekend bars)."""
    import pandas as pd
    if step != "1h": return pd.Series(pd.bdate_range(ts.iloc[-1], periods=horizon + 1)[1:])
    last_day = ts.iloc[-1].normalize(); pattern = sorted({(t.hour, t.minute) for t in ts[ts.dt.normalize() == last_day]}) or [(14, 30)]
    prev = ts[ts.dt.normalize() < last_day]
    if prev.size and len(pattern) < 5:
        pd_day = prev.iloc[-1].normalize(); pattern = sorted({(t.hour, t.minute) for t in prev[prev.dt.normalize() == pd_day]}) or pattern
    out, day, last = [], last_day, ts.iloc[-1]
    while len(out) < horizon:
        for hh, mm in pattern:
            t = day + pd.Timedelta(hours=hh, minutes=mm)
            if t > last: out.append(t)
            if len(out) >= horizon: break
        day = day + pd.offsets.BDay(1)
    return pd.Series(out[:horizon])

def _kronos_paths(df, ts, horizon, n, step):
    """n independent sampled paths in ONE batched pass (predict() would average samples; predict_batch keeps them apart)."""
    import pandas as pd
    pred = _load_kronos()
    future = _future_stamps(ts, horizon, step)
    outs = pred.predict_batch([df] * n, [ts] * n, [future] * n, pred_len=horizon, T=1.0, top_p=0.9, sample_count=1, verbose=False)
    return np.array([o["close"].to_numpy() for o in outs])

def forecast(bars, horizon=24, n=400, step="1h"):
    closes = np.array([b["c"] for b in bars], dtype=float)
    if len(closes) < 60: raise ValueError("not enough history")
    eng = engine_status()
    if eng["engine"] == "kronos-small":
        import pandas as pd
        df = pd.DataFrame(bars[-512:]).rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
        df["amount"] = df["close"] * df["volume"]
        ts = pd.to_datetime(df.pop("t"), unit="s")
        paths = _kronos_paths(df[["open", "high", "low", "close", "volume", "amount"]], ts, horizon, min(n, KRONOS_N), step)
    else:
        paths = _mc(closes, horizon, n)
    q = lambda p: np.percentile(paths, p, axis=0)
    last = closes[-1]
    return {**eng, "horizon": horizon, "samples": paths.shape[0], "last": last,
            "_np": paths, "paths": np.round(paths[:100], 4).tolist(),
            "median": np.round(q(50), 4).tolist(), "p10": np.round(q(10), 4).tolist(), "p90": np.round(q(90), 4).tolist(),
            "probUp": float((paths[:, -1] > last).mean()),
            "expMovePct": float((np.median(paths[:, -1]) / last - 1) * 100)}


# ---------------------------------------------------------------------------
# Scenario analysis: "most likely outcome" from holistic evidence, not the median.
# ---------------------------------------------------------------------------
SCEN = ["Selloff", "Drifts lower", "Sideways", "Drifts higher", "Rally"]
VERB = ["sells off", "drifts lower", "moves sideways", "drifts higher", "rallies"]
EDGES = np.array([-1.0, -0.35, 0.35, 1.0])      # in units of sigma_h (typical move over the horizon)
DIRS = np.array([-1, -.5, 0, .5, 1.0])

def _sigma_h(closes, horizon):
    r = np.diff(np.log(closes[-80:]))
    return max(r.std(), 1e-6) * math.sqrt(horizon)

def _rsi(c, n=14):
    d = np.diff(c[-(n * 4):]); up = np.clip(d, 0, None); dn = -np.clip(d, None, 0)
    au, ad = up[:n].mean(), dn[:n].mean()
    for u, v in zip(up[n:], dn[n:]):
        au, ad = (au * (n - 1) + u) / n, (ad * (n - 1) + v) / n
    return 100.0 if ad == 0 else 100 - 100 / (1 + au / ad)

def evidence(closes, horizon):
    c = np.asarray(closes, float); sv = np.diff(np.log(c[-80:])).std()
    sma = c[-50:].mean()
    trend = float(np.clip(np.log(c[-1] / sma) / (2 * sv * math.sqrt(50)), -1, 1))
    rsi = _rsi(c)
    rev = float(np.clip((50 - rsi) / 30, -1, 1)) if (rsi < 35 or rsi > 65) else 0.0   # only at extremes
    tilt = 0.6 * trend + 0.4 * rev
    return {"trend": round(trend, 2), "rsi": round(float(rsi), 1), "reversion": round(rev, 2), "tilt": round(tilt, 2),
            "volPerBarPct": round(float(sv) * 100, 3)}

def scenario_probs(paths, closes, horizon, tilt=0.0, event_shrink=0.0):
    last = closes[-1]; s = _sigma_h(np.asarray(closes), horizon)
    z = np.log(paths[:, -1] / last) / s
    b = np.digitize(z, EDGES)
    p = np.bincount(b, minlength=5) / len(b)
    p = p * np.exp(0.35 * tilt * DIRS); p /= p.sum()           # modest evidence tilt (max ~ +/-35% relative)
    if event_shrink: p = (1 - event_shrink) * p + event_shrink / 5
    return p, b, s

def analyse(paths, closes, horizon, events=None, calib=None, sym="", unit="hours"):
    paths = np.asarray(paths); closes = np.asarray(closes, float); last = closes[-1]
    ev = evidence(closes, horizon)
    p, b, s = scenario_probs(paths, closes, horizon, ev["tilt"], 0.15 if events else 0.0)
    k = int(p.argmax()); raw = float(p[k]); top = _calibrated_top(raw, calib)
    if events: top = 0.85 * top + 0.15 * 0.2          # event risk pulls the call toward "anyone's guess"
    rest = np.delete(p, k); rest = rest / rest.sum() * (1 - top)
    pc = np.insert(rest, k, top)                      # headline and bar now agree
    sc = []
    for i in range(5):
        m = b == i; lo_z = -np.inf if i == 0 else EDGES[i - 1]; hi_z = np.inf if i == 4 else EDGES[i]
        sc.append({"name": SCEN[i], "prob": round(float(pc[i]), 4), "n": int(m.sum()),
                   "from": None if i == 0 else round(last * math.exp(lo_z * s), 4),
                   "to": None if i == 4 else round(last * math.exp(hi_z * s), 4),
                   "path": np.round(paths[m].mean(axis=0), 4).tolist() if m.any() else None})
    conf = "Strong signal" if top >= 0.45 else "Moderate signal" if top >= 0.32 else "Weak signal"
    skill = (calib or {}).get("skill")
    T = sc[k]; rng = f"{T['from'] or 0:.2f}" if T["from"] else "below"
    why = []
    if ev["trend"] <= -0.25: why.append("trend is down")
    elif ev["trend"] >= 0.25: why.append("trend is up")
    if ev["rsi"] < 35: why.append("it looks oversold")
    elif ev["rsi"] > 65: why.append("it looks stretched")
    if not why: why.append("no strong trend or stretch")
    lead = f"{sym or 'It'} most likely {VERB[k]} over the next {horizon} {unit}, about a {round(top*100)}% chance"
    summ = lead + f" ({', '.join(why)})."
    if events: summ += " Event risk in the window lowers confidence."
    if calib and calib.get("n"):
        verdict = "slightly better than" if (skill or 0) > 0.003 else "no better than"
        summ += f" Over {calib['n']:,} past walk-forward tests this method has been {verdict} guessing from history alone."
    return {"scenarios": sc, "top": k, "topName": SCEN[k], "topProb": round(float(top), 4), "topProbRaw": round(raw, 4),
            "confidence": conf, "summary": summ, "evidence": ev, "events": events or [], "calibration": calib}

def calibrate(closes, horizon, step=1, n=300, start=250, per_year=252):
    """Deep walk-forward backtest. At EVERY bar t (>= start) uses only data up to t, runs the same pipeline
    (bootstrapped paths -> evidence tilt -> scenario probabilities), then scores against what happened
    `horizon` bars later. Returns hit-rate of the favoured scenario, a reliability table, and log-loss skill
    versus a baseline that only knows the historical scenario frequencies (expanding window)."""
    c = np.asarray(closes, float); P = []; Real = []
    for t in range(start, len(c) - horizon, step):
        hist = c[: t + 1]; paths = _mc(hist, horizon, n)
        ev = evidence(hist, horizon); p, _, sg = scenario_probs(paths, hist, horizon, ev["tilt"])
        P.append(p); Real.append(int(np.digitize(math.log(c[t + horizon] / c[t]) / sg, EDGES)))
    if len(P) < 60: return None
    P = np.array(P); R = np.array(Real); top = P.argmax(1); ptop = P.max(1); hit = top == R
    # baseline: expanding class frequencies (Laplace), no lookahead
    cnt = np.ones(5); ll_m = ll_b = 0.0
    for i in range(len(R)):
        ll_m -= math.log(max(P[i, R[i]], 1e-3)); ll_b -= math.log(cnt[R[i]] / cnt.sum()); cnt[R[i]] += 1
    edges = [0.0, .25, .30, .35, .40, .50, 1.01]; rel = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (ptop >= lo) & (ptop < hi)
        if m.sum() >= 15: rel.append({"lo": lo, "hi": hi, "n": int(m.sum()), "stated": round(float(ptop[m].mean()), 3), "realized": round(float(hit[m].mean()), 3)})
    freq = np.bincount(R, minlength=5) / len(R)
    return {"n": int(len(R)), "years": round(len(R) * step / per_year, 1),
            "realized": round(float(hit.mean()), 3), "stated": round(float(ptop.mean()), 3),
            "alwaysRange": round(float(freq[2]), 3), "bestConstant": round(float(freq.max()), 3),
            "skill": round(1 - ll_m / ll_b, 4), "reliability": rel}

def _calibrated_top(raw, calib):
    """Map the model's stated top-probability to the frequency it actually delivered in that band."""
    rel = (calib or {}).get("reliability") or []
    if not rel: return raw
    pts = [(r["stated"], r["realized"], r["n"]) for r in rel]
    if raw <= pts[0][0]: return pts[0][1]
    if raw >= pts[-1][0]: return pts[-1][1]
    for (x0, y0, _), (x1, y1, _) in zip(pts, pts[1:]):
        if x0 <= raw <= x1: return y0 + (y1 - y0) * (raw - x0) / max(x1 - x0, 1e-9)
    return raw
