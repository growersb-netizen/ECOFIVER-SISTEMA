FROM node:22-alpine
RUN npm install -g pnpm@9
RUN apk add --no-cache openssl python3 make g++

WORKDIR /app

COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY packages/database/package.json ./packages/database/
COPY packages/shared/package.json    ./packages/shared/
COPY workers/ai-worker/package.json ./workers/ai-worker/

RUN pnpm install --frozen-lockfile

COPY packages/ ./packages/
COPY workers/ai-worker/src/        ./workers/ai-worker/src/
COPY workers/ai-worker/tsconfig.json ./workers/ai-worker/
COPY tsconfig.json ./

RUN pnpm --filter @fitness-os/database exec prisma generate
RUN pnpm --filter @fitness-os/shared build
RUN pnpm --filter @fitness-os/database build
RUN pnpm --filter @fitness-os/ai-worker build

ENV NODE_ENV=production
CMD ["node", "workers/ai-worker/dist/index.js"]
