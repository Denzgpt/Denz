"""Auto-assign holdings to groups; unknown names create a new group. Overrides in groups_override.json."""
import json, os
HERE = os.path.dirname(__file__)
SECTOR = {  # curated sector map for common tickers (extend freely)
 "Tech & AI": "NVDA AMD INTC AVGO TSM MU ARM QCOM MSFT GOOGL GOOG META AMZN AAPL ORCL CRM PLTR PANW NBIS CRWV SMCI ASML SAP SNOW NOW ADBE TSLA NFLX".split(),
 "Gaming & Media": "TTWO EA RBLX U NTDOY DIS WBD SPOT".split(),
 "Financials": "JPM BAC GS MS C WFC V MA BRK.B UBSG UBS HSBA UCG ISP BAMI CBK SAN BBVA ".split(),
 "Energy": "XOM CVX COP OXY SLB XLE".split(),
 "Healthcare": "LLY UNH JNJ PFE MRK ABBV NVO XLV".split(),
 "Industrials & Materials": "CAT DE BA GE ACX RIO BHP FCX NUE X MT".split(),
 "Consumer": "WMT COST HD MCD NKE KO PEP PG".split(),
}
ETF = {  # (group, keywords in name or ticker)
 "Gold & Commodities": ["AAAU", "GLD", "IAU", "SLV", "GDX", "USO", "DBC", "GOLD", "SILVER", "COMMODIT"],
 "Income ETFs": ["QQQI", "JEPI", "JEPQ", "SCHD", "SPYI", "DIVO", "HIGH INCOME", "COVERED CALL", "DIVIDEND"],
 "Broad Market ETFs": ["VT", "QQQ", "SPY", "VOO", "VTI", "IVV", "IWM", "VWO", "VEA", "EEM", "ACWI", "TOTAL WORLD", "EMERGING", "NASDAQ-100", "S&P 500"],
 "Bonds & Cash ETFs": ["TLT", "BND", "AGG", "SHY", "BIL", "TREASURY", "BOND"],
 "Crypto": ["IBIT", "BITO", "FBTC", "ETHA", "BTC", "ETH", "BITCOIN", "ETHEREUM"],
}
def _base(sym): return sym.split(".")[0].split(" ")[0].upper()

def classify(h, meta=None):
    s, name = _base(h["symbol"]), (h.get("name") or "").upper()
    ytype = (meta or {}).get("type")
    for g, kws in ETF.items():
        if s in kws:
            return g
    if ytype == "ETF" or " ETF" in name or "TRUST" in name:
        for g, kws in ETF.items():
            if any(k in name for k in kws if len(k) > 4):
                return g
        return "Other ETFs"
    for g, syms in SECTOR.items():
        if s in [x.strip() for x in syms]:
            return g
    if ytype == "CRYPTOCURRENCY": return "Crypto"
    ex = ((meta or {}).get("exchange") or "").lower()
    cur = h.get("currency", "USD")
    return f"Other stocks ({cur})" if cur != "USD" else "Other stocks"

def assign(holdings, metas):
    try: ov = json.load(open(os.path.join(HERE, "groups_override.json")))
    except Exception: ov = {}
    out = {}
    for h in holdings:
        out[h["symbol"]] = ov.get(h["symbol"]) or classify(h, metas.get(h["yahoo"]))
    return out
