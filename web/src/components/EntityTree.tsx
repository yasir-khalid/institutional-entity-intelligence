"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import type { TreeNode } from "@/lib/api";

// react-force-graph-2d touches `window`/`document` on load - must never run
// during Next.js's server render pass. next/dynamic's wrapper loses the
// library's generic type params, so the ref below is untyped (only
// zoomToFit is actually called on it) rather than fighting that mismatch.
const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), { ssr: false });

interface GraphNode {
  id: string;
  name: string;
  isRoot: boolean;
  direction: "upward" | "downward" | null;
  label: string | null;
  level: number;
  fx: number;
  fy: number;
}

const LEVEL_HEIGHT = 140;
const NODE_SPACING = 190;

interface GraphLink {
  source: string;
  target: string;
  direction: "upward" | "downward";
}

const FONT = "600 13px Inter, system-ui, -apple-system, sans-serif";
const LABEL_FONT = "500 10px Inter, system-ui, -apple-system, sans-serif";

const COLORS = {
  root: { fill: "#2563eb", stroke: "#1e3a8a", text: "#ffffff" },
  upward: { fill: "#dcfce7", stroke: "#16a34a", text: "#14532d" },
  downward: { fill: "#f3e8ff", stroke: "#9333ea", text: "#3b0764" },
} as const;

/** Flattens the nested TreeNode into a deterministic, fixed layout - each
 * node gets fx/fy set from a simple BFS-by-level layout (upward = negative
 * levels/above, downward = positive levels/below), so the tree renders
 * exactly the same way every time and never drifts once drawn. Dragging a
 * node still works (it just overrides that one node's fx/fy on drop); only
 * the *initial* layout is deterministic rather than physics-simulated. */
function flatten(root: TreeNode): { nodes: GraphNode[]; links: GraphLink[] } {
  type PendingNode = Omit<GraphNode, "fx" | "fy">;
  const nodes = new Map<string, PendingNode>();
  const links: GraphLink[] = [];
  // Undirected edge-identity key (sorted pair) - GLEIF relationships get
  // independently expanded from both ends at depth >= 2 (e.g. a fund's
  // upward "umbrella" edge and the umbrella's own downward "sub-fund" edge
  // are the SAME real-world relationship, just each entity discovering it
  // from its own side), so without this a real graph often contains literal
  // A->B and B->A pairs describing one edge twice. Keeping only one direction
  // per unordered pair avoids duplicate visual links between the same nodes.
  const seenPairs = new Set<string>();

  function visit(node: TreeNode, parentId: string | null, parentLevel: number, ancestors: Set<string>) {
    // The API's own cycle protection re-emits an already-visited entity as an
    // unexpanded leaf (e.g. root -> parent -> root) - skip it entirely, it
    // carries no new information beyond "connects back to something already
    // shown higher up in this exact branch."
    if (ancestors.has(node.entity_id)) return;

    const level = node.direction === "upward" ? parentLevel - 1 : node.direction === "downward" ? parentLevel + 1 : 0;
    if (!nodes.has(node.entity_id)) {
      nodes.set(node.entity_id, {
        id: node.entity_id,
        name: node.name ?? node.entity_id,
        isRoot: node.direction === null,
        direction: node.direction,
        label: node.label,
        level,
      });
    }
    if (parentId !== null && node.direction) {
      const pairKey = [parentId, node.entity_id].sort().join("|");
      if (!seenPairs.has(pairKey)) {
        seenPairs.add(pairKey);
        links.push({ source: parentId, target: node.entity_id, direction: node.direction });
      }
    }

    const nextAncestors = new Set(ancestors);
    nextAncestors.add(node.entity_id);
    for (const child of node.children) visit(child, node.entity_id, level, nextAncestors);
  }

  visit(root, null, 0, new Set());

  const byLevel = new Map<number, PendingNode[]>();
  for (const n of nodes.values()) {
    if (!byLevel.has(n.level)) byLevel.set(n.level, []);
    byLevel.get(n.level)!.push(n);
  }

  const positioned: GraphNode[] = [];
  for (const [level, levelNodes] of byLevel) {
    const totalWidth = (levelNodes.length - 1) * NODE_SPACING;
    levelNodes.forEach((n, i) => {
      positioned.push({
        ...n,
        fx: i * NODE_SPACING - totalWidth / 2,
        fy: level * LEVEL_HEIGHT,
      });
    });
  }

  return { nodes: positioned, links };
}

function nodeRectSize(node: GraphNode, ctx: CanvasRenderingContext2D): [number, number] {
  ctx.font = FONT;
  const label = node.name.length > 28 ? `${node.name.slice(0, 26)}…` : node.name;
  const textWidth = ctx.measureText(label).width;
  const width = Math.max(textWidth + 24, 60);
  const height = node.label ? 42 : 30;
  return [width, height];
}

function drawRoundedRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
  radius: number,
) {
  const r = Math.min(radius, width / 2, height / 2);
  ctx.beginPath();
  ctx.moveTo(x - width / 2 + r, y - height / 2);
  ctx.arcTo(x + width / 2, y - height / 2, x + width / 2, y + height / 2, r);
  ctx.arcTo(x + width / 2, y + height / 2, x - width / 2, y + height / 2, r);
  ctx.arcTo(x - width / 2, y + height / 2, x - width / 2, y - height / 2, r);
  ctx.arcTo(x - width / 2, y - height / 2, x + width / 2, y - height / 2, r);
  ctx.closePath();
}

export default function EntityTree({
  data,
  onNodeClick,
}: {
  data: TreeNode;
  onNodeClick: (entityId: string) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const fgRef = useRef<any>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      setSize({ width, height });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const graphData = useMemo(() => flatten(data), [data]);

  useEffect(() => {
    // Positions are already fixed (fx/fy) by flatten()'s deterministic
    // layout - no physics settling to wait for, just frame the result.
    const fg = fgRef.current;
    if (!fg) return;
    const t = setTimeout(() => fg.zoomToFit(300, 60), 50);
    return () => clearTimeout(t);
  }, [graphData]);

  return (
    <div ref={containerRef} className="h-full w-full overflow-hidden rounded-lg border border-slate-200 bg-slate-50">
      {size.width > 0 && (
        <ForceGraph2D
          ref={fgRef}
          width={size.width}
          height={size.height}
          graphData={graphData}
          backgroundColor="#f8fafc"
          nodeId="id"
          linkSource="source"
          linkTarget="target"
          enableNodeDrag
          cooldownTicks={0}
          linkColor={(link) => {
            const l = link as unknown as GraphLink;
            return l.direction === "upward" ? "#86efac" : "#d8b4fe";
          }}
          linkWidth={1.5}
          linkDirectionalArrowLength={4}
          linkDirectionalArrowRelPos={1}
          onNodeClick={(node) => onNodeClick((node as GraphNode).id)}
          nodeCanvasObject={(node, ctx) => {
            const n = node as unknown as GraphNode & { x: number; y: number };
            const [w, h] = nodeRectSize(n, ctx);
            const palette = n.isRoot ? COLORS.root : n.direction === "upward" ? COLORS.upward : COLORS.downward;

            drawRoundedRect(ctx, n.x, n.y, w, h, 8);
            ctx.fillStyle = palette.fill;
            ctx.fill();
            ctx.lineWidth = n.isRoot ? 2.5 : 1.5;
            ctx.strokeStyle = palette.stroke;
            ctx.stroke();

            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.font = FONT;
            ctx.fillStyle = palette.text;
            const label = n.name.length > 28 ? `${n.name.slice(0, 26)}…` : n.name;
            ctx.fillText(label, n.x, n.label ? n.y - 6 : n.y);

            if (n.label) {
              ctx.font = LABEL_FONT;
              ctx.fillStyle = n.isRoot ? "#dbeafe" : palette.stroke;
              ctx.fillText(n.label, n.x, n.y + 10);
            }
          }}
          nodePointerAreaPaint={(node, color, ctx) => {
            const n = node as unknown as GraphNode & { x: number; y: number };
            const [w, h] = nodeRectSize(n, ctx);
            ctx.fillStyle = color;
            drawRoundedRect(ctx, n.x, n.y, w, h, 8);
            ctx.fill();
          }}
        />
      )}
    </div>
  );
}
