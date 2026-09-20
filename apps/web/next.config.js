const path = require("path");

// Next.js only auto-loads .env files from this directory (apps/web), not the
// monorepo root where our single shared .env actually lives (same file
// docker-compose points both services at). The line below loads it explicitly.
// In a container build that file is absent by design - secrets arrive as build
// args instead - and dotenv is a no-op when the path does not exist.
require("dotenv").config({ path: path.resolve(__dirname, "../../.env") });

// Vars must be listed here to be inlined into the client bundle, but listing
// one that is undefined inlines the literal `undefined` and defeats the `??`
// fallbacks at the use sites, so only defined values are passed through.
const publicEnv = {};
for (const key of ["NEXT_PUBLIC_API_URL", "NEXT_PUBLIC_ELEVENLABS_AGENT_ID"]) {
  if (process.env[key]) publicEnv[key] = process.env[key];
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Emits .next/standalone with a self-contained server.js, so the runtime
  // image ships the traced dependencies instead of all of node_modules.
  output: "standalone",
  env: publicEnv,
};

module.exports = nextConfig;
