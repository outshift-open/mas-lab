//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

/** @type {import('vite').UserConfig} */
export default defineConfig(({ mode }) => {
  process.env = { ...process.env, ...loadEnv(mode, process.cwd()) };
  return {
    server: {
      port: parseInt(process.env.VITE_APP_CLIENT_PORT || "5173", 10),
      strictPort: true,
      open: true,
    },
    preview: {
      port: parseInt(process.env.VITE_APP_CLIENT_PORT || "5173", 10),
      strictPort: true,
    },
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    build: {
      chunkSizeWarningLimit: 1600,
      sourcemap: false,
    },
    plugins: [react()],
  };
});
