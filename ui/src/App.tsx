import { useCallback, useEffect, useReducer } from "react";
import { api, installDispatch } from "./bridge";
import Sidebar from "./components/Sidebar";
import StatusBar from "./components/StatusBar";
import { initI18n } from "./i18n";
import { initialState, reducer } from "./state";
import "./App.css";

export default function App() {
  const [state, dispatch] = useReducer(reducer, initialState);

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
      <Sidebar snap={state.snap} onOpenSettings={() => {}} onError={onError} />
      <main className="main">
        <div className="log" />
        <StatusBar status={state.status} stats={state.stats} />
      </main>
    </div>
  );
}
