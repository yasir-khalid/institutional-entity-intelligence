"use client";

/* The research answer's generative-UI library. OpenUI defines the language (component names, positional
   props, the agent's prompt - see spec.json); every kept component is drawn here with the app's shadcn
   components and charts instead of OpenUI's own styling, so an answer block looks like the rest of the app. */

import type { ReactNode } from "react";
import type { ActionPlan, ComponentRenderProps } from "@openuidev/react-lang";
import { useIsStreaming, useTriggerAction } from "@openuidev/react-lang";
import { openuiLibrary } from "@openuidev/react-ui";
import ReactMarkdown from "react-markdown";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ColumnChart, DonutChart, RankedBarChart, TrendChart, guessFormat, type Datum } from "@/components/charts";
import { cn } from "@/lib/utils";
import spec from "./spec.json";

type Props = ComponentRenderProps<Record<string, unknown>>;
type Node = { typeName?: string; props?: Record<string, unknown> };

const keep = new Set<string>(spec.keep);
const list = (value: unknown): unknown[] => (Array.isArray(value) ? value : value == null ? [] : [value]);
const nodes = (value: unknown) => list(value).filter((item): item is Node => typeof item === "object" && item !== null);
const text = (value: unknown) => (value == null ? "" : String(value));

const GAP: Record<string, string> = { none: "gap-0", xs: "gap-1", s: "gap-2", m: "gap-3", l: "gap-4", xl: "gap-6", "2xl": "gap-8" };
const ALIGN: Record<string, string> = { start: "items-start", center: "items-center", end: "items-end", stretch: "items-stretch", baseline: "items-baseline" };
const JUSTIFY: Record<string, string> = { start: "justify-start", center: "justify-center", end: "justify-end", between: "justify-between", around: "justify-around", evenly: "justify-evenly" };

function flex(props: Record<string, unknown>) {
  return cn("flex min-w-0", props.direction === "row" ? "flex-row" : "flex-col", GAP[text(props.gap)] ?? "gap-3",
    ALIGN[text(props.align)], JUSTIFY[text(props.justify)], props.wrap ? "flex-wrap" : "");
}

/** labels + Series(category, values) -> one row per label, one key per series. */
function rows(props: Record<string, unknown>) {
  const series = nodes(props.series).map((node, index) => ({
    key: `s${index}`, label: text(node.props?.category) || `Series ${index + 1}`, values: list(node.props?.values),
  }));
  const data: Datum[] = list(props.labels).map((label, row) => ({
    label: text(label), ...Object.fromEntries(series.map((item) => [item.key, Number(item.values[row]) || 0])),
  }));
  const format = guessFormat(text(props.yLabel), text(props.xLabel), ...series.map((item) => item.label));
  return { data, series: series.map(({ key, label }) => ({ key, label })), format };
}

function Columns({ props }: Props) {
  const { data, series, format } = rows(props);
  const signed = data.some((row) => series.some((item) => Number(row[item.key]) < 0));
  return data.length ? <ColumnChart data={data} series={series} format={format} stacked={props.variant === "stacked"} signed={signed} /> : null;
}

function Trend(kind: "area" | "line") {
  return function TrendBlock({ props }: Props) {
    const { data, series, format } = rows(props);
    return data.length ? <TrendChart data={data} series={series} format={format} kind={kind} stepped={props.variant === "step"} /> : null;
  };
}

function Ranked({ props }: Props) {
  const { data, series, format } = rows(props);
  if (!data.length) return null;
  if (series.length !== 1) return <ColumnChart data={data} series={series} format={format} />;
  const ranked = data.map((row) => ({ label: text(row.label), value: Number(row.s0) || 0 }));
  return <RankedBarChart data={ranked} format={format} label={series[0].label} signed={ranked.some((row) => row.value < 0)} />;
}

function Donut({ props }: Props) {
  const values = list(props.values);
  const data = list(props.labels).map((label, index) => ({ label: text(label), value: Number(values[index]) || 0 }));
  return data.length ? <DonutChart data={data} format={guessFormat(...data.map((row) => row.label))} /> : null;
}

function Markdown({ children, className }: { children: string; className?: string }) {
  return (
    <div className={cn("text-sm leading-relaxed [&_a]:text-primary [&_p]:m-0 [&_strong]:font-medium", className)}>
      <ReactMarkdown>{children}</ReactMarkdown>
    </div>
  );
}

function ActionButton({ props }: Props) {
  const triggerAction = useTriggerAction();
  const streaming = useIsStreaming();
  const label = text(props.label);
  return (
    <Button variant={props.variant === "primary" ? "default" : "outline"} size="sm" className="h-auto min-h-8 max-w-full shrink whitespace-normal text-left"
      disabled={streaming} onClick={() => triggerAction(label, undefined, props.action as ActionPlan | undefined)}>
      {label}
    </Button>
  );
}

function Cell({ value, renderNode }: { value: unknown; renderNode: (value: unknown) => ReactNode }) {
  return <>{typeof value === "object" && value !== null ? renderNode(value) : text(value)}</>;
}

const renderers: Record<string, (props: Props) => ReactNode> = {
  Stack: ({ props, renderNode }) => <div className={flex(props)}>{renderNode(props.children)}</div>,
  Card: ({ props, renderNode }) => (
    <Card className={cn("px-5 py-5 shadow-none", props.variant === "sunk" && "bg-muted/40", props.variant === "clear" && "border-0 p-0", flex(props))}>
      {renderNode(props.children)}
    </Card>
  ),
  CardHeader: ({ props }) => (
    <div className="grid gap-1">
      {props.title ? <CardTitle className="text-sm font-medium">{text(props.title)}</CardTitle> : null}
      {props.subtitle ? <CardDescription className="text-xs">{text(props.subtitle)}</CardDescription> : null}
    </div>
  ),
  TextContent: ({ props }) => (
    <Markdown className={cn(String(props.size ?? "").startsWith("small") && "text-xs text-muted-foreground",
      String(props.size ?? "").startsWith("large") && "text-base", String(props.size ?? "").endsWith("heavy") && "font-medium")}>
      {text(props.text)}
    </Markdown>
  ),
  Callout: ({ props }) => (
    <Alert variant={props.variant === "error" ? "destructive" : "default"}>
      <AlertTitle>{text(props.title)}</AlertTitle>
      {props.description ? <AlertDescription>{text(props.description)}</AlertDescription> : null}
    </Alert>
  ),
  Separator: ({ props }) => <Separator orientation={props.orientation === "vertical" ? "vertical" : "horizontal"} />,
  Table: ({ props, renderNode }) => {
    const columns = nodes(props.columns).map((node) => ({
      label: text(node.props?.label), data: list(node.props?.data), numeric: node.props?.type === "number",
    }));
    const count = Math.max(0, ...columns.map((column) => column.data.length));
    if (!columns.length) return null;
    return (
      <div className="overflow-hidden rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/50">
              {columns.map((column, index) => <TableHead key={index} className={cn(column.numeric && "text-right")}>{column.label}</TableHead>)}
            </TableRow>
          </TableHeader>
          <TableBody>
            {Array.from({ length: count }, (_, row) => (
              <TableRow key={row}>
                {columns.map((column, index) => (
                  <TableCell key={index} className={cn("whitespace-normal", column.numeric && "text-right tabular-nums", index === 0 && "font-medium")}>
                    <Cell value={column.data[row]} renderNode={renderNode} />
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    );
  },
  Col: () => null,
  Series: () => null,
  Slice: () => null,
  BarChart: Columns,
  LineChart: Trend("line"),
  AreaChart: Trend("area"),
  HorizontalBarChart: Ranked,
  PieChart: Donut,
  Tabs: ({ props, renderNode }) => {
    const items = nodes(props.items);
    if (!items.length) return null;
    return (
      <Tabs defaultValue={text(items[0].props?.value) || "0"}>
        <TabsList>{items.map((item, index) => <TabsTrigger key={index} value={text(item.props?.value) || String(index)}>{text(item.props?.trigger)}</TabsTrigger>)}</TabsList>
        {items.map((item, index) => (
          <TabsContent key={index} value={text(item.props?.value) || String(index)} className="grid gap-3 pt-2">{renderNode(item.props?.content)}</TabsContent>
        ))}
      </Tabs>
    );
  },
  TabItem: () => null,
  TagBlock: ({ props }) => <div className="flex flex-wrap gap-1.5">{list(props.tags).map((tag, index) => <Badge key={index} variant="outline">{text(tag)}</Badge>)}</div>,
  Tag: ({ props }) => (
    <Badge variant={({ success: "positive", warning: "caution", danger: "critical", info: "accent" } as const)[text(props.variant) as "success"] ?? "outline"}>
      {text(props.text)}
    </Badge>
  ),
  Buttons: ({ props, renderNode }) => (
    <div className={cn("flex flex-wrap gap-2", props.direction === "column" && "flex-col items-start")}>{renderNode(props.buttons)}</div>
  ),
  Button: ActionButton,
  MetricIndicatorInline: ({ props }) => (
    <div className="flex items-baseline gap-2">
      <span className="text-2xl font-medium tracking-tight tabular-nums">{text(props.value)}</span>
      {props.subtext ? <span className="text-xs text-muted-foreground">{text(props.subtext)}</span> : null}
    </div>
  ),
  OverviewCardBlock: ({ props, renderNode }) => (
    <div className="grid gap-3 sm:grid-cols-[repeat(auto-fit,minmax(10rem,1fr))]">{renderNode(props.items)}</div>
  ),
  OverviewCardItem: ({ props, renderNode }) => (
    <Card className="gap-2 px-4 py-4 shadow-none">{renderNode(props.top)}{renderNode(props.bottom)}</Card>
  ),
  IconText: ({ props }) => (
    <div className="grid gap-0.5">
      <span className={cn("text-xs text-muted-foreground", props.bold ? "font-medium text-foreground" : "")}>{text(props.title)}</span>
      {props.subtitle ? <span className="text-xs text-muted-foreground">{text(props.subtitle)}</span> : null}
    </div>
  ),
  Icon: () => null,
};

export const answerLibrary = openuiLibrary.extend({
  components: {
    remove: Object.keys(openuiLibrary.components).filter((name) => !keep.has(name)),
    override: Object.entries(renderers)
      .filter(([name]) => keep.has(name))
      .map(([name, component]) => ({ ...openuiLibrary.components[name], component })),
  },
});

/** Fenced-code languages that carry OpenUI Lang in an answer. */
export const OPENUI_LANGS = new Set(["openui-lang", "openui"]);
