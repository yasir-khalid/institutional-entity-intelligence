"use client";

import { useMemo, useState } from "react";
import type { TreeNode } from "@/lib/api";

interface SpanningNode {
  id: string;
  name: string;
  isRoot: boolean;
  direction: "upward" | "downward" | null;
  label: string | null;
  children: SpanningNode[];
}

/** Rebuilds the API's nested tree into a proper spanning tree - one parent
 * per entity, first-discovery wins - before rendering. Without this, GLEIF's
 * cross-referenced relationships (a fund's own "umbrella" listing pointing
 * back at a sibling already reached directly from root) show the same
 * entity twice with two different sets of children, which is confusing in a
 * plain indented tree in exactly the way it broke collapse state in an
 * earlier graph-based version of this view (see docs/phases.md Phase 14).
 */
function toSpanningTree(root: TreeNode): SpanningNode {
  const seen = new Set<string>();

  function visit(node: TreeNode, ancestors: Set<string>): SpanningNode | null {
    if (ancestors.has(node.entity_id)) return null;
    if (seen.has(node.entity_id)) return null;
    seen.add(node.entity_id);

    const next = new Set(ancestors);
    next.add(node.entity_id);
    const children = node.children.map((c) => visit(c, next)).filter((c): c is SpanningNode => c !== null);

    return {
      id: node.entity_id,
      name: node.name ?? node.entity_id,
      isRoot: node.direction === null,
      direction: node.direction,
      label: node.label,
      children,
    };
  }

  return visit(root, new Set())!;
}

const DIRECTION_ACCENT: Record<string, string> = {
  upward: "border-l-green-500",
  downward: "border-l-purple-500",
};

function Card({
  node,
  isSelected,
  onSelect,
}: {
  node: SpanningNode;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const accent = node.direction ? DIRECTION_ACCENT[node.direction] : "border-l-blue-600";
  return (
    <button
      onClick={onSelect}
      className={`flex items-center gap-2 rounded-md border border-l-4 bg-white px-3 py-1.5 text-left text-sm shadow-sm transition-shadow hover:shadow ${accent} ${
        isSelected ? "ring-2 ring-blue-400" : "border-slate-200"
      }`}
    >
      <span className={`truncate ${node.isRoot ? "font-semibold text-slate-900" : "text-slate-800"}`}>
        {node.name}
      </span>
      {node.label && <span className="shrink-0 text-xs text-slate-400">{node.label}</span>}
      {node.isRoot && (
        <span className="shrink-0 rounded bg-blue-600 px-1.5 py-0.5 text-[9px] font-semibold uppercase text-white">
          Query
        </span>
      )}
    </button>
  );
}

function Branch({
  node,
  depth,
  selectedEntityId,
  onSelect,
}: {
  node: SpanningNode;
  depth: number;
  selectedEntityId: string | null;
  onSelect: (entityId: string) => void;
}) {
  // Only the root's direct children are expanded by default - everything
  // past that starts collapsed so a large fan-out (a manager with dozens of
  // funds) doesn't dump hundreds of cards on first paint.
  const [expanded, setExpanded] = useState(depth < 1);
  const hasChildren = node.children.length > 0;

  return (
    <div>
      <div className="flex items-center gap-1.5">
        {hasChildren ? (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="flex h-5 w-5 shrink-0 items-center justify-center rounded text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            aria-label={expanded ? "Collapse" : "Expand"}
          >
            {expanded ? "▾" : "▸"}
          </button>
        ) : (
          <span className="w-5 shrink-0" />
        )}
        <Card node={node} isSelected={node.id === selectedEntityId} onSelect={() => onSelect(node.id)} />
      </div>

      {expanded && hasChildren && (
        <div className="ml-[10px] border-l border-slate-200 pl-4">
          {node.children.map((child) => (
            <div key={child.id} className="pt-1.5 first:pt-1.5">
              <Branch node={child} depth={depth + 1} selectedEntityId={selectedEntityId} onSelect={onSelect} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function EntityTreeView({
  data,
  selectedEntityId,
  onSelect,
}: {
  data: TreeNode;
  selectedEntityId: string | null;
  onSelect: (entityId: string) => void;
}) {
  const tree = useMemo(() => toSpanningTree(data), [data]);

  return (
    <div className="h-full w-full overflow-auto rounded-lg border border-slate-200 bg-white p-3">
      <Branch node={tree} depth={0} selectedEntityId={selectedEntityId} onSelect={onSelect} />
    </div>
  );
}
