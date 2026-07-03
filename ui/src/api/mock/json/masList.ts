//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
import type { MASManifest } from "@/types/mas-types";

export const masList = [
  {
    apiVersion: "mas/v1",
    kind: "MAS",
    metadata: {
      name: "trip-planner-single",
      description:
        "Collapse the MAS to a single generalist agent with all tools and skills. No delegation — one agent handles the entire request. Useful as a baseline to compare against multi-agent topologies.",
    },
    spec: {
      agents: [
        {
          id: "generalist",
          ref: "apps/trip-planner/agents/generalist/agent.yaml",
        },
      ],
      workflow: {
        type: "dynamic",
        entry: "generalist",
        nodes: [{ id: "generalist" }],
      },
    },
  },
  {
    apiVersion: "mas/v1",
    kind: "MAS",
    metadata: {
      name: "trip-planner-linear",
      description:
        "Sequential pipeline topology — lab overlay on trip-planner. An automaton walks through each specialist in a fixed order (schedule → itinerary → concierge).",
    },
    spec: {
      agents: [
        {
          id: "schedule_agent",
          ref: "apps/trip-planner/agents/schedule.yaml",
        },
        {
          id: "itinerary_agent",
          ref: "apps/trip-planner/agents/itinerary_agent.yaml",
        },
        {
          id: "concierge_agent",
          ref: "apps/trip-planner/agents/concierge_agent.yaml",
        },
      ],
      workflow: {
        type: "sequential",
        entry: "schedule_agent",
        nodes: [
          { id: "schedule_agent" },
          { id: "itinerary_agent" },
          { id: "concierge_agent" },
        ],
      },
    },
  },
  {
    apiVersion: "mas/v1",
    kind: "MAS",
    metadata: {
      name: "trip-planner",
      description:
        "Moderator-broker topology — moderator orchestrates three specialists dynamically. The canonical trip planner configuration.",
    },
    spec: {
      agents: [
        {
          id: "moderator",
          ref: "apps/trip-planner/agents/moderator.yaml",
        },
        {
          id: "schedule_agent",
          ref: "apps/trip-planner/agents/schedule.yaml",
        },
        {
          id: "itinerary_agent",
          ref: "apps/trip-planner/agents/itinerary_agent.yaml",
        },
        {
          id: "concierge_agent",
          ref: "apps/trip-planner/agents/concierge_agent.yaml",
        },
      ],
      workflow: {
        type: "dynamic",
        entry: "moderator",
        nodes: [
          {
            id: "moderator",
            delegates_to: [
              "schedule_agent",
              "itinerary_agent",
              "concierge_agent",
            ],
          },
          { id: "schedule_agent" },
          { id: "itinerary_agent" },
          { id: "concierge_agent" },
        ],
      },
    },
  },
] satisfies MASManifest[];
