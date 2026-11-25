/** Next passes a page's `searchParams` as a promise of string-or-array
 * values. The directory clients only use scalar query values, so flatten once
 * on the server and pass a plain object into the client component. This keeps
 * the page out of the `useSearchParams` / Suspense hydration path, which left
 * these routes stuck on their loading skeleton after a hard refresh. */
export type PageSearchParams = Promise<
  Record<string, string | string[] | undefined>
>;

export function firstValues(
  input: Record<string, string | string[] | undefined>,
): Record<string, string> {
  const values: Record<string, string> = {};
  for (const [key, value] of Object.entries(input)) {
    if (value === undefined) continue;
    values[key] = Array.isArray(value) ? (value[0] ?? "") : value;
  }
  return values;
}
