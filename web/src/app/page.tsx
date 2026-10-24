"use client";

import { useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowUp, MessageSquare, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Field, FieldLabel, FieldDescription } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Loading, LoadError, NoData } from "@/components/WorkspaceStates";
import { useResource } from "@/hooks/use-resource";
import { useDeveloperView } from "@/hooks/use-developer-view";
import {
  workspaceMutation,
  type Investigation,
  type InvestigationSummary,
} from "@/lib/api";

export default function ResearchHome() {
  const router = useRouter();
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [offset, setOffset] = useState(0);
  const [trace, setTrace] = useDeveloperView();
  const operation = useRef<
    { question: string; id: string; trace: boolean } | undefined
  >(undefined);
  const saved = useResource<{
    items: InvestigationSummary[];
    next_offset: number | null;
  }>(`/api/investigations?limit=50&offset=${offset}`);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!question.trim() || busy) return;
    setBusy(true);
    setError(undefined);
    if (
      operation.current?.question !== question.trim() ||
      operation.current.trace !== trace
    )
      operation.current = {
        question: question.trim(),
        id: crypto.randomUUID(),
        trace,
      };
    try {
      const doc = await workspaceMutation<Investigation>(
        "/api/investigations",
        { question: question.trim(), request_id: operation.current.id, trace },
      );
      router.push(`/research/${doc.id}`);
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Could not start research.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="workspace-page research-home">
      <div className="workspace-heading">
        <p>Institutional intelligence</p>
        <h1>What do you want to investigate?</h1>
        <span>
          Resolve identities, trace relationships, and inspect reported
          activity—with evidence attached.
        </span>
      </div>
      <form onSubmit={submit} className="research-launcher">
        <Field>
          <FieldLabel htmlFor="question">Research question</FieldLabel>
          <div className="flex gap-2">
            <Input
              id="question"
              maxLength={4000}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="What was Point72’s latest reported holding in Apple?"
              required
            />
            <Button
              disabled={busy || !question.trim()}
              type="submit"
              aria-label="Start investigation"
            >
              <ArrowUp />
            </Button>
          </div>
          <FieldDescription>
            Saved on the server. You can leave this page and return while
            research continues.
          </FieldDescription>
        </Field>
      </form>
      <label className="workspace-note flex items-center gap-2">
        <input
          type="checkbox"
          checked={trace}
          onChange={(event) => setTrace(event.target.checked)}
        />{" "}
        Collect developer trace for this question
      </label>
      {error && <LoadError error={error} retry={() => setError(undefined)} />}
      <div className="research-suggestions">
        {[
          "Who ultimately manages Albacore Partners I Master Fund?",
          "What is Fred Alger Management’s registration status?",
          "What was Point72’s latest reported holding in Apple?",
        ].map((text) => (
          <Button
            key={text}
            variant="outline"
            onClick={() => setQuestion(text)}
          >
            {text}
          </Button>
        ))}
      </div>
      <Link className="workspace-text-link" href="/entities">
        <Search size={15} /> Just looking for an entity? Search the registers
      </Link>
      <section className="workspace-section">
        <div className="workspace-section-heading">
          <h2>
            <MessageSquare size={16} /> Saved investigations
          </h2>
          <span>Shared workspace · newest first</span>
        </div>
        {saved.error ? (
          <LoadError error={saved.error} retry={saved.refresh} />
        ) : !saved.data ? (
          <Loading />
        ) : saved.data.items.length === 0 ? (
          <NoData
            title="A place for your research"
            description="Your first investigation will appear here with its answer, citations, and progress preserved."
          />
        ) : (
          <ul className="investigation-list">
            {saved.data.items.map((item) => (
              <li key={item.id}>
                <Link href={`/research/${item.id}`}>
                  <span>
                    {item.title}
                    <small>
                      {new Date(item.updated_at).toLocaleDateString()}
                    </small>
                  </span>
                  <Badge
                    variant={
                      item.status === "failed" ? "destructive" : "secondary"
                    }
                  >
                    {item.status === "succeeded" ? "Complete" : item.status}
                  </Badge>
                </Link>
              </li>
            ))}
          </ul>
        )}
        <nav
          className="workspace-actions"
          aria-label="Investigation pagination"
        >
          {offset > 0 && (
            <Button
              variant="outline"
              onClick={() => setOffset((value) => Math.max(0, value - 50))}
            >
              Newer
            </Button>
          )}
          {saved.data?.next_offset !== undefined &&
            saved.data.next_offset !== null &&
            saved.data.next_offset <= 9000 && (
              <Button
                variant="outline"
                onClick={() => setOffset(saved.data!.next_offset!)}
              >
                Older
              </Button>
            )}
        </nav>
      </section>
    </div>
  );
}
