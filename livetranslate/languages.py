"""Translation languages, the codes sent to Gemini, mirroring, and first-run defaults."""

from __future__ import annotations

import locale as _locale
import sys

TRANSLATION_LANGS: tuple[str, ...] = (
    "en", "zh-Hant", "zh-Hans", "ja", "ko", "es", "fr", "de", "it", "pt", "ru",
    "uk", "pl", "nl", "tr", "ar", "th", "vi", "id", "ms", "fil", "hi",
)
UI_LANGS: tuple[str, ...] = ("en", "zh-Hant", "ja", "ko")

ENGLISH_NAMES: dict[str, str] = {
    "en": "English", "zh-Hant": "Traditional Chinese", "zh-Hans": "Simplified Chinese", "ja": "Japanese",
    "ko": "Korean", "es": "Spanish", "fr": "French", "de": "German", "it": "Italian", "pt": "Portuguese",
    "ru": "Russian", "uk": "Ukrainian", "pl": "Polish", "nl": "Dutch", "tr": "Turkish", "ar": "Arabic",
    "th": "Thai", "vi": "Vietnamese", "id": "Indonesian", "ms": "Malay", "fil": "Filipino", "hi": "Hindi",
}

# Code sent to Gemini for each list entry. Identity until the live probe says otherwise.
GEMINI_CODES: dict[str, str] = {code: code for code in TRANSLATION_LANGS}

_HANT_REGIONS = {"tw", "hk", "mo"}


def gemini_code(code: str) -> str:
    return GEMINI_CODES.get(code, code)


def theirs_target(source_lang: str, ui_language: str) -> str:
    """Other players' speech is translated into my language; Auto-detect falls back to the UI language."""
    return ui_language if source_lang == "auto" else source_lang


def _translation_lang(locale: str | None) -> str:
    if not locale:
        return "en"
    parts = locale.replace("_", "-").split(".")[0].lower().split("-")
    primary, rest = parts[0], set(parts[1:])
    if primary == "zh":
        return "zh-Hant" if rest & (_HANT_REGIONS | {"hant"}) else "zh-Hans"
    if primary == "tl":
        return "fil"
    return primary if primary in TRANSLATION_LANGS else "en"


def default_ui_language(locale: str | None) -> str:
    lang = _translation_lang(locale)
    return lang if lang in UI_LANGS else "en"


def default_languages(locale: str | None) -> tuple[str, str]:
    source = _translation_lang(locale)
    return source, "ja" if source == "en" else "en"


def os_locale() -> str | None:
    if sys.platform == "win32":
        import ctypes

        buf = ctypes.create_unicode_buffer(85)
        if ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, len(buf)):
            return buf.value
    return _locale.getlocale()[0]
