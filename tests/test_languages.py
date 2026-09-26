import pytest

from livetranslate.languages import (
    ENGLISH_NAMES, GEMINI_CODES, TRANSLATION_LANGS, default_languages, default_ui_language, gemini_code,
    theirs_target,
)


def test_list_shape():
    assert len(TRANSLATION_LANGS) == 22 and TRANSLATION_LANGS[:5] == ("en", "zh-Hant", "zh-Hans", "ja", "ko")
    assert set(ENGLISH_NAMES) == set(TRANSLATION_LANGS) == set(GEMINI_CODES)


@pytest.mark.parametrize("loc, ui, pair", [
    ("zh_TW", "zh-Hant", ("zh-Hant", "en")), ("zh-HK", "zh-Hant", ("zh-Hant", "en")),
    ("zh_CN", "en", ("zh-Hans", "en")), ("ja_JP", "ja", ("ja", "en")), ("ko-KR", "ko", ("ko", "en")),
    ("en_US", "en", ("en", "ja")), ("tl_PH", "en", ("fil", "en")), ("xx_YY", "en", ("en", "ja")),
    (None, "en", ("en", "ja"))])
def test_first_run_defaults(loc, ui, pair):
    assert default_ui_language(loc) == ui and default_languages(loc) == pair


def test_theirs_target_mirrors_and_falls_back():
    assert theirs_target("ja", "zh-Hant") == "ja" and theirs_target("auto", "zh-Hant") == "zh-Hant"


def test_gemini_code_identity_by_default():
    assert gemini_code("zh-Hant") == "zh-Hant"
