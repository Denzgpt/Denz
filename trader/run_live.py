#!/usr/bin/env python3
"""One hourly live run: replay new 5-minute bars into the two paper accounts, then rebuild the dashboard page.
The scheduled Claude session first refreshes config/swarm.json (veto + regime) from news/calendar, then runs this."""
import os, subprocess, sys, shutil
try:
    import numpy  # noqa: F401
except ImportError:  # default python3 may lack numpy; re-run under one that has it
    for c in ("python3.13", "python3.12", "python3.11", "python3.14"):
        exe = shutil.which(c)
        if exe and exe != sys.executable and subprocess.run([exe, "-c", "import numpy"], capture_output=True).returncode == 0:
            os.execv(exe, [exe] + sys.argv)
    sys.exit("numpy not found in any python3.x interpreter on PATH; install it with: pip install numpy")
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import engine
accts, B = engine.run()                      # forward run on trader/state (created on first run)
for k, a in accts.items(): print(k, f"equity {a.equity():.2f} positions {list(a.pos)} trades {len(a.trades)}")
subprocess.run([sys.executable, os.path.join(HERE, "build_dashboard.py"), os.path.join(HERE, "state"), "Live"], check=True)
