"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  BookOpen,
  Building2,
  ClipboardCheck,
  Database,
  MessageSquare,
  Search,
  Waypoints,
} from "lucide-react";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarRail,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar";
import {
  CommandDialog,
  CommandInput,
  CommandList,
  CommandGroup,
  CommandItem,
  CommandEmpty,
} from "@/components/ui/command";
import { Button } from "@/components/ui/button";
import { useResource } from "@/hooks/use-resource";
import type { InvestigationSummary } from "@/lib/api";

const navigation = [
  { href: "/", label: "Research", icon: MessageSquare },
  { href: "/entities", label: "Entities", icon: Building2 },
  { href: "/reviews", label: "Match reviews", icon: ClipboardCheck },
  { href: "/coverage", label: "Data coverage", icon: Database },
];

function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { setOpenMobile } = useSidebar();
  const [commandOpen, setCommandOpen] = useState(false);
  const [query, setQuery] = useState("");
  const saved = useResource<{ items: InvestigationSummary[] }>(
    "/api/investigations?limit=20",
  );
  const { refresh } = saved;
  useEffect(() => {
    const update = () => refresh();
    const key = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === "k") {
        event.preventDefault();
        setCommandOpen((value) => !value);
      }
    };
    window.addEventListener("workspace-updated", update);
    window.addEventListener("keydown", key);
    return () => {
      window.removeEventListener("workspace-updated", update);
      window.removeEventListener("keydown", key);
    };
  }, [refresh]);
  function go(href: string) {
    setCommandOpen(false);
    setOpenMobile(false);
    router.push(href);
  }
  return (
    <>
      <a href="#workspace-main" className="skip-link">
        Skip to content
      </a>
      <Sidebar collapsible="icon">
        <SidebarHeader>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton
                asChild
                size="lg"
                tooltip="Institutional Entity Intelligence"
              >
                <Link href="/" onClick={() => setOpenMobile(false)}>
                  <span className="query-logo">
                    <Waypoints />
                  </span>
                  <span className="workspace-brand">
                    Institutional
                    <br />
                    <small>Entity Intelligence</small>
                  </span>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarHeader>
        <SidebarContent>
          <SidebarGroup>
            <SidebarGroupLabel>Workspace</SidebarGroupLabel>
            <SidebarMenu>
              {navigation.map(({ href, label, icon: Icon }) => (
                <SidebarMenuItem key={href}>
                  <SidebarMenuButton
                    asChild
                    isActive={
                      href === "/"
                        ? pathname === "/" || pathname.startsWith("/research/")
                        : pathname.startsWith(href)
                    }
                    tooltip={label}
                  >
                    <Link href={href} onClick={() => setOpenMobile(false)}>
                      <Icon />
                      <span>{label}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroup>
          <SidebarGroup className="group-data-[collapsible=icon]:hidden">
            <SidebarGroupLabel>Saved investigations</SidebarGroupLabel>
            <SidebarMenu>
              {saved.data?.items.map((item) => (
                <SidebarMenuItem key={item.id}>
                  <SidebarMenuButton
                    asChild
                    isActive={pathname === `/research/${item.id}`}
                  >
                    <Link
                      href={`/research/${item.id}`}
                      onClick={() => setOpenMobile(false)}
                      title={item.title}
                    >
                      <MessageSquare />
                      <span>{item.title}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
              {!saved.data?.items.length && (
                <li className="px-2 text-xs text-muted-foreground">
                  {saved.error
                    ? "Saved research unavailable."
                    : "Your research will appear here."}
                </li>
              )}
            </SidebarMenu>
          </SidebarGroup>
        </SidebarContent>
        <SidebarFooter>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton asChild tooltip="How it works">
                <Link href="/how-it-works">
                  <BookOpen />
                  <span>How it works</span>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarFooter>
        <SidebarRail />
      </Sidebar>
      <SidebarInset className="min-w-0">
        <header className="workspace-topbar">
          <SidebarTrigger />
          <span>
            {navigation.find(
              (item) => item.href !== "/" && pathname.startsWith(item.href),
            )?.label ?? "Research workspace"}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setCommandOpen(true)}
          >
            <Search /> Search & navigate <kbd>⌘ K</kbd>
          </Button>
        </header>
        <div id="workspace-main" tabIndex={-1} className="workspace-main">
          {children}
        </div>
      </SidebarInset>
      <CommandDialog
        open={commandOpen}
        onOpenChange={setCommandOpen}
        title="Search and navigate"
        description="Find a page, saved investigation, or search institutional entities."
      >
        <CommandInput
          placeholder="Search pages, investigations, or entities…"
          value={query}
          onValueChange={setQuery}
        />
        <CommandList>
          <CommandEmpty>No matches. Try an entity name.</CommandEmpty>
          <CommandGroup heading="Workspace">
            {navigation.map(({ href, label, icon: Icon }) => (
              <CommandItem key={href} onSelect={() => go(href)}>
                <Icon />
                {label}
              </CommandItem>
            ))}
          </CommandGroup>
          {query.trim() && (
            <CommandGroup heading="Entity search">
              <CommandItem
                value={query}
                onSelect={() =>
                  go(`/entities?q=${encodeURIComponent(query.trim())}`)
                }
              >
                <Search />
                Search entities for “{query.trim()}”
              </CommandItem>
            </CommandGroup>
          )}
          <CommandGroup heading="Saved investigations">
            {saved.data?.items.map((item) => (
              <CommandItem
                key={item.id}
                value={item.title + item.id}
                onSelect={() => go(`/research/${item.id}`)}
              >
                <MessageSquare />
                {item.title}
              </CommandItem>
            ))}
          </CommandGroup>
        </CommandList>
      </CommandDialog>
    </>
  );
}

export default function WorkspaceShell({
  children,
  defaultOpen,
}: {
  children: ReactNode;
  defaultOpen: boolean;
}) {
  const pathname = usePathname();
  if (pathname.startsWith("/how-it-works") || pathname.startsWith("/blog"))
    return children;
  return (
    <SidebarProvider defaultOpen={defaultOpen}>
      <Shell>{children}</Shell>
    </SidebarProvider>
  );
}
