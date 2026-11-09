import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AuthProvider } from "./lib/auth";
import { SiteProvider } from "./lib/site";
import { ToastProvider } from "./components/Ui";
import { ComboProvider } from "./lib/combo";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/football.css";
import "./styles/admin.css";
import "./styles/growth.css";
import "./styles/live.css";
import "./components/ui/kit.css";
import "./styles/teams.css";
import "./styles/shell.css";
import "./styles/matchday.css";
import "./styles/power.css";
import "./styles/you.css";
import "./styles/adminhome.css";
import "./styles/combo.css";
import "./styles/hig.css";
import "./styles/hig-admin.css";
import "./styles/swiss.css";
import "./styles/v2.css";
import "./styles/likely.css";
import "./styles/waitlist.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <SiteProvider>
        <AuthProvider>
          <ToastProvider>
            <ComboProvider>
              <App />
            </ComboProvider>
          </ToastProvider>
        </AuthProvider>
      </SiteProvider>
    </BrowserRouter>
  </React.StrictMode>
);
