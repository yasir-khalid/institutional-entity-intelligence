"use client";

import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import styles from "./Figure.module.css";

export const INK = "#191818";
export const ACCENT = "#ff3c00";
export const PRIMARY = "#c72f08";
export const SOFT = "#f3f2ee";
export const LINE = "#e4e1dc";
export const MUTE = "#6f6c6a";
export const font = { fontFamily: "var(--font-sans)" } as const;

export const clamp = (value: number, min = 0, max = 1) => Math.min(max, Math.max(min, value));
export const seg = (time: number, start: number, end: number) => clamp((time - start) / (end - start));
export const lerp = (start: number, end: number, amount: number) => start + (end - start) * amount;
export const ease = (value: number) => value < 0.5 ? 4 * value * value * value : 1 - Math.pow(-2 * value + 2, 3) / 2;
export const easeOut = (value: number) => 1 - Math.pow(1 - value, 3);

export type Play = { active: boolean; reduced: boolean };

function useStage() {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [reduced, setReduced] = useState(false);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const updateMotion = () => setReduced(query.matches);
    updateMotion();
    query.addEventListener("change", updateMotion);

    const element = ref.current;
    if (!element) return () => query.removeEventListener("change", updateMotion);
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), { rootMargin: "-5% 0px -5% 0px" });
    observer.observe(element);
    return () => {
      observer.disconnect();
      query.removeEventListener("change", updateMotion);
    };
  }, []);

  return { ref, active: visible && !reduced && !paused, reduced, paused, setPaused };
}

export function useFrame(active: boolean, step: (delta: number) => void) {
  const callback = useRef(step);
  useLayoutEffect(() => { callback.current = step; });
  useEffect(() => {
    if (!active) return;
    let frame = 0;
    let last = performance.now();
    const loop = (now: number) => {
      callback.current(Math.min(.05, (now - last) / 1000));
      last = now;
      frame = requestAnimationFrame(loop);
    };
    frame = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(frame);
  }, [active]);
}

export function useLoop({ active, reduced }: Play, duration: number, still: number) {
  const [time, setTime] = useState(0);
  useFrame(active, (delta) => setTime((value) => value + delta));
  return { t: reduced ? still : (time % duration) / duration, time };
}

export function Stage({ alt, caption, children }: { alt: string; caption: string; children: (play: Play) => ReactNode }) {
  const { ref, active, reduced, paused, setPaused } = useStage();
  return (
    <figure className={styles.figure}>
      <div className={styles.frame}>
        <div ref={ref} role="img" aria-label={alt} className={styles.stage}>
          {children({ active, reduced })}
        </div>
        {!reduced && <PlayBadge paused={paused} onToggle={() => setPaused((value) => !value)} />}
      </div>
      <figcaption>{caption}</figcaption>
    </figure>
  );
}

function PlayBadge({ paused, onToggle }: { paused: boolean; onToggle: () => void }) {
  return (
    <button type="button" onClick={onToggle} aria-label={paused ? "Play animation" : "Pause animation"} title={paused ? "Play" : "Pause"} className={styles.playBadge}>
      {paused ? (
        <svg viewBox="0 0 12 12" aria-hidden="true"><path d="M3 1.8v8.4L10 6z" fill="currentColor" /></svg>
      ) : (
        <span className={styles.equalizer} aria-hidden="true"><i /><i /><i /></span>
      )}
    </button>
  );
}
