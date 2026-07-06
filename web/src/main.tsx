import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./styles.css";
import { ModelSettingsProvider } from "./context/ModelSettingsContext";
import { ConsentProvider } from "./context/ConsentContext";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <ConsentProvider>
        <ModelSettingsProvider>
          <App />
        </ModelSettingsProvider>
      </ConsentProvider>
    </BrowserRouter>
  </React.StrictMode>
);
