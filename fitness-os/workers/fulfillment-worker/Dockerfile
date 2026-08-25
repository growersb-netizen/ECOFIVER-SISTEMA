FROM node:22-alpine
RUN npm install -g pnpm@9
# openssl needed for Prisma on alpine
RUN apk add --no-cache openssl python3 make g++

WORKDIR /app

# Install dependencies first (layer cache)
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY packages/database/package.json ./packages/database/
COPY packages/shared/package.json    ./packages/shared/
COPY workers/fulfillment-worker/package.json ./workers/fulfillment-worker/

RUN pnpm install --frozen-lockfile

# Copy source files
COPY packages/ ./packages/
COPY workers/fulfillment-worker/src/        ./workers/fulfillment-worker/src/
COPY workers/fulfillment-worker/tsconfig.json ./workers/fulfillment-worker/
COPY tsconfig.json ./

# Generate Prisma client for alpine/linux
RUN pnpm --filter @fitness-os/database exec prisma generate

# Build packages in dependency order
RUN pnpm --filter @fitness-os/shared build
RUN pnpm --filter @fitness-os/database build

# Build worker
RUN pnpm --filter @fitness-os/fulfillment-worker build

ENV NODE_ENV=production
CMD ["node", "workers/fulfillment-worker/dist/index.js"]
