import type { Metadata } from "next";
import { Geist } from "next/font/google";
import "./globals.css";

/* Geist, and only Geist - there is deliberately no monospace face anywhere in
 * the UI. Identifiers, payloads and timings use Geist's tabular figures so a
 * column of LEIs or durations still aligns. A variable font, so no weight list
 * is needed. */
const sans = Geist({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-sans",
});

export const metadata: Metadata = {
  title: "Institutional Entity Intelligence",
  description: "Resolve institutional entities across GLEIF and SEC filings.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${sans.variable} h-full antialiased`}>
      <body className="h-full font-sans">{children}</body>
    </html>
  );
}
