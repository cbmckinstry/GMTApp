"""GMTCrewManager desktop app: the calculator in its own window, with the Java solver and the page server local.

packaging/build.py turns this into a standalone app. To run it from this folder, use `python run_local.py`, which
compiles the solver in core/ first. `python main.py` also works once the solver is compiled.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import sys
import threading
import time
from pathlib import Path

APP_NAME = "GMTCrewManager"
OLD_APP_NAME = "Pre-Clustering"  # the app's name before; its data folder is moved over on first launch
PY4J_JAR = "py4j0.10.9.9.jar"


def resource_dir() -> Path:
    """Where the bundled files are: PyInstaller's unpack folder when built, this folder otherwise."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def version(base: Path) -> str:
    try:
        return (base / "VERSION").read_text().strip()
    except OSError:
        return "dev"


def data_dir() -> Path:
    """A per-user folder for saved results. It is outside the app, so updates never touch it."""
    if sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    elif sys.platform == "win32":
        root = Path(os.environ.get("APPDATA", Path.home()))
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    folder = root / APP_NAME
    old = root / OLD_APP_NAME
    if old.is_dir() and not folder.exists():
        old.rename(folder)  # keeps results saved before the app was renamed
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_port(port: int, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.1)
    raise RuntimeError(f"nothing started on port {port} within {timeout:.0f} s")


def java_command(base: Path) -> list[str]:
    """The bundled Java runtime and solver jar if built, otherwise Java from the PATH and the solver in core/."""
    bundled = base / "runtime" / "bin" / ("java.exe" if sys.platform == "win32" else "java")
    java = str(bundled) if bundled.exists() else shutil.which("java")
    if not java:
        raise RuntimeError("Java was not found")
    built = (base / "solver.jar").exists()
    solver = base / "solver.jar" if built else base / "core"
    py4j = base / PY4J_JAR if built else base / "core" / PY4J_JAR
    ortools = sorted((base / "ortools").glob("*.jar"))      # without them the solver works, more slowly
    classpath = os.pathsep.join(map(str, [solver, py4j, *ortools]))
    return [java, "-Xmx1g", "-cp", classpath, "Combine"]


STARTING_PAGE = """<!doctype html><html><body style="margin:0;height:100vh;display:flex;align-items:center;
justify-content:center;font-family:-apple-system,'Segoe UI',sans-serif;color:#555;background:#fff">
<div style="text-align:center"><div style="font-size:22px;margin-bottom:8px">{title}</div>
<div>{message}</div></div></body></html>"""


class Services:
    """The solver and the page server, started behind the window so it can appear at once."""

    def __init__(self, base: Path):
        self.base = base

    def start(self, window) -> None:
        try:
            web_port = free_port()
            os.environ["PRECLUSTERING_DATA_DIR"] = str(data_dir())
            # core.Solver runs the solver while the window is in use, stopping it after a long idle spell.
            os.environ["COMBINE_COMMAND"] = json.dumps(java_command(self.base))
            from core import Solver
            Solver.ensure_running()

            from app import app  # after the environment is set: app reads it on import
            threading.Thread(target=lambda: app.run(host="127.0.0.1", port=web_port, threaded=True,
                                                    use_reloader=False), daemon=True).start()
            wait_for_port(web_port, timeout=60)
            window.load_url(f"http://127.0.0.1:{web_port}/")
        except Exception as e:
            window.load_html(STARTING_PAGE.format(title=f"{APP_NAME} could not start", message=str(e)))

    def stop(self) -> None:
        from core import Solver
        Solver.stop()


def main() -> None:
    import webview

    base = resource_dir()
    services = Services(base)
    window = webview.create_window(f"{APP_NAME} {version(base)}",
                                   html=STARTING_PAGE.format(title=APP_NAME, message="Starting…"),
                                   width=1280, height=900, min_size=(800, 600))
    try:
        webview.start(services.start, window)    # runs services.start on a background thread
    finally:
        services.stop()


if __name__ == "__main__":
    main()
