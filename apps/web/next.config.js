const path = require("path");
require("dotenv").config({ path: path.resolve(__dirname, "../../.env") });

// Next.js only auto-loads .env files from this directory (apps/web), not the
// monorepo root where our single shared .env actually lives (same file
// docker-compose points both services at). The line above loads it
// explicitly. Vars must be listed here to be inlined into the client bundle.
/** @type {import('next').NextConfig} */
const nextConfig = {
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
    NEXT_PUBLIC_ELEVENLABS_AGENT_ID: process.env.NEXT_PUBLIC_ELEVENLABS_AGENT_ID,
  },
};

module.exports = nextConfig;
