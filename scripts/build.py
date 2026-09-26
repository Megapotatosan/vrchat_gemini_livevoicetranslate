"""Build dist/LiveTranslate.exe: the React UI, then a one-file windowed PyInstaller bundle."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def pyinstaller_args(sep: str) -> list[str]:
    return ["--noconfirm", "--onefile", "--windowed", "--name", "LiveTranslate", "--icon", "assets/app.ico",
            "--add-data", f"ui/dist{sep}ui/dist", "--add-data", f"assets{sep}assets",
            "--collect-submodules", "webview", "--additional-hooks-dir", "scripts/pyinstaller_hooks",
            "livetranslate/__main__.py"]


def main() -> int:
    npm = shutil.which("npm") or "npm"
    subprocess.run([npm, "ci"], cwd=ROOT / "ui", check=True)
    subprocess.run([npm, "run", "build"], cwd=ROOT / "ui", check=True)
    os.chdir(ROOT)
    import PyInstaller.__main__

    PyInstaller.__main__.run(pyinstaller_args(os.pathsep))
    exe = ROOT / "dist" / ("LiveTranslate.exe" if sys.platform == "win32" else "LiveTranslate")
    print(f"built {exe} ({exe.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
