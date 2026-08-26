/**
 * FITNESS BUSINESS OS — API Entry Point
 * Fastify + TypeScript — Puerto 3001
 */

import { buildApp } from "./app.js";

const PORT = parseInt(process.env["PORT"] ?? "3001", 10);
const HOST = process.env["HOST"] ?? "0.0.0.0";

async function main() {
  const app = await buildApp();

  try {
    await app.listen({ port: PORT, host: HOST });
    app.log.info(`🚀 Fitness OS API running on http://localhost:${PORT}`);
  } catch (err) {
    app.log.error(err);
    process.exit(1);
  }
}

main();
