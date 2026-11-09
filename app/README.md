# Holdings Forecast (read-only, live)

Per-holding forecast dashboard: most likely scenario + probability, chart with levels and event markers.
**No order placement exists in this code.**

## Run it (your own machine, so prices are live)
    ./app/start.sh          # installs deps, clones Kronos once, serves http://localhost:8765

The first Kronos forecast downloads the model weights (~100 MB) from Hugging Face. On CPU a forecast of
60 sampled paths takes roughly 10-60 s per holding (cached for 5 min); set `KRONOS_SAMPLES` to change it.
Without Kronos installed the app falls back to a Monte Carlo and says so on the page.

## What feeds each call
- Sampled price paths from Kronos (or the Monte Carlo fallback), tilted slightly by trend and RSI.
- Events: `events.json` (macro), `../trader/config/earnings.json` (earnings) and `../trader/config/swarm.json` (swarm vetoes). Anything inside the forecast window lowers confidence and is drawn on the chart.
- Probabilities are mapped to what each confidence band really delivered in a walk-forward backtest (`forecast.calibrate`).

## Staying fresh
Prices poll every 10 s, forecasts recompute on each new bar, every card shows "price as of", amber when stale.
`holdings.json` is a snapshot of your IBKR positions; new entries are grouped automatically (`groups.py`).

## Demo page
`python3 app/build_demo.py` freezes the app into `demo/artifact.html`.

## Kronos: tested, experimental
Walk-forward test (`kronos_backtest.py`, QQQ/NVDA/JPM, 96 dates, 10-day horizon, 16 sampled paths each, data up to each date only):

| | Median-return direction right | Correlation with outcome | Mean predicted vs realised | Top-scenario hit vs claimed |
|---|---|---|---|---|
| Kronos-small (raw) | 56% | +0.23 | -5.8% vs 0.0% | 17% vs 57% |
| Monte Carlo fallback | 44% | -0.17 | +0.6% vs 0.0% | 26% vs 29% |

Kronos has a strong built-in downward bias (NVDA -11.5% on average) and is far too confident, so its raw probabilities are not used.
There is a weak relative signal: after a higher-than-usual Kronos forecast the next 10 days averaged +0.66%, after a lower one -0.62% (small sample).
It stays off unless you set `USE_KRONOS=1`. To use it properly it needs a per-holding bias correction from its own walk-forward run (about 6 minutes per holding on CPU) or fine-tuning (`Kronos/finetune`).
