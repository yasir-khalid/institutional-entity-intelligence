"use client";

import { useState, useSyncExternalStore } from "react";

const key = "er:developer-view";
function read() {
  try {
    return localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}
function subscribe(notify: () => void) {
  window.addEventListener("storage", notify);
  window.addEventListener("developer-view-changed", notify);
  return () => {
    window.removeEventListener("storage", notify);
    window.removeEventListener("developer-view-changed", notify);
  };
}

/** Optional browser preference, with a working toggle even if storage is blocked. */
export function useDeveloperView() {
  const saved = useSyncExternalStore(subscribe, read, () => false);
  const [override, setOverride] = useState<boolean>();
  const open = override ?? saved;
  function setOpen(value: boolean) {
    setOverride(value);
    try {
      localStorage.setItem(key, value ? "1" : "0");
    } catch {
      /* Browser preference only. */
    }
    window.dispatchEvent(new Event("developer-view-changed"));
  }
  return [open, setOpen] as const;
}
