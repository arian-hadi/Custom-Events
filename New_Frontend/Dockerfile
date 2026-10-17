FROM node:22-bookworm-slim AS dependencies
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-bookworm-slim AS development
WORKDIR /app
ENV NODE_ENV=development NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
COPY --from=dependencies --chown=node:node /app/node_modules ./node_modules
COPY --chown=node:node . .
# Keep the launcher outside the source bind mount. Named volumes inherit these
# directories and ownership; Windows node_modules/.next never enter the container.
COPY scripts/docker-dev.mjs /usr/local/lib/platform-frontend-dev.mjs
RUN mkdir -p /app/.next && chown node:node /app /app/.next
USER node
RUN node /usr/local/lib/platform-frontend-dev.mjs --record-installed
EXPOSE 3000
CMD ["node", "/usr/local/lib/platform-frontend-dev.mjs"]

FROM node:22-bookworm-slim AS builder
WORKDIR /app
ARG BACKEND_INTERNAL_URL=http://backend:8000
ENV BACKEND_INTERNAL_URL=$BACKEND_INTERNAL_URL
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=dependencies /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-bookworm-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static
COPY --from=builder --chown=node:node /app/public ./public
USER node
EXPOSE 3000
CMD ["node", "server.js"]
