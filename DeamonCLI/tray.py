#!/usr/bin/env python3
"""DeamonCLI system tray icon — runs in background, shows icon near wifi/bluetooth."""
import gi, os, shutil, subprocess, sys
from pathlib import Path

ICON       = str(Path.home() / ".local/share/icons/deamoncli.png")
SCRIPT_DIR = Path(__file__).parent

_local_bin = Path.home() / ".local/bin/deamoncli"
LAUNCH     = str(_local_bin if _local_bin.exists() else SCRIPT_DIR / "launch.sh")

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

def _session_env():
    """Build an environment that includes the user's DBUS session bus,
    which gnome-terminal needs to launch correctly from a background process."""
    env = {**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")}
    if "DBUS_SESSION_BUS_ADDRESS" not in env:
        uid = os.getuid()
        bus_path = f"/run/user/{uid}/bus"
        if os.path.exists(bus_path):
            env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={bus_path}"
    if "XDG_RUNTIME_DIR" not in env:
        env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"
    return env

def open_app(_=None):
    env = _session_env()
    if shutil.which("wmctrl"):
        r = subprocess.run(["wmctrl", "-a", "DeamonCLI"], capture_output=True, env=env)
        if r.returncode == 0:
            return
    if shutil.which("tmux"):
        r = subprocess.run(["tmux", "has-session", "-t", "deamoncli"], capture_output=True)
        if r.returncode == 0:
            subprocess.Popen(["bash", LAUNCH], env=env)
            return
    subprocess.Popen(["bash", LAUNCH], env=env)

def quit_cb(_=None):
    subprocess.call(["tmux", "kill-session", "-t", "deamoncli"])
    subprocess.call(["pkill", "-f", "linux_ref.py"])
    Gtk.main_quit()

def do_uninstall():
    home = Path.home()
    paths = [
        home / ".local/share/deamoncli",
        home / ".local/share/icons/deamoncli.png",
        home / ".local/share/applications/deamoncli.desktop",
        home / ".local/share/applications/linuxref.desktop",
        home / "Desktop/deamoncli.desktop",
        home / "Desktop/linuxref.desktop",
        home / ".local/bin/deamoncli",
        home / ".config/autostart/deamoncli-tray.desktop",
        home / ".config/deamoncli/config.json",
    ]
    subprocess.call(["tmux", "kill-session", "-t", "deamoncli"])
    subprocess.call(["pkill", "-f", "linux_ref.py"])
    for p in paths:
        p = Path(p)
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        elif p.exists():
            p.unlink(missing_ok=True)
    subprocess.call(
        ["update-desktop-database", str(home / ".local/share/applications")],
        stderr=subprocess.DEVNULL,
    )
    Gtk.main_quit()

def uninstall_cb(_=None):
    dialog = Gtk.MessageDialog(
        message_type=Gtk.MessageType.WARNING,
        buttons=Gtk.ButtonsType.NONE,
        text="Uninstall DeamonCLI?",
        secondary_text=(
            "This will remove all app files, the desktop shortcut,\n"
            "the tray icon, and the launcher from your system."
        ),
    )
    dialog.set_title("Uninstall DeamonCLI")
    dialog.set_keep_above(True)
    dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    uninstall_btn = dialog.add_button("Uninstall", Gtk.ResponseType.OK)
    uninstall_btn.get_style_context().add_class("destructive-action")

    response = dialog.run()
    dialog.destroy()
    if response == Gtk.ResponseType.OK:
        do_uninstall()

# ── Indicator ─────────────────────────────────────────────────────────────────
ind = AI.Indicator.new(
    "deamoncli", ICON,
    AI.IndicatorCategory.APPLICATION_STATUS
)
ind.set_status(AI.IndicatorStatus.ACTIVE)

menu = Gtk.Menu()
for label, cb in [
    ("Open DeamonCLI", open_app),
    ("Uninstall", uninstall_cb),
    ("Quit", quit_cb),
]:
    item = Gtk.MenuItem(label=label)
    item.connect("activate", cb)
    menu.append(item)

menu.show_all()
ind.set_menu(menu)
Gtk.main()
