import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Self-contained server bundle for the Docker image.
  output: "standalone",
  // The app is a standalone pnpm project (no workspace), so the tracing root
  // is this directory. Pinned so Next never infers a parent from a stray
  // lockfile higher up the repo.
  outputFileTracingRoot: __dirname,
  poweredByHeader: false,
};

export default nextConfig;
