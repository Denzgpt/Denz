"""Forecasters. Kronos if installed (see README), otherwise a bootstrapped Monte Carlo fallback.
Both return the same shape: horizon bars x N sampled close paths + OHLC median bars."""
import os, sys, math, numpy as np
KRONOS_DIR = os.path.join(os.path.dirname(__file__), "Kronos")
_kronos = {"tried": False, "pred": None, "err": None}

def _load_kronos():
    if _kronos["tried"]: return _kronos["pred"]
    _kronos["tried"] = True
    try:
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

def _kronos_paths(df, ts, horizon, n, step):
    import pandas as pd
    pred = _load_kronos()
    future = pd.Series(pd.date_range(ts.iloc[-1], periods=horizon + 1, freq=step)[1:])
    paths = []
    for _ in range(n):
        out = pred.predict(df=df, x_timestamp=ts, y_timestamp=future, pred_len=horizon, T=1.0, top_p=0.9, sample_count=1, verbose=False)
        paths.append(out["close"].to_numpy())
    return np.array(paths)

def forecast(bars, horizon=24, n=400, step="1h"):
    closes = np.array([b["c"] for b in bars], dtype=float)
    if len(closes) < 60: raise ValueError("not enough history")
    eng = engine_status()
    if eng["engine"] == "kronos-small":
        import pandas as pd
        df = pd.DataFrame(bars[-512:]).rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
        df["amount"] = df["close"] * df["volume"]
        ts = pd.to_datetime(df.pop("t"), unit="s")
        paths = _kronos_paths(df[["open", "high", "low", "close", "volume", "amount"]], ts, horizon, n, step)
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
SCEN = ["Sharp drop", "Grind lower", "Range-bound", "Grind higher", "Sharp rally"]
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

def analyse(paths, closes, horizon, events=None, calib=None):
    paths = np.asarray(paths); closes = np.asarray(closes, float); last = closes[-1]
    ev = evidence(closes, horizon)
    shrink = 0.15 if events else 0.0
    p, b, s = scenario_probs(paths, closes, horizon, ev["tilt"], shrink)
    k = int(p.argmax()); sc = []
    for i in range(5):
        m = b == i
        term = paths[m, -1] if m.any() else np.array([last * math.exp(s * (np.r_[-1.6, EDGES + 0, 1.6][i] if False else 0))])
        lo_z = -np.inf if i == 0 else EDGES[i - 1]; hi_z = np.inf if i == 4 else EDGES[i]
        sc.append({"name": SCEN[i], "prob": round(float(p[i]), 4), "n": int(m.sum()),
                   "from": None if i == 0 else round(last * math.exp(lo_z * s), 4),
                   "to": None if i == 4 else round(last * math.exp(hi_z * s), 4),
                   "path": np.round(paths[m].mean(axis=0), 4).tolist() if m.any() else None})
    top = float(p[k])
    raw = top
    if calib and calib.get("stated"):       # shrink to what past calls actually delivered
        top = top * float(np.clip(calib["realized"] / calib["stated"], 0.6, 1.2))
    conf = "Clear favorite" if top >= 0.45 else "Lean" if top >= 0.32 else "Toss-up"
    return {"scenarios": sc, "top": k, "topName": SCEN[k], "topProb": round(top, 4), "topProbRaw": round(raw, 4), "confidence": conf,
            "evidence": ev, "events": events or [], "calibration": calib}

def calibrate(closes, horizon, step=6, n=150, start=150):
    """Walk-forward check of the same pipeline: did the favoured scenario actually happen?"""
    c = np.asarray(closes, float); hits = []; probs = []; base = []
    for t in range(start, len(c) - horizon, step):
        hist = c[: t + 1]; paths = _mc(hist, horizon, n)
        ev = evidence(hist, horizon); p, _, s = scenario_probs(paths, hist, horizon, ev["tilt"])
        k = int(p.argmax()); z = math.log(c[t + horizon] / c[t]) / s
        real = int(np.digitize(z, EDGES)); hits.append(real == k); probs.append(p[k]); base.append(real == 2)
    if len(hits) < 12: return None
    return {"n": len(hits), "realized": round(float(np.mean(hits)), 3), "stated": round(float(np.mean(probs)), 3),
            "alwaysRange": round(float(np.mean(base)), 3)}
