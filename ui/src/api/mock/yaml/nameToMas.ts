//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
// imports linear.yaml as raw text via Vite's ?raw
import linearYaml from "./linear.yaml?raw";
import singleAgentYaml from "./single-agent.yaml?raw";
import moderatorYaml from "./moderator.yaml?raw";

export const nameToMas = {
  "trip-planner": moderatorYaml,
  "trip-planner-linear": linearYaml,
  "trip-planner-single": singleAgentYaml,
};
