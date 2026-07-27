FROM node:20-slim

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install --omit=dev

COPY tsconfig.json ./
COPY src ./src
RUN npm install typescript && npm run build && npm prune --omit=dev

EXPOSE 3000

CMD ["node", "dist/index.js"]
