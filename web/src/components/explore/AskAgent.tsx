"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { MessageSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { workspaceMutation, type Investigation } from "@/lib/api";

/** Starts a saved investigation with a prepared question and opens it. */
export default function AskAgent({ question, entityId, label = "Ask the research agent" }: {
  question: string; entityId?: string | null; label?: string;
}) {
  const router = useRouter();
  const request = useRef(crypto.randomUUID());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  async function start() {
    setBusy(true);
    setError(undefined);
    try {
      const doc = await workspaceMutation<Investigation>("/api/investigations", {
        question, request_id: request.current, entity_id: entityId ?? null,
      });
      router.push(`/research/${doc.id}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not start research.");
      setBusy(false);
    }
  }
  return (
    <span className="inline-flex flex-col gap-1">
      <Button variant="outline" size="sm" disabled={busy} onClick={start} title={question}>
        <MessageSquare /> {label}
      </Button>
      {error && <small className="text-xs text-destructive">{error}</small>}
    </span>
  );
}
