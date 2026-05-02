"""
NOEMA — launcher
Starts the FastAPI server in a background thread, then opens a WebKit window.
Works both as a plain Python script and as a PyInstaller .app bundle.
"""
import os, sys, time, threading, subprocess, platform, random
import requests

_IS_MAC = platform.system() == "Darwin"
_IS_WIN = platform.system() == "Windows"

def is_running() -> bool:
    try:
        return requests.get("http://localhost:8000/api/status", timeout=1).ok
    except Exception:
        return False

def start_server():
    if is_running():
        return
    import uvicorn
    import server as _server  # noqa: import triggers path setup in server.py
    _server.ensure_ollama()
    t = threading.Thread(
        target=uvicorn.run,
        args=(_server.app,),
        kwargs={"host": "127.0.0.1", "port": 8000, "log_level": "warning"},
        daemon=True,
    )
    t.start()
    for _ in range(40):
        time.sleep(0.3)
        if is_running():
            return
    print("NOEMA: server did not start in time.", file=sys.stderr)

if __name__ == "__main__":
    if _IS_MAC:
        subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])
    start_server()

    try:
        import webview
        _bust = random.randint(100000, 999999)
        win = webview.create_window(
            "NOEMA",
            f"http://localhost:8000/?v={_bust}",
            width=1320,
            height=840,
            min_size=(900, 620),
            background_color="#000000",
        )
        def _clear_cache():
            try:
                win.evaluate_js(
                    "if('caches' in window){caches.keys().then(ks=>ks.forEach(k=>caches.delete(k)))}"
                )
            except Exception:
                pass
        webview.start(func=_clear_cache, args=[win])
    except Exception:
        url = "http://localhost:8000"
        if _IS_MAC:
            subprocess.Popen(["open", url])
        elif _IS_WIN:
            os.startfile(url)
        else:
            subprocess.Popen(["xdg-open", url])
        while True:
            time.sleep(60)
