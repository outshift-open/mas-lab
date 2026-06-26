//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
import { parse as parseYaml } from "yaml";

import { getManifestValidators, areManifestSchemasReady } from "@/lib/loadManifestSchemas";
import type { YamlOutputMap } from "@/components/CanvasBuilder/types";

export interface ValidationError {
  manifest: string;
  errors: string[];
}

function stripExtensionFields(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(stripExtensionFields);
  }
  if (value !== null && typeof value === "object") {
    const cleaned: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      if (!k.startsWith("x-")) {
        cleaned[k] = stripExtensionFields(v);
      }
    }
    return cleaned;
  }
  return value;
}

function formatError(e: { instancePath?: string; message?: string; params?: Record<string, unknown> }): string {
  const path = e.instancePath || "/";
  const msg = e.message ?? "unknown error";
  if (e.params?.additionalProperty) {
    return `${path} has unknown property "${e.params.additionalProperty}"`;
  }
  return `${path} ${msg}`;
}

export function validateManifests(yamlOutputMap: YamlOutputMap): ValidationError[] {
  if (!areManifestSchemasReady()) {
    return [];
  }

  const { validateMas, validateAgent } = getManifestValidators();
  const results: ValidationError[] = [];

  // Pre-validation: check all agents have non-empty names
  for (const [key, yamlStr] of Object.entries(yamlOutputMap)) {
    if (!key.startsWith("agent:")) continue;
    const doc = parseYaml(yamlStr);
    if (!doc) continue;
    const name = doc?.metadata?.name;
    if (!name || (typeof name === "string" && name.trim() === "")) {
      results.push({
        manifest: `Agent node (unnamed)`,
        errors: ["/metadata/name must not be empty — please provide a name for every agent"],
      });
    }
  }

  if (results.length > 0) return results;

  for (const [key, yamlStr] of Object.entries(yamlOutputMap)) {
    const doc = parseYaml(yamlStr);
    if (!doc) continue;

    const label =
      key === "mas"
        ? "MAS manifest"
        : `Agent "${key.replace("agent:", "")}"`;

    const cleanDoc = stripExtensionFields(doc) as Record<string, unknown>;

    if (key === "mas") {
      const valid = validateMas(cleanDoc);
      if (!valid && validateMas.errors) {
        results.push({
          manifest: label,
          errors: validateMas.errors.map(formatError),
        });
      }
    } else if (key.startsWith("agent:")) {
      const valid = validateAgent(cleanDoc);
      if (!valid && validateAgent.errors) {
        results.push({
          manifest: label,
          errors: validateAgent.errors.map(formatError),
        });
      }
    }
  }

  return results;
}
