"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent, type ReactNode } from "react";
import { ArrowRight, Briefcase, ChartCandlestick, HandCoins, Search } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { LoadError, Loading, NoData } from "@/components/WorkspaceStates";
import { PageHeader } from "@/components/PageHeader";
import { useResource } from "@/hooks/use-resource";
import type { ExploreResults } from "@/lib/api";
import { count, day, usd } from "@/lib/format";

function Group({ title, icon, more, empty, children }: { title: string; icon: ReactNode; more: string; empty: boolean; children: ReactNode }) {
  return (
    <Card className="min-w-0 gap-3 py-4 shadow-none">
      <CardHeader className="px-4">
        <CardTitle className="flex items-center gap-2 text-sm font-medium">{icon}{title}</CardTitle>
        <CardAction><Button variant="ghost" size="sm" asChild><Link href={more}>See all <ArrowRight /></Link></Button></CardAction>
      </CardHeader>
      <CardContent className="px-2">
        {empty ? <p className="px-2 py-3 text-sm text-muted-foreground">No matches.</p> : <ul className="grid min-w-0">{children}</ul>}
      </CardContent>
    </Card>
  );
}

function Row({ href, title, detail, badge }: { href: string; title: string; detail: string; badge?: ReactNode }) {
  return (
    <li className="min-w-0">
      <Link href={href} className="flex min-w-0 items-start gap-3 rounded-md px-2 py-2 hover:bg-muted" title={title}>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium">{title}</span>
          <span className="block truncate text-xs text-muted-foreground">{detail}</span>
        </span>
        {badge}
      </Link>
    </li>
  );
}

export default function ExploreSearch({
  searchParams,
}: {
  searchParams: Record<string, string>;
}) {
  const router = useRouter();
  const q = searchParams.q ?? "";
  const [query, setQuery] = useState(q);
  const resource = useResource<ExploreResults>(q.trim().length >= 2 ? `/api/explore?q=${encodeURIComponent(q)}` : null);
  function submit(event: FormEvent) {
    event.preventDefault();
    if (query.trim()) router.push(`/explore?q=${encodeURIComponent(query.trim())}`);
  }
  const data = resource.data;
  const empty = data && !data.advisers.length && !data.offerings.length && !data.securities.length;
  return (
    <div className="workspace-page wide">
      <PageHeader
        eyebrow="The index"
        title="Explore the registers"
        description="One query across Form ADV advisers, Form D offerings and 13F-reported securities. Names, tickers and CUSIPs all work."
      />
      <form className="flex max-w-2xl gap-2" onSubmit={submit}>
        <Input aria-label="Name, ticker or CUSIP" autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="e.g. Blackstone, NVDA" />
        <Button type="submit"><Search /> Search</Button>
      </form>
      <div className="mt-6">
        {!q ? (
          <div className="mt-8 grid gap-4 lg:grid-cols-3">
            {[
              { href: "/advisers", title: "Investment advisers", note: "Form ADV registrations, regulatory AUM and private funds.", icon: <Briefcase className="size-4" /> },
              { href: "/raises", title: "Private raises", note: "Form D notices for funds and operating companies.", icon: <HandCoins className="size-4" /> },
              { href: "/securities", title: "Securities", note: "13F ownership, short sale volume and fails to deliver.", icon: <ChartCandlestick className="size-4" /> },
            ].map((item) => (
              <Link key={item.href} href={item.href} className="surface group flex flex-col gap-3 p-5 transition hover:border-[var(--line-strong)]">
                <span className="grid size-8 place-items-center rounded-md bg-[var(--fill)] text-[var(--accent)]">{item.icon}</span>
                <span className="font-serif text-xl leading-none">{item.title}</span>
                <span className="text-sm leading-relaxed text-muted-foreground">{item.note}</span>
                <span className="mt-auto inline-flex items-center gap-1 pt-2 text-xs font-medium text-primary">Open the ledger <ArrowRight className="size-3.5" /></span>
              </Link>
            ))}
          </div>
        ) : resource.error ? (
          <LoadError error={resource.error} retry={resource.refresh} />
        ) : !data ? (
          <Loading />
        ) : empty ? (
          <NoData title={`Nothing found for “${q}”`} description="Names match whole words. Entity names (GLEIF) are searched on the Entities page." />
        ) : (
          <div className="grid gap-4 lg:grid-cols-3">
            <Group title="Advisers" icon={<Briefcase className="size-4 text-muted-foreground" />} more={`/advisers?q=${encodeURIComponent(q)}`} empty={!data.advisers.length}>
              {data.advisers.map((firm) => (
                <Row key={firm.crd_number} href={`/advisers/${firm.crd_number}`} title={firm.business_name}
                  detail={[firm.city, firm.state].filter(Boolean).join(", ")} badge={<Badge variant="accent">{usd(firm.raum)}</Badge>} />
              ))}
            </Group>
            <Group title="Private raises" icon={<HandCoins className="size-4 text-muted-foreground" />} more={`/raises?q=${encodeURIComponent(q)}&days=`} empty={!data.offerings.length}>
              {data.offerings.map((item) => (
                <Row key={item.accession_number} href={`/raises/${item.accession_number}`} title={item.issuer_name}
                  detail={`${day(item.filing_date)} · ${item.fund_type ?? item.industry_group ?? ""}`} badge={<Badge variant="positive">{usd(item.total_sold)}</Badge>} />
              ))}
            </Group>
            <Group title="Securities" icon={<ChartCandlestick className="size-4 text-muted-foreground" />} more={`/securities?q=${encodeURIComponent(q)}`} empty={!data.securities.length}>
              {data.securities.map((item) => (
                <Row key={item.cusip} href={`/securities/${item.cusip}`} title={item.issuer_name ?? item.cusip}
                  detail={`${item.tickers.join(", ") || item.cusip} · ${count(item.holder_count)} holders`} />
              ))}
            </Group>
          </div>
        )}
      </div>
    </div>
  );
}
