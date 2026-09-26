import { useTranslation } from "react-i18next";
import { api } from "../bridge";
import type { Stats, Status } from "../state";
import "./StatusBar.css";

const CABLE_URL = "https://vb-audio.com/Cable/";

export default function StatusBar({ status, stats }: { status: Status | null; stats: Stats }) {
  const { t } = useTranslation();
  const params: Record<string, unknown> = { ...(status?.params ?? {}) };
  if (typeof params.side === "string") params.side = t(`side.${params.side}`);
  const text = status ? t(status.key, params) : t(stats.running ? "status.running" : "status.ready");
  const statsText = stats.first_text_ms != null
    ? t("status.stats", { count: stats.count, ms: stats.first_text_ms })
    : t("status.stats_idle", { count: stats.count });

  return (
    <div className={`status ${status?.level ?? "info"}${stats.running ? " running" : ""}`} role="status">
      <span className="dot" />
      <span className="text">{text}</span>
      {status?.key === "errors.no_virtual_cable" && (
        <button type="button" className="link" onClick={() => void api.open_url(CABLE_URL)}>{t("status.get_cable")}</button>
      )}
      <span className="stats">{stats.running ? `${t("status.running")} · ` : ""}{statsText}</span>
    </div>
  );
}
