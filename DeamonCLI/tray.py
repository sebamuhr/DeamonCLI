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

from gi.repository import Gtk, GLib

COUNTDOWN_SECONDS = 5

def open_app(_=None):
    env = {**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")}
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
    subprocess.call(["update-desktop-database",
                     str(home / ".local/share/applications")],
                    stderr=subprocess.DEVNULL)
    Gtk.main_quit()

def uninstall_cb(_=None):
    dialog = Gtk.Dialog(title="Uninstall DeamonCLI")
    dialog.set_default_size(360, -1)
    dialog.set_border_width(16)
    dialog.set_keep_above(True)

    # Content
    box = dialog.get_content_area()
    box.set_spacing(12)

    title_label = Gtk.Label()
    title_label.set_markup("<b>Uninstall DeamonCLI?</b>")
    title_label.set_halign(Gtk.Align.START)
    box.pack_start(title_label, False, False, 0)

    body_label = Gtk.Label(
        label="This will remove all app files, the desktop shortcut,\n"
              "the tray icon, and the launcher from your system."
    )
    body_label.set_halign(Gtk.Align.START)
    box.pack_start(body_label, False, False, 0)

    countdown_label = Gtk.Label()
    countdown_label.set_halign(Gtk.Align.START)
    box.pack_start(countdown_label, False, False, 0)

    box.show_all()

    # Buttons
    cancel_btn = dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    uninstall_btn = dialog.add_button(
        f"Uninstall ({COUNTDOWN_SECONDS})", Gtk.ResponseType.OK
    )
    uninstall_btn.set_sensitive(False)
    uninstall_btn.get_style_context().add_class("destructive-action")

    remaining = [COUNTDOWN_SECONDS]

    def tick():
        remaining[0] -= 1
        if remaining[0] > 0:
            uninstall_btn.set_label(f"Uninstall ({remaining[0]})")
            countdown_label.set_markup(
                f"<span foreground='gray' size='small'>"
                f"Uninstall button unlocks in {remaining[0]} second"
                f"{'s' if remaining[0] != 1 else ''}…</span>"
            )
            return True  # keep ticking
        # Countdown done
        uninstall_btn.set_label("Uninstall")
        uninstall_btn.set_sensitive(True)
        countdown_label.set_markup(
            "<span foreground='gray' size='small'>Ready — click Uninstall to proceed.</span>"
        )
        return False  # stop timer

    countdown_label.set_markup(
        f"<span foreground='gray' size='small'>"
        f"Uninstall button unlocks in {COUNTDOWN_SECONDS} seconds…</span>"
    )
    GLib.timeout_add(1000, tick)

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
    (None, None),
    ("Quit", quit_cb),
    (None, None),
    ("Uninstall DeamonCLI…", uninstall_cb),
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
