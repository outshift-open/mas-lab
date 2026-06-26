#!/usr/bin/env node
//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
/**
 * Smoke test: resolved schemas are served by the running controller (same path as the UI).
 * Requires: mas-lab serve (default http://localhost:8090)
 */
const base =
  process.env.VITE_API_BASE_URL ||
  process.env.VITE_API_URL ||
  "http://localhost:8090";

async function main() {
  const health = await fetch(`${base}/api/health`);
  if (!health.ok) {
    console.error(`FAIL: controller not reachable at ${base}`);
    process.exit(1);
  }

  for (const id of ["agent", "mas"]) {
    const res = await fetch(`${base}/api/schemas/${id}?format=json&resolved=1`);
    if (!res.ok) {
      console.error(`FAIL: GET /api/schemas/${id}?resolved=1 → ${res.status}`);
      process.exit(1);
    }
    const schema = await res.json();
    const text = JSON.stringify(schema);
    if (text.includes('"$ref":"./')) {
      console.error(`FAIL: ${id} schema still contains unresolved ./ refs`);
      process.exit(1);
    }
    console.log(`OK: resolved schema ${id} (${text.length} bytes)`);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
