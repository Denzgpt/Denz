"""Black-Scholes reprice of the TTWO Mar-19-2027 $230 call across earnings-day moves. IV/greeks from IBKR snapshot, rate 4% assumed."""
import math, datetime as dt, json
from statistics import NormalDist
N = NormalDist().cdf
def bs(S, K, T, v, r=0.04):
    d1 = (math.log(S / K) + (r + v * v / 2) * T) / (v * math.sqrt(T)); d2 = d1 - v * math.sqrt(T)
    return S * N(d1) - K * math.exp(-r * T) * N(d2)
S0, K, iv = 218.04, 230.0, 0.5016
T = (dt.date(2027, 3, 19) - dt.date(2026, 11, 10)).days / 365
base = bs(S0, K, (dt.date(2027, 3, 19) - dt.date(2026, 11, 9)).days / 365, iv); cost = 21.69; px = 21.34
print(f"model {base:.2f} vs market mid 21.2; position value ${px*100:,.0f}, cost ${cost*100:,.0f}")
print("stock move | stock | call @IV-0pt | P&L$ vs now | call @IV-3pt | P&L$ vs now")
for m in (-0.15, -0.10, -0.081, -0.05, -0.03, 0, 0.03, 0.05, 0.06, 0.10, 0.14, 0.20):
    S = S0 * (1 + m); a = bs(S, K, T, iv); b = bs(S, K, T, iv - 0.03)
    print(f"{m*100:+6.1f}%  {S:7.2f}   {a:6.2f}   {(a-px)*100:+8.0f}   {b:6.2f}   {(b-px)*100:+8.0f}")
