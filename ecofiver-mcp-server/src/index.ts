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
import type { Request, Response, NextFunction } from "express";
import { timingSafeEqual } from "node:crypto";
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

/**
 * Autenticación del endpoint MCP.
 * Con MCP_AUTH_TOKEN configurado se exige el token, por header
 * (Authorization: Bearer <token>) o en la ruta (/mcp/<token>, para conectores
 * que no permiten headers, como Claude.ai). Sin MCP_AUTH_TOKEN el servidor
 * mantiene el comportamiento anterior (abierto) y lo advierte en el log:
 * así el deploy no corta el conector existente hasta que se configure el token.
 */
const MCP_AUTH_TOKEN = (process.env.MCP_AUTH_TOKEN || "").trim();

function tokenOk(candidate: string | undefined): boolean {
  if (!MCP_AUTH_TOKEN || !candidate) return false;
  const a = Buffer.from(candidate.trim());
  const b = Buffer.from(MCP_AUTH_TOKEN);
  return a.length === b.length && timingSafeEqual(a, b);
}

export function requireMcpAuth(req: Request, res: Response, next: NextFunction): void {
  if (!MCP_AUTH_TOKEN) return next();
  const auth = req.headers.authorization || "";
  const bearer = auth.startsWith("Bearer ") ? auth.slice(7) : undefined;
  const pathToken = typeof req.params.token === "string" ? req.params.token : undefined;
  if (tokenOk(bearer) || tokenOk(pathToken)) return next();
  res.status(401).json({ jsonrpc: "2.0", error: { code: -32001, message: "No autorizado" }, id: null });
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

  if (!MCP_AUTH_TOKEN) {
    console.error("ADVERTENCIA: MCP_AUTH_TOKEN no configurado — POST /mcp está abierto (crea contratos y registra pagos). Configurarlo.");
  }

  const handleMcp = async (req: Request, res: Response) => {
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
  };

  app.post("/mcp", requireMcpAuth, handleMcp);
  app.post("/mcp/:token", requireMcpAuth, handleMcp);

  const port = parseInt(process.env.PORT || "3000", 10);
  app.listen(port, () => {
    console.error(`ecofiver-contratos-mcp-server escuchando en el puerto ${port} (POST /mcp)`);
  });
}

runHTTP().catch((error) => {
  console.error("Server error:", error);
  process.exit(1);
});
