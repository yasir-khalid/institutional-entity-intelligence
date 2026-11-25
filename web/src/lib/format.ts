const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
const whole = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

export function usd(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `$${compact.format(value)}`;
}

export function count(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : whole.format(value);
}

export function shortCount(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : compact.format(value);
}

export function percent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

/** "31-MAR-2026" (13F) or "2026-03-31" -> "Mar 31, 2026". */
export function day(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = /^\d{2}-[A-Z]{3}-\d{4}$/.test(value) ? new Date(`${value.slice(3, 6)} ${value.slice(0, 2)} ${value.slice(7)} UTC`)
    : new Date(`${value}T00:00:00Z`);
  return Number.isNaN(parsed.getTime()) ? value
    : parsed.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
}

export function edgarFiling(cik: string, accession: string): string {
  return `https://www.sec.gov/Archives/edgar/data/${Number(cik)}/${accession.replaceAll("-", "")}/`;
}

/** Compact chart label: "Mar 26" (month), "Mar 31" (day) or "Mar 31 '26" (both). */
export function tick(value: string, style: "month" | "day" | "both" = "month"): string {
  const parsed = new Date(`${day(value)} UTC`);
  if (Number.isNaN(parsed.getTime())) return value;
  const format = (options: Intl.DateTimeFormatOptions) => parsed.toLocaleDateString("en-US", { ...options, timeZone: "UTC" });
  if (style === "month") return format({ month: "short", year: "2-digit" });
  if (style === "day") return format({ month: "short", day: "numeric" });
  return `${format({ month: "short", day: "numeric" })} '${format({ year: "2-digit" })}`;
}
