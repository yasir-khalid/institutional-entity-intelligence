"use client";

import { useMemo, useState } from "react";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  type Node,
  type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import dagre from "dagre";
import type { TreeNode } from "@/lib/api";
import EntityNode, { NODE_WIDTH, NODE_HEIGHT, type EntityNodeData } from "@/components/EntityNode";

const nodeTypes = { entity: EntityNode };

interface RawNode {
  id: string;
  name: string;
  isRoot: boolean;
  direction: "upward" | "downward" | null;
  label: string | null;
  /** Hops from root along the path it was FIRST discovered on - used only to
   * pick a sane initial collapse state (see initialCollapsed below), since a
   * large asset manager's real fan-out can be genuinely huge (confirmed
   * live: one real entity's depth=2 tree flattens to 1,108 distinct nodes -
   * rendering all of that at once on first paint is unusable regardless of
   * which visualization is used, canvas or list). */
  level: number;
}
interface RawEdge {
  source: string;
  target: string;
  direction: "upward" | "downward";
}

/** Flattens the nested TreeNode into a plain node/edge list, keeping only
 * ONE parent edge per entity (its first-discovery path) - a proper spanning
 * tree, not a general graph. This matters for two reasons, both found live
 * on a real large entity (Fred Alger Management):
 *
 * 1. GLEIF relationships get independently rediscovered from both ends (a
 *    fund's "umbrella" edge and the umbrella's own "sub-fund" edge are the
 *    same real relationship) AND siblings can cross-reference each other
 *    (fund A's own upward listing can point at fund B, a sibling already
 *    reached directly from root) - keeping every such edge turns the
 *    "children" of a collapsed node into an inconsistent mix of its real
 *    descendants plus unrelated siblings reached through a back-reference,
 *    so collapsing one node was transitively hiding ~35 of ~47 unrelated
 *    top-level entities.
 * 2. The API's own cycle protection re-emits an already-visited entity as an
 *    unexpanded leaf (e.g. root -> parent -> root) - skipped via the
 *    ancestors path-check, same as before.
 *
 * Once a node is discovered, its subtree is processed exactly once (the
 * `!nodes.has(...)` check gates both node insertion AND recursion) - a
 * second reference to an already-known entity is dropped entirely rather
 * than re-explored, which is also what keeps the total node count bounded
 * instead of exploding combinatorially.
 */
function flatten(root: TreeNode): { nodes: RawNode[]; edges: RawEdge[] } {
  const nodes = new Map<string, RawNode>();
  const edges: RawEdge[] = [];

  function visit(node: TreeNode, parentId: string | null, level: number, ancestors: Set<string>) {
    if (ancestors.has(node.entity_id)) return;
    if (nodes.has(node.entity_id)) return; // already discovered via another path - don't re-explore or re-link

    nodes.set(node.entity_id, {
      id: node.entity_id,
      name: node.name ?? node.entity_id,
      isRoot: node.direction === null,
      direction: node.direction,
      label: node.label,
      level,
    });
    if (parentId !== null && node.direction) {
      edges.push({ source: parentId, target: node.entity_id, direction: node.direction });
    }

    const next = new Set(ancestors);
    next.add(node.entity_id);
    for (const child of node.children) visit(child, node.entity_id, level + 1, next);
  }

  visit(root, null, 0, new Set());
  return { nodes: Array.from(nodes.values()), edges };
}

/** Default collapse state: only the root's direct neighbors (level 1) are
 * visible on first paint - everything past that starts collapsed and is
 * revealed on demand via a node's +/- toggle. Without this, a real
 * asset-manager-sized entity can dump 1,000+ cards on first render. */
function initialCollapsed(nodes: RawNode[]): Set<string> {
  return new Set(nodes.filter((n) => n.level === 1).map((n) => n.id));
}

/** Which nodes are hidden because an ancestor is collapsed. Parents
 * (upward) collapse upward from a node; children (downward) collapse
 * downward - collapsing the root's own "downward" side hides all
 * descendants, not the root itself. */
function hiddenByCollapse(
  nodes: RawNode[],
  edges: RawEdge[],
  collapsed: Set<string>,
): Set<string> {
  const childrenOf = new Map<string, string[]>();
  for (const e of edges) {
    if (!childrenOf.has(e.source)) childrenOf.set(e.source, []);
    childrenOf.get(e.source)!.push(e.target);
  }
  const hidden = new Set<string>();
  function hide(id: string) {
    for (const childId of childrenOf.get(id) ?? []) {
      if (!hidden.has(childId)) {
        hidden.add(childId);
        hide(childId);
      }
    }
  }
  for (const id of collapsed) hide(id);
  return hidden;
}

function layout(nodes: RawNode[], edges: RawEdge[]): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "TB", nodesep: 40, ranksep: 70 });

  for (const n of nodes) g.setNode(n.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  for (const e of edges) g.setEdge(e.source, e.target);
  dagre.layout(g);

  const flowNodes: Node[] = nodes.map((n) => {
    const pos = g.node(n.id);
    return {
      id: n.id,
      type: "entity",
      position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 },
      data: { name: n.name, label: n.label, direction: n.direction, isRoot: n.isRoot } as unknown as Record<
        string,
        unknown
      >,
    };
  });

  const flowEdges: Edge[] = edges.map((e) => ({
    id: `${e.source}->${e.target}`,
    source: e.source,
    target: e.target,
    style: { stroke: e.direction === "upward" ? "#86efac" : "#d8b4fe", strokeWidth: 1.5 },
  }));

  return { nodes: flowNodes, edges: flowEdges };
}

function TreeGraphInner({
  data,
  selectedEntityId,
  onSelect,
}: {
  data: TreeNode;
  selectedEntityId: string | null;
  onSelect: (entityId: string) => void;
}) {
  const { nodes: rawNodes, edges: rawEdges } = useMemo(() => flatten(data), [data]);
  const [collapsed, setCollapsed] = useState<Set<string>>(() => initialCollapsed(rawNodes));

  const childrenOf = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const e of rawEdges) {
      if (!map.has(e.source)) map.set(e.source, []);
      map.get(e.source)!.push(e.target);
    }
    return map;
  }, [rawEdges]);

  const hidden = useMemo(() => hiddenByCollapse(rawNodes, rawEdges, collapsed), [rawNodes, rawEdges, collapsed]);

  const visibleNodes = rawNodes.filter((n) => !hidden.has(n.id));
  const visibleEdges = rawEdges.filter((e) => !hidden.has(e.source) && !hidden.has(e.target));

  const { nodes: flowNodes, edges: flowEdges } = useMemo(
    () => layout(visibleNodes, visibleEdges),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [visibleNodes.map((n) => n.id).join(","), visibleEdges.map((e) => `${e.source}-${e.target}`).join(",")],
  );

  const decoratedNodes: Node[] = flowNodes.map((n) => {
    const raw = rawNodes.find((r) => r.id === n.id)!;
    const hasChildren = (childrenOf.get(n.id) ?? []).length > 0;
    const data: EntityNodeData = {
      name: raw.name,
      label: raw.label,
      direction: raw.direction,
      isRoot: raw.isRoot,
      isSelected: raw.id === selectedEntityId,
      hasChildren,
      collapsed: collapsed.has(n.id),
      onToggleCollapse: () =>
        setCollapsed((prev) => {
          const next = new Set(prev);
          if (next.has(n.id)) next.delete(n.id);
          else next.add(n.id);
          return next;
        }),
    };
    return { ...n, data: data as unknown as Record<string, unknown> };
  });

  return (
    <ReactFlow
      nodes={decoratedNodes}
      edges={flowEdges}
      nodeTypes={nodeTypes}
      onNodeClick={(_, node) => onSelect(node.id)}
      fitView
      fitViewOptions={{ padding: 0.3 }}
      minZoom={0.2}
      maxZoom={1.5}
      nodesDraggable
      nodesConnectable={false}
      edgesFocusable={false}
    >
      <Background gap={20} color="#e2e8f0" />
      <Controls showInteractive={false} />
    </ReactFlow>
  );
}

export default function TreeGraph(props: {
  data: TreeNode;
  selectedEntityId: string | null;
  onSelect: (entityId: string) => void;
}) {
  return (
    <div className="h-full w-full overflow-hidden rounded-lg border border-slate-200 bg-slate-50">
      <ReactFlowProvider>
        <TreeGraphInner {...props} />
      </ReactFlowProvider>
    </div>
  );
}
