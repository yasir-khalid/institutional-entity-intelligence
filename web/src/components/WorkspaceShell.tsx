"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  BookOpen,
  Briefcase,
  Building2,
  ChartCandlestick,
  ChevronRight,
  ClipboardCheck,
  Compass,
  Database,
  HandCoins,
  Search,
  SquarePen,
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
import { OnboardingTour } from "@/components/OnboardingTour";

const navigation = [
  { href: "/", label: "Research", icon: SquarePen, group: "Workspace" },
  { href: "/entities", label: "Entities", icon: Building2, group: "Workspace" },
  { href: "/explore", label: "Explore", icon: Compass, group: "Workspace" },
  { href: "/advisers", label: "Advisers", icon: Briefcase, group: "Markets" },
  { href: "/raises", label: "Private raises", icon: HandCoins, group: "Markets" },
  { href: "/securities", label: "Securities", icon: ChartCandlestick, group: "Markets" },
  { href: "/reviews", label: "Match reviews", icon: ClipboardCheck, group: "Operations" },
  { href: "/coverage", label: "Data coverage", icon: Database, group: "Operations" },
];

const groups = ["Workspace", "Markets", "Operations"] as const;

function currentLabel(pathname: string): string {
  if (pathname.startsWith("/research/")) return "Research note";
  if (pathname.startsWith("/entities/")) return "Entity profile";
  if (pathname.startsWith("/advisers/")) return "Adviser profile";
  if (pathname.startsWith("/raises/")) return "Private raise";
  if (pathname.startsWith("/securities/")) return "Security";
  return (
    navigation.find(
      (item) => item.href !== "/" && pathname.startsWith(item.href),
    )?.label ?? (pathname === "/" ? "Research" : "Workspace")
  );
}

function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { setOpenMobile } = useSidebar();
  const [commandOpen, setCommandOpen] = useState(false);
  const [query, setQuery] = useState("");
  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === "k") {
        event.preventDefault();
        setCommandOpen((value) => !value);
        return;
      }
      const target = event.target as HTMLElement | null;
      const typing =
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.tagName === "SELECT" ||
          target.isContentEditable);
      if (
        !typing &&
        !event.metaKey &&
        !event.ctrlKey &&
        !event.altKey &&
        event.key.toLowerCase() === "n"
      ) {
        event.preventDefault();
        router.push("/");
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [router]);
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
                className="gap-2.5"
              >
                <Link href="/" onClick={() => setOpenMobile(false)}>
                  <span className="sidebar-brand-mark"><Waypoints aria-hidden /></span>
                  <span className="workspace-brand">
                    Institutional
                    <small>Entity Intelligence</small>
                  </span>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
          <Link
            href="/"
            className="sidebar-new-chat group-data-[collapsible=icon]:hidden"
            onClick={() => setOpenMobile(false)}
          >
            <SquarePen aria-hidden />
            New chat
            <kbd>N</kbd>
          </Link>
        </SidebarHeader>
        <SidebarContent role="navigation" aria-label="Workspace">
          {groups.map((group) => (
            <SidebarGroup key={group}>
              <SidebarGroupLabel>{group}</SidebarGroupLabel>
              <SidebarMenu>
                {navigation
                  .filter((item) => item.group === group)
                  .map(({ href, label, icon: Icon }) => (
                    <SidebarMenuItem key={href}>
                      <SidebarMenuButton
                        asChild
                        isActive={
                          href === "/"
                            ? pathname === "/" ||
                              pathname.startsWith("/research/")
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
          ))}
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
          <div className="topbar-breadcrumb">
            <Link href="/" className="topbar-crumb-link">
              Workspace
            </Link>
            <ChevronRight aria-hidden />
            <strong>{currentLabel(pathname)}</strong>
          </div>
          <button
            type="button"
            className="topbar-command"
            aria-label="Search & navigate"
            onClick={() => setCommandOpen(true)}
          >
            <Search aria-hidden />
            <span>Search entities and filings…</span>
            <kbd>⌘ K</kbd>
          </button>
        </header>
        <div id="workspace-main" tabIndex={-1} className="workspace-main">
          {children}
        </div>
      </SidebarInset>
      <CommandDialog
        open={commandOpen}
        onOpenChange={setCommandOpen}
        title="Search and navigate"
        description="Find a page or search institutional entities."
      >
        <CommandInput
          placeholder="Search pages or entities…"
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
              <CommandItem
                value={`explore ${query}`}
                onSelect={() =>
                  go(`/explore?q=${encodeURIComponent(query.trim())}`)
                }
              >
                <Compass />
                Search advisers, raises and securities for “{query.trim()}”
              </CommandItem>
            </CommandGroup>
          )}
        </CommandList>
      </CommandDialog>
      <OnboardingTour />
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
