"use client";

import { useMemo, useRef, useState, useEffect } from "react";
import Tree, { type RawNodeDatum, type CustomNodeElementProps } from "react-d3-tree";
import type { TreeNode } from "@/lib/api";

function toRawTree(node: TreeNode): RawNodeDatum {
  return {
    name: node.name ?? node.entity_id,
    attributes: {
      entity_id: node.entity_id,
      direction: node.direction ?? "root",
      label: node.label ?? "",
    },
    children: node.children.map(toRawTree),
  };
}

function NodeLabel({
  nodeDatum,
  onEntityClick,
}: CustomNodeElementProps & { onEntityClick: (entityId: string) => void }) {
  const direction = nodeDatum.attributes?.direction as string | undefined;
  const entityId = nodeDatum.attributes?.entity_id as string;
  const isRoot = direction === "root";
  const fill = isRoot ? "#2563eb" : direction === "upward" ? "#16a34a" : "#9333ea";

  return (
    <g onClick={() => onEntityClick(entityId)} style={{ cursor: "pointer" }}>
      <circle r={isRoot ? 10 : 7} fill={fill} stroke="#1e293b" strokeWidth={1} />
      <text x={isRoot ? 16 : 12} y={4} style={{ fontSize: isRoot ? 14 : 12, fontWeight: isRoot ? 700 : 400 }} fill="#0f172a">
        {nodeDatum.name}
      </text>
      {nodeDatum.attributes?.label ? (
        <text x={isRoot ? 16 : 12} y={20} style={{ fontSize: 10 }} fill="#64748b">
          {String(nodeDatum.attributes.label)}
        </text>
      ) : null}
    </g>
  );
}

export default function EntityTree({
  data,
  onNodeClick,
}: {
  data: TreeNode;
  onNodeClick: (entityId: string) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [translate, setTranslate] = useState({ x: 0, y: 0 });

  useEffect(() => {
    if (containerRef.current) {
      const { width, height } = containerRef.current.getBoundingClientRect();
      setTranslate({ x: width / 2, y: height / 6 });
    }
  }, [data]);

  const rawData = useMemo(() => toRawTree(data), [data]);

  return (
    <div ref={containerRef} className="h-[600px] w-full rounded-lg border border-slate-200 bg-white">
      <Tree
        data={rawData}
        translate={translate}
        orientation="vertical"
        pathFunc="step"
        collapsible={false}
        zoomable
        separation={{ siblings: 1.2, nonSiblings: 1.5 }}
        renderCustomNodeElement={(props) => <NodeLabel {...props} onEntityClick={onNodeClick} />}
      />
    </div>
  );
}
