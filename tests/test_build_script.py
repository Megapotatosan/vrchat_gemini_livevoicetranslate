import importlib.util
import sys
from pathlib import Path

_path = Path(__file__).resolve().parent.parent / "scripts" / "build.py"
_spec = importlib.util.spec_from_file_location("build_script", _path)
build = importlib.util.module_from_spec(_spec)
sys.modules["build_script"] = build
_spec.loader.exec_module(build)


def test_pyinstaller_args_bundle_ui_and_assets():
    args = build.pyinstaller_args(";")
    assert "--onefile" in args and "--windowed" in args and args[args.index("--name") + 1] == "LiveTranslate"
    assert "ui/dist;ui/dist" in args and "assets;assets" in args and args[-1] == "livetranslate/__main__.py"
