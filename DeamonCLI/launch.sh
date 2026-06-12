#!/usr/bin/env bash
export DISPLAY="${DISPLAY:-:0}"

# Auto-detect: use ~/.local/share/deamoncli if installed, otherwise use this script's directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$HOME/.local/share/deamoncli/linux_ref.py" ]; then
    INSTALL_DIR="$HOME/.local/share/deamoncli"
else
    INSTALL_DIR="$SCRIPT_DIR"
fi
CONFIG="$HOME/.config/deamoncli/config.json"

# Start tray icon in background if not already running
if ! pgrep -f "tray.py" > /dev/null 2>&1; then
    DISPLAY=:0 python3 "$INSTALL_DIR/tray.py" &
fi

GEOMETRY=$(python3 -c "
import json
try:
    d = json.load(open('$CONFIG'))
    g = d.get('geometry', '')
    if g: print(g)
except: pass
" 2>/dev/null)

if [ -n "$GEOMETRY" ]; then
    gnome-terminal --class=DeamonCLI --geometry="$GEOMETRY" --title="DeamonCLI" \
        -- bash -c "python3 $INSTALL_DIR/linux_ref.py"
else
    gnome-terminal --class=DeamonCLI --maximize --title="DeamonCLI" \
        -- bash -c "python3 $INSTALL_DIR/linux_ref.py"
fi
