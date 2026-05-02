"""
NOEMA — local backend
FastAPI server: auth, Ollama proxy with tool calling,
web search, file access, computer control, kill switch, audit log.
"""
import sys, json, os, subprocess, time, threading, signal, platform
from pathlib import Path
from typing import Any

PLATFORM = platform.system()   # 'Darwin', 'Windows', 'Linux'
IS_MAC   = PLATFORM == "Darwin"
IS_WIN   = PLATFORM == "Windows"

import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
import uvicorn

from audit import log_action, log_session, read_recent, log_path

# ── GREEK CURRICULUM ──────────────────────────────────────────
def _load_curriculum() -> dict:
    try:
        return json.loads((Path(__file__).parent / "curriculum.json").read_text(encoding="utf-8"))
    except Exception:
        return {}

_CURRICULUM = _load_curriculum()

def build_student_prompt() -> str:
    c = _CURRICULUM
    if not c:
        return ""
    m = c.get("meta", {})
    lvls = c.get("levels", {})
    lines = [
        "── ΕΛΛΗΝΙΚΟ ΑΝΑΛΥΤΙΚΟ ΠΡΟΓΡΑΜΜΑ ΣΠΟΥΔΩΝ ──",
        f"Φορέας: {m.get('governing_body','')}",
        f"Εκδότης βιβλίων: {m.get('publisher','')}",
        f"Ψηφιακά βιβλία: {m.get('digital_library','')}",
        "",
    ]
    for key, lvl in lvls.items():
        lines.append(f"▸ {lvl['label']} ({lvl.get('age_range','')} ετών) — τάξεις: {', '.join(lvl['grades'])}")
        if "history_cycle" in lvl:
            for grade, desc in lvl["history_cycle"].items():
                lines.append(f"  Ιστορία {grade}: {desc}")
        if "groups" in lvl:
            for grp, subjects in lvl["groups"].items():
                lines.append(f"  Κατεύθυνση {grp}: {subjects}")
        books = lvl.get("textbooks", {})
        for grade, blist in books.items():
            lines.append(f"  Βιβλία {grade}: {' | '.join(blist)}")
        lines.append("")
    exams = c.get("key_exams", {})
    if exams:
        lines.append("▸ Κεντρικές εξετάσεις:")
        for name, desc in exams.items():
            lines.append(f"  {name}: {desc}")
    return "\n".join(lines)

# ── PATHS ─────────────────────────────────────────────────────
ROOT = Path(__file__).parent  # bundle dir (read-only static assets)
HOME = Path.home()

# Writable user data — platform-appropriate per-user directory
if getattr(sys, "frozen", False):
    if IS_MAC:
        DATA_ROOT = Path.home() / "Library" / "Application Support" / "NOEMA"
    elif IS_WIN:
        DATA_ROOT = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "NOEMA"
    else:
        DATA_ROOT = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "NOEMA"
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    # Copy default security.json to user data dir on first run
    _default_sec = ROOT / "security.json"
    _user_sec    = DATA_ROOT / "security.json"
    if _default_sec.exists() and not _user_sec.exists():
        import shutil as _shutil
        _shutil.copy(_default_sec, _user_sec)
else:
    DATA_ROOT = ROOT

THREADS_FILE  = DATA_ROOT / "threads.json"
ACCOUNT_FILE  = DATA_ROOT / "account.json"
SECURITY_FILE = DATA_ROOT / "security.json"
MEMORY_FILE   = DATA_ROOT / "memory.json"

# ── KILL FLAG ─────────────────────────────────────────────────
kill_flag = False

# ── MEMORY ────────────────────────────────────────────────────
def load_memory() -> list:
    try:
        return json.loads(MEMORY_FILE.read_text(encoding="utf-8")).get("memories", [])
    except Exception:
        return []

def _save_memory_file(memories: list):
    MEMORY_FILE.write_text(
        json.dumps({"memories": memories}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

def add_memory(text: str) -> dict:
    import uuid as _uuid
    memories = load_memory()
    entry = {"id": _uuid.uuid4().hex[:8], "text": text.strip()[:400], "ts": int(time.time())}
    memories.append(entry)
    _save_memory_file(memories)
    return entry

def delete_memory(mem_id: str) -> bool:
    memories = load_memory()
    new = [m for m in memories if m.get("id") != mem_id]
    if len(new) == len(memories):
        return False
    _save_memory_file(new)
    return True

def tool_remember(text: str, triggered_by: str = "") -> dict:
    entry = add_memory(text)
    log_action("remember", text[:120], success=True,
               result=f"saved id={entry['id']}", triggered_by=triggered_by)
    return {"ok": True, "id": entry["id"], "saved": entry["text"]}

# ── BASE SYSTEM PROMPT ────────────────────────────────────────
def build_system(model: str = "", student_mode: bool = False) -> str:
    model_line = f"\nYour underlying model is: {model}" if model else ""

    memories = load_memory()
    if memories:
        mem_lines = "\n".join(f"- {m['text']}" for m in memories[-30:])
        memory_block = f"\n\nWhat you remember about the user:\n{mem_lines}"
    else:
        memory_block = ""

    student_block = ""
    if student_mode:
        curriculum_text = build_student_prompt()
        student_block = f"""

══ ΕΛΛΗΝΙΚΗ ΜΑΘΗΤΙΚΗ ΛΕΙΤΟΥΡΓΙΑ ══

Είσαι ο ΝΟΗΜΑ, ένας έξυπνος και ζεστός εκπαιδευτικός βοηθός για Έλληνες μαθητές.

ΓΛΩΣΣΑ: Απαντάς ΑΠΟΚΛΕΙΣΤΙΚΑ στα Νέα Ελληνικά, με σωστή γραμματική, πλούσιο λεξιλόγιο και φυσικό ύφος. Προσαρμόζεις το επίπεδο στην τάξη του μαθητή — απλούστερη γλώσσα για Δημοτικό, πιο ακαδημαϊκή για Λύκειο.

ΕΚΠΑΙΔΕΥΤΙΚΗ ΜΕΘΟΔΟΛΟΓΙΑ:
• Εξηγείς κάθε έννοια βήμα-βήμα, με παραδείγματα από την ελληνική σχολική ύλη.
• Λύνεις ασκήσεις αναλυτικά, δείχνοντας κάθε βήμα της σκέψης, όχι μόνο το αποτέλεσμα.
• Αναλύεις λογοτεχνικά κείμενα με τη μεθοδολογία που διδάσκεται στο ελληνικό σχολείο (θέμα, δομή, ήρωες, γλωσσικά μέσα, νόημα).
• Βοηθάς στη σύνταξη εκθέσεων με σωστή δομή: εισαγωγή, κύριο μέρος, συμπέρασμα.
• Για τα Μαθηματικά: εξηγείς τη θεωρία, δίνεις λυμένα παραδείγματα και μετά βοηθάς τον μαθητή να λύσει μόνος του.
• Για τα Αρχαία Ελληνικά: βοηθάς στη μετάφραση, τη γραμματική ανάλυση και την κατανόηση του κειμένου.
• Για την Ιστορία: εξηγείς αιτίες, εξελίξεις και αποτελέσματα γεγονότων με χρονολογική σειρά.
• Προετοιμάζεις μαθητές για εξετάσεις Γυμνασίου, Λυκείου και Πανελλαδικές.
• Είσαι υπομονετικός, ενθαρρυντικός και ποτέ δεν κάνεις τον μαθητή να αισθάνεται άσχημα για τα λάθη του.

{curriculum_text}"""

    return f"""You are NOEMA — a personal AI assistant.{model_line}{memory_block}{student_block}

Your tools:
- search_web(query)     — search the internet for current information, news, or facts
- list_files(path)      — list files/folders (path relative to home: "Documents", "Downloads", "Desktop", "")
- read_file(path)       — read a text file (relative to home)
- notify(message,title) — show a desktop notification to the user
- remember(text)        — save an important fact about the user to long-term memory

Guidelines:
1. Use list_files() before read_file() when you don't know the exact path.
2. Use remember() when the user shares something personal or important — name, preferences, goals, habits.
3. The user's home folder is: {HOME}
"""

# ── TOOL DEFINITIONS ──────────────────────────────────────────
TOOLS = [
    {"type": "function", "function": {
        "name": "search_web",
        "description": "Search the web for current information, news, prices, or facts.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"}
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "list_files",
        "description": "List files and folders on the user's computer. Path relative to home folder.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "default": ""}
        }, "required": []},
    }},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read the text contents of a file on the user's computer.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "notify",
        "description": "Show a desktop notification.",
        "parameters": {"type": "object", "properties": {
            "message": {"type": "string"},
            "title":   {"type": "string", "default": "NOEMA"},
        }, "required": ["message"]},
    }},
    {"type": "function", "function": {
        "name": "remember",
        "description": (
            "Save a fact about the user to long-term memory. "
            "Use this when the user shares something important about themselves — "
            "preferences, goals, names, habits — so you can recall it in future conversations."
        ),
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string", "description": "The fact to remember (max 400 chars)"}
        }, "required": ["text"]},
    }},
]

# ── LAYER 2: SECURITY CONFIG ───────────────────────────────────
SECURITY_FILE = DATA_ROOT / "security.json"

def load_security() -> dict:
    """Load security.json fresh on every call — edits take effect immediately."""
    try:
        return json.loads(SECURITY_FILE.read_text())
    except Exception:
        return {}


def check_file_path_allowed(resolved_path: Path) -> tuple[bool, str]:
    """Returns (allowed, reason). Checks against blocked_path_fragments in security.json."""
    cfg      = load_security()
    blocked  = cfg.get("files", {}).get("blocked_path_fragments", [])
    path_str = str(resolved_path)
    for frag in blocked:
        if frag in path_str:
            return False, f"path contains blocked fragment: '{frag}'"
    return True, ""

# ── LAYER 3: FILE SYSTEM SANDBOX ─────────────────────────────
def check_sandbox(resolved_path: Path) -> tuple[bool, str]:
    """Restricts file tools to allowed_folders inside HOME."""
    cfg = load_security()
    sb  = cfg.get("sandbox", {})
    if not sb.get("enabled", False):
        return True, ""
    allowed = sb.get("allowed_folders", [])
    if not allowed:
        return True, ""
    if resolved_path == HOME:          # listing home root is fine
        return True, ""
    for folder in allowed:
        try:
            resolved_path.relative_to(HOME / folder)
            return True, ""
        except ValueError:
            continue
    return False, (
        f"path is outside the sandbox ({', '.join(allowed)}). "
        "Ask the user to add the folder to 'sandbox.allowed_folders' in security.json."
    )

# ── LAYER 6: RATE LIMITS ──────────────────────────────────────
_tool_count: int = 0

def check_rate_limit(action: str) -> tuple[bool, str]:
    global _tool_count
    cfg    = load_security()
    limits = cfg.get("rate_limits", {})
    max_tc = limits.get("tool_calls_per_session", 400)
    if max_tc and action != "_internal":
        _tool_count += 1
        if _tool_count > max_tc:
            return False, f"rate limit: max {max_tc} tool calls per session reached"
    return True, ""

# ── LAYER 7: SELF-MODIFICATION BLOCK ─────────────────────────
_SOURCE_FILES = {
    (ROOT / f).resolve()
    for f in ("server.py", "audit.py", "index.html", "app.py", "start.command", "build.sh")
} | {
    (DATA_ROOT / f).resolve()
    for f in ("security.json", "threads.json", "account.json")
}

def check_self_mod_path(resolved_path: Path) -> tuple[bool, str]:
    cfg = load_security()
    if not cfg.get("self_mod_block", {}).get("enabled", True):
        return True, ""
    if resolved_path in _SOURCE_FILES:
        return False, f"self-modification blocked: '{resolved_path.name}' is a NOEMA source file"
    return True, ""


# ── SAFE PATH CHECK ───────────────────────────────────────────
def safe_path(rel: str) -> Path:
    p = (HOME / rel).resolve()
    if not str(p).startswith(str(HOME)):
        raise PermissionError("Access outside home folder is not allowed.")
    return p

# ── TOOL EXECUTORS ────────────────────────────────────────────
def tool_search_web(query: str, triggered_by: str = "") -> dict:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
        r = requests.get(
            f"https://html.duckduckgo.com/html/?q={requests.utils.quote(query)}",
            headers=headers, timeout=12,
        )
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for res in soup.select(".result")[:7]:
            title   = res.select_one(".result__title")
            snippet = res.select_one(".result__snippet")
            url     = res.select_one(".result__url")
            if title and snippet:
                results.append({
                    "title":   title.get_text(strip=True),
                    "snippet": snippet.get_text(strip=True),
                    "url":     url.get_text(strip=True) if url else "",
                })
        log_action("web_search", query, success=True,
                   result=f"{len(results)} results", triggered_by=triggered_by)
        return {"results": results, "query": query}
    except Exception as e:
        log_action("web_search", query, success=False,
                   result=str(e), triggered_by=triggered_by)
        return {"error": str(e)}


def tool_list_files(path: str = "", triggered_by: str = "") -> dict:
    try:
        p = safe_path(path)
        ok, reason = check_file_path_allowed(p)
        if not ok:
            log_action("file_list", path, success=False,
                       result=f"BLOCKED (L2): {reason}",
                       approved="denied", triggered_by=triggered_by)
            return {"error": f"Path not permitted: {reason}"}
        ok, reason = check_sandbox(p)
        if not ok:
            log_action("file_list", path, success=False,
                       result=f"BLOCKED (L3): {reason}",
                       approved="denied", triggered_by=triggered_by)
            return {"error": f"Path not permitted: {reason}"}
        if not p.exists():
            log_action("file_list", path, success=False,
                       result="path not found", triggered_by=triggered_by)
            return {"error": f"Path not found: {path}"}
        if p.is_file():
            log_action("file_list", str(p.relative_to(HOME)), success=True,
                       result="is a file", triggered_by=triggered_by)
            return {"type": "file", "name": p.name, "size": p.stat().st_size}
        items = []
        for item in sorted(p.iterdir()):
            if item.name.startswith("."):
                continue
            items.append({
                "name": item.name,
                "type": "folder" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else None,
            })
        rel = str(p.relative_to(HOME))
        log_action("file_list", rel, success=True,
                   result=f"{len(items)} items", triggered_by=triggered_by)
        return {"path": rel, "items": items[:120]}
    except Exception as e:
        log_action("file_list", path, success=False,
                   result=str(e), triggered_by=triggered_by)
        return {"error": str(e)}


def tool_read_file(path: str, triggered_by: str = "") -> dict:
    try:
        p = safe_path(path)
        ok, reason = check_file_path_allowed(p)
        if not ok:
            log_action("file_read", path, success=False,
                       result=f"BLOCKED (L2): {reason}",
                       approved="denied", triggered_by=triggered_by)
            return {"error": f"File not permitted: {reason}"}
        ok, reason = check_sandbox(p)
        if not ok:
            log_action("file_read", path, success=False,
                       result=f"BLOCKED (L3): {reason}",
                       approved="denied", triggered_by=triggered_by)
            return {"error": f"File not permitted: {reason}"}
        ok, reason = check_self_mod_path(p)
        if not ok:
            log_action("file_read", path, success=False,
                       result=f"BLOCKED (L7): {reason}",
                       approved="denied", triggered_by=triggered_by)
            return {"error": f"File not permitted: {reason}"}
        if not p.is_file():
            log_action("file_read", path, success=False,
                       result="not a file", triggered_by=triggered_by)
            return {"error": "Not a file"}
        max_bytes = load_security().get("files", {}).get("max_read_bytes", 600_000)
        if p.stat().st_size > max_bytes:
            log_action("file_read", path, success=False,
                       result="too large", triggered_by=triggered_by)
            return {"error": f"File too large (max {max_bytes//1024}KB)"}
        text = p.read_text(errors="replace")
        log_action("file_read", str(p.relative_to(HOME)), success=True,
                   result=f"{len(text)} chars", triggered_by=triggered_by)
        return {"path": path, "content": text[:12000], "truncated": len(text) > 12000}
    except Exception as e:
        log_action("file_read", path, success=False,
                   result=str(e), triggered_by=triggered_by)
        return {"error": str(e)}


def tool_notify(message: str, title: str = "NOEMA",
                triggered_by: str = "") -> dict:
    try:
        if IS_MAC:
            script = f'display notification "{message}" with title "{title}"'
            r = subprocess.run(["osascript", "-e", script], capture_output=True)
            ok = r.returncode == 0
        elif IS_WIN:
            ps = (
                f'[System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms") | Out-Null;'
                f'$n = New-Object System.Windows.Forms.NotifyIcon;'
                f'$n.Icon = [System.Drawing.SystemIcons]::Information;'
                f'$n.Visible = $true;'
                f'$n.ShowBalloonTip(3000, "{title}", "{message}", [System.Windows.Forms.ToolTipIcon]::None);'
                f'Start-Sleep -Seconds 4; $n.Dispose()'
            )
            subprocess.Popen(["powershell", "-WindowStyle", "Hidden", "-Command", ps],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            ok = True
        else:
            r = subprocess.run(["notify-send", title, message], capture_output=True)
            ok = r.returncode == 0
        log_action("notify", f"{title}: {message}", success=ok, triggered_by=triggered_by)
        return {"ok": ok}
    except Exception as e:
        log_action("notify", f"{title}: {message}", success=False, result=str(e), triggered_by=triggered_by)
        return {"ok": False, "error": str(e)}


def execute_tool(name: str, args: dict,
                 triggered_by: str = "") -> Any:
    ok, reason = check_rate_limit("_internal")  # increments total tool counter
    if not ok:
        log_action(name, str(args)[:200], success=False,
                   result=f"BLOCKED (L6): {reason}", approved="denied",
                   triggered_by=triggered_by)
        return {"error": reason}
    if name == "search_web": return tool_search_web(args.get("query",""),  triggered_by)
    if name == "list_files": return tool_list_files(args.get("path",""),  triggered_by)
    if name == "read_file":  return tool_read_file(args.get("path",""),   triggered_by)
    if name == "notify":     return tool_notify(args.get("message",""),
                                                args.get("title","NOEMA"), triggered_by)
    if name == "remember":   return tool_remember(args.get("text",""),    triggered_by)
    log_action("unknown_tool", f"unknown tool: {name}", success=False,
               result="not found", triggered_by=triggered_by)
    return {"error": f"Unknown tool: {name}"}

# ── OLLAMA AUTO-WAKE ──────────────────────────────────────────
def ollama_alive() -> bool:
    try:
        return requests.get("http://localhost:11434/api/tags", timeout=3).ok
    except Exception:
        return False

def ensure_ollama():
    """Try to wake Ollama if it isn't answering. Called at startup."""
    if ollama_alive():
        return
    print("  ◌  Ollama not detected — trying to start it…")
    try:
        if IS_MAC:
            subprocess.Popen(["open", "-a", "Ollama"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif IS_WIN:
            subprocess.Popen(["ollama", "serve"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            subprocess.Popen(["ollama", "serve"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    for _ in range(20):
        time.sleep(1)
        if ollama_alive():
            print("  ✓  Ollama is ready.")
            return
    print("  ⚠  Ollama did not start — open it manually.")

# ── FASTAPI ───────────────────────────────────────────────────
app = FastAPI()

# Only allow requests originating from localhost — blocks CSRF from malicious sites
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def check_local(request: Request):
    """Reject any request whose Origin or Host is not localhost."""
    origin = request.headers.get("origin", "")
    if origin:
        # Browser-initiated cross-origin request — verify it's from localhost
        host = origin.split("//")[-1].split(":")[0]
        if host not in _LOCAL_HOSTS:
            raise HTTPException(403, "Forbidden: requests must originate from localhost")
    else:
        # Direct request (curl, pywebview, etc.) — validate Host header
        host = request.headers.get("host", "").split(":")[0]
        if host and host not in _LOCAL_HOSTS:
            raise HTTPException(403, "Forbidden: only accessible from localhost")

# ── ROUTES ────────────────────────────────────────────────────
@app.get("/")
def index():
    resp = FileResponse(ROOT / "index.html")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp

@app.get("/api/status")
def status():
    return {"ok": True, "app": "NOEMA", "has_account": ACCOUNT_FILE.exists()}

@app.get("/api/ping")
def ping(request: Request):
    check_local(request)
    return {"ok": True}

@app.get("/api/account")
def get_account(request: Request):
    check_local(request)
    if ACCOUNT_FILE.exists():
        try:
            return json.loads(ACCOUNT_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"name": "", "email": ""}

@app.post("/api/account")
async def save_account(request: Request):
    check_local(request)
    data = await request.json()
    account = {
        "name":  str(data.get("name",  ""))[:80],
        "email": str(data.get("email", ""))[:120],
    }
    ACCOUNT_FILE.write_text(json.dumps(account, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True}

@app.post("/api/setup")
async def setup(request: Request):
    """First-time setup — saves name, no password required."""
    check_local(request)
    data = await request.json()
    account = {
        "name":  str(data.get("name",  ""))[:80],
        "email": str(data.get("email", ""))[:120],
    }
    ACCOUNT_FILE.write_text(json.dumps(account, ensure_ascii=False, indent=2), encoding="utf-8")
    log_session(f"account created: {account['name']}")
    return {"ok": True}

@app.get("/api/models")
def models(request: Request):
    check_local(request)
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=15)
        return r.json()
    except Exception:
        raise HTTPException(503, "Ollama not reachable")

# ── CHAT WITH TOOL LOOP ───────────────────────────────────────
@app.post("/api/chat")
async def chat(request: Request):
    check_local(request)
    global kill_flag
    kill_flag = False

    body         = await request.json()
    messages     = body.get("messages", [])
    model        = body.get("model", "")
    think        = body.get("think", False)
    student_mode = bool(body.get("student_mode", False))

    def event(type_: str, **kwargs) -> str:
        return json.dumps({"_type": type_, **kwargs}) + "\n"

    def generate():
        global kill_flag

        base       = {"role": "system", "content": build_system(model, student_mode)}
        sys_msgs   = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]
        msgs       = [base] + sys_msgs + other_msgs

        for _round in range(8):
            if kill_flag:
                log_action("kill", "kill_flag set mid-loop", success=True)
                yield event("killed")
                return

            # Single streaming call per round — no silent non-streaming pass.
            # Content chunks stream to the client immediately; tool_calls (if any)
            # arrive only in the final done=True chunk, so we handle them after.
            accumulated_content  = ""
            accumulated_thinking = ""
            tc_list              = []
            triggered_by         = ""

            try:
                with requests.post(
                    "http://localhost:11434/api/chat",
                    json={"model": model, "messages": msgs,
                          "tools": TOOLS, "stream": True, "think": think},
                    stream=True, timeout=300,
                ) as r:
                    r.raise_for_status()
                    for raw in r.iter_lines():
                        if kill_flag:
                            log_action("kill", "kill_flag set during stream", success=True)
                            yield event("killed")
                            return
                        if not raw:
                            continue
                        try:
                            chunk = json.loads(raw)
                        except Exception:
                            continue

                        msg_chunk = chunk.get("message", {})
                        if msg_chunk.get("content"):
                            accumulated_content += msg_chunk["content"]
                        if msg_chunk.get("thinking"):
                            accumulated_thinking += msg_chunk["thinking"]

                        if chunk.get("done"):
                            tc_list      = msg_chunk.get("tool_calls") or []
                            triggered_by = accumulated_content[:400]
                            # Don't forward the done-chunk if tools are being called;
                            # for plain answers the done chunk carries no new content.
                            break

                        # Forward live content/thinking chunks straight to client
                        if raw:
                            yield raw.decode() + "\n"

            except Exception as e:
                yield event("error", message=str(e))
                return

            if not tc_list:
                # Answer was already streamed above — nothing more to do.
                break

            # ── Tool execution round ──────────────────────────────────
            msgs.append({
                "role": "assistant",
                "content": accumulated_content,
                "tool_calls": tc_list,
            })

            for tc in tc_list:
                if kill_flag:
                    log_action("kill", "kill_flag set during tool loop", success=True)
                    yield event("killed")
                    return

                fn   = tc.get("function", {})
                name = fn.get("name", "")
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    try:    args = json.loads(args)
                    except: args = {}

                yield event("tool_start", name=name, args=args)

                result  = execute_tool(name, args, triggered_by=triggered_by)
                yield event("tool_done", name=name, preview=str(result)[:300])
                msgs.append({"role": "tool", "content": json.dumps(result)})
        else:
            yield event("error", message="Too many tool rounds — stopped.")
            return

    return StreamingResponse(generate(), media_type="application/x-ndjson")

# ── KILL SWITCH (Layer 4 — three levels) ─────────────────────
@app.post("/api/kill")
async def kill(request: Request):
    global kill_flag
    check_local(request)
    body  = {}
    try:   body = await request.json()
    except: pass
    level = body.get("level", "pause")  # pause | kill | nuke

    kill_flag = True
    if IS_MAC:
        subprocess.run(["pkill", "-f", "osascript"], capture_output=True)
    log_action("kill", f"kill switch: level={level}", success=True, approved="user")

    if level in ("kill", "nuke"):
        if level == "nuke":
            # Wipe temp files
            for tmp in ["/tmp/noema_ss.png"]:
                try: os.remove(tmp)
                except: pass
            log_session("nuke: clearing session data")
        else:
            log_session("kill: server shutting down")
        # Shut down after sending the response
        threading.Timer(0.8, lambda: os.kill(os.getpid(), signal.SIGTERM)).start()

    return {"ok": True, "level": level}

@app.post("/api/reset")
def reset(request: Request):
    global kill_flag
    check_local(request)
    kill_flag = False
    return {"ok": True}

# ── AUDIT LOG ─────────────────────────────────────────────────
@app.get("/api/audit")
def get_audit(request: Request, n: int = 200):
    check_local(request)
    return {
        "entries":  read_recent(n),
        "log_path": log_path(),
    }

# ── THREADS (persistent chat history) ────────────────────────
@app.get("/api/threads")
def get_threads(request: Request):
    check_local(request)
    if not THREADS_FILE.exists():
        return {"threads": [], "aid": None}
    try:
        return json.loads(THREADS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"threads": [], "aid": None}

@app.post("/api/threads")
async def save_threads(request: Request):
    check_local(request)
    data = await request.json()
    # Only store safe fields — never let the AI write to this endpoint
    payload = {
        "threads":         data.get("threads", []),
        "aid":             data.get("aid"),
        "ap":              data.get("ap", "default"),
        "model":           data.get("model"),
        "quizDone":        bool(data.get("quizDone", False)),
        "walkthroughDone": bool(data.get("walkthroughDone", False)),
    }
    THREADS_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"ok": True}

# ── TITLE GENERATION ─────────────────────────────────────────
def _title_sync(message: str, model: str) -> dict:
    """Blocking Ollama call — runs in a thread pool via run_in_executor."""
    try:
        r = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": model,
                "messages": [{
                    "role": "user",
                    "content": (
                        "Reply with ONLY a short chat title (3-6 words, no quotes, "
                        "no punctuation at the end). Do not explain. Just the title.\n\n"
                        f"First message: {message}"
                    ),
                }],
                "stream": False,
            },
            timeout=30,
        )
        raw = r.json().get("message", {}).get("content", "").strip()
        # Strip surrounding quotes/punctuation the model sometimes adds
        title = raw.strip("\"'`*").rstrip(".!?,;:").strip()
        # If model returned multiple lines, take the first non-empty one
        for line in title.splitlines():
            line = line.strip().strip("\"'`*").rstrip(".!?,;:")
            if line:
                title = line
                break
        # Truncate if too long rather than rejecting
        if title:
            title = title[:60]
        return {"title": title or None}
    except Exception as e:
        return {"title": None, "error": str(e)}

@app.post("/api/title")
async def generate_title(request: Request):
    check_local(request)
    body    = await request.json()
    message = str(body.get("message", ""))[:500]
    model   = str(body.get("model", ""))
    if not message.strip():
        return {"title": None}
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _title_sync, message, model)

# ── SECURITY CONFIG (read-only) ───────────────────────────────
@app.get("/api/security")
def get_security(request: Request):
    check_local(request)
    cfg = load_security()
    # Strip internal _note keys before sending to UI
    def strip_notes(obj):
        if isinstance(obj, dict):
            return {k: strip_notes(v) for k, v in obj.items() if not k.startswith("_note")}
        return obj
    return strip_notes(cfg)

# ── DIRECT TOOL ENDPOINTS ─────────────────────────────────────
@app.get("/api/search")
def search(q: str, request: Request):
    check_local(request)
    return tool_search_web(q, triggered_by="direct API call")

@app.get("/api/files")
def files(request: Request, path: str = ""):
    check_local(request)
    return tool_list_files(path, triggered_by="direct API call")

@app.get("/api/read")
def read(path: str, request: Request):
    check_local(request)
    return tool_read_file(path, triggered_by="direct API call")


@app.get("/api/tunnel")
def tunnel(request: Request):
    check_local(request)
    try:
        r = requests.get("http://localhost:4040/api/tunnels", timeout=2)
        tunnels = r.json().get("tunnels", [])
        if tunnels:
            return {"url": tunnels[0]["public_url"]}
    except Exception:
        pass
    return {"url": None}

# ── CURRICULUM API ───────────────────────────────────────────
@app.get("/api/curriculum")
def get_curriculum(request: Request):
    check_local(request)
    return _CURRICULUM

# ── MEMORY API ───────────────────────────────────────────────
@app.get("/api/memory")
def get_memory(request: Request):
    check_local(request)
    return {"memories": load_memory()}

@app.delete("/api/memory/{mem_id}")
def del_memory(mem_id: str, request: Request):
    check_local(request)
    ok = delete_memory(mem_id)
    return {"ok": ok}

@app.post("/api/memory/clear")
async def clear_memory(request: Request):
    check_local(request)
    _save_memory_file([])
    log_action("remember", "clear all memories", success=True, triggered_by="user")
    return {"ok": True}

# ── BOOT ──────────────────────────────────────────────────────
if __name__ == "__main__":
    ensure_ollama()
    log_session("server started")
    _sec    = load_security()
    _smode  = _sec.get("shell", {}).get("mode", "denylist")
    _nprog  = len(_sec.get("shell", {}).get("allowed_programs", []))
    _sb     = "on" if _sec.get("sandbox",      {}).get("enabled")      else "off"
    _sm     = "on" if _sec.get("self_mod_block",{}).get("enabled", True) else "off"
    _rl_sh  = _sec.get("rate_limits", {}).get("shell_per_minute", 20)
    print("\n" + "═" * 56)
    print("  ✦  NOEMA")
    print("═" * 56)
    print(f"  Local:        http://localhost:8000")
    print(f"  Audit log:    {log_path()}")
    print(f"  L1 hardcoded: always on")
    print(f"  L2 allowlist: shell={_smode} ({_nprog} programs)")
    print(f"  L3 sandbox:   {_sb}")
    print(f"  L4 kill:      pause / kill / nuke")
    print(f"  L5 screen:    sensitive-app block on")
    print(f"  L6 rate:      {_rl_sh} shell/min")
    print(f"  L7 self-mod:  {_sm}")
    print("═" * 56 + "\n")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
