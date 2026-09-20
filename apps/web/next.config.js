const path = require("path");

// Next.js only auto-loads .env files from this directory (apps/web), not the
// monorepo root where our single shared .env actually lives (same file
// docker-compose points both services at). The line below loads it explicitly.
// On Vercel and in a container build that file is absent by design - values
// arrive as build env vars instead - and dotenv is a no-op when it is missing.
require("dotenv").config({ path: path.resolve(__dirname, "../../.env") });

// Vars must be listed here to be inlined into the client bundle, but listing
// one that is undefined inlines the literal `undefined` and defeats the `??`
// fallbacks at the use sites, so only defined values are passed through.
const publicEnv = {};
for (const key of ["NEXT_PUBLIC_API_URL", "NEXT_PUBLIC_ELEVENLABS_AGENT_ID"]) {
  if (process.env[key]) publicEnv[key] = process.env[key];
}

// When the frontend and API share one origin, NEXT_PUBLIC_API_URL can be left
// unset and the client uses relative paths (lib/constants.ts). On Vercel they
// are NOT on one origin, so an unset value silently produces a dashboard that
// fetches itself and renders nothing. Fail the production build instead -
// previews still build, so UI work is not blocked.
if (process.env.VERCEL && !process.env.NEXT_PUBLIC_API_URL) {
  const message =
    "NEXT_PUBLIC_API_URL is not set. On Vercel the API is on a different " +
    "origin, so it must point at the deployed API (e.g. the Koyeb URL). " +
    "Set it in Project Settings -> Environment Variables and redeploy.";
  if (process.env.VERCEL_ENV === "production") throw new Error(message);
  console.warn(`\n[next.config] WARNING: ${message}\n`);
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Emits .next/standalone with a self-contained server.js, so a container
  // image ships the traced dependencies instead of all of node_modules.
  // Vercel builds its own output format and does not want this.
  output: process.env.VERCEL ? undefined : "standalone",
  env: publicEnv,
};

module.exports = nextConfig;
