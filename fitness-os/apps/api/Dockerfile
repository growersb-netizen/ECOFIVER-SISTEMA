FROM node:22-alpine AS base
RUN npm install -g pnpm@9

# ── Builder ────────────────────────────────────────────────────────────────────
FROM base AS builder
WORKDIR /app

# Install dependencies
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY packages/database/package.json ./packages/database/
COPY packages/shared/package.json    ./packages/shared/
COPY apps/api/package.json           ./apps/api/

RUN pnpm install --frozen-lockfile

# Copy source
COPY packages/ ./packages/
COPY apps/api/ ./apps/api/
COPY tsconfig.json ./

# Generate Prisma client
RUN pnpm --filter @fitness-os/database exec prisma generate

# Build API
RUN pnpm --filter @fitness-os/api build

# ── Runner ─────────────────────────────────────────────────────────────────────
FROM node:22-alpine AS runner
RUN npm install -g pnpm@9
WORKDIR /app

# Copy built output and runtime deps
COPY --from=builder /app/package.json ./
COPY --from=builder /app/pnpm-workspace.yaml ./
COPY --from=builder /app/pnpm-lock.yaml ./
COPY --from=builder /app/packages/database/package.json ./packages/database/
COPY --from=builder /app/packages/shared/package.json ./packages/shared/
COPY --from=builder /app/apps/api/package.json ./apps/api/

# Install production deps only (includes native binaries for linux/alpine)
RUN pnpm install --frozen-lockfile --prod

# Copy Prisma schema & migrations for migrate deploy
COPY --from=builder /app/packages/database/prisma ./packages/database/prisma

# Copy generated Prisma client
COPY --from=builder /app/packages/database/node_modules/.prisma ./packages/database/node_modules/.prisma
COPY --from=builder /app/packages/database/node_modules/@prisma ./packages/database/node_modules/@prisma

# Copy compiled API
COPY --from=builder /app/apps/api/dist ./apps/api/dist

ENV NODE_ENV=production
ENV PORT=3001
EXPOSE 3001

CMD ["sh", "-c", "pnpm --filter @fitness-os/database exec prisma migrate deploy && node apps/api/dist/index.js"]
