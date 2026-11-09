# Mechanical paper trader (no real orders)
- `engine.py`: two accounts (Playbook rules, Max-ROI rules) on the same data. Each run replays every 5-minute bar since the last run.
- `config/`: universe, playbook.json (your rules + gate lines, refresh the stale ones), maxroi.json, swarm.json (veto/regime), earnings.json.
- `backtest_maxroi.py`: 9-year daily sanity check of the Max-ROI rules (survivorship-biased universe).
- `run_live.py`: one live run + dashboard rebuild. First run starts both accounts at $5,000 from now.
- Replay test: `TRADER_STATE=$PWD/state_replay python3 engine.py --replay-from 2026-10-12 --reset`
