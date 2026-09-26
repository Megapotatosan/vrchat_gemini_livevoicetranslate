import { useCallback, useEffect, useReducer, useState } from "react";
import { api, installDispatch } from "./bridge";
import ChatLog from "./components/ChatLog";
import Composer from "./components/Composer";
import SettingsDialog from "./components/SettingsDialog";
import Sidebar from "./components/Sidebar";
import StatusBar from "./components/StatusBar";
import { initI18n } from "./i18n";
import { initialState, reducer } from "./state";
import "./App.css";

export default function App() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const [settingsOpen, setSettingsOpen] = useState(false);

  useEffect(() => {
    installDispatch((batch) => dispatch({ type: "events", batch }));
    void api.get_state().then((r) => { if (r.ok) dispatch({ type: "snapshot", snap: r.state }); });
  }, []);

  useEffect(() => { if (state.snap) initI18n(state.snap.ui_language); }, [state.snap?.ui_language]);

  const onError = useCallback((key: string) =>
    dispatch({ type: "events", batch: [{ type: "status", level: "error", key, params: {} }] }), []);

  if (!state.snap) return <div className="app loading" />;
  return (
    <div className="app">
      <Sidebar snap={state.snap} onOpenSettings={() => setSettingsOpen(true)} onError={onError} />
      <main className="main">
        <ChatLog messages={state.messages} />
        <Composer snap={state.snap} onError={onError} />
        <StatusBar status={state.status} stats={state.stats} />
      </main>
      <SettingsDialog snap={state.snap} open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}
