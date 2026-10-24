"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Link as LinkIcon, MessageSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { useResource } from "@/hooks/use-resource";
import {
  workspaceMutation,
  type EntityDetail,
  type TreeNode,
  type Investigation,
} from "@/lib/api";
import EntityProfile from "@/components/EntityProfile";
import EntityTreeView from "@/components/EntityTreeView";
import { LoadError, Loading } from "@/components/WorkspaceStates";

const tabs = ["overview", "relationships", "holdings", "resolution"] as const;
export default function EntityPage({ id }: { id: string }) {
  const router = useRouter();
  const params = useSearchParams();
  const tab = tabs.find((value) => value === params.get("tab")) ?? "overview";
  const detail = useResource<EntityDetail>(
    `/api/entity/${encodeURIComponent(id)}`,
  );
  const tree = useResource<TreeNode>(
    tab === "relationships"
      ? `/api/entity/${encodeURIComponent(id)}/tree?depth=2`
      : null,
  );
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const open = (entityId: string) =>
    router.push(`/entities/${encodeURIComponent(entityId)}?tab=${tab}`);
  async function investigate() {
    setBusy(true);
    try {
      const doc = await workspaceMutation<Investigation>(
        "/api/investigations",
        {
          question: `Summarize the identity, sourced relationships, and available latest reported activity of ${detail.data?.canonical_name || id}.`,
          entity_id: id,
          request_id: crypto.randomUUID(),
        },
      );
      router.push(`/research/${doc.id}`);
    } catch (error) {
      setNotice(
        error instanceof Error ? error.message : "Unable to start research.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="workspace-page entity-page">
      <Link className="workspace-text-link" href="/entities">
        ← Entity search
      </Link>
      <div className="workspace-heading compact">
        <p>Entity dossier</p>
        <h1>{detail.data?.canonical_name || "Entity profile"}</h1>
        <span className="break-all">{id}</span>
      </div>
      <div className="workspace-actions">
        <Button
          size="sm"
          variant="outline"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(window.location.href);
              setNotice("Link copied.");
            } catch {
              setNotice(
                "Copy the address from your browser to share this view.",
              );
            }
          }}
        >
          <LinkIcon />
          Copy view link
        </Button>
        <Button size="sm" disabled={busy || !detail.data} onClick={investigate}>
          <MessageSquare />
          Investigate this entity
        </Button>
      </div>
      <p role="status" className="workspace-note">
        {notice}
      </p>
      {detail.error ? (
        <LoadError error={detail.error} retry={detail.refresh} />
      ) : !detail.data ? (
        <Loading />
      ) : (
        <Tabs
          value={tab}
          onValueChange={(value) => {
            const next = new URLSearchParams(params);
            next.set("tab", value);
            router.push(`/entities/${encodeURIComponent(id)}?${next}`, {
              scroll: false,
            });
          }}
        >
          <TabsList className="entity-tabs">
            {tabs.map((value) => (
              <TabsTrigger key={value} value={value}>
                {value === "holdings"
                  ? "Reported activity"
                  : value.charAt(0).toUpperCase() + value.slice(1)}
              </TabsTrigger>
            ))}
          </TabsList>
          {tabs.map((value) => (
            <TabsContent key={value} value={value}>
              <EntityProfile
                detail={detail.data!}
                loading={false}
                view={value}
                onOpenEntity={open}
              />
              {value === "relationships" && (
                <section className="workspace-section">
                  <h2>GLEIF accounting hierarchy</h2>
                  <p className="workspace-note">
                    Depth two · accounting consolidation, not regulatory control
                    or beneficial ownership.
                  </p>
                  {tree.error ? (
                    <LoadError error={tree.error} retry={tree.refresh} />
                  ) : tree.data ? (
                    <EntityTreeView
                      data={tree.data}
                      selectedEntityId={id}
                      onSelect={open}
                    />
                  ) : (
                    <Loading />
                  )}
                </section>
              )}
            </TabsContent>
          ))}
        </Tabs>
      )}
    </div>
  );
}
