import type { Metadata } from "next";
import { Geist_Mono, Inter } from "next/font/google";
import "./globals.css";
import { cookies } from "next/headers";
import WorkspaceShell from "@/components/WorkspaceShell";

/* Matter is Warp's licensed geometric face; Inter is the guide's declared free
 * substitute. Headlines and UI share one family, with weight, size and very
 * tight display tracking doing the hierarchy. Geist Mono is reserved for
 * identifiers, payloads and terminal micro-copy. */
const sans = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-body",
});

const mono = Geist_Mono({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-code",
});

export const metadata: Metadata = {
  title: "Institutional Entity Intelligence",
  description: "Resolve institutional entities across GLEIF and SEC filings.",
};

export default async function RootLayout({ children }: LayoutProps<"/">) {
  const defaultOpen = (await cookies()).get("sidebar_state")?.value !== "false";
  return (
    <html
      lang="en"
      className={`${sans.variable} ${mono.variable} h-full antialiased`}
    >
      <body className="h-full font-sans">
        <WorkspaceShell defaultOpen={defaultOpen}>{children}</WorkspaceShell>
      </body>
    </html>
  );
}
