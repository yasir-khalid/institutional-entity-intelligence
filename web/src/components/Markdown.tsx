"use client";

import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Citation, Evidence } from "@/lib/api";
import CitationChip from "@/components/CitationChip";

/* ---------------------------------------------------------------------------
   Renders an agent answer as real Markdown (headings, bold, lists, GFM
   tables) instead of the raw text the model returns. Inline [n] citation
   markers are left in the answer text by the orchestrator, so before handing
   the string to react-markdown we rewrite each one into a Markdown link whose
   href is a `citation:` pseudo-scheme; the custom `a` renderer turns those
   into CitationChip, which opens a provenance popover on hover and scrolls the
   sources rail on click. A real link opens out to a new tab.

   react-markdown's default `urlTransform` strips any protocol outside
   `https?|ircs?|mailto|xmpp`, which silently rewrote `citation:ev_...` to an
   empty href - so the renderer below never matched and citations fell through
   as dead links. We pass a urlTransform that lets the `citation:` scheme
   through untouched and delegates everything else to the default.
--------------------------------------------------------------------------- */

export default function Markdown({
  content,
  citations,
  evidence,
  onCitationClick,
}: {
  content: string;
  citations: Citation[];
  evidence?: Record<string, Evidence>;
  onCitationClick?: (evidenceId: string) => void;
}) {
  const markerToEvidence = new Map(citations.map((c) => [c.marker, c.evidence_id]));
  const linked = content.replace(/\[(\d+)\](?!\()/g, (match, digits: string) => {
    const evidenceId = markerToEvidence.get(Number(digits));
    return evidenceId ? `[${digits}](citation:${evidenceId})` : match;
  });

  return (
    <div className="markdown answer-copy">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        urlTransform={(url) => (url.startsWith("citation:") ? url : defaultUrlTransform(url))}
        components={{
          a: ({ href, children }) => {
            if (href?.startsWith("citation:")) {
              const evidenceId = href.slice("citation:".length);
              const marker = Number(Array.isArray(children) ? children.join("") : children);
              return (
                <CitationChip
                  marker={Number.isFinite(marker) ? marker : 0}
                  evidence={evidence?.[evidenceId]}
                  onOpen={onCitationClick}
                />
              );
            }
            return (
              <a href={href} target="_blank" rel="noreferrer">
                {children}
              </a>
            );
          },
        }}
      >
        {linked}
      </ReactMarkdown>
    </div>
  );
}