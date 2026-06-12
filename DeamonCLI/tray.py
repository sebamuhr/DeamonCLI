#!/usr/bin/env python3
"""DeamonCLI system tray icon — runs in background, shows icon near wifi/bluetooth."""
import datetime, gi, os, shutil, subprocess, sys, threading, urllib.request, json as _json
from pathlib import Path

ICON         = str(Path.home() / ".local/share/icons/deamoncli.png")
SCRIPT_DIR   = Path(__file__).parent
INSTALL_DIR  = Path.home() / ".local/share/deamoncli"
VERSION_FILE = INSTALL_DIR / "version"
SESSION      = "deamoncli"
DESKTOP      = str(Path.home() / ".local/share/applications/deamoncli.desktop")
LAUNCH       = str(Path.home() / ".local/bin/deamoncli")   # installed launcher

REPO   = "sebamuhr/DeamonCLI"
BRANCH = "master"
FILES  = ["linux_ref.py", "commands_db.json", "tray.py", "launch.sh"]

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

# ── Logging ───────────────────────────────────────────────────────────────────

LOG = "/tmp/deamoncli_open.log"

def log(msg):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    with open(LOG, "a") as f:
        f.write(f"[{ts}] {msg}\n")

# ── Session environment ───────────────────────────────────────────────────────

def _session_env():
    """Get the real desktop session environment (DBUS etc) from gnome-shell."""
    env = {**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")}
    for proc in ["gnome-shell", "gnome-session", "xfce4-session", "plasmashell"]:
        pids = subprocess.run(["pgrep", proc], capture_output=True, text=True).stdout.split()
        if pids:
            try:
                with open(f"/proc/{pids[0]}/environ", "rb") as f:
                    for item in f.read().split(b"\x00"):
                        if b"=" in item:
                            k, v = item.split(b"=", 1)
                            key = k.decode(errors="replace")
                            if key in ("DBUS_SESSION_BUS_ADDRESS", "XDG_RUNTIME_DIR",
                                       "XDG_SESSION_TYPE", "XDG_CURRENT_DESKTOP"):
                                env[key] = v.decode(errors="replace")
                break
            except Exception:
                pass
    if "DBUS_SESSION_BUS_ADDRESS" not in env:
        bus = f"/run/user/{os.getuid()}/bus"
        if os.path.exists(bus):
            env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={bus}"
    if "XDG_RUNTIME_DIR" not in env:
        env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"
    return env

# ── Open ──────────────────────────────────────────────────────────────────────

def open_app(_=None):
    env = _session_env()
    log(f"--- open_app ---")
    log(f"DBUS={env.get('DBUS_SESSION_BUS_ADDRESS', 'MISSING')}")
    log(f"DISPLAY={env.get('DISPLAY', 'MISSING')}")

    # 1. Raise window if already on screen
    if shutil.which("wmctrl"):
        r = subprocess.run(["wmctrl", "-a", "DeamonCLI"], capture_output=True, env=env)
        log(f"wmctrl rc={r.returncode} err={r.stderr.decode().strip()}")
        if r.returncode == 0:
            return

    # 2. Make sure the tmux session (app) is running
    session_up = subprocess.run(
        ["tmux", "has-session", "-t", SESSION], capture_output=True
    ).returncode == 0
    log(f"tmux session up={session_up}")
    if not session_up:
        subprocess.Popen(["tmux", "new-session", "-d", "-s", SESSION, "-x", "220", "-y", "50",
                          f"TERM=xterm-256color python3 {INSTALL_DIR}/linux_ref.py"])
        log("started new tmux session")

    # 3. Open a terminal window (try three methods, log each)

    # Method A — systemd-run: runs in the user's full session, always has DBUS
    if shutil.which("systemd-run"):
        r = subprocess.run(
            ["systemd-run", "--user", "--no-block",
             "gnome-terminal", "--class=DeamonCLI", "--title=DeamonCLI",
             "--", "tmux", "attach-session", "-t", SESSION],
            capture_output=True
        )
        log(f"systemd-run rc={r.returncode} err={r.stderr.decode().strip()}")
        if r.returncode == 0:
            return

    # Method B — gio launch: same code path as clicking in the apps menu
    if shutil.which("gio") and os.path.exists(DESKTOP):
        r = subprocess.run(["gio", "launch", DESKTOP], capture_output=True, env=env)
        log(f"gio launch rc={r.returncode} err={r.stderr.decode().strip()}")
        if r.returncode == 0:
            return

    # Method C — direct Popen with injected session env
    r = subprocess.Popen(["bash", LAUNCH], env=env, start_new_session=True)
    log(f"direct Popen pid={r.pid}")

# ── Quit ──────────────────────────────────────────────────────────────────────

def quit_cb(_=None):
    subprocess.call(["tmux", "kill-session", "-t", SESSION])
    subprocess.call(["pkill", "-f", "linux_ref.py"])
    Gtk.main_quit()

# ── Preferences dialog ────────────────────────────────────────────────────────

def preferences_cb(_=None):
    dialog = Gtk.Dialog(title="DeamonCLI Preferences")
    dialog.set_default_size(320, -1)
    dialog.set_border_width(20)
    dialog.set_keep_above(True)

    box = dialog.get_content_area()
    box.set_spacing(12)

    title = Gtk.Label()
    title.set_markup("<b>DeamonCLI</b>")
    title.set_halign(Gtk.Align.START)
    box.pack_start(title, False, False, 0)

    sep1 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
    box.pack_start(sep1, False, False, 4)

    update_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    update_lbl = Gtk.Label(label="Check for a newer version on GitHub")
    update_lbl.set_halign(Gtk.Align.START)
    update_lbl.set_hexpand(True)
    update_btn = Gtk.Button(label="Update")
    update_row.pack_start(update_lbl, True, True, 0)
    update_row.pack_start(update_btn, False, False, 0)
    box.pack_start(update_row, False, False, 0)

    sep2 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
    box.pack_start(sep2, False, False, 4)

    uninstall_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    uninstall_lbl = Gtk.Label(label="Remove DeamonCLI from this computer")
    uninstall_lbl.set_halign(Gtk.Align.START)
    uninstall_lbl.set_hexpand(True)
    uninstall_btn = Gtk.Button(label="Uninstall")
    uninstall_btn.get_style_context().add_class("destructive-action")
    uninstall_row.pack_start(uninstall_lbl, True, True, 0)
    uninstall_row.pack_start(uninstall_btn, False, False, 0)
    box.pack_start(uninstall_row, False, False, 0)

    box.show_all()
    dialog.add_button("Close", Gtk.ResponseType.CLOSE)

    def on_update(_):
        dialog.hide()
        _run_update()
        dialog.destroy()

    def on_uninstall(_):
        dialog.hide()
        _confirm_uninstall()
        dialog.destroy()

    update_btn.connect("clicked", on_update)
    uninstall_btn.connect("clicked", on_uninstall)
    dialog.run()
    dialog.destroy()

# ── Uninstall ─────────────────────────────────────────────────────────────────

def _confirm_uninstall():
    d = Gtk.MessageDialog(
        message_type=Gtk.MessageType.WARNING, buttons=Gtk.ButtonsType.NONE,
        text="Uninstall DeamonCLI?",
        secondary_text="This will remove all app files, the desktop shortcut,\n"
                       "the tray icon, and the launcher from your system.",
    )
    d.set_title("Uninstall DeamonCLI")
    d.set_keep_above(True)
    d.add_button("Cancel", Gtk.ResponseType.CANCEL)
    btn = d.add_button("Uninstall", Gtk.ResponseType.OK)
    btn.get_style_context().add_class("destructive-action")
    response = d.run(); d.destroy()
    if response == Gtk.ResponseType.OK:
        _do_uninstall()

def _do_uninstall():
    home = Path.home()
    for p in [
        home / ".local/share/deamoncli",
        home / ".local/share/icons/deamoncli.png",
        home / ".local/share/applications/deamoncli.desktop",
        home / ".local/share/applications/linuxref.desktop",
        home / "Desktop/deamoncli.desktop",
        home / "Desktop/linuxref.desktop",
        home / ".local/bin/deamoncli",
        home / ".config/autostart/deamoncli-tray.desktop",
        home / ".config/deamoncli/config.json",
    ]:
        p = Path(p)
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        elif p.exists():
            p.unlink(missing_ok=True)
    subprocess.call(["tmux", "kill-session", "-t", SESSION])
    subprocess.call(["pkill", "-f", "linux_ref.py"])
    subprocess.call(["update-desktop-database",
                     str(home / ".local/share/applications")],
                    stderr=subprocess.DEVNULL)
    Gtk.main_quit()

# ── Update ────────────────────────────────────────────────────────────────────

def _simple_dialog(msg_type, title, text, secondary, buttons):
    d = Gtk.MessageDialog(message_type=msg_type, buttons=Gtk.ButtonsType.NONE,
                          text=text, secondary_text=secondary)
    d.set_title(title); d.set_keep_above(True)
    for label, resp in buttons:
        d.add_button(label, resp)
    r = d.run(); d.destroy(); return r

def _run_update():
    result = {}

    def do_check():
        try:
            req = urllib.request.Request(
                f"https://api.github.com/repos/{REPO}/commits/{BRANCH}",
                headers={"User-Agent": "DeamonCLI-updater"})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = _json.loads(r.read())
            result["sha"] = data["sha"]
            result["msg"] = data["commit"]["message"].split("\n")[0]
        except Exception as e:
            result["error"] = str(e)
        GLib.idle_add(show_result)

    checking = Gtk.MessageDialog(
        message_type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.NONE,
        text="Checking for updates…", secondary_text="Connecting to GitHub.")
    checking.set_title("DeamonCLI Update"); checking.set_keep_above(True); checking.show()

    def show_result():
        checking.destroy()
        if "error" in result:
            _simple_dialog(Gtk.MessageType.ERROR, "Update check failed",
                           "Could not reach GitHub", result["error"],
                           [("OK", Gtk.ResponseType.OK)])
            return
        sha, msg = result["sha"], result["msg"]
        try:
            local = VERSION_FILE.read_text().strip()
        except Exception:
            local = ""
        if local == sha:
            _simple_dialog(Gtk.MessageType.INFO, "Up to date",
                           "DeamonCLI is up to date",
                           "You already have the latest version.",
                           [("OK", Gtk.ResponseType.OK)])
            return
        response = _simple_dialog(
            Gtk.MessageType.QUESTION, "Update available",
            "A new version is available",
            f"Latest change:\n{msg}\n\nUpdate now?",
            [("Cancel", Gtk.ResponseType.CANCEL), ("Update", Gtk.ResponseType.OK)])
        if response != Gtk.ResponseType.OK:
            return

        progress = Gtk.Dialog(title="Updating DeamonCLI…")
        progress.set_keep_above(True); progress.set_border_width(20)
        lbl = Gtk.Label(label="Starting download…")
        progress.get_content_area().pack_start(lbl, True, True, 8)
        progress.show_all()

        def do_download():
            try:
                for fname in FILES:
                    GLib.idle_add(lbl.set_text, f"Downloading {fname}…")
                    req = urllib.request.Request(
                        f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/DeamonCLI/{fname}",
                        headers={"User-Agent": "DeamonCLI-updater"})
                    with urllib.request.urlopen(req, timeout=30) as r:
                        (INSTALL_DIR / fname).write_bytes(r.read())
                VERSION_FILE.write_text(sha)
                GLib.idle_add(done, None)
            except Exception as e:
                GLib.idle_add(done, str(e))

        def done(error):
            progress.destroy()
            if error:
                _simple_dialog(Gtk.MessageType.ERROR, "Update failed",
                               "Could not download the update", error,
                               [("OK", Gtk.ResponseType.OK)])
                return
            _simple_dialog(Gtk.MessageType.INFO, "Updated!",
                           "DeamonCLI updated successfully",
                           "The tray icon will restart to apply the update.",
                           [("OK", Gtk.ResponseType.OK)])
            env = _session_env()
            subprocess.Popen([sys.executable, str(INSTALL_DIR / "tray.py")], env=env)
            Gtk.main_quit()

        threading.Thread(target=do_download, daemon=True).start()

    threading.Thread(target=do_check, daemon=True).start()
    checking.run()

# ── Indicator ─────────────────────────────────────────────────────────────────

ind = AI.Indicator.new("deamoncli", ICON, AI.IndicatorCategory.APPLICATION_STATUS)
ind.set_status(AI.IndicatorStatus.ACTIVE)

menu = Gtk.Menu()
for label, cb in [
    ("Open DeamonCLI", open_app),
    ("Preferences",    preferences_cb),
    ("Quit",           quit_cb),
]:
    item = Gtk.MenuItem(label=label)
    item.connect("activate", cb)
    menu.append(item)

menu.show_all()
ind.set_menu(menu)
Gtk.main()
