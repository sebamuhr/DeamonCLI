#!/usr/bin/env python3
"""Linux Reference — find commands by what they do, not by their name."""

import os, sys, json, sqlite3, subprocess, shutil, difflib
from datetime import datetime
from pathlib import Path

try:
    from textual.app import App, ComposeResult
    from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
    from textual.widgets import (
        Header, Footer, ListView, ListItem, Label,
        Button, Input, Static, RichLog, DataTable,
        TabbedContent, TabPane, Rule
    )
    from textual.screen import ModalScreen
    from textual.binding import Binding
    from textual._work_decorator import work
    from rich.text import Text
except ImportError:
    print("Run: pip3 install --break-system-packages textual")
    sys.exit(1)

try:
    import pyperclip
    CLIPBOARD_OK = True
except ImportError:
    CLIPBOARD_OK = False

APP_DIR   = Path(__file__).parent
DB_PATH   = APP_DIR / "commands_db.json"
HIST_PATH = APP_DIR / "history.db"
HOME      = Path.home()

# ── Data ──────────────────────────────────────────────────────────────────────

# Words that add no search value
STOPWORDS = {
    "how", "to", "a", "an", "the", "my", "your", "i", "do", "can", "what",
    "is", "are", "for", "in", "on", "at", "of", "it", "this", "that", "with",
    "make", "get", "want", "need", "help", "me", "us", "we", "please", "way",
    "using", "use", "from", "into", "and", "or", "not", "be", "been",
}

# Natural language → technical keywords
SYNONYMS = {
    "navigate": ["folder", "directory", "cd", "go"],
    "go":       ["cd", "folder", "directory", "navigate"],
    "move":     ["mv", "navigate", "cd", "folder"],
    "connect":  ["ssh", "server", "remote", "login"],
    "server":   ["ssh", "remote", "host", "connection"],
    "remote":   ["ssh", "server", "connect"],
    "login":    ["ssh", "connect", "server", "auth"],
    "host":     ["ssh", "server", "remote"],
    "delete":   ["remove", "rm", "erase"],
    "erase":    ["delete", "rm", "remove"],
    "show":     ["list", "view", "see", "display"],
    "see":      ["list", "view", "show"],
    "view":     ["cat", "show", "display"],
    "open":     ["launch", "start", "run", "xdg"],
    "install":  ["apt", "package", "software"],
    "download": ["wget", "curl", "get"],
    "search":   ["find", "grep", "locate"],
    "find":     ["search", "grep", "locate"],
    "copy":     ["cp", "scp", "duplicate"],
    "rename":   ["mv", "move"],
    "compress": ["zip", "tar", "archive"],
    "extract":  ["unzip", "tar", "decompress"],
    "network":  ["wifi", "internet", "ip", "connection"],
    "internet": ["network", "wifi", "ip"],
    "wireless": ["wifi", "network", "wlan"],
    "folder":   ["directory", "cd", "navigate"],
    "directory":["folder", "cd", "navigate"],
    "program":  ["app", "software", "package"],
    "app":      ["program", "software", "install"],
    "update":   ["upgrade", "refresh", "latest"],
    "restart":  ["reboot", "reload"],
    "reboot":   ["restart"],
    "stop":     ["kill", "terminate", "close"],
    "kill":     ["stop", "terminate"],
    "close":    ["kill", "stop"],
    "run":      ["execute", "start", "launch"],
    "execute":  ["run", "start"],
    "check":    ["status", "see", "verify"],
    "loud":     ["volume", "sound", "audio"],
    "quiet":    ["volume", "sound", "mute"],
    "sound":    ["audio", "volume", "music"],
    "audio":    ["sound", "volume"],
    "screen":   ["display", "monitor", "brightness"],
    "bright":   ["brightness", "screen", "display"],
    "memory":   ["ram", "free", "usage"],
    "ram":      ["memory", "free", "usage"],
    "cpu":      ["processor", "cores", "speed", "lscpu"],
    "backup":   ["copy", "archive", "rsync", "sync"],
    "sync":     ["rsync", "backup"],
    "upload":   ["scp", "rsync", "transfer", "send"],
    "send":     ["scp", "transfer", "upload"],
    "transfer": ["scp", "rsync", "upload", "download"],
    "firewall": ["ufw", "security", "port", "block"],
    "ssh":      ["server", "remote", "connect", "login"],
    "port":     ["ssh", "network", "firewall", "connection"],
    "password": ["passwd", "security", "auth", "login"],
    "log":      ["journal", "syslog", "history", "monitor"],
    "monitor":  ["top", "watch", "log", "display"],
    "git":      ["github", "repository", "version"],
    "github":   ["git", "repository", "clone", "push"],
    "python":   ["pip", "script", "py"],
    "package":  ["install", "apt", "pip", "npm"],
    "service":  ["systemctl", "daemon", "server", "nginx"],
    "deploy":   ["scp", "rsync", "server", "upload"],
}

def load_commands():
    with open(DB_PATH) as f:
        return json.load(f)["commands"]

def search_commands(query: str, commands: list) -> list:
    # Strip stopwords, expand synonyms
    raw_words = query.lower().strip().split()
    words = [w for w in raw_words if w not in STOPWORDS] or raw_words
    if not words:
        return []

    expanded: set[str] = set(words)
    for w in words:
        expanded.update(SYNONYMS.get(w, []))

    scored = []
    for cmd in commands:
        title  = cmd["title"].lower()
        cat    = cmd.get("category", "").lower()
        kws    = [k.lower() for k in cmd.get("keywords", [])]
        desc   = cmd.get("description", "").lower()
        score  = 0

        for term in expanded:
            if term in title:
                score += 10
            if term in cat:
                score += 5
            for kw in kws:
                # Exact match, or substring only when both strings are ≥4 chars
                # (prevents "ram" from matching "programs", "see" from matching "seed", etc.)
                exact = (term == kw)
                substr = (len(term) >= 4 and len(kw) >= 4 and (term in kw or kw in term))
                if exact or substr:
                    score += 3
                    break
            if term in desc:
                score += 1
            # Fuzzy match catches typos ("conect", "foldr")
            if score == 0 and len(term) >= 4:
                for kw in kws:
                    if len(kw) >= 4 and difflib.SequenceMatcher(None, term, kw).ratio() >= 0.72:
                        score += 2
                        break

        if score > 0:
            scored.append((score, cmd))

    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored]

# ── History ───────────────────────────────────────────────────────────────────

def init_history():
    con = sqlite3.connect(HIST_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS history (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        title   TEXT,
        command TEXT NOT NULL,
        category TEXT,
        action  TEXT,
        ran_at  TEXT
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS search_history (
        id     INTEGER PRIMARY KEY AUTOINCREMENT,
        query  TEXT NOT NULL,
        ran_at TEXT
    )""")
    con.commit()
    return con

def save_search(con, query: str):
    q = query.strip()
    if not q:
        return
    # Avoid saving the same query twice in a row
    last = con.execute(
        "SELECT query FROM search_history ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if last and last[0] == q:
        return
    con.execute(
        "INSERT INTO search_history (query, ran_at) VALUES (?, ?)",
        (q, datetime.now().strftime("%Y-%m-%d %H:%M"))
    )
    con.commit()

def delete_search(con, query: str):
    con.execute("DELETE FROM search_history WHERE query = ?", (query,))
    con.commit()

def get_recent_searches(con, limit: int = 8) -> list[str]:
    # GROUP BY + MAX(id) gives the most-recent occurrence of each unique query
    rows = con.execute(
        "SELECT query FROM search_history GROUP BY query ORDER BY MAX(id) DESC LIMIT ?",
        (limit,)
    ).fetchall()
    return [r[0] for r in rows]

def save_history(con, title, command, category, action):
    con.execute(
        "INSERT INTO history (title,command,category,action,ran_at) VALUES (?,?,?,?,?)",
        (title, command, category, action, datetime.now().strftime("%Y-%m-%d %H:%M"))
    )
    con.commit()

def get_history(con, limit=200):
    return con.execute(
        "SELECT ran_at, action, title, command FROM history ORDER BY id DESC LIMIT ?",
        (limit,)
    ).fetchall()

# ── System helpers ────────────────────────────────────────────────────────────

def copy_to_clipboard(text: str) -> bool:
    if CLIPBOARD_OK:
        try:
            pyperclip.copy(text)
            return True
        except Exception:
            pass
    for tool in [["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]]:
        if shutil.which(tool[0]):
            try:
                subprocess.run(tool, input=text.encode(), check=True)
                return True
            except Exception:
                pass
    return False

def run_command(cmd: str):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        return r.stdout, r.stderr, r.returncode
    except subprocess.TimeoutExpired:
        return "", "Timed out after 15 seconds.", 1
    except Exception as e:
        return "", str(e), 1

# ── Output modal ──────────────────────────────────────────────────────────────

class OutputModal(ModalScreen):
    def __init__(self, title, stdout, stderr, rc):
        super().__init__()
        self._title = title
        self._out   = stdout
        self._err   = stderr
        self._rc    = rc

    def compose(self) -> ComposeResult:
        with Container(classes="modal-box"):
            yield Label(f"▶  {self._title}", classes="modal-title")
            yield RichLog(classes="modal-log", highlight=True, wrap=True)
            yield Label("Press  ESC  or  Q  to close", classes="modal-hint")

    def on_mount(self) -> None:
        log = self.query_one(RichLog)
        if self._out:
            log.write(Text(self._out.rstrip()))
        if self._err:
            log.write(Text(self._err.rstrip(), style="bold red"))
        if not self._out and not self._err:
            style = "bold green" if self._rc == 0 else "bold red"
            msg   = "✓  Command completed." if self._rc == 0 else f"✗  Exited with code {self._rc}"
            log.write(Text(msg, style=style))

    def on_key(self, event) -> None:
        if event.key in ("escape", "q"):
            self.dismiss()

# ── Command detail (right panel) ──────────────────────────────────────────────

class CommandDetail(Vertical):
    def __init__(self, cmd: dict, history_con):
        # No fixed id — avoids duplicate-ID crash when switching commands quickly
        super().__init__(classes="cmd-detail")
        self.cmd = cmd
        self.hcon = history_con

    def compose(self) -> ComposeResult:
        c = self.cmd
        can_run = c.get("can_run", True)

        yield Label(c["title"], classes="detail-title")
        yield Label(c.get("category", "").upper(), classes="detail-category")
        yield Rule(classes="detail-rule")
        yield Static(c.get("description", ""), classes="detail-desc")
        yield Label("Command:", classes="section-label")
        yield Static(c["command"], classes="code-box detail-cmd")

        if not can_run:
            reason = c.get("shell_only_reason", "This command must run in your terminal.")
            yield Static(f"⚠   {reason}", classes="shell-warning")

        with Horizontal(classes="action-row"):
            if can_run:
                yield Button("▶   Run it", classes="btn-run", variant="success")
            yield Button(
                "📋  Copy" if can_run else "📋  Copy  —  paste in terminal",
                classes="btn-copy",
                variant="default" if can_run else "warning",
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        c = self.cmd
        if "btn-run" in event.button.classes:
            event.stop()
            btn = event.button
            btn.disabled = True
            btn.label = "⏳  Running…"
            save_history(self.hcon, c["title"], c["command"], c.get("category",""), "ran")
            self._do_run(c, btn)
        elif "btn-copy" in event.button.classes:
            event.stop()
            ok = copy_to_clipboard(c["command"])
            save_history(self.hcon, c["title"], c["command"], c.get("category",""), "copied")
            msg = "📋  Copied!" if ok else "Could not copy — run:  sudo apt install xclip"
            self.app.notify(msg, severity="information" if ok else "warning")

    @work(thread=True)
    def _do_run(self, cmd: dict, btn: Button) -> None:
        out, err, rc = run_command(cmd["command"])
        self.app.call_from_thread(self._show_result, btn, cmd["title"], out, err, rc)

    def _show_result(self, btn: Button, title: str, out: str, err: str, rc: int) -> None:
        btn.disabled = False
        btn.label = "▶   Run it"
        self.app.push_screen(OutputModal(title, out, err, rc))

# ── Main App ──────────────────────────────────────────────────────────────────

class DeamonCLIApp(App):

    TITLE = "DeamonCLI"

    CSS = """
    Screen {
        layout: horizontal;
        background: $background;
    }

    /* ── Left panel ── */
    #left {
        width: 38;
        border-right: solid $primary-darken-2;
        background: $panel;
    }
    TabbedContent {
        height: 1fr;
    }
    TabPane {
        padding: 0;
    }
    #search-input {
        margin: 1 1 0 1;
        width: 1fr;
    }
    #results-list {
        margin-top: 0;
        height: 1fr;
        border: none;
        background: transparent;
    }
    #history-table {
        height: 1fr;
        margin: 1;
        border: round $primary-darken-2;
    }
    #hist-clear-btn {
        margin: 0 1 1 1;
        width: 1fr;
    }

    /* ── Right panel ── */
    #right {
        width: 1fr;
        padding: 2 3;
        background: $background;
    }

    /* ── Welcome ── */
    #welcome {
        color: $text-muted;
        margin: 2 0;
    }
    .welcome-tag {
        color: $accent;
    }

    /* ── Command detail ── */
    .cmd-detail {
        height: auto;
    }
    .detail-title {
        text-style: bold;
        color: $text;
        margin-bottom: 0;
    }
    .detail-category {
        color: $primary;
        text-style: bold;
        margin-bottom: 1;
    }
    .detail-rule {
        margin: 0 0 1 0;
        color: $primary-darken-2;
    }
    .detail-desc {
        color: $text;
        margin-bottom: 1;
    }
    .section-label {
        color: $text-muted;
        text-style: italic;
        margin-top: 1;
    }
    .code-box {
        background: $surface;
        border: round $primary;
        padding: 0 1;
        margin: 0 0 1 0;
        color: $success;
    }
    .shell-warning {
        background: $warning-darken-3;
        color: $warning;
        border: round $warning;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    .action-row {
        height: auto;
        margin-top: 1;
    }
    .action-row Button {
        margin-right: 1;
    }

    /* ── Recent searches ── */
    .recent-row {
        height: 1;
        width: 1fr;
        align: left middle;
    }
    .recent-label {
        width: 1fr;
        height: 1;
    }
    .btn-del-search {
        min-width: 3;
        width: 3;
        height: 1;
        padding: 0 0;
        margin: 0;
        background: transparent;
        border: none;
        color: $error;
    }
    .btn-del-search:hover {
        background: $error-darken-3;
    }

    /* ── Output modal ── */
    .modal-box {
        background: $panel;
        border: round $primary;
        width: 82%;
        height: 72%;
        padding: 1 2;
    }
    .modal-title {
        text-style: bold;
        margin-bottom: 1;
    }
    .modal-log {
        height: 1fr;
        border: round $surface;
    }
    .modal-hint {
        color: $text-muted;
        text-align: center;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("escape", "dismiss_modal", "Close", show=False),
    ]

    def __init__(self):
        super().__init__()
        self._all_commands      = load_commands()
        self._hcon              = init_history()
        self._results: list     = []
        self._recent: list      = []
        self._deleting_search   = False

    # ── Layout ───────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with Vertical(id="left"):
                with TabbedContent(id="tabs"):
                    with TabPane("🔍  Search", id="tab-search"):
                        yield Input(
                            placeholder="Type anything: sound, wifi, git, ram…",
                            id="search-input"
                        )
                        yield ListView(id="results-list")
                    with TabPane("📜  History", id="tab-history"):
                        yield DataTable(id="history-table", cursor_type="row")
                        yield Button("🗑  Clear history", id="hist-clear-btn", variant="error")

            with ScrollableContainer(id="right"):
                yield self._welcome_widget()

        yield Footer()

    def _welcome_widget(self) -> Static:
        lines = [
            "Search for what you want to do:\n",
            "  sound   volume   audio   mute\n",
            "  wifi    network  ip      download\n",
            "  file    folder   copy    delete   find\n",
            "  install update   package software\n",
            "  memory  ram      cpu     processes\n",
            "  git     python   node    server\n",
            "  display screen   brightness\n",
            "  bluetooth   usb  hardware\n\n",
            "Type in the search box on the left →",
        ]
        return Static("".join(lines), id="welcome")

    # ── Search ────────────────────────────────────────────────────────────────

    def on_input_changed(self, event: Input.Changed):
        if event.input.id != "search-input":
            return
        q = event.value.strip()
        if q:
            results = search_commands(q, self._all_commands)
            self._results = results
            self._render_results(results, q)
        else:
            self._results = []
            self._show_recent_searches()

    def on_input_submitted(self, event: Input.Submitted):
        """Save search to history when user presses Enter."""
        if event.input.id == "search-input":
            save_search(self._hcon, event.value.strip())

    def _render_results(self, results: list, query: str):
        lv = self.query_one("#results-list", ListView)
        lv.clear()
        new_items = []
        for i, cmd in enumerate(results[:60]):
            icon = "  " if cmd.get("can_run", True) else "⚠ "
            new_items.append(
                ListItem(Label(f"{icon}{cmd['title']}", markup=False), name=f"r{i}")
            )
        if not new_items:
            new_items.append(ListItem(Label("No results — try other words or a phrase.")))
        self.call_after_refresh(lambda items=new_items: lv.mount(*items))

    def _show_recent_searches(self):
        self._recent = get_recent_searches(self._hcon)
        lv = self.query_one("#results-list", ListView)
        lv.clear()
        if not self._recent:
            return
        new_items = [ListItem(Label("  Recent searches:", markup=False))]
        for i, q in enumerate(self._recent):
            row = Horizontal(
                Label(f"  🕐 {q}", markup=False, classes="recent-label"),
                Button("✕", classes="btn-del-search", name=q, variant="error"),
                classes="recent-row",
            )
            new_items.append(ListItem(row, name=f"s{i}"))
        self.call_after_refresh(lambda items=new_items: lv.mount(*items))

    # ── Result / recent-search selection ─────────────────────────────────────

    def on_list_view_selected(self, event: ListView.Selected):
        if self._deleting_search:
            return
        if event.list_view.id != "results-list":
            return
        name = event.item.name or ""
        if name.startswith("r"):
            # Command result
            try:
                cmd = self._results[int(name[1:])]
            except (ValueError, IndexError):
                return
            save_search(self._hcon, self.query_one("#search-input", Input).value.strip())
            self._show_detail(cmd)
        elif name.startswith("s"):
            # Recent search — fill the input and re-run
            try:
                query = self._recent[int(name[1:])]
            except (ValueError, IndexError):
                return
            inp = self.query_one("#search-input", Input)
            inp.value = query   # triggers on_input_changed automatically

    def _show_detail(self, cmd: dict):
        panel = self.query_one("#right", ScrollableContainer)
        panel.remove_children()
        # Use call_after_refresh so the DOM removal completes before mounting
        # the new widget — prevents duplicate-ID crashes when clicking fast.
        self.call_after_refresh(lambda c=cmd: panel.mount(CommandDetail(c, self._hcon)))

    # ── History tab ───────────────────────────────────────────────────────────

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated):
        # Textual 8.x: pane is a property; guard against AttributeError
        try:
            pane_id = event.pane.id if event.pane else ""
        except AttributeError:
            pane_id = getattr(event.tab, "id", "")
        if "history" in pane_id:
            self._load_history_table()

    def _load_history_table(self):
        try:
            table = self.query_one("#history-table", DataTable)
            table.clear(columns=True)
            table.add_columns("Time", "Action", "What", "Command")
            for row in get_history(self._hcon):
                table.add_row(*row)
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed):
        if "btn-del-search" in event.button.classes:
            event.stop()
            self._deleting_search = True
            delete_search(self._hcon, event.button.name)
            self._show_recent_searches()
            self._deleting_search = False
            return
        if event.button.id == "hist-clear-btn":
            self._hcon.execute("DELETE FROM history")
            self._hcon.commit()
            self._load_history_table()
            self.notify("History cleared.")

    # ── Misc ──────────────────────────────────────────────────────────────────

    def action_dismiss_modal(self):
        if self.screen_stack and len(self.screen_stack) > 1:
            self.pop_screen()

    def on_unmount(self):
        self._hcon.close()


if __name__ == "__main__":
    DeamonCLIApp().run()
