// Same codes and order as livetranslate/languages.py
export const TRANSLATION_LANGS = [
  "en", "zh-Hant", "zh-Hans", "ja", "ko", "es", "fr", "de", "it", "pt", "ru",
  "uk", "pl", "nl", "tr", "ar", "th", "vi", "id", "ms", "fil", "hi",
] as const;
export const UI_LANGS = ["en", "zh-Hant", "ja", "ko"] as const;
export type UiLang = (typeof UI_LANGS)[number];
