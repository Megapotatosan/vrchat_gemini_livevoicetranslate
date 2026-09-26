import { expect, test } from "vitest";
import en from "../src/locales/en.json";
import ja from "../src/locales/ja.json";
import ko from "../src/locales/ko.json";
import zhHant from "../src/locales/zh-Hant.json";
import { TRANSLATION_LANGS } from "../src/languages";

const keys = (o: object, p = ""): string[] =>
  Object.entries(o).flatMap(([k, v]) => (typeof v === "object" ? keys(v, `${p}${k}.`) : [`${p}${k}`]));

test("all locales have identical keys", () => {
  const base = keys(en).sort();
  for (const l of [zhHant, ja, ko]) expect(keys(l).sort()).toEqual(base);
});

test("every translation language has a name", () => {
  for (const code of TRANSLATION_LANGS) expect(Object.keys(en.lang)).toContain(code);
});
