#!/usr/bin/env node
//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
/**
 * Generate TS types from resolved runtime schemas (fragment refs inlined).
 * Prefers mas-lab serve GET /api/schemas/{id}?resolved=1; falls back to
 * mas.ctl.validate.schemas.load_schema from the repo root when serve is down.
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
const repoRoot = resolve(uiRoot, "..");
const tmpDir = resolve(uiRoot, ".tmp/schemas");
mkdirSync(tmpDir, { recursive: true });

async function loadResolvedSchema(id) {
  try {
    const res = await fetch(`${base}/api/schemas/${id}?format=json&resolved=1`);
    if (res.ok) {
      return await res.json();
    }
  } catch {
    // serve not running — fall through to ctl loader
  }
  const kind = id.replace(/-/g, "_");
  const py = `import json; from mas.ctl.validate.schemas import load_schema; print(json.dumps(load_schema(${JSON.stringify(kind)})))`;
  const json = execSync(`python3 -c ${JSON.stringify(py)}`, {
    cwd: repoRoot,
    encoding: "utf-8",
  });
  return JSON.parse(json);
}

function stripXPatternProperties(schema) {
  if (schema === null || typeof schema !== "object") {
    return schema;
  }
  if (Array.isArray(schema)) {
    return schema.map(stripXPatternProperties);
  }
  const out = {};
  for (const [key, value] of Object.entries(schema)) {
    if (
      key === "patternProperties" &&
      value &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      Object.keys(value).every((pattern) => pattern.startsWith("^x-"))
    ) {
      continue;
    }
    out[key] = stripXPatternProperties(value);
  }
  return out;
}

for (const id of ["agent", "mas"]) {
  const schema = stripXPatternProperties(await loadResolvedSchema(id));
  writeFileSync(resolve(tmpDir, `${id}.schema.json`), JSON.stringify(schema, null, 2));
}

const agentTypesPath = resolve(uiRoot, "src/types/agent-types.ts");
const masTypesPath = resolve(uiRoot, "src/types/mas-types.ts");

execSync(
  `npx json2ts ${tmpDir}/agent.schema.json ${agentTypesPath} && npx json2ts ${tmpDir}/mas.schema.json ${masTypesPath}`,
  { cwd: uiRoot, stdio: "inherit" },
);

console.log("OK: types written to src/types/");
