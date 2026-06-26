//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
import { Handle, Position, NodeResizer, type NodeProps } from "@xyflow/react";
import type { OverlayInputPromptNodeType } from "../types";

export function OverlayInputPromptNode({ data, id, selected }: NodeProps<OverlayInputPromptNodeType>) {
  return (
    <div className={`canvas-node text-input-node${data.disabled ? " canvas-node--disabled" : ""}`}>
      <NodeResizer isVisible={selected} minWidth={220} minHeight={120} />
      <div className="canvas-node__header text-input-node__header">
        <span className="canvas-node__icon">📝</span>
        <span className="canvas-node__title">Instructions</span>
        <button
          className="canvas-node__toggle-btn nodrag"
          onClick={(e) => { e.stopPropagation(); data.onChange?.("disabled", !data.disabled); }}
          title={data.disabled ? "Enable node" : "Disable node"}
        >
          {data.disabled ? "🔴" : "🟢"}
        </button>
      </div>
      <div className="canvas-node__body">
        <label className="canvas-node__label">
          Role Instructions Override
          <textarea
            className="canvas-node__textarea nodrag"
            value={data.text}
            onChange={(e) => data.onChange?.("text", e.target.value)}
            placeholder="Override instructions for the connected agent..."
            rows={5}
          />
        </label>
      </div>
      <Handle type="source" position={Position.Right} id={`prompt-out-${id}`} className="handle--text-input" />
    </div>
  );
}
