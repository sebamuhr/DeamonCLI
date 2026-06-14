#!/usr/bin/env python3
"""Linux Reference — find commands by what they do, not by their name."""

import os, sys, json, sqlite3, subprocess, shutil, difflib, socket
import pty, fcntl, termios, struct, select, re, tempfile, shlex
from datetime import datetime
from pathlib import Path

try:
    from textual.app import App, ComposeResult
    from textual.widget import Widget
    from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
    from textual.widgets import (
        Header, Footer, ListView, ListItem, Label,
        Button, Input, Static, DataTable,
        TabbedContent, TabPane, Rule
    )
    from textual.binding import Binding
    from textual._work_decorator import work
    from rich.text import Text
    from rich.highlighter import Highlighter
except ImportError:
    print("Run: pip3 install --break-system-packages textual")
    sys.exit(1)

try:
    import pyperclip
    CLIPBOARD_OK = True
except ImportError:
    CLIPBOARD_OK = False

APP_DIR     = Path(__file__).parent
DB_PATH     = APP_DIR / "commands_db.json"
HIST_PATH   = APP_DIR / "history.db"
CONFIG_PATH = Path.home() / ".config" / "deamoncli" / "config.json"
HOME        = Path.home()

DEFAULT_LEFT_WIDTH  = 46   # terminal columns
DEFAULT_TOP_HEIGHT  = 45   # % of right pane given to detail panel

def load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text())
    except Exception:
        return {}

def save_config(data: dict) -> None:
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(data))
    except Exception:
        pass

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

def search_folders(query: str) -> list:
    """Find local directories whose name contains the query string."""
    q = query.strip()
    if len(q) < 2:
        return []
    home = Path.home()
    try:
        r = subprocess.run(
            ["find", str(home), "-maxdepth", "4", "-type", "d",
             "-not", "-path", "*/.*",
             "-not", "-path", "*/node_modules/*",
             "-not", "-path", "*/__pycache__/*",
             "-iname", f"*{q}*"],
            capture_output=True, text=True, timeout=2,
        )
        results = []
        for line in r.stdout.splitlines()[:6]:
            p = Path(line)
            try:
                rel = p.relative_to(home)
                cmd_str = f"cd ~/{rel}"
            except ValueError:
                cmd_str = f"cd {line}"
            results.append({
                "title": p.name,
                "command": cmd_str,
                "category": "Folders",
                "description": f"Navigate to  {line}",
                "keywords": ["cd", "folder", "navigate", p.name.lower()],
                "can_run": True,
                "_folder": True,
            })
        return results
    except Exception:
        return []

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

def _has_columns(con, table, needed):
    """True if `table` exists and contains every column in `needed`."""
    try:
        cols = {r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}
    except sqlite3.Error:
        return False
    return cols and needed.issubset(cols)

def init_history():
    con = sqlite3.connect(HIST_PATH)
    # Migrate any stale schema from older versions: if the table exists but is
    # missing the columns this version expects, drop and recreate it. (History
    # is non-critical convenience data, so a clean rebuild is fine.)
    if not _has_columns(con, "history", {"title", "command", "category", "action", "ran_at"}):
        con.execute("DROP TABLE IF EXISTS history")
    if not _has_columns(con, "search_history", {"query", "ran_at"}):
        con.execute("DROP TABLE IF EXISTS search_history")
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
    # Columns ordered for display: What, Action, Date/Time, Command (newest first)
    return con.execute(
        "SELECT title, action, ran_at, command FROM history ORDER BY id DESC LIMIT ?",
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

def run_command(cmd: str, cwd: str = None):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30, cwd=cwd)
        return r.stdout, r.stderr, r.returncode
    except subprocess.TimeoutExpired:
        return "", "Timed out after 30 seconds.", 1
    except Exception as e:
        return "", str(e), 1

# Full-screen / cursor-driven programs that can't render inside the embedded
# terminal — these open in a real terminal window instead.
EXTERNAL_TERM_PROGS = {
    "nano", "vim", "vi", "nvim", "emacs", "emacsclient", "pico", "joe", "micro",
    "htop", "top", "atop", "btop", "btm", "glances", "bashtop", "bpytop", "gotop",
    "iftop", "iotop", "nethogs", "nload", "vnstat",
    "less", "more", "most", "man", "info",
    "ranger", "mc", "vifm", "nnn", "lf", "ncdu",
    "tmux", "screen", "byobu",
    "ssh", "mosh", "telnet", "ftp", "sftp",
    "tig", "lazygit", "gitui", "lazydocker", "k9s",
    "alsamixer", "nmtui", "nmcli-tui", "raspi-config", "dpkg-reconfigure",
    "cmus", "mocp", "ncmpcpp", "newsboat", "vit", "calcurse", "watch",
}

ANSI_RE = re.compile(
    r'\x1b\[[0-9;?]*[ -/]*[@-~]'      # CSI sequences
    r'|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)'  # OSC sequences
    r'|\x1b[=>]'                       # keypad modes
    r'|\x1b[()][0-9A-Za-z]'           # charset selection
)

def _first_program(cmd: str) -> str:
    """The actual program a command runs, skipping env-assignments and sudo."""
    head = re.split(r'[|;&]| && | \|\| ', cmd.strip(), maxsplit=1)[0]
    try:
        toks = shlex.split(head)
    except Exception:
        toks = head.split()
    i = 0
    while i < len(toks) and "=" in toks[i] and not toks[i].startswith("-"):
        i += 1   # skip VAR=value prefixes
    if i < len(toks) and toks[i] in ("sudo", "doas"):
        i += 1
        while i < len(toks) and toks[i].startswith("-"):
            i += 1
    return os.path.basename(toks[i]) if i < len(toks) else ""

def needs_real_terminal(cmd: str) -> bool:
    return _first_program(cmd) in EXTERNAL_TERM_PROGS

# ── Placeholder detection ───────────────────────────────────────────────────────
# Parts of a command the user must replace before running, with a friendly hint.
# Rules are tried in order; earlier rules win when spans overlap.
PLACEHOLDER_RULES = [
    (re.compile(r'<[^<>\s][^<>]*>'),
     "Replace the part inside < > with your own value"),
    (re.compile(r'"My changes"'),
     "Your commit message — briefly describe what you changed"),
    (re.compile(r'"NetworkName"'),
     "Your Wi-Fi network name (list nearby ones with:  nmcli dev wifi)"),
    (re.compile(r'"?YourPassword"?'),
     "Your Wi-Fi password"),
    (re.compile(r"'Your[^']*'|\"Your[^\"]*\"|'your[^']*'|\"your[^\"]*\""),
     "Replace with your own text or question"),
    (re.compile(r'sk-ant-[\w-]+|sk-[A-Za-z][\w-]+'),
     "Paste your secret API key here (keep it private)"),
    (re.compile(r'[A-Za-z]*your-key[\w-]*|[\w-]*-key-here'),
     "Paste your secret API key here (keep it private)"),
    (re.compile(r'\buser(?:name)?@[\w.-]+'),
     "Your login and server address, e.g.  alice@203.0.113.5"),
    (re.compile(r'\b[\w.+-]+@[\w.-]*(?:server|host|remote)[\w.-]*'),
     "Your login and server address, e.g.  alice@203.0.113.5"),
    (re.compile(r'\b\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?\b'),
     "The IP address or range to use. Find your own with:  ip addr"),
    (re.compile(r'\b(?:www\.)?(?:example|yourdomain|mydomain)\.[a-z]{2,}\b'),
     "Your domain name, e.g.  mysite.com"),
    (re.compile(r'/path/to/[\w./-]+'),
     "Replace with the real path on your computer"),
    (re.compile(r'\b(?:My|New|Old|Your|Sample|Example)[A-Z][\w-]*'
                r'|\bmy-[\w-]+'
                r'|\b(?:mymodel|mydata|mysession|mysite|myvm|my-llama|mybackup|newfolder|newproject)\b'),
     "Replace with a name of your choosing"),
    # CamelCase words ending in a placeholder-noun (FolderName, FileName, ServerName…)
    # but NOT real names like AppImage / AnythingLLM / ServerAliveInterval
    (re.compile(r'\b[A-Z][a-zA-Z0-9]*?'
                r'(?:Name|Folder|File|Dir|Directory|Path|Server|Host|Hostname|Address'
                r'|Password|Passwd|Project|Branch|Repo|Repository|Device|Network|Domain|Account)\b'),
     "Replace with your own value"),
    # lowercase compound placeholders (foldername, servername, username…).
    # Deliberately excludes 'host'/'dir' so real commands hostname/dirname stay untouched.
    (re.compile(r'\b(?:folder|file|path|server|user|domain|device|branch|repo|project)name\b'),
     "Replace with your own value"),
    # install / service / container placeholders: package-name, app.id, container-id…
    # (NOT the 'name' flag in `find -name`, nor copy-id from ssh-copy-id)
    (re.compile(r'\b(?:program|package|app|module|library|service|image|container|project)[-_]name\b'
                r'|\b(?:container|image|app)[-_]id\b|\bapp\.id\b'),
     "Replace with the name of the program / item you want"),
    # example process ID (kill 12345) and GitHub owner/repo in clone URLs
    (re.compile(r'\b12345\b'),
     "Replace with the process ID — find it with:  ps aux | grep <name>"),
    (re.compile(r'\buser/repo\b'),
     "Replace 'user/repo' with the GitHub owner and repository"),
    (re.compile(r'\b(?:new|old|input|output|audio|video|image|photo|sample|example)[\w-]*\.\w+'),
     "Replace with your file's name"),
    (re.compile(r'\./[\w-]+\.\w+'),
     "Replace with the path to your file"),
    (re.compile(r'\b(?:newfile|newname|oldname|newfolder|filename|foldername)\b'),
     "Replace with your file or folder name"),
]

def find_placeholders(cmd: str):
    """Return non-overlapping (start, end, hint) spans the user should edit."""
    if not cmd:
        return []
    claimed = [False] * len(cmd)
    spans = []
    for rx, hint in PLACEHOLDER_RULES:
        for m in rx.finditer(cmd):
            s, e = m.span()
            if s == e or any(claimed[s:e]):
                continue
            for i in range(s, e):
                claimed[i] = True
            spans.append((s, e, hint))
    spans.sort()
    return spans

class PlaceholderHighlighter(Highlighter):
    """Colours the replace-me parts inside the editable command line.

    Re-runs on every keystroke, so a part loses its colour once you've
    replaced it with your own value — colour means 'still needs editing'."""
    def highlight(self, text: Text) -> None:
        for s, e, _ in find_placeholders(text.plain):
            text.stylize("bold black on yellow", s, e)

# ── Draggable dividers ───────────────────────────────────────────────────────

class ResizeDivider(Widget):
    """Thin draggable separator — orientation='vertical' or 'horizontal'."""

    DEFAULT_CSS = """
    ResizeDivider {
        background: $background;
        color: $primary-darken-2;
    }
    ResizeDivider.-vertical {
        width: 1;
    }
    ResizeDivider.-horizontal {
        height: 1;
        width: 1fr;
    }
    ResizeDivider:hover {
        color: $accent;
    }
    """

    def __init__(self, orientation: str = "vertical") -> None:
        super().__init__(classes=f"-{orientation}")
        self._orientation = orientation
        self._dragging = False

    def render(self):
        if self._orientation == "vertical":
            return "│\n" * 500
        return "─" * 500

    def on_mouse_down(self, event) -> None:
        self.capture_mouse()
        self._dragging = True
        event.stop()

    def on_mouse_move(self, event) -> None:
        if not self._dragging:
            return
        if self._orientation == "vertical":
            new_w = max(28, min(80, int(event.screen_x)))
            self.app.query_one("#left", Vertical).styles.width = new_w
            self.app._left_width = new_w
        else:
            pane = self.app.query_one("#right-pane", Vertical)
            pane_top = pane.region.y
            pane_h = pane.region.height - 4  # terminal-input-row(3) + this divider(1)
            rel_y = event.screen_y - pane_top
            pct = max(10, min(80, int(rel_y / max(1, pane_h) * 100)))
            self.app.query_one("#detail-panel", ScrollableContainer).styles.height = f"{pct}%"
            self.app._top_height = pct
        event.stop()

    def on_mouse_up(self, event) -> None:
        if self._dragging:
            self.release_mouse()
            self._dragging = False
            cfg = load_config()
            cfg["left_width"] = self.app._left_width
            cfg["top_height"] = self.app._top_height
            save_config(cfg)
        event.stop()

# ── Command detail (right panel) ──────────────────────────────────────────────

class CommandDetail(Vertical):
    def __init__(self, cmd: dict, history_con):
        # No fixed id — avoids duplicate-ID crash when switching commands quickly
        super().__init__(classes="cmd-detail")
        self.cmd = cmd
        self.hcon = history_con

    def compose(self) -> ComposeResult:
        c = self.cmd
        cmd = c["command"]
        external = needs_real_terminal(cmd)
        spans = find_placeholders(cmd)

        yield Label(c["title"], classes="detail-title")
        yield Label(c.get("category", "").upper(), classes="detail-category")
        yield Rule(classes="detail-rule")
        yield Static(c.get("description", ""), classes="detail-desc")

        if spans:
            yield Label("✎   Replace the highlighted parts below, then Run it:",
                        classes="section-label")
            seen = set()
            for s, e, hint in spans:
                tok = cmd[s:e]
                if (tok, hint) in seen:
                    continue
                seen.add((tok, hint))
                line = Text()
                line.append("• ", style="dim")
                line.append(tok, style="bold black on yellow")
                line.append("  →  ", style="dim")
                line.append(hint, style="grey85")
                yield Static(line, classes="ph-hint")
        else:
            yield Label("Command — edit if you like, then Run it:", classes="section-label")

        # The single command line: editable, with the replace-me parts coloured
        with Horizontal(classes="cmd-row"):
            yield Input(value=cmd, classes="cmd-edit",
                        highlighter=PlaceholderHighlighter())
            yield Button("▶  Run it", classes="btn-run", variant="success")
            yield Button("📋  Copy", classes="btn-copy", variant="default")

        if external:
            yield Static("↗   Opens in a new terminal window, ready for you to press Enter.",
                         classes="shell-warning")

    def _edited_command(self) -> str:
        """The command as the user has edited it (falls back to the original)."""
        try:
            v = self.query_one(".cmd-edit", Input).value
            return v if v.strip() else self.cmd["command"]
        except Exception:
            return self.cmd["command"]

    def _run(self) -> None:
        c = self.cmd
        cmd = self._edited_command()
        save_history(self.hcon, c["title"], cmd, c.get("category", ""), "ran")
        self.app._execute_terminal_cmd(cmd)
        self.app.query_one("#terminal-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # Pressing Enter inside the edit field runs the command
        if "cmd-edit" in event.input.classes:
            event.stop()
            self._run()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        c = self.cmd
        if "btn-run" in event.button.classes:
            event.stop()
            self._run()
        elif "btn-copy" in event.button.classes:
            event.stop()
            cmd = self._edited_command()
            ok = copy_to_clipboard(cmd)
            save_history(self.hcon, c["title"], cmd, c.get("category", ""), "copied")
            msg = "📋  Copied!" if ok else "Could not copy — run:  sudo apt install xclip"
            self.app.notify(msg, severity="information" if ok else "warning")

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
        width: 46;
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

    /* ── Right panel (split: detail top, terminal bottom) ── */
    #right-pane {
        width: 1fr;
        layout: vertical;
    }
    #detail-panel {
        height: auto;
        padding: 2 3;
        background: $background;
    }

    /* ── Embedded terminal — ONE black box; output grows from top, prompt follows ── */
    #terminal {
        height: 1fr;
        min-height: 6;
        background: black;
        border-top: tall $primary;     /* the ONLY divider: separates terminal from description */
        padding: 0 1;
        overflow-y: auto;
        scrollbar-size: 1 1;
    }
    #terminal-scrollback {
        height: auto;                  /* only as tall as its content → prompt sits right under */
        width: 1fr;
        background: black;
    }
    #terminal-input-row {
        height: 1;
        width: 1fr;
        background: black;             /* same bg, no border → flush under the last output line */
    }
    #terminal-prompt {
        width: auto;
        height: 1;
        color: $success;
        text-style: bold;
        background: black;
    }
    #terminal-input {
        width: 1fr;
        height: 1;
        background: black;
        border: none;
        padding: 0;
        color: $text;
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
    .ph-hint {
        color: $text-muted;
        margin: 0 0 0 1;
    }
    .cmd-row {
        height: 3;
        margin: 0 0 1 0;
    }
    .cmd-edit {
        width: 1fr;
        height: 3;
        margin: 0;
        border: round $accent;
        background: $surface;
        color: $text;
    }
    .cmd-edit:focus {
        border: round $success;
    }
    .cmd-row Button {
        height: 3;
        min-width: 12;
        margin-left: 1;
        content-align: center middle;
    }
    .action-row {
        height: 3;
        margin-top: 1;
    }
    .action-row Button {
        height: 3;
        min-width: 14;
        margin-right: 1;
        content-align: center middle;
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

    """

    BINDINGS = []  # quit only via tray icon

    def __init__(self):
        super().__init__()
        self._all_commands      = load_commands()
        self._hcon              = init_history()
        self._results: list     = []
        self._recent: list      = []
        self._deleting_search   = False
        self._cwd               = str(Path.home())
        self._term_buffer       = Text()   # committed terminal scrollback
        self._cur_line          = ""       # in-progress (un-newlined) output line
        self._proc              = None     # running child process
        self._master_fd         = None     # PTY master fd while a command runs
        self._cmd_running           = False
        self._cmd_history: list = []       # terminal commands, for ↑/↓ recall
        self._cmd_hist_idx: int = 0        # cursor into _cmd_history
        self._history_rows: list = []      # rows backing the History table
        self._render_seq        = 0        # guards against stale search results
        cfg                     = load_config()
        self._left_width: int   = cfg.get("left_width", DEFAULT_LEFT_WIDTH)
        self._top_height: int   = cfg.get("top_height", DEFAULT_TOP_HEIGHT)

    @property
    def _prompt(self) -> str:
        user = os.environ.get('USER', os.environ.get('USERNAME', 'user'))
        try:
            host = socket.gethostname()
        except Exception:
            host = 'localhost'
        home = str(Path.home())
        if self._cwd == home:
            short = '~'
        elif self._cwd.startswith(home + '/'):
            short = '~' + self._cwd[len(home):]
        else:
            short = self._cwd
        return f"{user}@{host}:{short}$ "

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

            yield ResizeDivider()

            with Vertical(id="right-pane"):
                with ScrollableContainer(id="detail-panel"):
                    yield self._welcome_widget()
                with ScrollableContainer(id="terminal"):
                    yield Static("", id="terminal-scrollback", markup=False)
                    with Horizontal(id="terminal-input-row"):
                        yield Label("", id="terminal-prompt", markup=False)
                        yield Input(id="terminal-input", placeholder="")

        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#left", Vertical).styles.width = self._left_width
        # Cap the description so the terminal always has room below it
        self.query_one("#detail-panel", ScrollableContainer).styles.max_height = "55%"
        self.query_one("#terminal-prompt", Label).update(self._prompt)

    def on_key(self, event) -> None:
        # Ctrl+C interrupts a running command instead of doing nothing
        if event.key == "ctrl+c" and self._cmd_running:
            self._interrupt()
            event.stop()
            event.prevent_default()
            return
        # ↑/↓ recall previous terminal commands, like a normal shell
        focused = self.focused
        if (focused is not None and focused.id == "terminal-input"
                and not self._cmd_running and event.key in ("up", "down")):
            self._recall_command(-1 if event.key == "up" else 1)
            event.stop()
            event.prevent_default()

    def _recall_command(self, direction: int) -> None:
        if not self._cmd_history:
            return
        inp = self.query_one("#terminal-input", Input)
        n = len(self._cmd_history)
        self._cmd_hist_idx = max(0, min(n, self._cmd_hist_idx + direction))
        if self._cmd_hist_idx >= n:          # past the newest → blank line
            inp.value = ""
        else:
            inp.value = self._cmd_history[self._cmd_hist_idx]
        inp.cursor_position = len(inp.value)

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

    async def on_input_changed(self, event: Input.Changed):
        if event.input.id != "search-input":
            return
        q = event.value.strip()
        self._render_seq += 1
        seq = self._render_seq
        if q:
            results = search_commands(q, self._all_commands)
            self._results = results
            await self._render_results(results, q, seq)
            self._search_folders_async(q)   # prepends folder hits when ready
        else:
            self._results = []
            await self._show_recent_searches(seq)

    @work(thread=True)
    def _search_folders_async(self, query: str) -> None:
        folders = search_folders(query)
        if folders:
            self.app.call_from_thread(self._prepend_folder_results, query, folders)

    def _prepend_folder_results(self, query: str, folders: list) -> None:
        current_q = self.query_one("#search-input", Input).value.strip()
        if current_q == query:
            self._results = folders + self._results
            self._render_seq += 1
            self.run_worker(self._render_results(self._results, query, self._render_seq))

    def on_input_submitted(self, event: Input.Submitted):
        if event.input.id == "search-input":
            save_search(self._hcon, event.value.strip())
        elif event.input.id == "terminal-input":
            text = event.value
            event.input.value = ""
            if self._cmd_running and self._master_fd is not None:
                # A command is running: send this line to its stdin (password, y/n, chat…)
                try:
                    os.write(self._master_fd, (text + "\n").encode())
                except OSError:
                    pass
            else:
                cmd = text.strip()
                if cmd:
                    self._execute_terminal_cmd(cmd)

    # ── Embedded terminal ─────────────────────────────────────────────────────

    def _term_commit(self, renderable, style: str = "") -> None:
        """Append a finished line to the committed scrollback."""
        if self._term_buffer.plain:
            self._term_buffer.append("\n")
        if isinstance(renderable, Text):
            self._term_buffer.append_text(renderable)
        else:
            self._term_buffer.append(str(renderable), style=style)
        # Keep memory bounded: trim to the last ~1500 lines
        nlines = self._term_buffer.plain.count("\n")
        if nlines > 1500:
            keep = "\n".join(self._term_buffer.plain.split("\n")[-1200:])
            self._term_buffer = Text(keep, style="grey85")

    def _render_terminal(self) -> None:
        """Repaint the scrollback (committed lines + the in-progress line)."""
        disp = self._term_buffer.copy()
        if self._cur_line:
            if disp.plain:
                disp.append("\n")
            disp.append(self._cur_line, style="grey85")
        self.query_one("#terminal-scrollback", Static).update(disp)
        self.call_after_refresh(
            lambda: self.query_one("#terminal", ScrollableContainer).scroll_end(animate=False)
        )

    def _feed_output(self, text: str) -> None:
        """Stream raw PTY output into the scrollback, handling \\r, \\b and ANSI."""
        # Normalise CRLF first; a lone \r remains (progress-bar line overwrite)
        text = ANSI_RE.sub("", text).replace("\r\n", "\n")
        for ch in text:
            if ch == "\r":
                self._cur_line = ""
            elif ch == "\n":
                self._term_commit(self._cur_line, style="grey85")
                self._cur_line = ""
            elif ch == "\b":
                self._cur_line = self._cur_line[:-1]
            elif ch == "\t":
                self._cur_line += "    "
            elif ch >= " ":
                self._cur_line += ch
        self._render_terminal()

    def _set_running(self, running: bool) -> None:
        self._cmd_running = running
        inp = self.query_one("#terminal-input", Input)
        lbl = self.query_one("#terminal-prompt", Label)
        if running:
            lbl.update("» ")
            inp.placeholder = "type to answer the running command — Ctrl+C to stop"
        else:
            lbl.update(self._prompt)
            inp.placeholder = ""

    def _execute_terminal_cmd(self, cmd: str) -> None:
        # Echo the prompt + command, coloured like a real shell
        line = Text()
        line.append(self._prompt, style="bold green")
        line.append(cmd, style="bold bright_white")
        self._term_commit(line)
        self._render_terminal()
        self.query_one("#terminal-input", Input).value = ""

        if self._cmd_running:
            self._term_commit(Text("a command is already running — press Ctrl+C to stop it first",
                                   style="yellow"))
            self._render_terminal()
            return

        # Record in the ↑/↓ recall history (skip consecutive duplicates)
        if cmd.strip() and (not self._cmd_history or self._cmd_history[-1] != cmd):
            self._cmd_history.append(cmd)
        self._cmd_hist_idx = len(self._cmd_history)

        # cd is handled locally so it persists across commands
        parts = cmd.strip().split()
        if parts and parts[0] == "cd":
            target = os.path.expanduser(parts[1] if len(parts) > 1 else "~")
            if not os.path.isabs(target):
                target = os.path.join(self._cwd, target)
            target = os.path.normpath(target)
            if os.path.isdir(target):
                self._cwd = target
                self.query_one("#terminal-prompt", Label).update(self._prompt)
            else:
                self._term_commit(f"cd: no such directory: {target}", style="bold red")
                self._render_terminal()
            return

        # Full-screen / cursor programs open in a real terminal, pre-typed
        if needs_real_terminal(cmd):
            self._open_in_real_terminal(cmd)
            return

        self._spawn_pty(cmd)

    # ── PTY-backed execution (sudo, prompts and interactive all work here) ──────
    def _spawn_pty(self, cmd: str) -> None:
        master, slave = pty.openpty()
        try:
            cols = max(self.query_one("#terminal", ScrollableContainer).size.width - 2, 20)
        except Exception:
            cols = 80
        try:
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, cols, 0, 0))
        except Exception:
            pass
        env = {**os.environ, "TERM": "xterm-256color", "PAGER": "cat", "GIT_PAGER": "cat"}
        try:
            proc = subprocess.Popen(
                ["bash", "-lc", cmd],
                stdin=slave, stdout=slave, stderr=slave,
                cwd=self._cwd, env=env,
                preexec_fn=os.setsid, close_fds=True,
            )
        except Exception as e:
            try:
                os.close(master); os.close(slave)
            except Exception:
                pass
            self._term_commit(Text(f"failed to start: {e}", style="bold red"))
            self._render_terminal()
            return
        os.close(slave)
        self._proc = proc
        self._master_fd = master
        self._set_running(True)
        self._read_pty_worker()

    @work(thread=True)
    def _read_pty_worker(self) -> None:
        fd, proc = self._master_fd, self._proc
        while True:
            try:
                r, _, _ = select.select([fd], [], [], 0.1)
            except (OSError, ValueError):
                break
            if r:
                try:
                    data = os.read(fd, 65536)
                except OSError:
                    break
                if not data:
                    break
                self.call_from_thread(self._feed_output, data.decode("utf-8", "replace"))
            elif proc.poll() is not None:
                break
        # Drain anything left after the process exits
        try:
            while True:
                r, _, _ = select.select([fd], [], [], 0.05)
                if not r:
                    break
                data = os.read(fd, 65536)
                if not data:
                    break
                self.call_from_thread(self._feed_output, data.decode("utf-8", "replace"))
        except OSError:
            pass
        rc = proc.wait()
        self.call_from_thread(self._cmd_finished, rc)

    def _cmd_finished(self, rc: int) -> None:
        if self._cur_line:
            self._term_commit(self._cur_line, style="grey85")
            self._cur_line = ""
        try:
            if self._master_fd is not None:
                os.close(self._master_fd)
        except Exception:
            pass
        self._master_fd = None
        self._proc = None
        self._set_running(False)
        if rc not in (0, None):
            self._term_commit(Text(f"[exit {rc}]", style="yellow"))
        self._render_terminal()

    def _interrupt(self) -> None:
        """Send Ctrl-C to the running command (without quitting the app)."""
        if self._cmd_running and self._master_fd is not None:
            try:
                os.write(self._master_fd, b"\x03")
            except OSError:
                pass

    # ── Open a full-screen program in a real terminal, command pre-typed ────────
    def _open_in_real_terminal(self, cmd: str) -> None:
        env = {**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")}
        rcfile = tempfile.NamedTemporaryFile("w", suffix=".dcrc", delete=False)
        rcfile.write("source ~/.bashrc 2>/dev/null\n")
        rcfile.write(f"cd {shlex.quote(self._cwd)} 2>/dev/null\n")
        if "\n" not in cmd:
            esc = cmd.replace("\\", "\\\\").replace('"', '\\"')
            rcfile.write(f'history -s "{esc}"\n')
            # Pre-fill the prompt with the command (user just presses Enter to run)
            rcfile.write(f"bind '\"\\e[0n\": \"{esc}\"' 2>/dev/null\n")
            rcfile.write("printf '\\e[5n'\n")
        else:
            rcfile.write("printf '%s\\n' '# paste-ready command was multi-line; see below'\n")
            for ln in cmd.splitlines():
                rcfile.write(f'history -s {shlex.quote(ln)}\n')
        # The bind lives in shell memory, so the temp rcfile can delete itself now
        rcfile.write(f"rm -f {shlex.quote(rcfile.name)}\n")
        rcfile.close()

        launched = False
        for term in (["gnome-terminal", "--", "bash", "--rcfile", rcfile.name, "-i"],
                     ["x-terminal-emulator", "-e", f"bash --rcfile {shlex.quote(rcfile.name)} -i"],
                     ["xterm", "-e", f"bash --rcfile {shlex.quote(rcfile.name)} -i"]):
            if shutil.which(term[0]):
                try:
                    subprocess.Popen(term, env=env, start_new_session=True)
                    launched = True
                    break
                except Exception:
                    continue
        if launched:
            self._term_commit(Text("↗ opened in a new terminal window — press Enter there to run it",
                                   style="cyan"))
        else:
            self._term_commit(Text("could not open a terminal window — use Copy instead",
                                   style="bold red"))
        self._render_terminal()

    async def _render_results(self, results: list, query: str, seq: int = None):
        lv = self.query_one("#results-list", ListView)
        await lv.clear()                       # wait for the old items to clear
        if seq is not None and seq != self._render_seq:
            return                             # a newer query already superseded this one
        new_items = []
        for i, cmd in enumerate(results[:60]):
            if cmd.get("_folder"):
                icon = "📁 "
            elif cmd.get("can_run", True):
                icon = "  "
            else:
                icon = "⚠ "
            new_items.append(
                ListItem(Label(f"{icon}{cmd['title']}", markup=False), name=f"r{i}")
            )
        if not new_items:
            new_items.append(ListItem(Label("No results — try other words or a phrase.")))
        await lv.extend(new_items)

    async def _show_recent_searches(self, seq: int = None):
        self._recent = get_recent_searches(self._hcon)
        lv = self.query_one("#results-list", ListView)
        await lv.clear()
        if seq is not None and seq != self._render_seq:
            return
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
        await lv.extend(new_items)

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
        panel = self.query_one("#detail-panel", ScrollableContainer)
        panel.remove_children()
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
            table.add_columns("What", "Action", "Date/Time", "Command")
            self._history_rows = get_history(self._hcon)
            for row in self._history_rows:
                table.add_row(*row)
        except Exception:
            pass

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        # Selecting a history row loads it into the top-right field to run again
        if event.data_table.id != "history-table":
            return
        try:
            title, _action, _when, command = self._history_rows[event.cursor_row]
        except (IndexError, AttributeError, TypeError):
            return
        self._show_detail({"title": title, "command": command, "category": "History"})

    def on_button_pressed(self, event: Button.Pressed):
        if "btn-del-search" in event.button.classes:
            event.stop()
            self._deleting_search = True
            delete_search(self._hcon, event.button.name)
            self._render_seq += 1
            self.run_worker(self._show_recent_searches(self._render_seq))
            self._deleting_search = False
            return
        if event.button.id == "hist-clear-btn":
            self._hcon.execute("DELETE FROM history")
            self._hcon.commit()
            self._load_history_table()
            self.notify("History cleared.")
            return

    def on_unmount(self):
        # Stop any running child so it doesn't linger after the app closes
        if self._proc is not None:
            try:
                os.killpg(os.getpgid(self._proc.pid), 15)
            except Exception:
                pass
        cfg = load_config()
        cfg["left_width"] = self._left_width
        try:
            ts = os.get_terminal_size()
            cfg["geometry"] = f"{ts.columns}x{ts.lines}"
        except Exception:
            pass
        save_config(cfg)
        self._hcon.close()


if __name__ == "__main__":
    DeamonCLIApp().run()
