import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

// Inter for UI text, JetBrains Mono for identifiers (LEI/CIK/CUSIP/ISIN).
// Identifiers are codes, not prose - rendering them in a monospace face with
// tabular figures makes them scannable and keeps columns of them aligned.
const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-sans",
});

const mono = JetBrains_Mono({
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
    <html lang="en" className={`${inter.variable} ${mono.variable} h-full antialiased`}>
      <body className="h-full font-sans">{children}</body>
    </html>
  );
}
