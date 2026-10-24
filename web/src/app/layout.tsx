import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { cookies } from "next/headers";
import WorkspaceShell from "@/components/WorkspaceShell";

/* Inter Variable, the typeface Linear is built on. There is deliberately no
 * monospace face anywhere in the UI: identifiers, payloads and timings use
 * Inter's tabular figures so a column of LEIs or durations still aligns. The
 * single-story "a" (cv01) and the curved-tail "l" (ss03) alternates are the
 * two stylistic sets that give Linear its voice; both are enabled on `body`
 * in globals.css. A variable font, so no weight list is needed. */
const sans = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-sans",
});

export const metadata: Metadata = {
  title: "Institutional Entity Intelligence",
  description: "Resolve institutional entities across GLEIF and SEC filings.",
};

export default async function RootLayout({ children }: LayoutProps<"/">) {
  const defaultOpen = (await cookies()).get("sidebar_state")?.value !== "false";
  return (
    <html lang="en" className={`${sans.variable} h-full antialiased`}>
      <body className="h-full font-sans">
        <WorkspaceShell defaultOpen={defaultOpen}>{children}</WorkspaceShell>
      </body>
    </html>
  );
}
