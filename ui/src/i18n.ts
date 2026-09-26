import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./locales/en.json";
import ja from "./locales/ja.json";
import ko from "./locales/ko.json";
import zhHant from "./locales/zh-Hant.json";

export function initI18n(lang = "en") {
  if (!i18n.isInitialized) {
    void i18n.use(initReactI18next).init({
      resources: { en: { translation: en }, "zh-Hant": { translation: zhHant }, ja: { translation: ja }, ko: { translation: ko } },
      lng: lang,
      fallbackLng: "en",
      interpolation: { escapeValue: false },
      initImmediate: false,
    });
  } else if (i18n.language !== lang) {
    void i18n.changeLanguage(lang);
  }
  return i18n;
}

export default i18n;
