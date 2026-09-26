import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { installErrorForwarding } from "./bridge";
import { initI18n } from "./i18n";
import "./theme.css";

initI18n("en");
installErrorForwarding();
createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
