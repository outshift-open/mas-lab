//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App.tsx";
import { loadManifestSchemas } from "@/lib/loadManifestSchemas";
import { API_BASE_URL } from "@/api/apiCalls";

function renderBootstrapError(message: string) {
  const root = document.getElementById("root");
  if (!root) return;
  root.innerHTML = `
    <div style="font-family: system-ui, sans-serif; max-width: 42rem; margin: 4rem auto; padding: 0 1rem;">
      <h1 style="font-size: 1.25rem; margin-bottom: 0.75rem;">Cannot start mas-lab UI</h1>
      <p style="line-height: 1.5; margin-bottom: 1rem;">${message.replace(/</g, "&lt;")}</p>
      <p style="line-height: 1.5; color: #555;">
        API base: <code>${API_BASE_URL}</code><br/>
        Start the controller from the repo root: <code>mas-lab serve</code>
      </p>
    </div>
  `;
}

async function bootstrap() {
  try {
    await loadManifestSchemas();
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    renderBootstrapError(message);
    return;
  }

  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}

bootstrap();
