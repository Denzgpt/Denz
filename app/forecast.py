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

def forecast(bars, horizon=24, n=100, step="1h"):
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
            "paths": np.round(paths[:100], 4).tolist(),
            "median": np.round(q(50), 4).tolist(), "p10": np.round(q(10), 4).tolist(), "p90": np.round(q(90), 4).tolist(),
            "probUp": float((paths[:, -1] > last).mean()),
            "expMovePct": float((np.median(paths[:, -1]) / last - 1) * 100)}
