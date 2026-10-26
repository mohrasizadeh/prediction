import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AuthProvider } from "./lib/auth";
import { SiteProvider } from "./lib/site";
import { ToastProvider } from "./components/Ui";
import "@fontsource-variable/plus-jakarta-sans/wght.css";
import "@fontsource-variable/manrope/wght.css";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/football.css";
import "./styles/admin.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <SiteProvider>
        <AuthProvider>
          <ToastProvider>
            <App />
          </ToastProvider>
        </AuthProvider>
      </SiteProvider>
    </BrowserRouter>
  </React.StrictMode>
);
