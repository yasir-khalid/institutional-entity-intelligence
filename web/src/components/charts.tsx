"use client";

/* The app's charts: shadcn Chart (Recharts) themed from the --chart-* tokens.
   Explore pages and generative answer blocks both draw with these, so a chart
   reads the same wherever it appears. Values arrive unscaled; `format` decides
   how axes and tooltips print them. */

import { type ReactNode } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ReferenceLine,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { cn } from "@/lib/utils";
import { MetricInfo, type MetricDefinition } from "@/components/metrics";

export type ValueFormat = "usd" | "number" | "percent";
export type Datum = Record<string, string | number | null>;
export type SeriesSpec = { key: string; label: string };

const PALETTE = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)"];
const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
const precise = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 2 });

export function formatValue(value: number, format: ValueFormat = "number", exact = false): string {
  const number = exact ? precise : compact;
  if (format === "usd") return `${value < 0 ? "-" : ""}$${number.format(Math.abs(value))}`;
  if (format === "percent") return `${value.toFixed(exact ? 2 : 0)}%`;
  return number.format(value);
}

/** USD when the labels say so, a percentage likewise, otherwise a plain count. */
export function guessFormat(...labels: (string | null | undefined)[]): ValueFormat {
  const text = labels.filter(Boolean).join(" ").toLowerCase();
  if (/\busd\b|\$|dollar|value|aum|assets|sold|raised/.test(text)) return "usd";
  if (/%|percent|share of|ratio/.test(text)) return "percent";
  return "number";
}

function config(series: SeriesSpec[]): ChartConfig {
  return Object.fromEntries(series.map((item, index) => [item.key, { label: item.label, color: PALETTE[index % PALETTE.length] }]));
}

function tooltip(format: ValueFormat, indicator: "dot" | "line" = "dot") {
  return (
    <ChartTooltip
      cursor={indicator === "line" ? { strokeDasharray: "3 3" } : { fill: "var(--fill)" }}
      content={<ChartTooltipContent indicator={indicator} valueFormatter={(value) => formatValue(value, format, true)} />}
    />
  );
}

/** A value over time: filled areas with a soft gradient, or lines. */
export function TrendChart({
  data, series, format = "number", kind = "area", stepped = false, height = 240, xKey = "label",
}: {
  data: Datum[]; series: SeriesSpec[]; format?: ValueFormat; kind?: "area" | "line"; stepped?: boolean;
  height?: number; xKey?: string;
}) {
  const curve = stepped ? "stepAfter" : "monotone";
  const axes = (
    <>
      <CartesianGrid vertical={false} strokeDasharray="3 3" />
      <XAxis dataKey={xKey} tickLine={false} axisLine={false} tickMargin={8} minTickGap={24} />
      <YAxis tickLine={false} axisLine={false} tickMargin={4} width={52} tickFormatter={(value: number) => formatValue(value, format)} />
      {tooltip(format, "line")}
      {series.length > 1 && <ChartLegend content={<ChartLegendContent />} />}
    </>
  );
  return (
    <ChartContainer config={config(series)} className="aspect-auto w-full" style={{ height }}>
      {kind === "line" ? (
        <LineChart data={data} margin={{ left: 4, right: 12, top: 8 }}>
          {axes}
          {series.map((item) => (
            <Line key={item.key} dataKey={item.key} type={curve} stroke={`var(--color-${item.key})`} strokeWidth={2}
              dot={false} activeDot={{ r: 4 }} isAnimationActive={false} />
          ))}
        </LineChart>
      ) : (
        <AreaChart data={data} margin={{ left: 4, right: 12, top: 8 }}>
          {axes}
          {series.map((item) => (
            <Area key={item.key} dataKey={item.key} type={curve} stroke={`var(--color-${item.key})`} strokeWidth={2}
              fill={`var(--color-${item.key})`} fillOpacity={0.08} activeDot={{ r: 4 }} isAnimationActive={false} />
          ))}
        </AreaChart>
      )}
    </ChartContainer>
  );
}

/** Vertical columns per category; `signed` colours gains and losses. */
export function ColumnChart({
  data, series, format = "number", height = 240, stacked = false, signed = false, xKey = "label",
}: {
  data: Datum[]; series: SeriesSpec[]; format?: ValueFormat; height?: number; stacked?: boolean; signed?: boolean;
  xKey?: string;
}) {
  return (
    <ChartContainer config={config(series)} className="aspect-auto w-full" style={{ height }}>
      <BarChart data={data} margin={{ left: 4, right: 12, top: 8 }}>
        <CartesianGrid vertical={false} strokeDasharray="3 3" />
        <XAxis dataKey={xKey} tickLine={false} axisLine={false} tickMargin={8} minTickGap={12} />
        <YAxis tickLine={false} axisLine={false} tickMargin={4} width={52} tickFormatter={(value: number) => formatValue(value, format)} />
        {signed && <ReferenceLine y={0} stroke="var(--line-strong)" />}
        {tooltip(format)}
        {series.length > 1 && <ChartLegend content={<ChartLegendContent />} />}
        {series.map((item, index) => (
          <Bar key={item.key} dataKey={item.key} stackId={stacked ? "stack" : undefined} fill={`var(--color-${item.key})`}
            radius={stacked && index < series.length - 1 ? 0 : [4, 4, 0, 0]} maxBarSize={44} isAnimationActive={false}>
            {signed && data.map((row, rowIndex) => (
              <Cell key={rowIndex} fill={Number(row[item.key]) < 0 ? "var(--chart-negative)" : `var(--color-${item.key})`} />
            ))}
          </Bar>
        ))}
      </BarChart>
    </ChartContainer>
  );
}

/** One labelled bar per row, longest first - for rankings and long category
 * names. Plain HTML rather than an SVG axis, so a long name gets the full row
 * width above its bar instead of being clipped to a fixed label column. */
export function RankedBarChart({
  data, format = "number", label = "Value", signed = false,
}: {
  data: { label: string; value: number }[]; format?: ValueFormat; label?: string; signed?: boolean;
}) {
  const max = Math.max(0, ...data.map((row) => Math.abs(row.value))) || 1;
  const diverging = signed && data.some((row) => row.value < 0);
  return (
    <ol aria-label={label} className="grid gap-3">
      {data.map((row, index) => {
        const width = `${(Math.abs(row.value) / max) * 100}%`;
        const negative = row.value < 0;
        const text = `${signed && row.value > 0 ? "+" : ""}${formatValue(row.value, format)}`;
        const value = (
          <span className={cn("shrink-0 tabular-nums text-muted-foreground", negative && "text-chart-negative")}>{text}</span>
        );
        if (diverging) {
          return (
            <li key={index} title={`${row.label}: ${formatValue(row.value, format, true)}`}
              className="grid min-w-0 grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_4rem] items-center gap-3 text-xs">
              <span className="truncate">{row.label}</span>
              <div className="grid h-1.5 grid-cols-2">
                <div className="flex justify-end border-r border-border">
                  {negative && <span className="h-full rounded-l-full bg-chart-negative" style={{ width }} />}
                </div>
                <div>{!negative && <span className="block h-full rounded-r-full bg-chart-1" style={{ width }} />}</div>
              </div>
              <span className="text-right">{value}</span>
            </li>
          );
        }
        return (
          <li key={index} className="grid min-w-0 gap-1.5" title={`${row.label}: ${formatValue(row.value, format, true)}`}>
            <div className="flex min-w-0 items-baseline justify-between gap-3 text-xs">
              <span className="min-w-0 truncate">{row.label}</span>
              {value}
            </div>
            <div className="h-1.5 rounded-full bg-muted">
              <span className={cn("block h-full rounded-full", negative ? "bg-chart-negative" : "bg-chart-1")} style={{ width }} />
            </div>
          </li>
        );
      })}
    </ol>
  );
}

/** Parts of a whole, with the total in the middle. */
export function DonutChart({
  data, format = "number", centerLabel = "Total",
}: {
  data: { label: string; value: number }[]; format?: ValueFormat; centerLabel?: string;
}) {
  const rows = data.map((row, index) => ({ ...row, key: `slice${index}`, fill: PALETTE[index % PALETTE.length] }));
  const total = rows.reduce((sum, row) => sum + row.value, 0);
  const chartConfig = Object.fromEntries(rows.map((row) => [row.key, { label: row.label, color: row.fill }]));
  return (
    <div className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-4">
      <ChartContainer config={chartConfig} className="mx-auto aspect-square w-full max-w-52">
        <PieChart>
          <ChartTooltip content={<ChartTooltipContent hideLabel nameKey="key" valueFormatter={(value) => formatValue(value, format, true)} />} />
          <Pie data={rows} dataKey="value" nameKey="key" innerRadius="62%" outerRadius="92%" paddingAngle={1.5}
            strokeWidth={0} isAnimationActive={false} />
          <text x="50%" y="47%" textAnchor="middle" className="fill-foreground text-lg font-medium tabular-nums">
            {formatValue(total, format)}
          </text>
          <text x="50%" y="59%" textAnchor="middle" className="fill-muted-foreground text-xs">{centerLabel}</text>
        </PieChart>
      </ChartContainer>
      <ul className="grid min-w-0 gap-1.5 text-xs">
        {rows.map((row) => (
          <li key={row.key} className="flex min-w-0 items-center gap-2">
            <span className="size-2.5 shrink-0 rounded-[3px]" style={{ background: row.fill }} />
            <span className="min-w-0 flex-1 truncate text-muted-foreground" title={row.label}>{row.label}</span>
            <span className="tabular-nums">{formatValue(row.value, format)}</span>
            <span className="w-10 text-right tabular-nums text-muted-foreground">
              {total ? `${Math.round((row.value / total) * 100)}%` : "—"}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** A shadcn Card around one chart: title, a line of context, an optional footnote. */
export function ChartCard({
  title, description, action, footer, children, className, explain,
}: {
  title: ReactNode; description?: ReactNode; action?: ReactNode; footer?: ReactNode; children: ReactNode;
  className?: string;
  /** The figure's definition, opened from the little info button in the header. */
  explain?: MetricDefinition;
}) {
  return (
    <Card className={cn("gap-4 py-5 shadow-none", className)}>
      <CardHeader className="px-5">
        <CardTitle className="flex items-center gap-1.5 text-sm font-medium">
          {title}
          {explain && <MetricInfo metric={explain} />}
        </CardTitle>
        {description && <CardDescription className="text-xs">{description}</CardDescription>}
        {action && <CardAction>{action}</CardAction>}
      </CardHeader>
      <CardContent className="px-3 sm:px-5">{children}</CardContent>
      {footer && <CardFooter className="px-5 text-xs text-muted-foreground">{footer}</CardFooter>}
    </Card>
  );
}
