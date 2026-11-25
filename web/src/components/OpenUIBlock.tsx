"use client";

/* Renders an ```openui-lang block from a research answer as live UI (OpenUI Lang, openui.com),
 * drawn with the app's shadcn components (src/lib/openui/library.tsx).
 *
 * The server's submission gate has already replaced every fact placeholder with its checked value,
 * so the block holds no number the model typed. The library is a curated subset with no images,
 * links or forms, no tool provider is passed, and the only action honoured is a follow-up question. */

import { useCallback, useState } from "react";
import { BuiltinActionType, Renderer, type ActionEvent, type OpenUIError } from "@openuidev/react-lang";
import { answerLibrary } from "@/lib/openui/library";

export default function OpenUIBlock({ code, onFollowUp }: { code: string; onFollowUp?: (question: string) => void }) {
  const [errors, setErrors] = useState<OpenUIError[]>([]);
  const onAction = useCallback(
    (event: ActionEvent) => {
      if (event.type !== BuiltinActionType.ContinueConversation) return;
      const text = (event.humanFriendlyMessage ?? "").trim().slice(0, 500);
      if (text) onFollowUp?.(text);
    },
    [onFollowUp],
  );
  return (
    <div className="my-4 grid gap-1" data-testid="openui-block">
      <Renderer response={code} library={answerLibrary} isStreaming={false} onAction={onAction} onError={setErrors} />
      {errors.length > 0 && <p className="text-xs text-muted-foreground">Part of this visualization couldn&apos;t be drawn.</p>}
    </div>
  );
}
