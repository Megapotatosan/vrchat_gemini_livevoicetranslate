import { useTranslation } from "react-i18next";
import { api, type Result } from "../bridge";
import { TRANSLATION_LANGS } from "../languages";
import type { Direction, Snapshot } from "../state";
import "./Sidebar.css";

const GET_KEY_URL = "https://aistudio.google.com/apikey";
const DIRECTIONS: Direction[] = ["mine", "theirs", "both"];

interface Props {
  snap: Snapshot;
  onOpenSettings: () => void;
  onError: (key: string) => void;
}

export default function Sidebar({ snap, onOpenSettings, onError }: Props) {
  const { t } = useTranslation();
  const run = (p: Promise<Result>) => void p.then((r) => { if (!r.ok) onError(r.error); });
  const lang = (code: string) => t(`lang.${code}`);
  const src = snap.source_lang;
  const dst = snap.target_lang;

  return (
    <aside className="sidebar">
      <div className="logo">
        <span className="name">Live<b>Translate</b></span>
        <span className="sub">{t("app.subtitle")}</span>
      </div>

      <button type="button" className={`start${snap.running ? " running" : ""}`}
              disabled={!snap.running && !snap.api_key.present}
              onClick={() => run(snap.running ? api.stop() : api.start())}>
        {snap.running ? t("sidebar.stop") : t("sidebar.start")}
      </button>

      <div className="section-label">{t("sidebar.direction")}</div>
      <div className="seg" role="group" aria-label={t("sidebar.direction")}>
        {DIRECTIONS.map((d) => (
          <button key={d} type="button" aria-pressed={snap.direction === d} onClick={() => run(api.set_direction(d))}>
            {t(`direction.${d}`)}
          </button>
        ))}
      </div>

      <div className="section-label">{t("sidebar.languages")}</div>
      <div className="lang">
        <label htmlFor="src">{t("sidebar.i_speak")}</label>
        <select id="src" value={src} onChange={(e) => run(api.set_languages(e.target.value, dst))}>
          <option value="auto">{t("sidebar.auto")}</option>
          {TRANSLATION_LANGS.map((c) => <option key={c} value={c}>{lang(c)}</option>)}
        </select>
        <button type="button" className="swap" aria-label={t("sidebar.swap")} title={t("sidebar.swap")}
                disabled={src === "auto"} onClick={() => run(api.set_languages(dst, src))}>⇅</button>
        <label htmlFor="dst">{t("sidebar.translate_to")}</label>
        <select id="dst" value={dst} onChange={(e) => run(api.set_languages(src, e.target.value))}>
          {TRANSLATION_LANGS.map((c) => <option key={c} value={c}>{lang(c)}</option>)}
        </select>
        <div className="mirror">
          {src === "auto"
            ? t("sidebar.mirror_auto", { to: lang(snap.theirs_target) })
            : t("sidebar.mirror", { from: lang(dst), to: lang(snap.theirs_target) })}
        </div>
      </div>

      <div className="section-label">{t("sidebar.outputs")}</div>
      <div className="rows">
        {(["chatbox", "voice"] as const).map((name) => (
          <div className="row" key={name}>
            <span>{t(`sidebar.${name}`)}<span className="hint">{t(`sidebar.${name}_hint`)}</span></span>
            <button type="button" className="switch" role="switch" aria-checked={snap.outputs[name]}
                    aria-label={t(`sidebar.${name}`)} onClick={() => run(api.set_output(name, !snap.outputs[name]))} />
          </div>
        ))}
      </div>

      <div className="side-foot">
        {snap.api_key.present
          ? <span className="key"><i />{t("sidebar.key_set")}</span>
          : <button type="button" className="key missing" onClick={() => run(api.open_url(GET_KEY_URL))}>
              {t("sidebar.get_key")}
            </button>}
        <button type="button" className="gear" aria-label={t("sidebar.settings")} title={t("sidebar.settings")}
                onClick={onOpenSettings}>⚙</button>
      </div>
    </aside>
  );
}
