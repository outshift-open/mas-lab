//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
import { Handle, Position, NodeResizer, type NodeProps } from "@xyflow/react";
import { useCallback, type ChangeEvent } from "react";
import type { TextInputNodeType } from "../types";

export function TextInputNode({ data, id, selected }: NodeProps<TextInputNodeType>) {
  const handleChange = useCallback(
    (e: ChangeEvent<HTMLTextAreaElement>) => {
      data.onChange?.("text", e.target.value);
    },
    [data],
  );

  return (
    <div className={`canvas-node text-input-node${data.disabled ? " canvas-node--disabled" : ""}`}>
      <NodeResizer isVisible={selected} minWidth={220} minHeight={120} />
      <div className="canvas-node__header text-input-node__header">
        <span className="canvas-node__icon">📝</span>
        <span className="canvas-node__title">Text Input</span>
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
          System Prompt
          <textarea
            className="canvas-node__textarea nodrag nowheel"
            value={data.text}
            onChange={handleChange}
            placeholder="Enter system prompt or instructions..."
            rows={4}
          />
        </label>
      </div>
      <Handle type="source" position={Position.Right} id={`text-input-out-${id}`} className="handle--text-input" />
    </div>
  );
}
