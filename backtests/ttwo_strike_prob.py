import json, math, datetime as dt, numpy as np
from statistics import NormalDist
N = NormalDist().cdf
def bs(S, K, T, v, r=0.04):
    d1 = (math.log(S / K) + (r + v * v / 2) * T) / (v * math.sqrt(T)); return S * N(d1) - K * math.exp(-r * T) * N(d1 - v * math.sqrt(T))
S0, K, cost, exp = 218.04, 230.0, 21.69, dt.date(2027, 3, 19)
d = json.load(open("TTWO_daily.json")); a = np.array([x for x in d["adj"] if x]); r = np.diff(np.log(a))[-2500:]   # ~10y of daily log returns
today = dt.date(2026, 11, 10); n_exp = int(np.busday_count(today, exp)); n_wk = int(np.busday_count(today, dt.date(2026, 11, 26)))
rng = np.random.default_rng(1); N_P = 100000
def sims(kind, vol=None):
    if kind == "hist":   # bootstrap TTWO's own 10y daily returns, de-meaned (no assumed drift)
        x = rng.choice(r - r.mean(), size=(N_P, n_exp))
    else:                # lognormal at a given annual vol, zero drift
        x = rng.normal(0, vol / math.sqrt(252), size=(N_P, n_exp))
    return S0 * np.exp(np.cumsum(x, axis=1))
print(f"trading days to expiry {n_exp}, to 26 Nov {n_wk}; hist daily vol {r.std()*math.sqrt(252)*100:.0f}% annualised")
for lab, p in (("TTWO own history (bootstrap)", sims("hist")), ("lognormal 37% (30d realised)", sims("ln", .37)), ("lognormal 50% (option IV)", sims("ln", .50))):
    be = K + cost
    print(f"{lab:32} P(close>230 at expiry)={np.mean(p[:,-1]>K)*100:4.1f}%  P(>={be:.1f} breakeven at expiry)={np.mean(p[:,-1]>be)*100:4.1f}%  "
          f"P(touch 230 any day)={np.mean(p.max(1)>=K)*100:4.1f}%  P(>230 on 26 Nov)={np.mean(p[:,n_wk-1]>K)*100:4.1f}%  P(>=breakeven price 26 Nov @IV45)=see below")
# break-even stock price (option worth its $21.69 cost) 1 week after launch (Thu 26 Nov), by IV level
T = (exp - dt.date(2026, 11, 26)).days / 365
print("\nBreak-even stock price on 26 Nov (call must be worth $21.69 = what you paid):")
for iv in (.55, .50, .45, .40, .35):
    lo, hi = 150, 400
    for _ in range(60):
        m = (lo + hi) / 2
        lo, hi = (m, hi) if bs(m, K, T, iv) < cost else (lo, m)
    print(f"  IV {iv*100:.0f}%: ${m:6.2f}  ({(m/S0-1)*100:+.1f}% vs $218.04)")
print("Break-even at expiry: $%.2f (%.1f%%)" % (K + cost, ((K + cost) / S0 - 1) * 100))
