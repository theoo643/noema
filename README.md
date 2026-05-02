# NOEMA

A personal AI assistant that runs entirely on your computer. No cloud, no subscriptions — everything stays local.

Built on [Ollama](https://ollama.com), NOEMA gives you a clean chat interface with personas, memory, web search, file access, and an exam quiz mode for students.

---

## Features

- **Local AI** — runs any Ollama model, fully offline
- **Personas** — switch between different assistants (homework helper, maths tutor, general chat, and more)
- **Greek Student Mode** — grade-aware quiz mode with curriculum-matched questions
- **Exam Quiz** — test yourself on any subject, scored and explained
- **Web Search** — searches the web and summarises results
- **File Access** — read and list files on your computer
- **Memory** — remembers things across conversations
- **Audit Log** — every action logged, nothing hidden
- **Export** — download any conversation as a .txt file
- **Emergency Stop** — Cmd+Shift+Esc kills everything instantly

---

## Requirements

- macOS 12 or later
- [Ollama](https://ollama.com) installed and running
- At least one model pulled, e.g. `ollama pull llama3`

---

## Install

1. Download `NOEMA.dmg` from [Releases](../../releases)
2. Open the DMG, drag NOEMA to Applications
3. Right-click NOEMA → Open (first launch only, to bypass Gatekeeper)
4. Make sure Ollama is running before you start

---

## Build from Source

```bash
git clone https://github.com/theoo643/noema.git
cd noema
pip3 install -r requirements.txt
./build.sh
```

This produces `NOEMA.app` (installed to `~/Applications`) and `NOEMA.dmg` for distribution.

For quick updates after editing source files:

```bash
./deploy.sh index.html
./deploy.sh server.py
```

---

## Running without building

```bash
pip3 install -r requirements.txt
python3 app.py
```

---

## Stack

- **Frontend** — vanilla HTML/CSS/JS
- **Backend** — Python, FastAPI, Uvicorn
- **AI** — Ollama (local LLM)
- **Desktop** — pywebview (WKWebView on macOS)
- **Packaging** — PyInstaller

---

## License

MIT
