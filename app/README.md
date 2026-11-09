# Holdings Forecast (read-only)

Live per-holding forecast dashboard, tabs per asset group. **No order placement exists in this code.**

## Run (on your own machine, so data is live)
    python3 -m pip install numpy
    python3 app/server.py 8765      # open http://localhost:8765

## Real Kronos model (recommended)
    cd app && git clone https://github.com/shiyu-coder/Kronos
    pip install torch pandas huggingface_hub einops safetensors
Restart the server; the badge flips from `monte-carlo` to `kronos-small`. Until then a bootstrapped
Monte Carlo fallback (same UI) is used and the page says so.

## Staying fresh
Prices poll every 10s, forecasts recompute on each new bar (cached 5 min), every card shows "price as of",
and turns amber when data is stale/market closed. Free Yahoo data can be ~15 min delayed on some exchanges.

## Holdings & groups
`holdings.json` is a snapshot of the IBKR positions. New entries are grouped automatically (`groups.py`:
sector map, ETF keywords, else a new "Other stocks" group). Override with `groups_override.json`
(`{"SYMBOL": "Group name"}`). Options are forecast via their underlying with the strike drawn.
