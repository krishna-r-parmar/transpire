import path from "node:path";
import type { NextConfig } from "next";

// One .env at the repository root serves backend and frontend, locally and on the
// server. Values already in the environment (e.g. Docker build args) take precedence.
// The Docker build context has no root .env, so a missing file is expected there.
try {
  process.loadEnvFile(path.resolve(__dirname, "..", ".env"));
} catch (error) {
  if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
}

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
};

export default nextConfig;
