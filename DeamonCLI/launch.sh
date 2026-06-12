#!/usr/bin/env bash
export DISPLAY="${DISPLAY:-:0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$HOME/.local/share/deamoncli/linux_ref.py" ]; then
    INSTALL_DIR="$HOME/.local/share/deamoncli"
else
    INSTALL_DIR="$SCRIPT_DIR"
fi
CONFIG="$HOME/.config/deamoncli/config.json"
SESSION="deamoncli"

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

GEOM_ARG=""
[ -n "$GEOMETRY" ] && GEOM_ARG="--geometry=$GEOMETRY"

if command -v tmux &>/dev/null; then
    # Existing session → reattach; otherwise start fresh
    if ! tmux has-session -t "$SESSION" 2>/dev/null; then
        tmux new-session -d -s "$SESSION" -x 220 -y 50 \
            "TERM=xterm-256color python3 $INSTALL_DIR/linux_ref.py"
    fi
    gnome-terminal --class=DeamonCLI $GEOM_ARG --title="DeamonCLI" \
        -- tmux attach-session -t "$SESSION"
else
    # No tmux — run directly (install tmux so X keeps the app alive)
    gnome-terminal --class=DeamonCLI $GEOM_ARG --maximize --title="DeamonCLI" \
        -- bash -c "python3 $INSTALL_DIR/linux_ref.py"
fi
