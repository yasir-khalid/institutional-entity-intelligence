"use client";

import { useState } from "react";
import type { TreeNode } from "@/lib/api";

const DIRECTION_DOT: Record<string, string> = {
  upward: "bg-green-500",
  downward: "bg-purple-500",
};

function Row({
  node,
  path,
  depth,
  rootEntityId,
  selectedEntityId,
  onSelect,
}: {
  node: TreeNode;
  path: string;
  depth: number;
  rootEntityId: string;
  selectedEntityId: string | null;
  onSelect: (entityId: string) => void;
}) {
  // Auto-expand the first two levels so the tree is useful at a glance;
  // deeper/wider branches (e.g. a manager with 45 funds) start collapsed so
  // the view stays scannable rather than dumping everything at once.
  const [expanded, setExpanded] = useState(depth < 2);
  const hasChildren = node.children.length > 0;
  const isRoot = node.entity_id === rootEntityId;
  const isSelected = node.entity_id === selectedEntityId;

  return (
    <div>
      <div
        onClick={() => onSelect(node.entity_id)}
        className={`flex cursor-pointer items-center gap-1.5 rounded px-2 py-1 text-sm ${
          isSelected
            ? "bg-blue-100 ring-1 ring-inset ring-blue-400"
            : isRoot
              ? "bg-blue-50"
              : "hover:bg-slate-50"
        }`}
        style={{ marginLeft: depth * 18 }}
      >
        {hasChildren ? (
          <button
            onClick={(e) => {
              e.stopPropagation();
              setExpanded((v) => !v);
            }}
            className="w-4 shrink-0 text-center text-slate-400 hover:text-slate-700"
          >
            {expanded ? "▾" : "▸"}
          </button>
        ) : (
          <span className="w-4 shrink-0" />
        )}

        <span
          className={`h-2 w-2 shrink-0 rounded-full ${
            node.direction ? DIRECTION_DOT[node.direction] : "bg-blue-600"
          }`}
        />

        <span className={`truncate ${isRoot ? "font-semibold text-slate-900" : "text-slate-800"}`}>
          {node.name ?? node.entity_id}
        </span>

        {node.label && <span className="shrink-0 text-xs text-slate-400">({node.label})</span>}

        {isRoot && (
          <span className="ml-1 shrink-0 rounded bg-blue-600 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white">
            Query
          </span>
        )}
        {!node.expanded && hasChildren === false && (
          <span className="shrink-0 text-[10px] italic text-slate-300">depth limit</span>
        )}
      </div>

      {expanded &&
        hasChildren &&
        node.children.map((child, i) => (
          <Row
            key={`${path}.${i}.${child.entity_id}`}
            node={child}
            path={`${path}.${i}`}
            depth={depth + 1}
            rootEntityId={rootEntityId}
            selectedEntityId={selectedEntityId}
            onSelect={onSelect}
          />
        ))}
    </div>
  );
}

export default function TreeExplorer({
  data,
  selectedEntityId,
  onSelect,
}: {
  data: TreeNode;
  selectedEntityId: string | null;
  onSelect: (entityId: string) => void;
}) {
  return (
    <div className="h-full w-full overflow-auto rounded-lg border border-slate-200 bg-white p-2">
      <Row
        node={data}
        path="root"
        depth={0}
        rootEntityId={data.entity_id}
        selectedEntityId={selectedEntityId}
        onSelect={onSelect}
      />
    </div>
  );
}
