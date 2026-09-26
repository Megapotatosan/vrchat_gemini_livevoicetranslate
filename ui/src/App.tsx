import { useEffect, useReducer } from "react";
import { api, installDispatch } from "./bridge";
import { initI18n } from "./i18n";
import { initialState, reducer } from "./state";

export default function App() {
  const [state, dispatch] = useReducer(reducer, initialState);

  useEffect(() => {
    installDispatch((batch) => dispatch({ type: "events", batch }));
    void api.get_state().then((r) => { if (r.ok) dispatch({ type: "snapshot", snap: r.state }); });
  }, []);

  useEffect(() => { if (state.snap) initI18n(state.snap.ui_language); }, [state.snap?.ui_language]);

  return <div className="app" data-running={state.snap?.running ?? false} />;
}
