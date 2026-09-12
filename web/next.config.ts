import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  // Without this, Turbopack walks up looking for a lockfile and finds an
  // unrelated one at /Users/yasir/package-lock.json (outside this git repo),
  // which can silently misresolve modules/workspace root - pin it to this
  // project explicitly.
  turbopack: {
    root: path.join(__dirname),
  },
};

export default nextConfig;
