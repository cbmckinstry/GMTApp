"""Runs the desktop app from this folder, without building it: `python run_local.py`.

Compiles the solver in core/ whenever its source is newer than the compiled classes (so a core update is picked up),
fetches the OR-Tools jars into ortools/ if they are missing, then opens the app window through main.py. Needs a JDK
(javac) on the PATH and the packages in requirements.txt.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
CORE_DIR = PROJECT_DIR / "core"         # the shared code, a git submodule
PY4J_JAR = CORE_DIR / "py4j0.10.9.9.jar"
ORTOOLS_DIR = PROJECT_DIR / "ortools"   # main.py puts the jars here on the solver's class path

os.chdir(PROJECT_DIR)
sys.path.insert(0, str(PROJECT_DIR))


def ortools_jars() -> list[Path]:
    """The OR-Tools jars, downloaded if missing. Empty if that fails: the solver then works without them."""
    try:
        from core import OrTools
        return OrTools.jars(ORTOOLS_DIR)
    except Exception as e:
        print(f"[!] Running without OR-Tools: {e}")
        return []


def compile_java(ortools: list[Path]) -> None:
    """Compiles Combine.java, and SatOracle.java when the OR-Tools jars are there, if any class is out of date."""
    if not shutil.which("javac"):
        sys.exit("[!] 'javac' not found on PATH. Install a JDK 17 or newer.")
    if not PY4J_JAR.exists():
        sys.exit(f"[!] {PY4J_JAR} not found. Run: git submodule update --init")

    java_files = [CORE_DIR / "Combine.java"]
    if ortools:
        java_files.append(CORE_DIR / "SatOracle.java")
    stale = [f for f in java_files
             if not f.with_suffix(".class").exists() or f.stat().st_mtime > f.with_suffix(".class").stat().st_mtime]
    if not stale:
        print("[*] Solver already compiled.")
        return

    print("[*] Compiling the solver...")
    classpath = os.pathsep.join(map(str, [PY4J_JAR, CORE_DIR, *ortools]))
    subprocess.check_call(["javac", "-cp", classpath, *map(str, java_files)])


def check_packages() -> None:
    """Stops with the install command if this Python lacks the packages in requirements.txt."""
    missing = []
    for module, package in [("webview", "pywebview"), ("flask", "Flask"), ("flask_session", "Flask-Session"),
                            ("py4j", "py4j")]:
        try:
            __import__(module)
        except ImportError:
            missing.append(package)
    if missing:
        sys.exit(f"[!] {sys.executable} is missing {', '.join(missing)}. Either run this with the Python that has them "
                 f"(such as .venv), or install them into this one:\n"
                 f"    \"{sys.executable}\" -m pip install -r requirements.txt")


if __name__ == "__main__":
    check_packages()
    compile_java(ortools_jars())
    import main
    main.main()
