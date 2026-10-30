# GMTCrewManager (desktop)

GMTCrewManager as a standalone desktop app for macOS, Windows and Linux. Everything runs on the
user's computer: no internet connection, no account and nothing else to install. It is separate from the web
version and shares no data with it.

## Install or update

Download `GMTCrewManager-<version>.zip` from the latest release of the public download repository,
[GMTDownload](https://github.com/cbmckinstry/GMTDownload/releases/latest), and unzip it. Open the folder for your system and double-click the app; it holds everything it needs.

```
GMTCrewManager-<version>/
  How to install.txt
  Mac (Apple Silicon)/  GMTCrewManager.app      M1 and newer
  Mac (Intel)/          GMTCrewManager.app      older Macs
  Windows/              GMTCrewManager.exe
  Linux/                GMTCrewManager
```

To update, replace the app with the newer one. Saved results are kept outside the app, so they survive updates.
On Mac you can move the app to **Applications**. On Windows the app unpacks itself each time it starts, so it
takes a few seconds to open.

First launch: the app is not signed with a paid developer certificate, so the system asks once.
- **Mac:** right-click the app, choose **Open**, then **Open** again.
- **Windows:** on "Windows protected your PC", choose **More info**, then **Run anyway**.

Saved results are kept in:
- Mac: `~/Library/Application Support/GMTCrewManager`
- Windows: `%APPDATA%\GMTCrewManager`
- Linux: `~/.local/share/GMTCrewManager`

## Publishing a new version

1. Change what you need and update the number in `VERSION` (for example `1.1.0`).
2. Commit and push.
3. Tag the commit with the same number and push the tag:
   ```
   git tag v1.1.0
   git push origin v1.1.0
   ```
4. The **Build and release** workflow builds every system and publishes the release with the zip above to
   GMTDownload (about 15 minutes). Users then download the new file to update. This needs a
   `RELEASE_TOKEN` secret here: a fine-grained token with Contents read and write on GMTDownload.

To build without publishing, open the **Actions** tab, choose **Build and release**, then **Run workflow**; the
zip is attached to that run.

## The shared core

`core/` is a git submodule: the same solver and page the web app uses, from the GMTCore repository.
Clone this repository with `git clone --recurse-submodules`, or run `git submodule update --init` after cloning.
When the core changes, `git status` here shows `core` as changed; commit and push it to ship that change in the
desktop app. If the core repository is private, the release workflow needs a `CORE_TOKEN` secret that can read it.

## Running from this folder

To try a change without building, with Python 3.12, a JDK 17 or newer and the packages in `requirements.txt`:

```
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt        # Windows: .venv\Scripts\pip
.venv/bin/python run_local.py                   # Windows: .venv\Scripts\python run_local.py
```

It compiles the solver in `core/` whenever the core has changed, fetches the OR-Tools jars into `ortools/` the first
time, and opens the app window. Saved results go to the same folder as the installed app's.

On Windows, make the environment with `py -3.12 -m venv .venv`. On Linux pywebview also needs Qt to draw the window:
`.venv/bin/pip install "pywebview[qt]"` (the release workflow lists the system libraries Qt uses, if any are missing).

## Building on your own computer

Needs Python 3.12 (what the release workflow uses) and a JDK 17 or newer (`javac`, `jar`, `jdeps`, `jlink`).

```
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt        # Windows: .venv\Scripts\pip
.venv/bin/python packaging/build.py
```

The result is in `dist/GMTCrewManager-<version>/`, in the subfolder for the system you built on. A build only
runs on the kind of system it was made on.

## What is in here

| File | Purpose |
|---|---|
| `main.py` | Starts the solver and the page server on free local ports and opens the app window |
| `run_local.py` | Compiles the solver if needed and runs `main.py`, for trying changes without building |
| `app.py` | The calculator, crew-matrices and clustering tabs |
| `core/` | The shared code (solver, helpers, page), a git submodule of the GMTCore repository |
| `packaging/build.py` | Builds the app for the current system |
| `packaging/app-icon.png` | The app icon; replace it with a square 1024 x 1024 PNG for a sharp icon |
| `.github/workflows/release.yml` | Builds every system and publishes releases |
| `VERSION` | The version number shown in the window title |
