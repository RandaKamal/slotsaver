const path = require("path");

// Next.js only auto-loads .env files from this directory (apps/web), not the
// monorepo root where our single shared .env actually lives (same file
// docker-compose points both services at). The line below loads it explicitly.
// On Vercel and in a container build that file is absent by design - values
// arrive as build env vars instead - and dotenv is a no-op when it is missing.
require("dotenv").config({ path: path.resolve(__dirname, "../../.env") });

// Where the deployed API actually lives. The browser never sees this value:
// requests go to /api on the frontend's own origin and Next proxies them
// server side (see rewrites below).
const API_ORIGIN =
  process.env.API_PROXY_TARGET || "https://slotsaver-api.onrender.com";

// Vars must be listed here to be inlined into the client bundle, but listing
// one that is undefined inlines the literal `undefined` and defeats the `??`
// fallbacks at the use sites, so only defined values are passed through.
const publicEnv = {};
for (const key of ["NEXT_PUBLIC_API_URL", "NEXT_PUBLIC_ELEVENLABS_AGENT_ID"]) {
  if (process.env[key]) publicEnv[key] = process.env[key];
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Emits .next/standalone with a self-contained server.js, so a container
  // image ships the traced dependencies instead of all of node_modules.
  // Vercel builds its own output format and does not want this.
  output: process.env.VERCEL ? undefined : "standalone",
  env: publicEnv,

  // Same-origin proxy to the API.
  //
  // The frontend and the API are deployed to different hosts, so the browser
  // would normally send cross-origin requests and the API would have to return
  // the right CORS headers. That puts a load-bearing setting in a dashboard,
  // invisible in this repo, and it fails silently when wrong: the dashboard
  // renders and then fetches nothing, which is exactly what happened.
  //
  // Proxying removes the problem instead of configuring around it. The browser
  // only ever talks to this origin, so there is no preflight and no CORS header
  // to get wrong, and the API URL stops being baked into the client bundle at
  // build time, which also means it can change without a rebuild.
  //
  // NEXT_PUBLIC_API_URL should now be UNSET in production: lib/constants.ts
  // then falls back to relative paths, which this proxy resolves.
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` },
      { source: "/health", destination: `${API_ORIGIN}/health` },
    ];
  },
};

module.exports = nextConfig;
