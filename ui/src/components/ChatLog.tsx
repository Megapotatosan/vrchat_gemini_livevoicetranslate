import { useLayoutEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import type { Message } from "../state";
import "./ChatLog.css";

const BOTTOM_SLACK_PX = 24;

export default function ChatLog({ messages }: { messages: Message[] }) {
  const { t } = useTranslation();
  const logRef = useRef<HTMLDivElement>(null);
  const atBottom = useRef(true);

  useLayoutEffect(() => {
    const log = logRef.current;
    if (log && atBottom.current) log.scrollTop = log.scrollHeight;
  }, [messages]);

  const onScroll = () => {
    const log = logRef.current;
    if (log) atBottom.current = log.scrollHeight - log.scrollTop - log.clientHeight <= BOTTOM_SLACK_PX;
  };

  return (
    <div className="log" ref={logRef} onScroll={onScroll} aria-live="polite">
      {messages.length === 0 && <p className="empty">{t("chat.empty")}</p>}
      {messages.map((m) => (
        <div key={m.id} className={`msg ${m.side}${m.final ? "" : " streaming"}`}>
          <span className="meta"><b>{t(m.side === "mine" ? "chat.sent" : "chat.received")}</b>{m.time}</span>
          <div className="bubble">
            {m.source && <span className="src">{m.source}</span>}
            <span className="tr">{m.translation}</span>
          </div>
        </div>
      ))}
    </div>
  );
}
