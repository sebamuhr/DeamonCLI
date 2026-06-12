#!/usr/bin/env python3
"""DeamonCLI system tray icon — runs in background, shows icon near wifi/bluetooth."""
import gi, os, shutil, subprocess, sys
from pathlib import Path

ICON       = str(Path.home() / ".local/share/icons/deamoncli.png")
SCRIPT_DIR = Path(__file__).parent

# Find the right launcher: installed version first, then repo launch.sh next to this file
_local_bin = Path.home() / ".local/bin/deamoncli"
LAUNCH     = str(_local_bin if _local_bin.exists() else SCRIPT_DIR / "launch.sh")

# Try Ayatana (Ubuntu 23.04+) then fall back to classic AppIndicator3
try:
    gi.require_version("AyatanaAppIndicator3", "0.1")
    from gi.repository import AyatanaAppIndicator3 as AI
except (ValueError, ImportError):
    try:
        gi.require_version("AppIndicator3", "0.1")
        from gi.repository import AppIndicator3 as AI
    except (ValueError, ImportError):
        print("AppIndicator not available — tray icon won't show.", file=sys.stderr)
        sys.exit(1)

from gi.repository import Gtk

def open_app(_=None):
    env = {**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")}
    # Raise existing window if already open, otherwise launch fresh
    if shutil.which("wmctrl"):
        result = subprocess.run(["wmctrl", "-a", "DeamonCLI"],
                                capture_output=True, env=env)
        if result.returncode == 0:
            return
    subprocess.Popen(["bash", LAUNCH], env=env)

def quit_cb(_=None):
    subprocess.call(["pkill", "-f", "linux_ref.py"])
    Gtk.main_quit()

ind = AI.Indicator.new(
    "deamoncli", ICON,
    AI.IndicatorCategory.APPLICATION_STATUS
)
ind.set_status(AI.IndicatorStatus.ACTIVE)

menu = Gtk.Menu()
for label, cb in [
    ("Open DeamonCLI", open_app),
    (None, None),
    ("Quit", quit_cb),
]:
    if label is None:
        item = Gtk.SeparatorMenuItem()
    else:
        item = Gtk.MenuItem(label=label)
        item.connect("activate", cb)
    menu.append(item)

menu.show_all()
ind.set_menu(menu)
Gtk.main()
