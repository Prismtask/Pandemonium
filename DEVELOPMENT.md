# Pandemonium — Developer Notes

Everything needed to run the game **from source** or **build `Pandemonium.exe`**.

> Just want to play? Grab a release zip, unzip it, and double-click `Pandemonium.exe`.
> No Python, no dependencies required — the exe is self-contained.

---

## 1. Requirements

| Package | Needed for | Install |
|---|---|---|
| **Python 3.11+** (developed on **3.14**) | Running the game | [python.org/downloads](https://www.python.org/downloads/windows/) — tick **"Add python.exe to PATH"** and leave **tcl/tk and IDLE** checked |
| **PyYAML** | Loading enemy / skill / family-scene YAML data | `pip install -r requirements.txt` |
| **PyInstaller** | Only for `make_exe.py` (the `.exe` build) | `pip install -r requirements-dev.txt` |
| **pytest** | Only for the test suite | included in `requirements-dev.txt` |

The GUI uses **tkinter**, which ships with the python.org Windows installer — nothing extra to install.
(Some minimal Python builds, e.g. stripped conda environments, ship without it; reinstall from python.org if
`import tkinter` fails.)

---

## 2. Run from source

From the project root (`C:\Code\Pandemonium` or wherever you unzipped it):

```powershell
# Create a virtual environment once
python -m venv .venv

# Activate it (PowerShell)
.\.venv\Scripts\Activate.ps1
# If activation is blocked, allow scripts for this session first:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned

# Install dependencies
pip install -r requirements.txt

# Play
python launcher.py
```

`python -m pandemonium` also works — it runs the same GUI entry point.

---

## 3. Build the .exe

```powershell
# In the activated venv, with dev dependencies installed
pip install -r requirements-dev.txt

python make_exe.py
```

Output goes to `dist\Pandemonium\`:

```
dist\Pandemonium\
  Pandemonium.exe      <- game (double-click)
  Open Wiki.bat        <- opens wiki\index.html in your browser
  wiki\index.html      <- offline game wiki
  _internal\           <- Python runtime + bundled libs (don't touch)
```

Zip that whole folder to share the game. Save files are created in a `savefile\` folder
next to the exe on first run.

> `make_exe.py` deletes `build\` and `dist\` before every build, and regenerates
> `Pandemonium.spec` — don't hand-edit the spec, it gets overwritten.

---

## 4. Troubleshooting

### `No module named PyInstaller`

`make_exe.py` invokes PyInstaller **using the same interpreter that runs the script**
(`sys.executable`), so PyInstaller must be installed *for that interpreter*:

```
Building with: C:\Users\<you>\AppData\Local\Python\pythoncore-3.14-64\python.exe
python.exe: No module named PyInstaller
[FAIL] Build failed.
```

Fix — install it into that exact interpreter:

```powershell
# Either let make_exe.py install into the interpreter it is using:
"C:\Users\<you>\AppData\Local\Python\pythoncore-3.14-64\python.exe" -m pip install -r requirements-dev.txt

# ...or simply run the build through the project venv:
.\.venv\Scripts\python.exe make_exe.py
```

`make_exe.py` now checks for PyInstaller before deleting `build\`/`dist\` and prints this
guidance instead of failing halfway through.

### `No module named yaml` / `No module named PyYAML`

PyYAML isn't installed in the interpreter running the game:

```powershell
pip install -r requirements.txt
```

### `No module named tkinter`

Your Python was built without Tcl/Tk. Install the official python.org build
(with the "tcl/tk and IDLE" option) and recreate the venv.

### `make_exe.py` builds with the wrong Python

The "Building with:" line in the output names the interpreter actually used. Prefer
`.\.venv\Scripts\python.exe make_exe.py` so the venv's packages are picked up.

### Downloaded the repo as a `.zip` from GitHub?

The zip contains **source only** — no `.venv`, no installed packages, and (because they're
gitignored) no `tests\`, `savefile\`, `.idea\`, or `.github\` folders. Run the steps in
sections 2–3 before building; the PyInstaller error above is exactly what a missing
`pip install -r requirements-dev.txt` looks like.

---

## 5. Tests

```powershell
pip install -r requirements-dev.txt
python -m pytest
```

Pytest is configured in `pyproject.toml` (`testpaths = ["tests"]`, repo root on `sys.path`).
The `tests\` folder is **local-only** (gitignored) and includes the pytest suite plus manual
`_diag_*` / `_smoke_*` scripts — see `tests\README.md` for naming rules.

---

## 6. What is *not* in the repo

These folders exist only in a working copy and are gitignored:

| Folder | Why |
|---|---|
| `.venv\` | Local virtual environment |
| `build\`, `dist\` | PyInstaller output |
| `savefile\` | Local saves + `gui_settings.json` (not safe to publish) |
| `tests\` | Local test suite / diagnostic scripts |
| `.idea\`, `.vscode\`, `.github\` | Editor and local tooling config |
