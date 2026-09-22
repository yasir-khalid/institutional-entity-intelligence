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
  relationshipType: string | null;
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
      relationshipType: node.relationship_type,
      children,
    };
  }

  return visit(root, new Set())!;
}

function DirectionIcon({ direction, isRoot }: { direction: SpanningNode["direction"]; isRoot: boolean }) {
  if (isRoot) return <Circle className="fill-accent text-accent h-3 w-3" strokeWidth={0} />;
  if (direction === "upward") return <ArrowUp className="text-upward h-3.5 w-3.5" strokeWidth={2.25} />;
  return <ArrowDown className="text-downward h-3.5 w-3.5" strokeWidth={2.25} />;
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
          isSelected ? "bg-accent-soft" : "hover:bg-canvas/70"
        }`}
      >
        {isSelected && <span className="absolute top-1.5 bottom-1.5 left-0 w-[3px] rounded-full bg-accent" />}

        <button
          type="button"
          onClick={() => hasChildren && setExpanded((v) => !v)}
          aria-label={
            hasChildren
              ? `${expanded ? "Collapse" : "Expand"} ${node.children.length} related ${node.children.length === 1 ? "entity" : "entities"}`
              : undefined
          }
          disabled={!hasChildren}
          className="text-ink-subtle hover:bg-line hover:text-ink flex h-5 w-5 shrink-0 items-center justify-center rounded transition-colors disabled:pointer-events-none disabled:opacity-0"
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
          aria-current={isSelected ? "true" : undefined}
          className="focus-visible:ring-accent flex min-w-0 flex-1 items-center gap-2 rounded py-1 text-left outline-none focus-visible:ring-2"
        >
          <span className="flex w-4 shrink-0 justify-center">
            <DirectionIcon direction={node.direction} isRoot={node.isRoot} />
          </span>

          <span
            className={`truncate text-[13px] ${
              node.isRoot ? "text-ink font-semibold" : isSelected ? "text-ink font-medium" : "text-ink-muted"
            }`}
            title={node.name}
          >
            {node.name}
          </span>

          {(node.label || node.relationshipType) && (
            <span className="text-ink-subtle hidden shrink-0 text-[11px] sm:inline">
              {node.label ?? node.relationshipType?.replaceAll("_", " ")}
            </span>
          )}

          {hasChildren && !expanded && (
            <Badge variant="neutral" className="hidden sm:inline-flex">
              {node.children.length} related
            </Badge>
          )}

          {node.isRoot && (
            <Badge variant="accent" className="ml-0.5">
              Query
            </Badge>
          )}

          <Mono className="text-ink-subtle group-hover:text-ink-muted ml-auto hidden shrink-0 pl-3 transition-colors lg:inline">
            {node.id}
          </Mono>
        </button>
      </div>

      {expanded && hasChildren && (
        // Indent guide: one continuous hairline per level, so depth is legible
        // at a glance without needing to count indentation by eye.
        <div className="border-line ml-[9px] border-l pl-3">
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
      {selectedEntityId && selectedEntityId !== tree.id && (
        <p className="text-ink-subtle border-line-soft mb-1.5 rounded-md border px-2.5 py-1.5 text-[11px]">
          Inspecting <span className="text-ink font-medium">{findNodeName(tree, selectedEntityId) ?? "related entity"}</span>
        </p>
      )}
      <Branch node={tree} depth={0} selectedEntityId={selectedEntityId} onSelect={onSelect} />
    </div>
  );
}

function findNodeName(node: SpanningNode, entityId: string): string | null {
  if (node.id === entityId) return node.name;
  for (const child of node.children) {
    const found = findNodeName(child, entityId);
    if (found) return found;
  }
  return null;
}
