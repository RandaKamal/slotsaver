# Build context is apps/web (App Platform: source_dir: apps/web).
# Multi-stage so the runtime image carries the standalone server only, not the
# full node_modules tree.

FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# NEXT_PUBLIC_* values are inlined into the client bundle at BUILD time - they
# cannot be changed by setting a runtime env var later. Both are optional:
# without NEXT_PUBLIC_API_URL the client falls back to same-origin relative
# paths, which is exactly right when web and api share one app's ingress.
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_ELEVENLABS_AGENT_ID
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_ELEVENLABS_AGENT_ID=$NEXT_PUBLIC_ELEVENLABS_AGENT_ID \
    NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
EXPOSE 8080
CMD ["sh", "-c", "HOSTNAME=0.0.0.0 PORT=${PORT:-8080} node server.js"]
