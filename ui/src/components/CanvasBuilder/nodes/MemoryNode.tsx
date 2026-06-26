//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
import { Handle, Position, NodeResizer, type NodeProps } from "@xyflow/react";
import { useCallback, type ChangeEvent } from "react";
import type { MemoryNodeType } from "../types";

const MEMORY_TYPE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "semantic", label: "Semantic (ephemeral)" },
  { value: "semantic-persistent", label: "Semantic Persistent (SQLite)" },
  { value: "episodic", label: "Episodic" },
  { value: "procedural", label: "Procedural" },
];

export function MemoryNode({ data, id, selected }: NodeProps<MemoryNodeType>) {
  const handleChange = useCallback(
    (field: string) => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
      data.onChange?.(field, e.target.value);
    },
    [data],
  );

  return (
    <div className={`canvas-node memory-node${data.disabled ? " canvas-node--disabled" : ""}`}>
      <NodeResizer isVisible={selected} minWidth={220} minHeight={100} />
      <div className="canvas-node__header memory-node__header">
        <span className="canvas-node__icon">💾</span>
        <span className="canvas-node__title">Memory</span>
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
          Memory Type
          <select
            className="canvas-node__select nodrag"
            value={data.type}
            onChange={handleChange("type")}
          >
            <option value="">Select type...</option>
            {MEMORY_TYPE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
        <label className="canvas-node__label">
          Path (for persistent)
          <input
            className="canvas-node__input nodrag"
            value={data.path}
            onChange={handleChange("path")}
            placeholder="./memory/agent.db"
          />
        </label>
      </div>
      <Handle type="source" position={Position.Right} id={`memory-out-${id}`} className="handle--memory" />
    </div>
  );
}
