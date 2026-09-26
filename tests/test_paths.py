import sys

from livetranslate import paths


def test_env_override_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("LIVETRANSLATE_HOME", str(tmp_path / "h"))
    assert paths.app_dir() == tmp_path / "h" and (tmp_path / "h").is_dir()


def test_portable_marker_next_to_frozen_exe(tmp_path, monkeypatch):
    monkeypatch.delenv("LIVETRANSLATE_HOME", raising=False)
    exe = tmp_path / "LiveTranslate.exe"
    exe.touch()
    (tmp_path / "portable.txt").touch()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    assert paths.app_dir() == tmp_path


def test_appdata_on_windows(tmp_path, monkeypatch):
    monkeypatch.delenv("LIVETRANSLATE_HOME", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(paths, "_is_windows", lambda: True)
    assert paths.app_dir() == tmp_path / "LiveTranslate"


def test_logs_dir_is_created_under_app_dir():
    assert paths.logs_dir() == paths.app_dir() / "logs" and paths.logs_dir().is_dir()


def test_resource_path_uses_meipass_when_frozen(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert paths.resource_path("ui/dist/index.html") == tmp_path / "ui/dist/index.html"
