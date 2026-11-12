# syntax=docker/dockerfile:1
#
# StoryForge web UI (Next.js standalone server on :3000). The build context is
# frontend/ (see compose.yaml); frontend/.dockerignore keeps the host's
# node_modules and .next out of it.

# ---- deps ------------------------------------------------------------------
FROM node:25-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# ---- build -----------------------------------------------------------------
FROM node:25-slim AS build
WORKDIR /app
# next.config.ts reads API_ORIGIN at build time and bakes it into the
# /api and /media rewrites; "api" is the compose service name.
ARG API_ORIGIN=http://api:7860
ENV API_ORIGIN=${API_ORIGIN} \
    NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# ---- runtime ---------------------------------------------------------------
FROM node:25-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
COPY --from=build --chown=node:node /app/public ./public
USER node
EXPOSE 3000
CMD ["node", "server.js"]
