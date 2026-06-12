#!/usr/bin/env python3
"""DeamonCLI system tray icon — runs in background, shows icon near wifi/bluetooth."""
import gi, os, shutil, subprocess, sys, threading, urllib.request, json as _json
from pathlib import Path

ICON        = str(Path.home() / ".local/share/icons/deamoncli.png")
SCRIPT_DIR  = Path(__file__).parent
INSTALL_DIR = Path.home() / ".local/share/deamoncli"
VERSION_FILE = INSTALL_DIR / "version"

_local_bin = Path.home() / ".local/bin/deamoncli"
LAUNCH     = str(_local_bin if _local_bin.exists() else SCRIPT_DIR / "launch.sh")

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

# ── Helpers ───────────────────────────────────────────────────────────────────

def _session_env():
    env = {**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")}
    if "DBUS_SESSION_BUS_ADDRESS" not in env:
        bus = f"/run/user/{os.getuid()}/bus"
        if os.path.exists(bus):
            env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={bus}"
    if "XDG_RUNTIME_DIR" not in env:
        env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"
    return env

def _gh_request(url):
    req = urllib.request.Request(url, headers={"User-Agent": "DeamonCLI-updater"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return _json.loads(r.read())

def _raw_url(fname):
    return f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/DeamonCLI/{fname}"

def _local_sha():
    try:
        return VERSION_FILE.read_text().strip()
    except Exception:
        return ""

# ── Tray actions ──────────────────────────────────────────────────────────────

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

# ── Uninstall ─────────────────────────────────────────────────────────────────

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
    subprocess.call(["tmux", "kill-session", "-t", "deamoncli"])
    subprocess.call(["pkill", "-f", "linux_ref.py"])
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
    btn = dialog.add_button("Uninstall", Gtk.ResponseType.OK)
    btn.get_style_context().add_class("destructive-action")
    response = dialog.run()
    dialog.destroy()
    if response == Gtk.ResponseType.OK:
        _do_uninstall()

# ── Update ────────────────────────────────────────────────────────────────────

def _show_dialog(msg_type, title, text, secondary, buttons):
    """Show a simple modal dialog, return the response."""
    dialog = Gtk.MessageDialog(
        message_type=msg_type,
        buttons=Gtk.ButtonsType.NONE,
        text=text,
        secondary_text=secondary,
    )
    dialog.set_title(title)
    dialog.set_keep_above(True)
    for label, response in buttons:
        dialog.add_button(label, response)
    response = dialog.run()
    dialog.destroy()
    return response

def _do_download(sha, progress_label, progress_dialog):
    """Download updated files in a background thread."""
    try:
        for i, fname in enumerate(FILES):
            GLib.idle_add(progress_label.set_text, f"Downloading {fname}…")
            req = urllib.request.Request(
                _raw_url(fname), headers={"User-Agent": "DeamonCLI-updater"}
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                (INSTALL_DIR / fname).write_bytes(r.read())
        VERSION_FILE.write_text(sha)
        GLib.idle_add(_update_done, progress_dialog, None)
    except Exception as e:
        GLib.idle_add(_update_done, progress_dialog, str(e))

def _update_done(progress_dialog, error):
    progress_dialog.destroy()
    if error:
        _show_dialog(
            Gtk.MessageType.ERROR, "Update failed",
            "Could not download the update", error,
            [("OK", Gtk.ResponseType.OK)],
        )
        return
    _show_dialog(
        Gtk.MessageType.INFO, "Updated!",
        "DeamonCLI updated successfully",
        "The tray icon will restart to apply the update.",
        [("OK", Gtk.ResponseType.OK)],
    )
    env = _session_env()
    subprocess.Popen([sys.executable, str(INSTALL_DIR / "tray.py")], env=env)
    Gtk.main_quit()

def update_cb(_=None):
    # 1. Check GitHub in a thread so the menu doesn't freeze
    result = {}

    def do_check():
        try:
            data = _gh_request(
                f"https://api.github.com/repos/{REPO}/commits/{BRANCH}"
            )
            result["sha"] = data["sha"]
            result["msg"] = data["commit"]["message"].split("\n")[0]
        except Exception as e:
            result["error"] = str(e)
        GLib.idle_add(show_result)

    # Checking dialog
    checking = Gtk.MessageDialog(
        message_type=Gtk.MessageType.INFO,
        buttons=Gtk.ButtonsType.NONE,
        text="Checking for updates…",
        secondary_text="Connecting to GitHub.",
    )
    checking.set_title("DeamonCLI Update")
    checking.set_keep_above(True)
    checking.show()

    def show_result():
        checking.destroy()

        if "error" in result:
            _show_dialog(
                Gtk.MessageType.ERROR, "Update check failed",
                "Could not reach GitHub", result["error"],
                [("OK", Gtk.ResponseType.OK)],
            )
            return

        sha, msg = result["sha"], result["msg"]
        local = _local_sha()

        if local and local == sha:
            _show_dialog(
                Gtk.MessageType.INFO, "Up to date",
                "DeamonCLI is up to date",
                "You already have the latest version.",
                [("OK", Gtk.ResponseType.OK)],
            )
            return

        # Update available — ask user
        response = _show_dialog(
            Gtk.MessageType.QUESTION, "Update available",
            "A new version is available",
            f"Latest change:\n{msg}\n\nDo you want to update now?",
            [("Cancel", Gtk.ResponseType.CANCEL), ("Update", Gtk.ResponseType.OK)],
        )
        if response != Gtk.ResponseType.OK:
            return

        # Progress dialog while downloading
        progress_dialog = Gtk.Dialog(title="Updating DeamonCLI…")
        progress_dialog.set_keep_above(True)
        progress_dialog.set_border_width(20)
        box = progress_dialog.get_content_area()
        progress_label = Gtk.Label(label="Starting download…")
        box.pack_start(progress_label, True, True, 8)
        progress_dialog.show_all()

        threading.Thread(
            target=_do_download, args=(sha, progress_label, progress_dialog), daemon=True
        ).start()

    threading.Thread(target=do_check, daemon=True).start()
    checking.run()  # blocks until destroyed by show_result

# ── Indicator ─────────────────────────────────────────────────────────────────

ind = AI.Indicator.new(
    "deamoncli", ICON,
    AI.IndicatorCategory.APPLICATION_STATUS
)
ind.set_status(AI.IndicatorStatus.ACTIVE)

menu = Gtk.Menu()
for label, cb in [
    ("Open DeamonCLI", open_app),
    ("Update", update_cb),
    ("Uninstall", uninstall_cb),
    ("Quit", quit_cb),
]:
    item = Gtk.MenuItem(label=label)
    item.connect("activate", cb)
    menu.append(item)

menu.show_all()
ind.set_menu(menu)
Gtk.main()
