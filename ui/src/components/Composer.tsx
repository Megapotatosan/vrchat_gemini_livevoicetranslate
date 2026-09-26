import { useState, type FormEvent, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../bridge";
import type { Snapshot } from "../state";
import "./Composer.css";

export default function Composer({ snap, onError }: { snap: Snapshot; onError: (key: string) => void }) {
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const disabled = !snap.running || snap.direction === "theirs";
  const placeholder = !snap.running ? t("composer.disabled_stopped")
    : snap.direction === "theirs" ? t("composer.disabled_theirs") : t("composer.placeholder");

  const submit = async (e?: FormEvent) => {
    e?.preventDefault();
    if (disabled || sending || !text.trim()) return;
    setSending(true);
    const result = await api.send_text(text);
    setSending(false);
    if (result.ok) setText("");
    else onError(result.error);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape") setText("");
  };

  return (
    <form className="compose" onSubmit={submit}>
      <input id="typed" type="text" value={text} disabled={disabled} placeholder={placeholder} autoComplete="off"
             maxLength={1000} aria-label={t("composer.placeholder")}
             onChange={(e) => setText(e.target.value)} onKeyDown={onKeyDown} />
      <button type="submit" disabled={disabled || sending}>{t("composer.send")}</button>
    </form>
  );
}
