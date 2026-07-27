# ecofiver-contratos-mcp-server

Servidor MCP (Model Context Protocol) que expone la emisión de contratos del CRM de EcoFiver como tools, para usar desde Claude.ai (como conector) o cualquier otro cliente MCP.

## Tools

- `ecofiver_crear_contrato` — crea una venta financiada, asigna el número de solicitud de forma atómica y genera el PDF real del contrato.
- `ecofiver_consultar_contrato` — estado completo de una solicitud existente (saldo, PDF, historial de pagos).
- `ecofiver_registrar_pago` — registra un pago posterior sobre una solicitud y genera el recibo real en PDF.

Todas las tools llaman al endpoint unificado `POST /api/contratos` del CRM (`eco-crm`) — es la única fuente de verdad, para que ningún canal (Claude.ai, el sistema de agentes, un frontend futuro) pueda pisarse el número de solicitud con otro.

## Variables de entorno

- `CRM_BASE_URL` — URL del CRM (default: `https://eco-crm-production.up.railway.app`)
- `CRM_API_KEY` — API key del CRM (mismo valor que `API_KEY` en el servicio `eco-crm`)
- `PORT` — puerto HTTP (Railway lo inyecta automáticamente)

## Desarrollo local

```bash
npm install
npm run build
CRM_API_KEY=... npm start
```

El servidor queda escuchando en `POST /mcp` (Streamable HTTP, stateless) y `GET /health`.
