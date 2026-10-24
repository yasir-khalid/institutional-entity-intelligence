"use client";

import { useEffect, useState, useCallback } from "react";
import { getJson } from "@/lib/api";

/** Cancel stale reads and keep polling alive through temporary API outages. */
export function useResource<T>(
  path: string | null,
  poll?: (data: T) => boolean,
) {
  const [state, setState] = useState<{
    path: string | null;
    data?: T;
    error?: string;
  }>({ path: null });
  const [version, setVersion] = useState(0);
  const refresh = useCallback(() => setVersion((value) => value + 1), []);
  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function read() {
      try {
        const data = await getJson<T>(path!, controller.signal);
        if (controller.signal.aborted) return;
        setState({ path, data });
        if (poll?.(data)) timer = setTimeout(read, 1500);
      } catch (error) {
        if (controller.signal.aborted) return;
        setState((old) => ({
          path,
          data: old.path === path ? old.data : undefined,
          error:
            error instanceof Error
              ? error.message
              : "Unable to load this view.",
        }));
        if (poll) timer = setTimeout(read, 5000);
      }
    }
    void read();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [path, version, poll]);
  return {
    data: state.path === path ? state.data : undefined,
    error: state.path === path ? state.error : undefined,
    loading: Boolean(path && state.path !== path),
    refresh,
  };
}
