# Pre-Clustering (desktop)

The Pre-Clustering calculator as a standalone desktop app for macOS, Windows and Linux. Everything runs on the
user's computer: no internet connection, no account and nothing else to install. It is separate from the web
version and shares no data with it.

## Install or update

Download `Pre-Clustering-<version>.zip` from the latest release of the public download repository,
[PreClusteringDownload](https://github.com/cbmckinstry/PreClusteringDownload/releases/latest), and unzip it. Open the folder for your system and double-click the app; it holds everything it needs.

```
Pre-Clustering-<version>/
  How to install.txt
  Mac (Apple Silicon)/  Pre-Clustering.app      M1 and newer
  Mac (Intel)/          Pre-Clustering.app      older Macs
  Windows/              Pre-Clustering.exe
  Linux/                Pre-Clustering
```

To update, replace the app with the newer one. Saved results are kept outside the app, so they survive updates.
On Mac you can move the app to **Applications**. On Windows the app unpacks itself each time it starts, so it
takes a few seconds to open.

First launch: the app is not signed with a paid developer certificate, so the system asks once.
- **Mac:** right-click the app, choose **Open**, then **Open** again.
- **Windows:** on "Windows protected your PC", choose **More info**, then **Run anyway**.

Saved results are kept in:
- Mac: `~/Library/Application Support/Pre-Clustering`
- Windows: `%APPDATA%\Pre-Clustering`
- Linux: `~/.local/share/Pre-Clustering`

## Publishing a new version

1. Change what you need and update the number in `VERSION` (for example `1.1.0`).
2. Commit and push.
3. Tag the commit with the same number and push the tag:
   ```
   git tag v1.1.0
   git push origin v1.1.0
   ```
4. The **Build and release** workflow builds every system and publishes the release with the zip above to
   PreClusteringDownload (about 15 minutes). Users then download the new file to update. This needs a
   `RELEASE_TOKEN` secret here: a fine-grained token with Contents read and write on PreClusteringDownload.

To build without publishing, open the **Actions** tab, choose **Build and release**, then **Run workflow**; the
zip is attached to that run.

## The shared core

`core/` is a git submodule: the same solver and page the web app uses, from the Pre-Clustering core repository.
Clone this repository with `git clone --recurse-submodules`, or run `git submodule update --init` after cloning.
When the core changes, `git status` here shows `core` as changed; commit and push it to ship that change in the
desktop app. If the core repository is private, the release workflow needs a `CORE_TOKEN` secret that can read it.

## Building on your own computer

Needs Python 3.9+ and a JDK 17 or newer (`javac`, `jar`, `jdeps`, `jlink`).

```
python -m venv .venv
.venv/bin/pip install -r requirements.txt        # Windows: .venv\Scripts\pip
.venv/bin/python packaging/build.py
```

The result is in `dist/Pre-Clustering-<version>/`, in the subfolder for the system you built on. A build only
runs on the kind of system it was made on.

## What is in here

| File | Purpose |
|---|---|
| `main.py` | Starts the solver and the page server on free local ports and opens the app window |
| `app.py` | The calculator, crew-matrices and clustering tabs |
| `core/` | The shared code (solver, helpers, page), a git submodule of the Pre-Clustering core repository |
| `packaging/build.py` | Builds the app for the current system |
| `packaging/app-icon.png` | The app icon; replace it with a square 1024 x 1024 PNG for a sharp icon |
| `.github/workflows/release.yml` | Builds every system and publishes releases |
| `VERSION` | The version number shown in the window title |
