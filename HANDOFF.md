# Handoff: forecast app, paper trader and daily predictions

Built in one long chat (Nov 9-15, 2026) for Denzel. Everything is read-only: no code here places, changes or cancels a real order.

## What exists

| Piece | Where | State |
|---|---|---|
| Daily Predictions page (frozen snapshot, rebuilt each weekday) | artifact https://claude.ai/artifact/BrFFpp45ZJt5zNswZeQtLq , built by `app/build_demo.py` | working |
| Live Holdings Forecast (reads IBKR positions and prices in the browser through the artifact `mcp` capability, read-only tools only) | artifact https://claude.ai/artifact/4X3K632zxgL762DcUE5Dmy , built by `app/build_live.py` | tested only with mock IBKR data, never with the real connection |
| Swarm Trader Desk dashboard (two mock accounts, replay at first, live since 9 Nov) | artifact https://claude.ai/artifact/YHojKKq3YUtJKsdu6f3LY7 , built by `trader/build_dashboard.py` | working |
| Forecast engine | `app/forecast.py` (bootstrapped Monte Carlo, evidence tilt, scenario probabilities mapped to walk-forward results), `app/server.py` (local live server), `app/start.sh` | working |
| Mechanical paper trader | `trader/engine.py`, `trader/config/*.json`, state on branch `trader-state` (`trader/state/`) | working |
| TTWO studies | `backtests/` (earnings moves, game launches, option scenarios, strike probability) | done |

## Scheduled tasks (claude.ai routines). Since 23 Nov all fire into the chat "Portfolio MD with Code" (session_01X4RgXcbjSBdR6QzY5Q7T68)

- `trig_01ECXT1U1Bk3sg9a8jaRwht4` Daily predictions: weekdays 08:37 New York (about 50 min before the US open). Runs `python3 app/run_daily.py`, publishes both forecast artifacts from that chat, sends a push, replies with the calls. No NBIS in the message. No images or files, by his choice.
- `trig_01D9A6C9J8xrHwjiheoTiVdg` Swarm trader hourly run: weekdays 08:07-21:07 UTC (Swiss and US hours). Replays 5-minute bars into both accounts, pushes state to branch `trader-state`, republishes the desk artifact. Silent: one-line reply, no notification.
- `trig_01C6U2CU1RJofoTGMjYjFrju` Swarm trader daily overview: weekdays 21:37 UTC, chat reply plus a push.
- Disabled (they ran as separate sessions, whose pushes never reached him): `trig_011mT8LEACNAwPo6VoyXnPmz`, `trig_01Vbhvb3Tik3pKzffW8TZgpR`, `trig_01RbiFNAEirJu14wzrnfR7RV`, `trig_01FWt1f9QwA82WKmy8GFg9cR`.
- That chat also holds older, separate jobs: the LLM-judgement "Paper Trader: autonomous mock trading" (ledger.py, artifact SvT6ysWDeMthuG3qeKrWcL), The Desk nightly bots, and the silent hourly gate watch. They are a different paper account from the mechanical Playbook and Max-ROI accounts here. Do not mix their state.
- A push sent from a chat reaches his phone (tested). Pushes from separate routine sessions did not.

## Decisions and preferences from the chat

- Read-only for now. Never place orders.
- Deliverables are artifacts, not slides, images or files.
- Swiss (SIX) and US trading hours. USD account, CHF converted at the live rate.
- Predictions: always name the most likely scenario with its probability, not the median. Wording: Selloff, Drifts lower, Sideways, Drifts higher, Rally. Conviction: Strong, Moderate, Weak signal.
- Two paper accounts side by side: "Playbook" (his Trading Playbook rules, coded) and "Max-ROI". The swarm can veto and add reasons but cannot trade.
- The older Paper Trader (hourly LLM judgement, artifact SvT6ysWDeMthuG3qeKrWcL) and The Desk (CnSAvw4myreyWWn5hgAerw) live in the chat "Portfolio MD with Code" and were left untouched.

## Known issues and open questions

1. The forecast method has little proven edge. Walk-forward tests show about 22-31% for the favoured scenario against about 30% for guessing from history. Most calls are "Weak signal". This is stated on the pages.
2. Kronos (the real model) works but has a strong downward bias (-5.8% predicted against 0.0% realised, 96 tests). It is off by default (`USE_KRONOS=1` turns it on). The per-holding bias-correction run died with a session restart and was not redone (`app/kronos_backtest.py`, now with results only saved at the end: fix that first).
3. The live page's IBKR connection is unverified with real data.
4. Daily push notification delivery is unverified. The routine runs and republishes, but the cloud session cannot git push (403), so the repo is not updated by the routines.
5. `app/holdings.json` is a static snapshot of the IBKR positions. Events and earnings dates (`app/events.json`, `trader/config/earnings.json`, `trader/config/swarm.json`) are hand-maintained.
6. The Portfolio MD chat has a standing rule not to mention NBIS. These pages list NBIS because it is in his IBKR holdings. Ask him whether to exclude it.
7. Roche (`ROG.SW`) fails to load from Yahoo and is skipped. Yahoo data can be delayed.

## Run it

    python3 app/server.py 8765            # local live forecast app (or ./app/start.sh)
    python3 app/run_daily.py              # rebuild both forecast pages, print today's calls
    python3 trader/run_live.py            # one live paper-trader run (state under trader/state)
    TRADER_STATE=$PWD/state_replay python3 trader/engine.py --replay-from 2026-10-12 --reset   # replay test
