import type { Metadata } from "next";
import { IBM_Plex_Sans, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";

/* One superfamily rather than two unrelated Google fonts. IBM Plex Sans and
 * IBM Plex Mono were drawn together, share skeletons and vertical metrics, and
 * were designed for exactly this context - dense technical and financial
 * interfaces - so an identifier set in the mono sits on the same baseline and
 * reads at the same weight as the label beside it. Identifiers are codes, not
 * prose: monospace with tabular figures keeps a column of LEIs scannable. */
const sans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
  variable: "--font-sans",
});

const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  display: "swap",
  variable: "--font-mono",
});

export const metadata: Metadata = {
  title: "Institutional Entity Intelligence",
  description: "Resolve institutional entities across GLEIF and SEC filings.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable} h-full antialiased`}>
      <body className="h-full font-sans">{children}</body>
    </html>
  );
}
