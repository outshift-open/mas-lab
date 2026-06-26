//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
import type { Edge, Node } from "@xyflow/react";

export type PipelineNodeType = "step";
export type DnDPipelineNodeType = PipelineNodeType | null;

export type NodeDataChangeHandler = (field: string, value: unknown) => void;

export interface StepNodeData extends Record<string, unknown> {
  name: string;
  type: string;
  phase: string;
  depends_on: string[];
  config: Record<string, unknown>;
  disabled?: boolean;
  onChange?: NodeDataChangeHandler;
}

export type YamlOutputMap = Record<string, string>;

export interface PipelineBuilderProps {
  initialYaml?: string;
  experimentName?: string;
  onYamlChange?: (yaml: string) => void;
  onExperimentChange?: (name: string) => void;
}

export interface SerializedGraph {
  nodes: Node[];
  edges: Edge[];
}

export type StepNodeType = Node<StepNodeData, "step">;
