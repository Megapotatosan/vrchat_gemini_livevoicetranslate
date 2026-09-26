"""Windows-only helpers. Import only when running on Windows."""

from __future__ import annotations

WEBVIEW2_CLIENT = r"Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
WEBVIEW2_DOWNLOAD = "https://developer.microsoft.com/microsoft-edge/webview2/"


def webview2_installed() -> bool:
    import winreg

    locations = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\\" + WEBVIEW2_CLIENT),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\\" + WEBVIEW2_CLIENT),
        (winreg.HKEY_CURRENT_USER, r"Software\\" + WEBVIEW2_CLIENT),
    ]
    for hive, path in locations:
        try:
            with winreg.OpenKey(hive, path) as key:
                version, _ = winreg.QueryValueEx(key, "pv")
                if version and version != "0.0.0.0":
                    return True
        except OSError:
            continue
    return False


def set_dark_title_bar(hwnd: int) -> None:
    import ctypes

    value = ctypes.c_int(1)
    for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (19 on older Windows 10 builds)
        if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)) == 0:
            return


def message_box(title: str, text: str) -> None:
    import ctypes

    ctypes.windll.user32.MessageBoxW(None, text, title, 0x10)
