"""
NOEMA — audit log
Append-only record of every action the agent takes.
Stored at ~/Documents/agent-workspace/audit.log

This file must never be modified by the agent itself (enforced in Layer 7).
"""
import json
from datetime import datetime
from pathlib import Path

WORKSPACE = Path.home() / "Documents" / "agent-workspace"
LOG_FILE  = WORKSPACE / "audit.log"

# Action type labels shown in the UI
ACTION_LABELS = {
    "shell":       "Shell command",
    "file_read":   "Read file",
    "file_list":   "List files",
    "file_write":  "Write file",
    "app_open":    "Open app",
    "screenshot":  "Screenshot",
    "web_search":  "Web search",
    "applescript": "AppleScript",
    "notify":      "Notification",
    "kill":        "Kill switch",
    "session":     "Session event",
}

def _ensure():
    WORKSPACE.mkdir(parents=True, exist_ok=True)

def log_action(
    action_type:  str,
    detail:       str,
    success:      bool,
    result:       str  = "",
    approved:     str  = "auto",   # "auto" | "confirmed" | "denied"
    triggered_by: str  = "",       # snippet of AI reasoning that called this tool
):
    """
    Write one entry to audit.log. Always appends, never overwrites.
    Called from every tool executor in server.py.
    """
    _ensure()
    entry = {
        "ts":           datetime.now().isoformat(timespec="milliseconds"),
        "type":         action_type,
        "label":        ACTION_LABELS.get(action_type, action_type),
        "detail":       str(detail)[:600],
        "approved":     approved,
        "success":      success,
        "result":       str(result)[:300] if result else "",
        "triggered_by": str(triggered_by)[:400] if triggered_by else "",
    }
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def log_session(event: str):
    """Log session-level events: startup, shutdown, kill, nuke."""
    log_action("session", event, success=True, approved="system")


def read_recent(n: int = 200) -> list[dict]:
    """Return the last n entries, newest first."""
    _ensure()
    if not LOG_FILE.exists():
        return []
    try:
        lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    entries = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except Exception:
            continue
        if len(entries) >= n:
            break
    return entries


def log_path() -> str:
    return str(LOG_FILE)
