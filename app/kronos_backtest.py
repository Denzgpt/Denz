"""Walk-forward test of Kronos vs the Monte Carlo fallback on daily bars (10-day horizon). Only data up to each test date is used."""
import sys, os, json, time, math, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(__file__)); os.environ.setdefault("KRONOS_SAMPLES", "16")
import data, forecast
syms = sys.argv[1].split(",") if len(sys.argv) > 1 else ["QQQ", "NVDA", "JPM"]; H = 10; N = int(os.environ.get("N", 16)); STEP = int(os.environ.get("STEP", 8)); OUTF = os.environ.get("OUTF", "kronos_backtest.json"); out = []
pred = forecast._load_kronos(); print("engine", forecast.engine_status(), flush=True)
for s in syms:
    b, _ = data.bars(s, "1d", "5y", ttl=3600); n = len(b); closes = np.array([x["c"] for x in b])
    for t in range(max(400, n - 260), n - H, STEP):
        hist = b[: t + 1]; df = pd.DataFrame(hist[-512:]).rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}); df["amount"] = df["close"] * df["volume"]
        ts = pd.to_datetime(df.pop("t"), unit="s")
        K = forecast._kronos_paths(df[["open", "high", "low", "close", "volume", "amount"]], ts, H, N, "1D")
        M = forecast._mc(closes[: t + 1], H, 300); last = closes[t]; real = closes[t + H] / last - 1
        sg = forecast._sigma_h(closes[: t + 1], H)
        rec = {"sym": s, "i": t, "real": float(real), "sg": float(sg)}
        for name, P in (("k", K), ("m", M)):
            rec[name + "_med"] = float(np.median(P[:, -1]) / last - 1); rec[name + "_pup"] = float((P[:, -1] > last).mean())
            z = np.log(P[:, -1] / last) / sg; pr = np.bincount(np.digitize(z, forecast.EDGES), minlength=5) / len(z); rec[name + "_top"] = int(pr.argmax()); rec[name + "_ptop"] = float(pr.max())
        rec["real_bin"] = int(np.digitize(math.log(1 + real) / sg, forecast.EDGES)); out.append(rec); print(s, t, round(real * 100, 1), round(rec["k_med"] * 100, 1), round(rec["m_med"] * 100, 1), flush=True)
json.dump(out, open(OUTF, "w"))
r = pd.DataFrame(out)
for k, lab in (("k", "Kronos"), ("m", "Monte Carlo")):
    sign = (np.sign(r[k + "_med"]) == np.sign(r.real)).mean(); corr = np.corrcoef(r[k + "_med"], r.real)[0, 1]
    print(f"{lab:12} n={len(r)} median-return sign right {sign*100:4.0f}%  corr {corr:+.2f}  mean predicted {r[k+'_med'].mean()*100:+.1f}% vs realised {r.real.mean()*100:+.1f}%  top-scenario hit {(r[k+'_top']==r.real_bin).mean()*100:4.0f}%  avg stated {r[k+'_ptop'].mean()*100:3.0f}%")
