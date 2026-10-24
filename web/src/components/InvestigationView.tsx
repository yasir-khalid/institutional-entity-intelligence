"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { ArrowUp, FileText, SquareTerminal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { LoadError, Loading } from "@/components/WorkspaceStates";
import Markdown from "@/components/Markdown";
import EvidenceList from "@/components/EvidenceLayer";
import VerificationBadge from "@/components/VerificationBadge";
import AuditTrail from "@/components/AuditTrail";
import { useResource } from "@/hooks/use-resource";
import { useDeveloperView } from "@/hooks/use-developer-view";
import { workspaceMutation, type Investigation } from "@/lib/api";

const DeveloperPanel = dynamic(() => import("@/components/DeveloperPanel"));
const pending = (doc: Investigation) =>
  doc.status === "queued" || doc.status === "running";

export default function InvestigationView({ id }: { id: string }) {
  const resource = useResource<Investigation>(
    `/api/investigations/${encodeURIComponent(id)}`,
    pending,
  );
  const doc = resource.data;
  const [question, setQuestion] = useState("");
  const [title, setTitle] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [developer, setDeveloper] = useDeveloperView();
  const [focused, setFocused] = useState<string | null>(null);
  const [sourceTurn, setSourceTurn] = useState<number | null>(null);
  useEffect(() => {
    if (focused)
      document
        .getElementById(`evidence-${focused}`)
        ?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [focused, sourceTurn]);
  const operation = useRef<
    { question: string; id: string; trace: boolean } | undefined
  >(undefined);
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
  async function followup(event: FormEvent) {
    event.preventDefault();
    if (!doc || busy || !question.trim()) return;
    if (
      operation.current?.question !== question.trim() ||
      operation.current.trace !== developer
    )
      operation.current = {
        question: question.trim(),
        id: crypto.randomUUID(),
        trace: developer,
      };
    if (
      await mutate("/api/investigations", {
        question: question.trim(),
        request_id: operation.current.id,
        investigation_id: id,
        entity_id: doc.entity_id,
        trace: developer,
      })
    ) {
      setQuestion("");
      operation.current = undefined;
    }
  }
  if (!doc)
    return (
      <div className="workspace-page">
        {resource.error ? (
          <LoadError error={resource.error} retry={resource.refresh} />
        ) : (
          <Loading />
        )}
      </div>
    );
  const running = pending(doc);
  const answers = doc.turns.map((turn) => turn.result);
  // Fact IDs are stable across identical lookups, but their evidence receipts
  // belong to a run. Never merge maps from separate answers and overwrite that
  // ownership. The rail selects an answer; a citation selects its owning run.
  const selectedTurn = Math.min(
    sourceTurn ?? answers.length - 1,
    answers.length - 1,
  );
  const sourceAnswer = answers[selectedTurn];
  const activity = doc.events
    .filter((event) => event.type !== "trace")
    .at(-1)?.message;
  function focusEvidence(evidenceId: string) {
    const index = answers.findIndex((answer) => evidenceId in answer.evidence);
    if (index >= 0) setSourceTurn(index);
    setFocused(evidenceId);
    document
      .getElementById(`evidence-${evidenceId}`)
      ?.scrollIntoView({ behavior: "smooth", block: "center" });
  }
  return (
    <div className="workspace-page investigation-page">
      <div className="workspace-heading compact">
        <div className="workspace-actions">
          <Badge
            variant={doc.status === "failed" ? "destructive" : "secondary"}
          >
            {doc.status === "succeeded" ? "Complete" : doc.status}
          </Badge>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setDeveloper(!developer)}
          >
            <SquareTerminal /> Developer
          </Button>
        </div>
        {developer && !doc.trace && (
          <p className="workspace-note">
            No developer trace was collected for this question. With Developer
            enabled, the next follow-up will collect a trace.
          </p>
        )}
        {title !== undefined ? (
          <form
            className="flex gap-2"
            onSubmit={async (event) => {
              event.preventDefault();
              if (await mutate(`/api/investigations/${id}`, { title }, "PATCH"))
                setTitle(undefined);
            }}
          >
            <Input
              aria-label="Investigation title"
              maxLength={120}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              required
            />
            <Button disabled={busy || !title.trim()}>Save</Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => setTitle(undefined)}
            >
              Cancel
            </Button>
          </form>
        ) : (
          <>
            <h1>{doc.title}</h1>
            <Button
              variant="link"
              size="sm"
              onClick={() => setTitle(doc.title)}
            >
              Rename investigation
            </Button>
          </>
        )}
        <span>
          {doc.entity_id ? (
            <Link href={`/entities/${encodeURIComponent(doc.entity_id)}`}>
              Entity context: {doc.entity_id}
            </Link>
          ) : (
            "Cross-source research"
          )}{" "}
          · Saved automatically · shared workspace
        </span>
      </div>
      {(error || resource.error) && (
        <LoadError
          error={error || resource.error!}
          retry={() => {
            setError(undefined);
            resource.refresh();
          }}
        />
      )}
      <div className="investigation-columns">
        <section className="conversation" aria-label="Research conversation">
          {doc.turns.map((turn, index) => (
            <article key={`${turn.completed_at}-${index}`}>
              <div className="question-turn">
                <span>You</span>
                <p>{turn.question}</p>
              </div>
              <div className="answer-turn">
                <div>
                  <span className="answer-label">Research answer</span>
                  <Markdown
                    content={turn.result.answer}
                    citations={turn.result.citations}
                    evidence={turn.result.evidence}
                    onCitationClick={focusEvidence}
                  />
                  <VerificationBadge verification={turn.result.verification} />
                  <AuditTrail answer={turn.result} />
                </div>
              </div>
            </article>
          ))}
          {doc.status !== "succeeded" && (
            <article>
              <div className="question-turn">
                <span>You</span>
                <p>{doc.question}</p>
              </div>
              {running ? (
                <div role="status" className="research-progress">
                  <span className="research-pulse" />
                  {activity ||
                    (doc.status === "queued"
                      ? "Queued for research…"
                      : "Researching source records…")}
                  <p>
                    You can close this tab. This run is saved on the server.
                  </p>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={busy}
                    onClick={() => mutate(`/api/investigations/${id}/stop`)}
                  >
                    Stop research
                  </Button>
                </div>
              ) : (
                <div className="research-progress">
                  <p role="alert">
                    {doc.status === "canceled"
                      ? "Research stopped. Previous answers are unchanged."
                      : doc.error || "Research could not finish."}
                  </p>
                  <Button
                    disabled={busy}
                    onClick={() => mutate(`/api/investigations/${id}/retry`)}
                  >
                    Retry question
                  </Button>
                </div>
              )}
            </article>
          )}
          {doc.status === "succeeded" && (
            <form onSubmit={followup}>
              <Field>
                <FieldLabel htmlFor="followup">Ask a follow-up</FieldLabel>
                <div className="flex gap-2">
                  <Input
                    id="followup"
                    maxLength={4000}
                    value={question}
                    onChange={(event) => setQuestion(event.target.value)}
                    required
                    placeholder="Continue this investigation…"
                  />
                  <Button
                    type="submit"
                    disabled={busy || !question.trim()}
                    aria-label="Send follow-up"
                  >
                    <ArrowUp />
                  </Button>
                </div>
              </Field>
            </form>
          )}
        </section>
        <aside className="investigation-evidence" aria-label="Source evidence">
          <h2>
            <FileText size={16} /> Sources & addressed facts
          </h2>
          {answers.length > 1 && (
            <label className="workspace-note">
              Sources for answer
              <Select
                value={String(selectedTurn)}
                onValueChange={(value) => {
                  setSourceTurn(Number(value));
                  setFocused(null);
                }}
              >
                <SelectTrigger className="mt-1 w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {doc.turns.map((turn, index) => (
                    <SelectItem key={index} value={String(index)}>
                      {index + 1}. {turn.question}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </label>
          )}
          <EvidenceList
            evidence={sourceAnswer?.evidence ?? {}}
            facts={sourceAnswer?.facts ?? {}}
            derivations={sourceAnswer?.derivations ?? {}}
            focusedEvidenceId={focused}
            contexts={sourceAnswer ? [sourceAnswer] : []}
          />
        </aside>
      </div>
      {developer && (
        <DeveloperPanel
          open={developer}
          onClose={() => setDeveloper(false)}
          spans={doc.events.flatMap((event) =>
            event.span ? [event.span] : [],
          )}
          running={running}
          question={doc.question}
          activity={activity ?? null}
          error={doc.error}
          onStartAgent={null}
        />
      )}
    </div>
  );
}
