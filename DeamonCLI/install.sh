#!/usr/bin/env bash
# DeamonCLI installer
# Usage:    bash install.sh
# Uninstall: bash install.sh --uninstall

set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'

ok()   { echo -e "  ${GREEN}✓${NC}  $*"; }
info() { echo -e "  ${CYAN}→${NC}  $*"; }
warn() { echo -e "  ${YELLOW}⚠${NC}   $*"; }
err()  { echo -e "  ${RED}✗${NC}  $*" >&2; }
step() { echo -e "\n${BOLD}$*${NC}"; }

INSTALL_DIR="$HOME/.local/share/deamoncli"
ICON_PATH="$HOME/.local/share/icons/deamoncli.png"
APPS_DIR="$HOME/.local/share/applications"
AUTOSTART_DIR="$HOME/.config/autostart"
DESKTOP_ENTRY="$APPS_DIR/deamoncli.desktop"
DESKTOP_SHORTCUT="$HOME/Desktop/deamoncli.desktop"
LAUNCH_SCRIPT="$HOME/.local/bin/deamoncli"
AUTOSTART_ENTRY="$AUTOSTART_DIR/deamoncli-tray.desktop"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Uninstall ──────────────────────────────────────────────────────────────────
if [[ "$1" == "--uninstall" ]]; then
    echo -e "\n${BOLD}Uninstalling DeamonCLI…${NC}"
    tmux kill-session -t deamoncli 2>/dev/null && ok "Stopped app session" || true
    pkill -f "deamoncli/tray.py" 2>/dev/null && ok "Stopped tray icon" || true
    rm -rf "$INSTALL_DIR"       && ok "Removed app files"
    rm -f  "$ICON_PATH"         && ok "Removed icon"
    rm -f  "$DESKTOP_ENTRY"     && ok "Removed app menu entry"
    rm -f  "$DESKTOP_SHORTCUT"  && ok "Removed desktop shortcut"
    rm -f  "$LAUNCH_SCRIPT"     && ok "Removed launcher"
    rm -f  "$AUTOSTART_ENTRY"   && ok "Removed tray autostart"
    rm -f  "$HOME/.config/deamoncli/config.json" 2>/dev/null || true
    update-desktop-database "$APPS_DIR" 2>/dev/null || true
    echo -e "\n${GREEN}DeamonCLI uninstalled.${NC}\n"
    exit 0
fi

# ── Banner ─────────────────────────────────────────────────────────────────────
echo -e "
${RED}  ██████╗ ███████╗ █████╗ ███╗   ███╗ ██████╗ ███╗   ██╗${NC}
${RED}  ██╔══██╗██╔════╝██╔══██╗████╗ ████║██╔═══██╗████╗  ██║${NC}
${RED}  ██║  ██║█████╗  ███████║██╔████╔██║██║   ██║██╔██╗ ██║${NC}
${RED}  ██║  ██║██╔══╝  ██╔══██║██║╚██╔╝██║██║   ██║██║╚██╗██║${NC}
${RED}  ██████╔╝███████╗██║  ██║██║ ╚═╝ ██║╚██████╔╝██║ ╚████║${NC}
${RED}  ╚═════╝ ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═══╝${NC}
${DIM}  Interactive Linux command reference — installer${NC}
"

# ── 1. Python ──────────────────────────────────────────────────────────────────
step "1 / 5  Checking Python…"
if ! command -v python3 &>/dev/null; then
    err "Python 3 not found. Run:  sudo apt install python3 python3-pip"
    exit 1
fi
ok "Python $(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")') found"

# ── 2. Python packages ─────────────────────────────────────────────────────────
step "2 / 5  Installing Python packages…"

pip_install() {
    local pkg="$1" mod="${2:-$1}"
    if python3 -c "import $mod" &>/dev/null; then
        ok "$pkg already installed"; return
    fi
    info "Installing $pkg…"
    pip3 install --user --quiet "$pkg" 2>/dev/null \
    || pip3 install --break-system-packages --quiet "$pkg" 2>/dev/null \
    || { err "Could not install $pkg — try:  pip3 install $pkg"; exit 1; }
    ok "$pkg installed"
}

pip_install textual
pip_install pyperclip

# ── 3. System packages ─────────────────────────────────────────────────────────
step "3 / 5  Installing system dependencies…"

apt_install() {
    local pkg="$1" label="${2:-$1}"
    if dpkg -s "$pkg" &>/dev/null; then
        ok "$label already installed"
    else
        info "Installing $label…"
        sudo apt-get install -y -q "$pkg" 2>/dev/null \
            && ok "$label installed" \
            || warn "Could not install $label — try:  sudo apt install $pkg"
    fi
}

# tmux — keeps the app running when the window is closed
apt_install tmux "tmux (background sessions)"

# AppIndicator — tray icon near wifi/bluetooth
INDICATOR_OK=false
if dpkg -s gir1.2-ayatanaappindicator3-0.1 &>/dev/null; then
    ok "AyatanaAppIndicator already installed"; INDICATOR_OK=true
elif dpkg -s gir1.2-appindicator3-0.1 &>/dev/null; then
    ok "AppIndicator3 already installed"; INDICATOR_OK=true
else
    info "Installing AppIndicator (tray icon)…"
    if sudo apt-get install -y -q python3-gi gir1.2-ayatanaappindicator3-0.1 2>/dev/null; then
        ok "AyatanaAppIndicator installed"; INDICATOR_OK=true
    elif sudo apt-get install -y -q python3-gi gir1.2-appindicator3-0.1 2>/dev/null; then
        ok "AppIndicator3 installed"; INDICATOR_OK=true
    else
        warn "Could not install AppIndicator — tray icon may not appear"
        warn "Try:  sudo apt install gir1.2-ayatanaappindicator3-0.1"
    fi
fi

# gnome-terminal — the window the app runs in
if ! command -v gnome-terminal &>/dev/null; then
    apt_install gnome-terminal
else
    ok "gnome-terminal already installed"
fi

# wmctrl — lets tray raise existing window instead of opening a duplicate
apt_install wmctrl "wmctrl (window focus)"

# xclip — clipboard support for the Copy button
if ! command -v xclip &>/dev/null && ! command -v xsel &>/dev/null; then
    apt_install xclip "xclip (clipboard)"
else
    ok "Clipboard tool already installed"
fi

# ── 4. App files ───────────────────────────────────────────────────────────────
step "4 / 5  Installing app files…"

mkdir -p "$INSTALL_DIR" "$HOME/.local/bin" "$HOME/.local/share/icons" \
         "$APPS_DIR" "$AUTOSTART_DIR"

for f in linux_ref.py commands_db.json DeamonCLI_logo.png tray.py; do
    [[ -f "$SRC/$f" ]] || { err "Missing file: $f — run from the DeamonCLI folder"; exit 1; }
    cp "$SRC/$f" "$INSTALL_DIR/$f"
done
ok "App files copied to $INSTALL_DIR"

cp "$SRC/DeamonCLI_logo.png" "$ICON_PATH"
ok "Icon installed"

# ── Launcher at ~/.local/bin/deamoncli ────────────────────────────────────────
cat > "$LAUNCH_SCRIPT" << 'LAUNCHER_EOF'
#!/usr/bin/env bash
export DISPLAY="${DISPLAY:-:0}"
INSTALL_DIR="$HOME/.local/share/deamoncli"
CONFIG="$HOME/.config/deamoncli/config.json"
SESSION="deamoncli"

# Start tray icon if not already running
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
    if ! tmux has-session -t "$SESSION" 2>/dev/null; then
        tmux new-session -d -s "$SESSION" -x 220 -y 50 \
            "TERM=xterm-256color python3 $INSTALL_DIR/linux_ref.py"
    fi
    gnome-terminal --class=DeamonCLI $GEOM_ARG --title="DeamonCLI" \
        -- tmux attach-session -t "$SESSION"
else
    gnome-terminal --class=DeamonCLI $GEOM_ARG --maximize --title="DeamonCLI" \
        -- bash -c "python3 $INSTALL_DIR/linux_ref.py"
fi
LAUNCHER_EOF
chmod +x "$LAUNCH_SCRIPT"
ok "Launcher created at $LAUNCH_SCRIPT"

# ── 5. Desktop integration ─────────────────────────────────────────────────────
step "5 / 5  Setting up desktop shortcuts…"

DESKTOP_CONTENT="[Desktop Entry]
Version=1.0
Type=Application
Name=DeamonCLI
GenericName=Command Reference
Comment=Interactive Linux command reference
Exec=$LAUNCH_SCRIPT
Icon=$ICON_PATH
Terminal=false
Categories=Utility;System;
Keywords=linux;command;terminal;reference;bash;shell;security;
StartupNotify=true
StartupWMClass=DeamonCLI"

echo "$DESKTOP_CONTENT" > "$DESKTOP_ENTRY"
ok "App menu entry created"

echo "$DESKTOP_CONTENT" > "$DESKTOP_SHORTCUT"
chmod +x "$DESKTOP_SHORTCUT"
ok "Desktop shortcut created"

# Autostart — tray starts automatically on login
cat > "$AUTOSTART_ENTRY" << EOF
[Desktop Entry]
Type=Application
Name=DeamonCLI Tray
Comment=DeamonCLI system tray icon
Exec=bash -c "DISPLAY=:0 python3 $INSTALL_DIR/tray.py"
Icon=$ICON_PATH
Terminal=false
Hidden=false
X-GNOME-Autostart-enabled=true
EOF
ok "Tray set to start automatically on login"

# Refresh desktop caches
update-desktop-database "$APPS_DIR" 2>/dev/null || true
gtk-update-icon-cache -f "$HOME/.local/share/icons" 2>/dev/null || true

# Start the tray right now
if $INDICATOR_OK; then
    pkill -f "tray.py" 2>/dev/null || true
    sleep 0.3
    DISPLAY=:0 python3 "$INSTALL_DIR/tray.py" &
    ok "Tray icon started — look near your wifi/bluetooth icons"
fi

# ── Done ───────────────────────────────────────────────────────────────────────
echo -e "
${GREEN}${BOLD}  DeamonCLI installed successfully!${NC}

  ${BOLD}How to open it:${NC}
    • Click the daemon icon near wifi/bluetooth in the panel
    • Double-click the icon on your desktop
    • Search \"DeamonCLI\" in your apps menu
    • Or type in a terminal:  ${CYAN}deamoncli${NC}

  ${BOLD}How it works:${NC}
    • Closing the window (X) keeps the app running in the background
    • Click the tray icon → Open DeamonCLI to bring it back
    • Click the tray icon → Quit to fully close everything

  ${DIM}To uninstall:  bash install.sh --uninstall${NC}
"
