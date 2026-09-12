"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";

export interface EntityNodeData {
  name: string;
  label: string | null;
  direction: "upward" | "downward" | null;
  isRoot: boolean;
  isSelected: boolean;
  hasChildren: boolean;
  collapsed: boolean;
  onToggleCollapse: () => void;
  [key: string]: unknown;
}

const DIRECTION_STYLE = {
  upward: { border: "border-t-green-500", dot: "bg-green-500" },
  downward: { border: "border-t-purple-500", dot: "bg-purple-500" },
} as const;

export const NODE_WIDTH = 220;
export const NODE_HEIGHT = 64;

export default function EntityNode({ data }: NodeProps & { data: EntityNodeData }) {
  const style = data.direction ? DIRECTION_STYLE[data.direction] : { border: "border-t-blue-600", dot: "bg-blue-600" };

  return (
    <div
      style={{ width: NODE_WIDTH }}
      className={`relative rounded-lg border border-t-4 bg-white px-3 py-2 shadow-sm transition-shadow ${style.border} ${
        data.isSelected ? "ring-2 ring-blue-400 ring-offset-1" : ""
      } ${data.isRoot ? "shadow-md" : ""}`}
    >
      <Handle type="target" position={Position.Top} className="!bg-slate-300" />
      <Handle type="source" position={Position.Bottom} className="!bg-slate-300" />

      <div className="flex items-start justify-between gap-1">
        <div className="min-w-0 flex-1">
          <div className={`truncate text-xs ${data.isRoot ? "font-bold" : "font-medium"} text-slate-900`} title={data.name}>
            {data.name}
          </div>
          {data.label && <div className="mt-0.5 truncate text-[10px] text-slate-400">{data.label}</div>}
        </div>
        {data.isRoot && (
          <span className="shrink-0 rounded bg-blue-600 px-1 py-0.5 text-[9px] font-semibold uppercase text-white">
            Query
          </span>
        )}
      </div>

      {data.hasChildren && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            data.onToggleCollapse();
          }}
          className="absolute -bottom-2.5 left-1/2 flex h-5 w-5 -translate-x-1/2 items-center justify-center rounded-full border border-slate-300 bg-white text-[10px] text-slate-500 shadow-sm hover:bg-slate-50"
        >
          {data.collapsed ? "+" : "−"}
        </button>
      )}
    </div>
  );
}
