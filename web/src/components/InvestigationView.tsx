"use client";

import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import Link from "next/link";
import {
  ArrowUp,
  ChevronDown,
  ChevronRight,
  FileText,
  RotateCcw,
  Square,
  Waypoints,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { LoadError, Loading } from "@/components/WorkspaceStates";
import Markdown from "@/components/Markdown";
import EvidenceList from "@/components/EvidenceLayer";
import VerificationBadge, {
  VerificationPill,
} from "@/components/VerificationBadge";
import AuditTrail from "@/components/AuditTrail";
import { useResource } from "@/hooks/use-resource";
import { workspaceMutation, type Investigation } from "@/lib/api";

const pending = (doc: Investigation) =>
  doc.status === "queued" || doc.status === "running";

/* The research note is a conversation, not a report page: a centered reading
 * column, the question as a right-aligned bubble, the sourced answer below it,
 * and a composer docked to the bottom of the viewport. Sources stay one click
 * away rather than occupying a permanent side rail, so the answer keeps the
 * reference's calm reading rhythm without giving up provenance. */

export default function InvestigationView({ id }: { id: string }) {
  const resource = useResource<Investigation>(
    `/api/investigations/${encodeURIComponent(id)}`,
    pending,
  );
  const doc = resource.data;
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [focused, setFocused] = useState<string | null>(null);
  const [openSources, setOpenSources] = useState<number | null>(null);
  const thread = useRef<HTMLDivElement>(null);
  const followupInput = useRef<HTMLTextAreaElement>(null);
  const previousTurns = useRef<number | null>(null);
  const status = doc?.status;
  useEffect(() => {
    thread.current?.scrollTo({ top: 0 });
  }, [id]);
  useEffect(() => {
    if (focused)
      document
        .getElementById(`evidence-${focused}`)
        ?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [focused, openSources]);
  useEffect(() => {
    const count = doc?.turns.length;
    if (count === undefined) return;
    if (previousTurns.current === null) {
      previousTurns.current = count;
      return;
    }
    if (count > previousTurns.current) {
      const last = count - 1;
      requestAnimationFrame(() =>
        document
          .getElementById(`turn-${last}`)
          ?.scrollIntoView({ behavior: "smooth", block: "start" }),
      );
    }
    previousTurns.current = count;
  }, [doc?.turns.length]);
  useEffect(() => {
    if (status === "queued" || status === "running") {
      requestAnimationFrame(() =>
        thread.current?.scrollTo({
          top: thread.current.scrollHeight,
          behavior: "smooth",
        }),
      );
    }
  }, [status]);
  const operation = useRef<{ question: string; id: string } | undefined>(
    undefined,
  );
  async function mutate(path: string, body?: unknown, method?: string) {
    setBusy(true);
    setError(undefined);
    try {
      await workspaceMutation(path, body, method);
      resource.refresh();
      return true;
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Could not save this change.",
      );
      return false;
    } finally {
      setBusy(false);
    }
  }
  async function sendFollowUp(text: string) {
    if (!doc || busy || !text.trim() || pending(doc)) return false;
    if (operation.current?.question !== text.trim())
      operation.current = {
        question: text.trim(),
        id: crypto.randomUUID(),
      };
    const sent = await mutate("/api/investigations", {
      question: text.trim(),
      request_id: operation.current.id,
      investigation_id: id,
      entity_id: doc.entity_id,
    });
    if (sent) operation.current = undefined;
    return sent;
  }
  async function followup(event: FormEvent) {
    event.preventDefault();
    if (await sendFollowUp(question)) {
      setQuestion("");
      followupInput.current?.focus();
    }
  }
  function followupKeys(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }
  if (!doc)
    return (
      <div className="chat-page">
        <div className="chat-loading">
          {resource.error ? (
            <LoadError error={resource.error} retry={resource.refresh} />
          ) : (
            <Loading />
          )}
        </div>
      </div>
    );

  const running = pending(doc);
  const uniqueSteps = new Map<string, string>();
  for (const event of doc.events) {
    if (event.type !== "trace" && event.message)
      uniqueSteps.set(event.message, event.message);
  }
  const steps = [...uniqueSteps.values()];
  const activity = steps.at(-1);
  function focusEvidence(evidenceId: string) {
    const index = doc!.turns.findIndex(
      (turn) => evidenceId in turn.result.evidence,
    );
    if (index >= 0) setOpenSources(index);
    setFocused(evidenceId);
  }
  const lastTurn = doc.turns.length - 1;
  return (
    <div className="chat-page">
      <h1 className="sr-only">{doc.title}</h1>
      <div className="chat-scroll" ref={thread}>
        <div className="chat-thread">
          {(error || resource.error) && (
            <LoadError
              error={error || resource.error!}
              retry={() => {
                setError(undefined);
                resource.refresh();
              }}
            />
          )}

          {doc.turns.map((turn, index) => (
            <article className="chat-turn" id={`turn-${index}`} key={`${turn.completed_at}-${index}`}>
              <div className="chat-user-turn">
                <p>{turn.question}</p>
              </div>
              <div className="chat-assistant">
                <span className="chat-avatar" aria-hidden>
                  <Waypoints />
                </span>
                <div className="chat-assistant-body">
                  <div className="chat-agent-head">
                    <span className="chat-agent-name">Research</span>
                    <span className="chat-agent-context">
                      ·{" "}
                      {doc.entity_id ? (
                        <Link
                          href={`/entities/${encodeURIComponent(doc.entity_id)}`}
                        >
                          entity scope
                        </Link>
                      ) : (
                        "cross-source"
                      )}
                    </span>
                    <VerificationPill verification={turn.result.verification} />
                  </div>
                  {index === lastTurn && steps.length > 0 && (
                    <details className="chat-activity">
                      <summary>
                        <ChevronRight aria-hidden />
                        Activity
                        <span>
                          · {steps.length} step{steps.length === 1 ? "" : "s"}
                        </span>
                      </summary>
                      <ol>
                        {steps.map((step, stepIndex) => (
                          <li key={`${stepIndex}-${step}`}>{step}</li>
                        ))}
                      </ol>
                    </details>
                  )}
                  <Markdown
                    content={turn.result.answer}
                    citations={turn.result.citations}
                    evidence={turn.result.evidence}
                    onCitationClick={focusEvidence}
                    onFollowUp={(text) => void sendFollowUp(text)}
                  />
                  <VerificationBadge verification={turn.result.verification} />
                  <AuditTrail answer={turn.result} />
                  <div className="chat-sources">
                    <button
                      type="button"
                      className="chat-sources-toggle"
                      aria-expanded={openSources === index}
                      onClick={() =>
                        setOpenSources((value) => (value === index ? null : index))
                      }
                    >
                      <FileText aria-hidden />
                      Sources &amp; addressed facts
                      <span>
                        · {Object.keys(turn.result.evidence).length}
                      </span>
                      <ChevronDown
                        aria-hidden
                        className={openSources === index ? "is-open" : undefined}
                      />
                    </button>
                    {openSources === index && (
                      <div className="chat-sources-body">
                        <EvidenceList
                          evidence={turn.result.evidence}
                          facts={turn.result.facts}
                          derivations={turn.result.derivations}
                          focusedEvidenceId={focused}
                          contexts={[turn.result]}
                        />
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </article>
          ))}

          {doc.status !== "succeeded" && (
            <article className="chat-turn">
              <div className="chat-user-turn">
                <p>{doc.question}</p>
              </div>
              <div className="chat-assistant">
                <span className="chat-avatar" aria-hidden>
                  <Waypoints />
                </span>
                <div className="chat-assistant-body">
                  <div className="chat-agent-head">
                    <span className="chat-agent-name">Research</span>
                    <span className="chat-agent-context">
                      · {running ? "working" : doc.status}
                    </span>
                  </div>
                  {running ? (
                    <p className="chat-preparing" role="status">
                      <span className="research-pulse" />
                      {activity ||
                        (doc.status === "queued"
                          ? "Queued for research…"
                          : "Preparing answer…")}
                    </p>
                  ) : (
                    <div className="chat-failure">
                      <p role="alert">
                        {doc.status === "canceled"
                          ? "Research stopped. Previous answers are unchanged."
                          : doc.error || "Research could not finish."}
                      </p>
                      <Button
                        disabled={busy}
                        onClick={() =>
                          mutate(`/api/investigations/${id}/retry`)
                        }
                      >
                        <RotateCcw /> Retry question
                      </Button>
                    </div>
                  )}
                </div>
              </div>
            </article>
          )}
        </div>
      </div>

      <div className="chat-dock">
        <div className="chat-dock-inner">
          {doc.status === "succeeded" ? (
            <form className="chat-composer" onSubmit={followup}>
              <textarea
                ref={followupInput}
                id="followup"
                aria-label="Ask a follow-up"
                maxLength={4000}
                rows={1}
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                onKeyDown={followupKeys}
                placeholder="Ask a follow-up…"
                required
              />
              <div className="chat-composer-foot">
                <span className="chat-hint">
                  Enter to send · Shift + Enter for a new line
                </span>
                <button
                  className="chat-send"
                  disabled={busy || !question.trim()}
                  type="submit"
                  aria-label="Send follow-up"
                >
                  <ArrowUp />
                </button>
              </div>
            </form>
          ) : running ? (
            <div className="chat-dock-status" role="status">
              <span className="research-pulse" />
              <span>
                {activity ||
                  (doc.status === "queued"
                    ? "Queued for research…"
                    : "Researching source records…")}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={busy}
                onClick={() => mutate(`/api/investigations/${id}/stop`)}
              >
                <Square /> Stop
              </Button>
            </div>
          ) : (
            <div className="chat-dock-status">
              <span>This run did not finish.</span>
              <Button
                disabled={busy}
                onClick={() => mutate(`/api/investigations/${id}/retry`)}
              >
                <RotateCcw /> Retry
              </Button>
            </div>
          )}
          <p className="chat-footnote">
            Answers use GLEIF and SEC records; every figure is cited. Agents can
            make mistakes — check the sources.
          </p>
        </div>
      </div>

    </div>
  );
}
