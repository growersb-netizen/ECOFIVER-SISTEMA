FROM node:22-alpine
RUN npm install -g pnpm@9
# openssl needed for Prisma on alpine
RUN apk add --no-cache openssl python3 make g++

WORKDIR /app

# Install dependencies first (layer cache)
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY packages/database/package.json ./packages/database/
COPY packages/shared/package.json    ./packages/shared/
COPY apps/api/package.json           ./apps/api/

RUN pnpm install --frozen-lockfile

# Copy source files
COPY packages/ ./packages/
COPY apps/api/src/        ./apps/api/src/
COPY apps/api/tsconfig.json ./apps/api/
COPY tsconfig.json ./

# Generate Prisma client for alpine/linux
RUN pnpm --filter @fitness-os/database exec prisma generate

# Build packages in dependency order (API imports both at runtime)
RUN pnpm --filter @fitness-os/shared build
RUN pnpm --filter @fitness-os/database build

# Build TypeScript API
RUN pnpm --filter @fitness-os/api build

ENV NODE_ENV=production
ENV PORT=3001
EXPOSE 3001

CMD ["sh", "-c", "pnpm --filter @fitness-os/database exec prisma migrate resolve --rolled-back 20260825144522_initial 2>/dev/null || true; pnpm --filter @fitness-os/database exec prisma migrate deploy && pnpm --filter @fitness-os/database run seed && pnpm --filter @fitness-os/database run catalog:seed && node apps/api/dist/index.js"]
