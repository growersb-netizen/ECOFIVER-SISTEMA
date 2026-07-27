#!/usr/bin/env node
/**
 * MCP Server para el CRM de EcoFiver — emisión de contratos.
 *
 * Expone 3 tools que envuelven el endpoint unificado de contratos del CRM
 * (POST /api/contratos, GET /api/contratos/solicitud/{numero}, POST
 * /api/contratos/{numero}/pagos), para que cualquier cliente MCP (Claude.ai,
 * el sistema de agentes, un frontend futuro) los use como única fuente de
 * verdad — evita que dos canales asignen el mismo número de solicitud.
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import express from "express";
import { registerContratosTools } from "./tools/contratos.js";
import { CRM_API_KEY } from "./constants.js";

function buildServer(): McpServer {
  const server = new McpServer({
    name: "ecofiver-contratos-mcp-server",
    version: "1.0.0",
  });
  registerContratosTools(server);
  return server;
}

async function runHTTP(): Promise<void> {
  if (!CRM_API_KEY) {
    console.error("ERROR: CRM_API_KEY environment variable is required");
    process.exit(1);
  }

  const app = express();
  app.use(express.json());

  app.get("/health", (_req, res) => {
    res.json({ status: "ok", sistema: "ecofiver-contratos-mcp-server" });
  });

  app.post("/mcp", async (req, res) => {
    // Nueva instancia de server + transport por request (stateless, evita
    // colisiones de ID entre requests concurrentes de distintos clientes)
    const server = buildServer();
    const transport = new StreamableHTTPServerTransport({
      sessionIdGenerator: undefined,
      enableJsonResponse: true,
    });
    res.on("close", () => {
      transport.close();
      server.close();
    });
    await server.connect(transport);
    await transport.handleRequest(req, res, req.body);
  });

  const port = parseInt(process.env.PORT || "3000", 10);
  app.listen(port, () => {
    console.error(`ecofiver-contratos-mcp-server escuchando en el puerto ${port} (POST /mcp)`);
  });
}

runHTTP().catch((error) => {
  console.error("Server error:", error);
  process.exit(1);
});
