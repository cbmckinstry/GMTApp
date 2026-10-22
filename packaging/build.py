"""Builds the app for the system this runs on: one double-clickable app that holds everything it needs.

    python packaging/build.py

Needs a JDK 17+ (javac, jar, jdeps, jlink) and `pip install -r requirements.txt`. Output goes to one folder per
version, with a subfolder per system:
    dist/Pre-Clustering-<version>/
        How to install.txt
        Mac (Apple Silicon)/  Pre-Clustering.app
        Mac (Intel)/          Pre-Clustering.app
        Windows/              Pre-Clustering.exe
        Linux/                Pre-Clustering
Each system has to be built on that system, so a local build fills in only its own subfolder; the release
workflow builds all of them and publishes the whole folder as one zip.
The version is APP_VERSION from the environment (the release workflow sets it from the tag), else VERSION.
The app icon is made from packaging/app-icon.png (best as a square PNG of 1024 x 1024).
"""
from __future__ import annotations

import os
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
WORK = PROJECT / "build"
DIST = PROJECT / "dist"
APP_NAME = "Pre-Clustering"
BUNDLE_ID = "com.preclustering.desktop"
CORE = PROJECT / "core"          # the shared code, a git submodule
PY4J_JAR = CORE / "py4j0.10.9.9.jar"
ICON_PNG = PROJECT / "packaging" / "app-icon.png"
APP_DIR = WORK / "app"          # PyInstaller's output, before packaging

HOW_TO_INSTALL = """Pre-Clustering {version}

Open the folder for your system and double-click the app. To update, replace it with the newer one;
saved results are kept separately and are not affected.

Mac       Use Mac (Apple Silicon) for M1 and newer, Mac (Intel) for older Macs. You can move the app to
          Applications. First launch: right-click the app, choose Open, then Open again.
Windows   Double-click Pre-Clustering.exe. First launch: on "Windows protected your PC" choose More info,
          then Run anyway.
Linux     Run the Pre-Clustering file.
"""


def app_version() -> str:
    return os.environ.get("APP_VERSION", "").strip().lstrip("v") or (PROJECT / "VERSION").read_text().strip()


def chip() -> str:
    return platform.machine().lower().replace("amd64", "x86_64").replace("aarch64", "arm64")


def jdk_tool(name: str) -> str:
    """A JDK tool from JAVA_HOME if set, otherwise from the PATH."""
    exe = name + (".exe" if sys.platform == "win32" else "")
    java_home = os.environ.get("JAVA_HOME")
    if java_home and (Path(java_home) / "bin" / exe).exists():
        return str(Path(java_home) / "bin" / exe)
    found = shutil.which(name)
    if not found:
        sys.exit(f"{name} not found: install a JDK 17 or newer")
    return found


def run(cmd: list[str]) -> str:
    print("$", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


# --- the pieces that go into the app ---

def build_solver() -> Path:
    """Combine.java compiled into one jar."""
    classes = WORK / "java"
    shutil.rmtree(classes, ignore_errors=True)
    classes.mkdir(parents=True)
    run([jdk_tool("javac"), "--release", "17", "-cp", str(PY4J_JAR), "-d", str(classes), str(CORE / "Combine.java")])
    jar = WORK / "solver.jar"
    jar.unlink(missing_ok=True)
    run([jdk_tool("jar"), "--create", "--file", str(jar), "-C", str(classes), "."])
    return jar


def build_runtime(solver: Path) -> Path:
    """A Java runtime trimmed to the modules the solver and py4j use."""
    modules = run([jdk_tool("jdeps"), "--print-module-deps", "--ignore-missing-deps", "--multi-release", "17",
                   "-cp", str(PY4J_JAR), str(PY4J_JAR), str(solver)]).strip() or "java.base,java.logging"
    runtime = WORK / "runtime"
    shutil.rmtree(runtime, ignore_errors=True)
    base = [jdk_tool("jlink"), "--add-modules", modules, "--strip-debug", "--no-header-files", "--no-man-pages",
            "--output", str(runtime)]
    try:
        run(base + ["--compress", "zip-6"])        # JDK 21+
    except subprocess.CalledProcessError:
        shutil.rmtree(runtime, ignore_errors=True)
        run(base + ["--compress=2"])               # JDK 17
    return runtime


def build_icon() -> Path | None:
    """The app icon for this system, made from ICON_PNG: .icns on macOS, .ico elsewhere."""
    png = ICON_PNG.read_bytes()
    if sys.platform == "darwin":
        iconset = WORK / "app.iconset"
        shutil.rmtree(iconset, ignore_errors=True)
        iconset.mkdir(parents=True)
        for size in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                name = f"icon_{size}x{size}{'@2x' if scale == 2 else ''}.png"
                run(["sips", "-z", str(size * scale), str(size * scale), str(ICON_PNG), "--out", str(iconset / name)])
        icns = WORK / "app.icns"
        run(["iconutil", "-c", "icns", str(iconset), "-o", str(icns)])
        return icns
    # An .ico holding the PNG as is (supported since Windows Vista). Sizes of 256 or more are written as 0.
    width, height = struct.unpack(">II", png[16:24])
    entry = struct.pack("<BBBBHHII", width % 256, height % 256, 0, 0, 1, 32, len(png), 6 + 16)
    ico = WORK / "app.ico"
    ico.write_bytes(struct.pack("<HHH", 0, 1, 1) + entry + png)
    return ico


def pyinstaller(solver: Path, runtime: Path, icon: Path | None, version: str, onefile: bool) -> None:
    version_file = WORK / "VERSION"
    version_file.write_text(version + "\n")
    data = [
        (CORE / "templates", "core/templates"),
        (CORE / "static", "core/static"),
        (solver, "."),
        (runtime, "runtime"),
        (PY4J_JAR, "."),
        (version_file, "."),
    ]
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--name", APP_NAME,
           "--distpath", str(APP_DIR), "--workpath", str(WORK / "pyinstaller"), "--specpath", str(WORK),
           "--paths", str(PROJECT), "--osx-bundle-identifier", BUNDLE_ID,
           # Both load parts of themselves by name at run time, which PyInstaller cannot see.
           "--collect-submodules", "flask_session", "--collect-submodules", "py4j"]
    if onefile:
        cmd.append("--onefile")
    if icon:
        cmd += ["--icon", str(icon)]
    for src, dest in data:
        cmd += ["--add-data", f"{src}{os.pathsep}{dest}"]
    cmd.append(str(PROJECT / "main.py"))
    print("$", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


# --- the app users double-click ---

def system_folder() -> str:
    if sys.platform == "darwin":
        return "Mac (Apple Silicon)" if chip() == "arm64" else "Mac (Intel)"
    return "Windows" if sys.platform == "win32" else "Linux"


def package_macos(out: Path) -> Path:
    """The .app, signed ad hoc so macOS will open it (users still confirm the first launch)."""
    app = out / f"{APP_NAME}.app"
    with tempfile.TemporaryDirectory() as tmp:
        # Synced folders (such as an iCloud Desktop) add file metadata that codesign rejects, so sign a clean
        # copy here and copy the signed app out.
        clean = Path(tmp) / f"{APP_NAME}.app"
        run(["ditto", "--norsrc", "--noextattr", str(APP_DIR / f"{APP_NAME}.app"), str(clean)])
        run(["codesign", "--force", "--deep", "--sign", "-", str(clean)])
        run(["ditto", "--norsrc", "--noextattr", str(clean), str(app)])
    return app


def package_single_file(out: Path) -> Path:
    """Windows and Linux: the one-file build, which unpacks itself each time it starts."""
    name = f"{APP_NAME}.exe" if sys.platform == "win32" else APP_NAME
    app = out / name
    shutil.move(str(APP_DIR / name), app)
    app.chmod(0o755)
    return app


def main() -> None:
    version = app_version()
    release = DIST / f"{APP_NAME}-{version}"
    out = release / system_folder()
    shutil.rmtree(out, ignore_errors=True)
    shutil.rmtree(APP_DIR, ignore_errors=True)
    out.mkdir(parents=True)
    (release / "How to install.txt").write_text(HOW_TO_INSTALL.format(version=version))
    WORK.mkdir(parents=True, exist_ok=True)
    solver = build_solver()
    runtime = build_runtime(solver)
    icon = build_icon()
    if sys.platform == "darwin":
        pyinstaller(solver, runtime, icon, version, onefile=False)
        app = package_macos(out)
    else:
        pyinstaller(solver, runtime, icon if sys.platform == "win32" else None, version, onefile=True)
        app = package_single_file(out)
    print(f"\nBuilt {app}")


if __name__ == "__main__":
    main()
