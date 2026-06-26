//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
import { Handle, Position, NodeResizer, type NodeProps } from "@xyflow/react";
import { useCallback, type ChangeEvent } from "react";
import { AGENT_OUTPUT_HANDLE, type OverlayAgentNodeType } from "../types";

export function OverlayAgentNode({ data, selected }: NodeProps<OverlayAgentNodeType>) {
  const handleChange = useCallback(
    (field: string) => (e: ChangeEvent<HTMLInputElement>) => {
      data.onChange?.(field, e.target.value);
    },
    [data],
  );

  return (
    <div className="canvas-node agent-node">
      <NodeResizer isVisible={selected} minWidth={260} minHeight={200} />
      <div className="canvas-node__header agent-node__header">
        <span className="canvas-node__icon">🤖</span>
        <span className="canvas-node__title">Agent Override</span>
      </div>
      <div className="canvas-node__body">
        <label className="canvas-node__label">
          Agent ID
          <input
            className="canvas-node__input nodrag"
            value={data.agentId}
            onChange={handleChange("agentId")}
            placeholder="e.g. moderator"
          />
        </label>

        <div className="agent-node__separator" />

        <div className="agent-node__slot">
          <Handle
            type="target"
            position={Position.Left}
            id="design_pattern"
            className="agent-node__handle agent-node__handle--design-pattern"
          />
          <span className="agent-node__slot-label">DESIGN PATTERN</span>
          <span className="agent-node__slot-value">
            {data.connectedDesignPattern || "—"}
          </span>
        </div>

        <div className="agent-node__slot">
          <Handle
            type="target"
            position={Position.Left}
            id="tools"
            className="agent-node__handle agent-node__handle--tools"
          />
          <span className="agent-node__slot-label">TOOLS (ADD)</span>
          <span className="agent-node__slot-value">
            {data.connectedTools && data.connectedTools.length > 0
              ? data.connectedTools.join(", ")
              : "—"}
          </span>
        </div>

        <div className="agent-node__slot">
          <Handle
            type="target"
            position={Position.Left}
            id="tools_remove"
            className="agent-node__handle agent-node__handle--tools"
          />
          <span className="agent-node__slot-label">TOOLS (REMOVE)</span>
          <span className="agent-node__slot-value">
            {data.connectedToolsRemove && data.connectedToolsRemove.length > 0
              ? data.connectedToolsRemove.join(", ")
              : "—"}
          </span>
        </div>

        <div className="agent-node__slot">
          <Handle
            type="target"
            position={Position.Left}
            id="input_prompt"
            className="agent-node__handle agent-node__handle--text-input"
          />
          <span className="agent-node__slot-label">INSTRUCTIONS</span>
          <span className="agent-node__slot-value">
            {data.connectedInputPrompt
              ? data.connectedInputPrompt.length > 30
                ? data.connectedInputPrompt.slice(0, 30) + "…"
                : data.connectedInputPrompt
              : "—"}
          </span>
        </div>

        <div className="agent-node__separator" />

        <div className="agent-node__slot agent-node__slot--output">
          <span className="agent-node__slot-label">AGENT OUTPUT</span>
          <Handle
            type="source"
            position={Position.Right}
            id={AGENT_OUTPUT_HANDLE}
            className="agent-node__handle agent-node__handle--agent-output"
          />
        </div>
      </div>
    </div>
  );
}
