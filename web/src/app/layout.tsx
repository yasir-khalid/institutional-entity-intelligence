import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

/* Geist and Geist Mono, the pairing supermemory.ai is built on and the one this
 * UI is styled after. The mono is not just for identifiers: section labels,
 * buttons and span kinds are set in it too, uppercase and slightly tracked -
 * that contrast against the sans is most of the look. Identifiers stay mono
 * with tabular figures so a column of LEIs stays scannable. Both are variable
 * fonts, so no weight list is needed. */
const sans = Geist({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-sans",
});

const mono = Geist_Mono({
  subsets: ["latin"],
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
