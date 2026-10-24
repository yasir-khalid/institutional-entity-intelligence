"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { DecisionCard } from "@/components/EntityProfile";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { LoadError, Loading, NoData } from "@/components/WorkspaceStates";
import { useResource } from "@/hooks/use-resource";
import type { MatchDecision } from "@/lib/api";

export default function ReviewQueue() {
  const params = useSearchParams();
  const router = useRouter();
  const decision = ["REVIEW", "AUTO_MATCH", "UNMATCHED"].includes(
    params.get("decision") || "",
  )
    ? params.get("decision")!
    : "REVIEW";
  const offset = Math.min(9000, Math.max(0, Number(params.get("offset")) || 0));
  const queue = useResource<{
    items: MatchDecision[];
    next_offset: number | null;
  }>(`/api/reviews?decision=${decision}&offset=${offset}&limit=25`);
  const url = (next: number) => `/reviews?decision=${decision}&offset=${next}`;
  return (
    <div className="workspace-page">
      <div className="workspace-heading compact">
        <p>Resolution evidence</p>
        <h1>Match reviews</h1>
        <span>
          Machine decisions stay immutable. Your dated review is separate
          evidence used by the next graph build.
        </span>
      </div>
      <Tabs
        value={decision}
        onValueChange={(value) => router.push(`/reviews?decision=${value}`)}
      >
        <TabsList>
          <TabsTrigger value="REVIEW">Needs review</TabsTrigger>
          <TabsTrigger value="AUTO_MATCH">Auto matched</TabsTrigger>
          <TabsTrigger value="UNMATCHED">Unmatched</TabsTrigger>
        </TabsList>
        <TabsContent value={decision}>
          <p className="workspace-note">
            SEC 13F crosswalk ·{" "}
            {decision === "REVIEW"
              ? "Includes previously reviewed decisions; the review history appears on each record."
              : "Published machine decisions, with any human reviews attached."}
          </p>
          {queue.error ? (
            <LoadError error={queue.error} retry={queue.refresh} />
          ) : !queue.data ? (
            <Loading />
          ) : queue.data.items.length === 0 ? (
            <NoData
              title="No decisions in this view"
              description="The queue comes from the published crosswalk. Run make publish after building or updating source links."
            />
          ) : (
            <div className="review-queue">
              {queue.data.items.map((item) => (
                <section key={`${item.node_id}-${item.lei}`}>
                  <div className="workspace-section-heading">
                    <h2>{item.source_name || item.node_id}</h2>
                    {item.lei ? (
                      <Link
                        className="workspace-text-link"
                        href={`/entities/${item.lei}?tab=resolution`}
                      >
                        Inspect proposed entity →
                      </Link>
                    ) : (
                      <Link
                        className="workspace-text-link"
                        href={`/entities?q=${encodeURIComponent(item.source_name || item.node_id)}`}
                      >
                        Find candidates →
                      </Link>
                    )}
                  </div>
                  <DecisionCard
                    key={item.node_id + item.reviews.length}
                    decision={item}
                    onOpenEntity={(id) =>
                      router.push(`/entities/${id}?tab=resolution`)
                    }
                  />
                </section>
              ))}
            </div>
          )}
          <nav
            className="workspace-actions"
            aria-label="Review queue pagination"
          >
            {offset > 0 && (
              <Button asChild variant="outline">
                <Link href={url(Math.max(0, offset - 25))}>Previous</Link>
              </Button>
            )}
            {queue.data?.next_offset !== null &&
              queue.data?.next_offset !== undefined &&
              queue.data.next_offset <= 9000 && (
                <Button asChild variant="outline">
                  <Link href={url(queue.data.next_offset)}>Next</Link>
                </Button>
              )}
          </nav>
        </TabsContent>
      </Tabs>
    </div>
  );
}
