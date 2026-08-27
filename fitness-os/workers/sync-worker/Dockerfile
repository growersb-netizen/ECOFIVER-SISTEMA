FROM node:22-alpine
RUN npm install -g pnpm@9
RUN apk add --no-cache openssl python3 make g++

WORKDIR /app

COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY packages/database/package.json ./packages/database/
COPY packages/shared/package.json    ./packages/shared/
COPY workers/sync-worker/package.json ./workers/sync-worker/

RUN pnpm install --frozen-lockfile

COPY packages/ ./packages/
COPY workers/sync-worker/src/        ./workers/sync-worker/src/
COPY workers/sync-worker/tsconfig.json ./workers/sync-worker/
COPY tsconfig.json ./

RUN pnpm --filter @fitness-os/database exec prisma generate
RUN pnpm --filter @fitness-os/shared build
RUN pnpm --filter @fitness-os/database build
RUN pnpm --filter @fitness-os/sync-worker build

ENV NODE_ENV=production
CMD ["node", "workers/sync-worker/dist/index.js"]
