import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

// Loaded as an actual "Inter" @font-face (not just a CSS variable) so the
// canvas-rendered tree (src/components/EntityTree.tsx, which can't use
// Tailwind/CSS classes) can reference the exact same family by name.
const inter = Inter({
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Institutional Entity Intelligence",
  description: "Search entities, explore relationship trees, and view SEC 13F activity.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${inter.className} h-full antialiased`}>
      <body className="h-full">{children}</body>
    </html>
  );
}
