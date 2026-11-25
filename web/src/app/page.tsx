"use client";

import { useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { useRouter } from "next/navigation";
import { ArrowUp, ArrowUpRight, ShieldCheck } from "lucide-react";
import { LoadError } from "@/components/WorkspaceStates";
import {
  workspaceMutation,
  type Investigation,
} from "@/lib/api";

const EXAMPLES = [
  "Who are the largest 13F holders of NVDA and how did their positions change last quarter?",
  "What was Point72’s latest reported holding in Apple?",
  "Which venture capital funds raised the most in the last 7 days of Form D filings?",
  "Who ultimately manages Albacore Partners I Master Fund?",
];

export default function ResearchHome() {
  const router = useRouter();
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const input = useRef<HTMLTextAreaElement>(null);
  const operation = useRef<{ question: string; id: string } | undefined>(
    undefined,
  );

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!question.trim() || busy) return;
    setBusy(true);
    setError(undefined);
    if (operation.current?.question !== question.trim())
      operation.current = {
        question: question.trim(),
        id: crypto.randomUUID(),
      };
    try {
      const doc = await workspaceMutation<Investigation>(
        "/api/investigations",
        { question: question.trim(), request_id: operation.current.id },
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

  function suggest(text: string) {
    setQuestion(text);
    input.current?.focus();
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  return (
    <div className="chat-home">
      <div className="chat-home-inner">
        <h1 className="chat-home-title">What do you want to investigate?</h1>

        <form className="chat-composer chat-composer-home" onSubmit={submit}>
          <textarea
            ref={input}
            id="question"
            aria-label="Research question"
            maxLength={4000}
            rows={2}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Ask a question about an institution…"
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
              aria-label="Start investigation"
            >
              <ArrowUp />
            </button>
          </div>
        </form>

        {error && (
          <div className="chat-home-error">
            <LoadError error={error} retry={() => setError(undefined)} />
          </div>
        )}

        <div className="chat-suggestions" aria-label="Sample questions">
          <p className="chat-suggestions-label">Sample questions</p>
          <div className="chat-suggestion-grid">
            {EXAMPLES.map((question) => (
              <button
                key={question}
                type="button"
                className="chat-question"
                title={question}
                onClick={() => suggest(question)}
              >
                <span>{question}</span>
                <ArrowUpRight aria-hidden />
              </button>
            ))}
          </div>
        </div>

        <p className="chat-footnote">
          <ShieldCheck aria-hidden />
          Answers use GLEIF and SEC records; every figure is cited. Agents can
          make mistakes — check the sources.
        </p>
      </div>
    </div>
  );
}
