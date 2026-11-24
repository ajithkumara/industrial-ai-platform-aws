import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, HashRouter } from "react-router-dom";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ToastProvider } from "@/components/ui/toast";
import { FleetProvider } from "@/store/FleetStore";
import { getToken, liveConfigured } from "@/services/auth";
import App from "./App";
import "./index.css";

// Hash routing lets the built app run from S3/CloudFront without rewrite rules.
const Router = import.meta.env.VITE_ROUTER === "hash" ? HashRouter : BrowserRouter;

async function start() {
  // When config.js is present (hosted build) require sign-in first; otherwise run as the offline demo.
  if (liveConfigured()) await getToken();
  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <Router>
        <FleetProvider>
          <TooltipProvider delayDuration={200}>
            <ToastProvider>
              <App />
            </ToastProvider>
          </TooltipProvider>
        </FleetProvider>
      </Router>
    </React.StrictMode>,
  );
}
void start();
