#!/usr/bin/env bash
CONFIG="$HOME/.config/deamoncli/config.json"
GEOMETRY=$(python3 -c "
import json, sys
try:
    d = json.load(open('$CONFIG'))
    g = d.get('geometry', '')
    if g: print(g)
except: pass
" 2>/dev/null)

if [ -n "$GEOMETRY" ]; then
    gnome-terminal --geometry="$GEOMETRY" --title="DeamonCLI" -- bash -c "cd /home/sebastian/Documents/APPS/MasterCLI && python3 linux_ref.py"
else
    gnome-terminal --maximize --title="DeamonCLI" -- bash -c "cd /home/sebastian/Documents/APPS/MasterCLI && python3 linux_ref.py"
fi
