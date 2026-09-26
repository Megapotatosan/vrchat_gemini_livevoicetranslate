import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, type DeviceLists } from "../bridge";
import { initI18n } from "../i18n";
import { UI_LANGS } from "../languages";
import type { Snapshot } from "../state";
import { VOICES } from "../voices";
import "./SettingsDialog.css";

type Kind = "mic" | "loopback" | "voice";
const EMPTY: DeviceLists = { inputs: [], loopbacks: [], outputs: [] };

export default function SettingsDialog({ snap, open, onClose }: { snap: Snapshot; open: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const [devices, setDevices] = useState<DeviceLists>(EMPTY);
  const [key, setKey] = useState("");
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);

  const refresh = () => void api.list_devices().then((r) => { if (r.ok) setDevices(r); });

  useEffect(() => {
    if (!open) return;
    refresh();
    setNote(null);
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!open) return null;

  const report = (ok: boolean, text: string) => setNote({ ok, text });
  const saveKey = async () => {
    const r = await api.set_api_key(key);
    if (r.ok) { setKey(""); report(true, t("settings.key_ok")); } else report(false, t(r.error));
  };
  const clearKey = async () => {
    const r = await api.clear_api_key();
    if (r.ok) report(true, t("settings.key_cleared")); else report(false, t(r.error));
  };
  const exportLogs = async () => {
    const r = await api.export_logs();
    if (r.ok) report(true, t("settings.exported", { path: r.path }));
    else if (r.error !== "errors.cancelled") report(false, t(r.error));
  };
  const setLanguage = (code: string) => {
    void api.set_ui_language(code);
    initI18n(code);
  };

  const deviceRow = (kind: Kind, label: string, auto: string, names: string[]) => {
    const current = snap.devices[kind];
    const options = current && !names.includes(current) ? [current, ...names] : names;
    return (
      <div className="field">
        <label htmlFor={`dev-${kind}`}>{label}</label>
        <span className="ctl">
          <select id={`dev-${kind}`} value={current} onChange={(e) => void api.set_device(kind, e.target.value)}>
            <option value="">{auto}</option>
            {options.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
          {kind === "voice" && <button type="button" className="btn" onClick={refresh}>{t("settings.refresh")}</button>}
        </span>
      </div>
    );
  };

  return (
    <div className="scrim" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="set-title">
        <h2 id="set-title">
          {t("settings.title")}
          <button type="button" className="close" aria-label={t("settings.close")} onClick={onClose}>✕</button>
        </h2>
        <div className="field">
          <label htmlFor="api-key">{t("settings.api_key")}</label>
          <span className="ctl">
            <input id="api-key" type="password" value={key} autoComplete="off"
                   placeholder={snap.api_key.masked ?? ""} onChange={(e) => setKey(e.target.value)}
                   onKeyDown={(e) => { if (e.key === "Enter") void saveKey(); }} />
            <button type="button" className="btn" disabled={!key.trim()} onClick={() => void saveKey()}>{t("settings.save")}</button>
            <button type="button" className="btn" disabled={!snap.api_key.present} onClick={() => void clearKey()}>{t("settings.clear")}</button>
          </span>
        </div>
        {note && <p className={`note ${note.ok ? "ok" : "bad"}`} role="status">{note.text}</p>}
        <div className="hr" />
        {deviceRow("mic", t("settings.mic"), t("settings.auto_mic"), devices.inputs)}
        {deviceRow("loopback", t("settings.loopback"), t("settings.auto_loopback"), devices.loopbacks)}
        {deviceRow("voice", t("settings.voice_out"), t("settings.auto_voice"), devices.outputs)}
        <div className="field">
          <label htmlFor="voice-name">{t("settings.voice_name")}</label>
          <span className="ctl">
            <select id="voice-name" value={snap.voice} onChange={(e) => void api.set_voice(e.target.value)}>
              <option value="">{t("settings.voice_auto")}</option>
              {VOICES.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </span>
        </div>
        <div className="hr" />
        <div className="field">
          <label htmlFor="ui-lang">{t("settings.ui_language")}</label>
          <span className="ctl">
            <select id="ui-lang" value={snap.ui_language} onChange={(e) => setLanguage(e.target.value)}>
              {UI_LANGS.map((c) => <option key={c} value={c}>{t(`ui_lang.${c}`)}</option>)}
            </select>
          </span>
        </div>
        <div className="field">
          <span className="label">{t("settings.logs")}</span>
          <span className="ctl"><button type="button" className="btn wide" onClick={() => void exportLogs()}>{t("settings.export")}</button></span>
        </div>
        <p className="version">{t("settings.version", { version: snap.version })}</p>
      </div>
    </div>
  );
}
