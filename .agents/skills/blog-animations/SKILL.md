---
name: blog-animations
description: How to build the animated figures in this site's blog posts (and the static-until-touched figures in blog-style labs) - the shared Figure kit, the scene recipe, timing rules, palette and verification. Use whenever adding, replacing or editing an illustration in a /blog post, turning a post image into an animation, or building a figure for a lab article that uses components/blog/Figure.tsx.
---

# Blog animations

Every illustration in a blog post is a small code-driven animation, not an
image, GIF or Lottie file. Each one is a React component drawing SVG (or
plain DOM) whose every frame is computed from a clock. This keeps them crisp
at any size, on-brand, tiny (no assets, no animation library) and
accessible.

Reference implementations, read one before writing a new figure:

- `components/blog/posts/StupidQuestionsFigures.tsx` - the canonical
  timeline scene (a bar splits, labels appear, a result lands). Start here.
- `components/blog/posts/BuildFigures.tsx` - a short repeating cycle with a
  counter that carries across loops (`time`, not just `t`).
- `components/blog/posts/MoatFigures.tsx` - a DOM (not SVG) scene: two lists,
  strike-through, then reveal.
- `components/blog/posts/LearningFigures.tsx` - six scenes, including a
  physics sim on `useFrame` with mutable state (pinball).
- `components/lab/BloomFilter.tsx` - the same kit used for **interactive**
  lab figures (`Stage interactive`) with sliders, inputs and a step model.

## When a post gets a figure

Only where a moving picture explains something the prose can't do as well:
a process, a before/after, a split, a flow, a curve. One figure per idea,
placed right after the paragraph it illustrates. If the source post (e.g.
Substack) had an image, replace it with an animation of the same idea. Don't
decorate posts that are pure argument.

## File layout

- Figures for a post live in `components/blog/posts/<Post>Figures.tsx`
  (`"use client"`), one exported `<NameFigure />` per figure.
- The post body `components/blog/posts/<Post>.tsx` imports and drops them
  between paragraphs. The post body itself stays a server component.
- New post: add the entry to `lib/blog.ts` (slug, title, blurb, date as the
  original publish date, readTime, topic, tags, status "live", optional
  `source` URL for "First on Substack"), then copy any
  `app/blog/<slug>/page.tsx` wrapper and swap the slug and component.

## The kit: `components/blog/Figure.tsx`

```ts
import { INK, ACCENT, PRIMARY, SOFT, LINE, MUTE, font,
         clamp, seg, lerp, ease, easeOut,
         Stage, useLoop, useFrame, type Play } from "@/components/blog/Figure";
```

- `Stage({ alt, caption, interactive?, children: (play) => node })` - the
  bordered white figure plus `<figcaption>`. It watches visibility
  (IntersectionObserver) and `prefers-reduced-motion`, and passes
  `play = { active, reduced }` to the scene. `active` is true only while the
  figure is on screen, not paused and motion is allowed. Non-interactive
  stages render `role="img"` with `alt` as the label, plus the top-right
  **play badge** (orange bouncing bars while playing, a triangle when
  paused; click to pause or resume). `interactive` stages render
  `role="group"` and have no badge.
- `useLoop(play, dur, still)` returns `{ t, time }`. `t` is the loop
  position in [0, 1) for a `dur`-second scene; under reduced motion it is
  pinned to `still`. `time` is total seconds played, for things that should
  accumulate across loops (counters, fills).
- `useFrame(active, step(dt))` - a raw rAF callback with `dt` in seconds
  (capped at 0.05). Use it for simulations (physics, step models) that keep
  mutable state in a `useState(() => ({...}))` object and force a re-render.
- Helpers: `seg(t, a, b)` maps a time window to 0..1 (the workhorse),
  `ease`/`easeOut` shape it, `lerp` interpolates, `clamp` bounds.
- Palette: `INK #191818` text/strong shapes, `MUTE #6f6c6a` secondary text,
  `PRIMARY #dc3300` orange strokes and text (AA), `ACCENT #ff3c00` orange
  **fills only** (never text), `SOFT #f3f2ee` panels/chips, `LINE #e4e1dc`
  wires/hairlines. Greys for de-emphasis: `#cfcbc5`, `#dcd8d2`, `#e8e5e0`,
  `#a9a7a2`. Teal (`var(--accent-teal)`) = healthy, crimson
  (`var(--accent-danger)`) = bad/overload, orange = active.
- `font` - spread onto every SVG `<text>` (`style={font}`). There is no
  monospace anywhere on the site, including SVG.

## The scene recipe

```tsx
function ThingScene(play: Play) {
  const { t } = useLoop(play, 8, 0.7);        // 8s loop; reduced motion shows t=0.7
  const step1 = ease(seg(t, 0.0, 0.18));      // something moves from frame one
  const step2 = seg(t, 0.25, 0.4);
  const result = easeOut(seg(t, 0.55, 0.7));
  const fade = 1 - seg(t, 0.95, 1);           // soft reset before the loop restarts

  return (
    <svg viewBox="0 0 700 250" className="h-auto w-full">
      <g opacity={fade}>{/* shapes driven only by step1/step2/result */}</g>
    </svg>
  );
}

export function ThingFigure() {
  return (
    <Stage
      alt="The whole story in one or two sentences: what appears, what changes, how it ends."
      caption="One line that says what to notice."
    >
      {(p) => <ThingScene {...p} />}
    </Stage>
  );
}
```

Write the story first as a timeline of beats (0-0.2 the question appears,
0.2-0.36 the bar splits, ...), then give each beat a `seg` window. Every
visual property derives from those values, never from separate timers or
CSS transitions, so a frame is a pure function of `t`.

## Rules (learned from Yasir's feedback)

- **Moving from the first frame.** Something must visibly change within
  ~0.5s of the figure arriving. A scene that idles until halfway through
  reads as broken ("unless the user waits on the animation nothing really
  happens"). Front-load motion; don't spend the opening on an empty stage.
- **Short loops.** 6-10s per loop, with the payoff landing by about 70% and
  a hold before the fade. Faster beats for simple ideas (~2s cycles).
- **Fade, don't jump.** End every loop with `fade = 1 - seg(t, 0.95, 1)` (or
  equivalent) so the restart isn't a hard cut.
- **Reduced motion = the most telling still frame.** Pick `still` so the
  frozen frame tells the whole story by itself (usually just after the
  payoff), and make sure sims render a sensible state with `active=false`.
- **Plain, calm drawing.** White stage, thin hairlines, sentence-case
  labels at 12-15px, rounded rects (rx 6-12), pills for chips. No drop
  shadows, gradients, grid paper or dark panels. One orange focal element at
  a time.
- **Responsive SVG.** `viewBox="0 0 700 H"` (H around 220-300) with
  `className="h-auto w-full"`. Keep labels inside the box at 700 wide and
  check they stay legible at phone width (~360px). Use fewer, bigger
  elements rather than fine detail.
- **Prose styles leak.** `.prose-article` list/paragraph styles are
  unlayered and beat Tailwind, so DOM scenes inside a post need inline
  resets (see `BARE` in `MoatFigures.tsx`).
- **Copy rules apply inside figures:** no em dashes (U+2014), sentence case,
  no stacked labels repeating a heading.
- **Accessible.** `alt` narrates the full sequence and its outcome; the
  caption adds the takeaway, never repeats the alt. Don't put interactive
  controls inside a non-interactive stage (its `role="img"` hides them).

## Lab figures are different

Blog figures loop on their own. **Lab figures never autoplay.** In a
blog-style lab (`<LabShell entry={entry} article>`), use
`<Stage interactive>`: the scene opens on meaningful default values (a slider
mid-range, a filter already filled, a finished run) and only animates in
response to the reader (dragging, typing, pressing a button). `useFrame` is
still fine for animating the reader's own action; stop re-rendering when
idle. See `components/lab/BloomFilter.tsx` and the lab section of
`AGENTS.md`.

## Verify

1. `npm run build` must pass (it stops a running `next dev`; restart it
   after, deleting `.next` first if the dev server serves 404 chunks).
2. Open the post in the browser at desktop and ~390px width. Screenshot the
   figure right as it scrolls in (it should already be moving) and again a
   few seconds later.
3. Click the badge: it should pause on the current frame and resume.
4. Emulate `prefers-reduced-motion: reduce` and check the still frame and
   that the badge is hidden.
5. Commit and push to main (the repo's standing rule).

