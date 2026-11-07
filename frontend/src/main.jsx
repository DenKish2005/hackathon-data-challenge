import "@fontsource-variable/roboto";
import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import WorkspaceErrorBoundary from "./WorkspaceErrorBoundary.jsx";
import "./styles.css";
import "./presentation.css";
import "./freedom-theme.css";
createRoot(document.getElementById("root")).render(
  <WorkspaceErrorBoundary>
    <App />
  </WorkspaceErrorBoundary>,
);
