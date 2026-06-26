#!/usr/bin/env node
//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
/**
 * Generate TS types from resolved schemas served by the controller.
 * Requires: mas-lab serve on VITE_API_BASE_URL (default http://localhost:8090)
 */
import { execSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const base =
  process.env.VITE_API_BASE_URL ||
  process.env.VITE_API_URL ||
  "http://localhost:8090";

const uiRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const tmpDir = resolve(uiRoot, ".tmp/schemas");
mkdirSync(tmpDir, { recursive: true });

for (const id of ["agent", "mas"]) {
  const res = await fetch(`${base}/api/schemas/${id}?format=json&resolved=1`);
  if (!res.ok) {
    console.error(`Fetch ${id} failed: ${res.status}. Is mas-lab serve running?`);
    process.exit(1);
  }
  const schema = await res.json();
  writeFileSync(resolve(tmpDir, `${id}.schema.json`), JSON.stringify(schema, null, 2));
}

execSync(
  `npx json2ts ${tmpDir}/agent.schema.json src/types/agent-types.ts && npx json2ts ${tmpDir}/mas.schema.json src/types/mas-types.ts`,
  { cwd: uiRoot, stdio: "inherit" },
);

console.log("OK: types written to src/types/");
