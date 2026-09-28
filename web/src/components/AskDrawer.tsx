"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowLeft, FileSearch, Loader2, MessageCircleQuestion, Send, X } from "lucide-react";
import { askQuestion, type AskResponse, type Citation, type Evidence, type Verification } from "@/lib/api";
import EvidenceList from "@/components/EvidenceLayer";
import CitationChip from "@/components/CitationChip";
import VerificationBadge from "@/components/VerificationBadge";

/* ---------------------------------------------------------------------------
   The "Ask" chat sidebar - a focus-trapped drawer (same pattern as
   WhyItMatters.tsx), not an inline box in the details panel. Holds a running
   conversation about the currently selected entity; each assistant answer
   carries inline [n] citation markers that open a provenance popover on hover
   and switch this same drawer into a "Sources & method" sub-view on click,
   rather than opening a second overlapping panel.
--------------------------------------------------------------------------- */

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  verification?: Verification | null;
}

function AnswerText({
  content,
  citations,
  evidence,
  onCiteClick,
}: {
  content: string;
  citations: Citation[];
  evidence: Record<string, Evidence>;
  onCiteClick: (evidenceId: string) => void;
}) {
  const parts = content.split(/(\[\d+\])/g);
  const markerToEvidence = new Map(citations.map((c) => [c.marker, c.evidence_id]));

  return (
    <>
      {parts.map((part, i) => {
        const match = /^\[(\d+)\]$/.exec(part);
        const marker = match ? Number(match[1]) : null;
        const evidenceId = marker !== null ? markerToEvidence.get(marker) : undefined;
        if (marker === null || !evidenceId) return <span key={i}>{part}</span>;
        return <CitationChip key={i} marker={marker} evidence={evidence[evidenceId]} onOpen={onCiteClick} />;
      })}
    </>
  );
}

export default function AskDrawer({
  entityId,
  entityName,
  open,
  onClose,
}: {
  entityId: string;
  entityName: string;
  open: boolean;
  onClose: () => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<"chat" | "evidence">("chat");
  const [focusedEvidenceId, setFocusedEvidenceId] = useState<string | null>(null);
  const [evidenceStore, setEvidenceStore] = useState<Record<string, Evidence>>({});

  const closeRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key !== "Tab") return;
      const focusable = dialogRef.current?.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      );
      if (!focusable?.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  useEffect(() => {
    if (view !== "chat") return;
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading, view]);

  const submit = async () => {
    const trimmed = question.trim();
    if (!trimmed || loading) return;
    setMessages((m) => [...m, { role: "user", content: trimmed }]);
    setQuestion("");
    setLoading(true);
    setError(null);
    try {
      const res: AskResponse = await askQuestion(trimmed, entityId);
      setEvidenceStore((prev) => ({ ...prev, ...res.evidence }));
      setMessages((m) => [
        ...m,
        { role: "assistant", content: res.answer, citations: res.citations, verification: res.verification },
      ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  };

  const openEvidence = (evidenceId: string | null) => {
    setFocusedEvidenceId(evidenceId);
    setView("evidence");
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40">
      <div className="animate-fade-in absolute inset-0 bg-slate-900/25 backdrop-blur-[1px]" onClick={onClose} aria-hidden />

      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="ask-title"
        className="animate-slide-in-right border-line bg-surface absolute inset-y-0 right-0 flex w-[min(26rem,100vw)] flex-col border-l shadow-[-8px_0_32px_rgba(15,23,42,0.12)]"
      >
        <header className="border-line-soft flex shrink-0 items-center gap-3 border-b px-5 py-4">
          {view === "evidence" ? (
            <button
              type="button"
              onClick={() => setView("chat")}
              aria-label="Back to chat"
              className="text-ink-subtle hover:bg-canvas hover:text-ink flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-colors"
            >
              <ArrowLeft className="h-4 w-4" strokeWidth={2} />
            </button>
          ) : (
            <span className="bg-accent-soft text-accent flex h-8 w-8 shrink-0 items-center justify-center rounded-lg">
              <MessageCircleQuestion className="h-4 w-4" strokeWidth={1.75} />
            </span>
          )}
          <div className="min-w-0 flex-1">
            <h2 id="ask-title" className="text-ink text-[14px] leading-snug font-semibold">
              {view === "evidence" ? "Sources & method" : "Ask"}
            </h2>
            <p className="text-ink-subtle truncate text-[11.5px]">
              {view === "evidence" ? "Evidence behind each claim" : entityName}
            </p>
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="text-ink-subtle hover:bg-canvas hover:text-ink focus-visible:ring-accent-soft flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-colors focus-visible:ring-4 focus-visible:outline-none"
          >
            <X className="h-4 w-4" strokeWidth={2} />
          </button>
        </header>

        {view === "evidence" ? (
          <div className="scroll-thin flex-1 overflow-y-auto px-5 py-4">
            <EvidenceList
              evidence={evidenceStore}
              focusedEvidenceId={focusedEvidenceId}
              contexts={messages
                .filter((message) => message.role === "assistant")
                .map((message) => ({ answer: message.content, citations: message.citations ?? [] }))}
            />
          </div>
        ) : (
          <>
            <div ref={scrollRef} className="scroll-thin flex flex-1 flex-col gap-3 overflow-y-auto px-5 py-4">
              {messages.length === 0 && (
                <p className="text-ink-subtle text-[12.5px] leading-relaxed">
                  Ask anything about this entity - its status, identifiers, or how it connects to other entities.
                </p>
              )}
              {messages.map((m, i) =>
                m.role === "user" ? (
                  <div key={i} className="flex justify-end">
                    <div className="bg-ink max-w-[85%] rounded-lg rounded-br-sm px-3 py-2 text-[12.5px] text-white">
                      {m.content}
                    </div>
                  </div>
                ) : (
                  <div key={i} className="flex justify-start">
                    <div className="bg-canvas border-line-soft text-ink max-w-[90%] rounded-lg rounded-bl-sm border px-3 py-2 text-[12.5px] leading-relaxed">
                      <AnswerText content={m.content} citations={m.citations ?? []} evidence={evidenceStore} onCiteClick={openEvidence} />
                      <VerificationBadge verification={m.verification} />
                      {(m.citations?.length ?? 0) > 0 && (
                        <button
                          type="button"
                          onClick={() => openEvidence(null)}
                          className="text-ink-subtle hover:text-ink mt-2 flex items-center gap-1.5 text-[11px] font-medium"
                        >
                          <FileSearch className="h-3 w-3" strokeWidth={2} />
                          View sources &amp; method
                        </button>
                      )}
                    </div>
                  </div>
                ),
              )}
              {loading && (
                <div className="flex justify-start">
                  <div className="bg-canvas border-line-soft text-ink-subtle flex items-center gap-2 rounded-lg rounded-bl-sm border px-3 py-2 text-[12px]">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    Thinking...
                  </div>
                </div>
              )}
              {error && <p className="text-[12px] text-rose-600">{error}</p>}
            </div>

            <div className="border-line-soft flex shrink-0 items-center gap-2 border-t px-4 py-3">
              <input
                type="text"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void submit();
                }}
                placeholder="Ask about this entity..."
                className="border-line bg-surface text-ink placeholder:text-ink-faint focus-visible:ring-accent-soft w-full rounded-lg border px-3 py-2 text-[12.5px] focus-visible:ring-4 focus-visible:outline-none"
              />
              <button
                type="button"
                onClick={() => void submit()}
                disabled={loading || !question.trim()}
                aria-label="Ask"
                className="bg-ink flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-white transition-opacity disabled:opacity-40"
              >
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
