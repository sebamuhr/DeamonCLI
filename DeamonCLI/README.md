# DeamonCLI

**An interactive Linux command reference with a built-in terminal.**

Stop googling the same commands over and over. DeamonCLI lives in your system tray and lets you search for what you want to do in plain English — it finds the command, explains it, and runs it right there.

![DeamonCLI logo](DeamonCLI_logo.png)

---

## What it does

- **Search by intent** — type *"make sound louder"*, *"scan my network"*, or *"connect to server"* and it finds the right command
- **172 commands** across 12 categories: Sound, WiFi, Files, SSH, Git, Security, Bluetooth, USB, Processes, and more
- **Built-in terminal** — run commands directly inside the app and keep working without switching windows
- **System tray icon** — lives near your wifi/bluetooth icons; click to open or quit
- **Remembers your layout** — window size, panel positions, and divider sizes are saved between sessions
- **Command history** — see everything you've run or copied, with timestamps

---

## Install

### Requirements
- Linux (Ubuntu, Zorin OS, or any Debian-based distro)
- Python 3.8+
- gnome-terminal

### One-command install

```bash
git clone https://github.com/sebamuhr/DeamonCLI.git
cd DeamonCLI/MasterCLI
bash install.sh
```

The installer will:
1. Install Python packages (`textual`, `pyperclip`)
2. Install the AppIndicator library (for the tray icon)
3. Copy files to `~/.local/share/deamoncli/`
4. Create a desktop shortcut and app menu entry
5. Set the tray icon to start automatically on login

To uninstall: `bash install.sh --uninstall`

---

## How to use

### Opening the app
- Click the **daemon face icon** in the system tray (near wifi/bluetooth)
- Or double-click the desktop shortcut
- Or search "DeamonCLI" in your apps menu

### Searching
Type anything in the search box — plain English works fine:

| You type | It finds |
|---|---|
| `loud` | Make the sound louder |
| `scan network` | Discover all devices on local network |
| `connect server` | SSH commands |
| `check who logged in` | Login history, failed attempts |
| `encrypt file` | GPG encryption commands |

Results appear instantly. Click any result to see the full explanation and command.

### Running commands
Each command shows:
- **What it does** — a plain English explanation
- **The command** — exact syntax, ready to use
- **Run it** — executes the command in the built-in terminal below
- **Copy** — copies to clipboard so you can paste in your own terminal

Commands marked ⚠ require a real terminal (they need sudo or are interactive) — use **Copy** and paste them.

### Built-in terminal
The bottom panel is a real terminal session. You can:
- Run any command, not just ones from the database
- Use `cd` to navigate folders — the prompt updates to show where you are
- Chain commands, pipe output, do your work without leaving the app

### Resizing panels
- Drag the **vertical bar** between the search panel and detail panel to resize them
- Drag the **horizontal bar** between the command detail and terminal to resize them
- Sizes are saved automatically

### Quitting
Click the tray icon → **Quit**. This is the only way to fully close the app. Closing the window with X keeps the tray icon running so you can reopen it.

---

## Categories

| Category | Examples |
|---|---|
| Sound & Audio | volume, mute, audio devices, PulseAudio |
| WiFi & Network | IP address, connect to WiFi, download files |
| Display & Screen | screenshots, brightness, monitor settings |
| Files & Folders | find, copy, move, compress, permissions |
| Processes & System | CPU, RAM, running processes, system info |
| SSH & Remote | connect, copy files, tunnels, firewall |
| Cybersecurity | nmap, tcpdump, GPG, openssl, fail2ban, lynis |
| Development | Git, Python, Node, packages |
| Bluetooth | pair, connect, scan devices |
| USB & Hardware | list devices, temperatures, battery |
| Users & Security | accounts, passwords, groups |
| Text & Files | grep, sed, head, tail, sort |

---

## Tech stack

- **[Textual](https://textual.textualize.io/)** — Python TUI framework
- **SQLite** — search and command history
- **AppIndicator3 / AyatanaAppIndicator3** — system tray icon
- **GTK3** — tray menu

---

## Files

```
MasterCLI/
├── linux_ref.py        # Main app (Textual TUI)
├── commands_db.json    # All 172 commands
├── tray.py             # System tray daemon
├── launch.sh           # Smart launcher (geometry, tray)
├── install.sh          # Installer / uninstaller
└── DeamonCLI_logo.png  # App icon
```

Config is stored at `~/.config/deamoncli/config.json` (window size, panel layout).
