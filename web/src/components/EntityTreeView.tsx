"use client";

import { useMemo, useState } from "react";
import { ChevronRight, ChevronDown, ArrowUp, ArrowDown, Circle } from "lucide-react";
import type { TreeNode } from "@/lib/api";
import { Badge, Mono } from "@/components/ui";

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
 * back at a sibling already reached directly from root) show the same entity
 * twice with two different sets of children, which is confusing in a plain
 * tree in exactly the way it broke collapse state in an earlier graph-based
 * version of this view (see docs/phases.md Phase 14). */
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

function DirectionIcon({ direction, isRoot }: { direction: SpanningNode["direction"]; isRoot: boolean }) {
  if (isRoot) return <Circle className="h-3 w-3 fill-indigo-500 text-indigo-500" strokeWidth={0} />;
  if (direction === "upward") return <ArrowUp className="h-3.5 w-3.5 text-emerald-600" strokeWidth={2.25} />;
  return <ArrowDown className="h-3.5 w-3.5 text-violet-500" strokeWidth={2.25} />;
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
  // Only the root's direct children are expanded by default - everything past
  // that starts collapsed so a large fan-out (a manager with dozens of funds)
  // doesn't dump hundreds of rows on first paint.
  const [expanded, setExpanded] = useState(depth < 1);
  const hasChildren = node.children.length > 0;
  const isSelected = node.id === selectedEntityId;

  return (
    <div>
      <div
        className={`group relative flex h-9 items-center gap-1 rounded-md pr-2 transition-colors ${
          isSelected ? "bg-indigo-50" : "hover:bg-slate-50"
        }`}
      >
        {isSelected && <span className="absolute top-1.5 bottom-1.5 left-0 w-0.5 rounded-full bg-indigo-500" />}

        <button
          type="button"
          onClick={() => hasChildren && setExpanded((v) => !v)}
          aria-label={hasChildren ? (expanded ? "Collapse" : "Expand") : undefined}
          disabled={!hasChildren}
          className="flex h-5 w-5 shrink-0 items-center justify-center rounded text-slate-400 transition-colors hover:bg-slate-200/70 hover:text-slate-600 disabled:pointer-events-none disabled:opacity-0"
        >
          {expanded ? (
            <ChevronDown className="h-3.5 w-3.5" strokeWidth={2.25} />
          ) : (
            <ChevronRight className="h-3.5 w-3.5" strokeWidth={2.25} />
          )}
        </button>

        <button
          type="button"
          onClick={() => onSelect(node.id)}
          className="flex min-w-0 flex-1 items-center gap-2 py-1 text-left outline-none"
        >
          <span className="flex w-4 shrink-0 justify-center">
            <DirectionIcon direction={node.direction} isRoot={node.isRoot} />
          </span>

          <span
            className={`truncate text-[13px] ${
              node.isRoot ? "font-semibold text-slate-900" : isSelected ? "font-medium text-slate-900" : "text-slate-700"
            }`}
            title={node.name}
          >
            {node.name}
          </span>

          {node.label && (
            <span className="hidden shrink-0 text-[11px] text-slate-400 sm:inline">{node.label}</span>
          )}

          {node.isRoot && (
            <Badge variant="accent" className="ml-0.5">
              Query
            </Badge>
          )}

          <Mono className="ml-auto hidden shrink-0 pl-3 text-slate-300 group-hover:text-slate-400 lg:inline">
            {node.id}
          </Mono>
        </button>
      </div>

      {expanded && hasChildren && (
        // Indent guide: one continuous hairline per level, so depth is legible
        // at a glance without needing to count indentation by eye.
        <div className="ml-[9px] border-l border-slate-150 pl-3" style={{ borderColor: "rgb(226 232 240)" }}>
          {node.children.map((child) => (
            <Branch
              key={child.id}
              node={child}
              depth={depth + 1}
              selectedEntityId={selectedEntityId}
              onSelect={onSelect}
            />
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

  // No border/radius here - the parent panel owns the card chrome so this and
  // the details panel share one consistent frame.
  return (
    <div className="scroll-thin h-full w-full overflow-auto p-2">
      <Branch node={tree} depth={0} selectedEntityId={selectedEntityId} onSelect={onSelect} />
    </div>
  );
}
