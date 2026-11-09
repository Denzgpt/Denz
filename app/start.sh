#!/usr/bin/env bash
# One command to run the live forecast app on your own machine:  ./app/start.sh
set -e
cd "$(dirname "$0")"
python3 -m pip install -q -r requirements.txt
[ -d Kronos ] || git clone --depth 1 https://github.com/shiyu-coder/Kronos Kronos
echo "Open http://localhost:8765"
exec python3 server.py 8765
