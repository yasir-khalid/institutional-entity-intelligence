import type { NextConfig } from "next";
import path from "path";

const devtools = "./src/lib/openui/devtools-disabled.ts";

const nextConfig: NextConfig = {
  // Bottom-left sits on the sidebar's "How it works" link.
  devIndicators: { position: "bottom-right" },
  // Without this, Turbopack walks up looking for a lockfile and finds an
  // unrelated one at /Users/yasir/package-lock.json (outside this git repo),
  // which can silently misresolve modules/workspace root - pin it to this
  // project explicitly.
  turbopack: {
    root: path.join(__dirname),
    // react-lang mounts OpenUI's inspector in development; answers never need it.
    resolveAlias: { "@openuidev/devtools": devtools },
  },
  webpack(config) {
    config.resolve.alias["@openuidev/devtools"] = path.join(__dirname, devtools);
    return config;
  },
};

export default nextConfig;
