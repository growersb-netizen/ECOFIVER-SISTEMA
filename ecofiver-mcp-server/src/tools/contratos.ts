import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { crmRequest, handleApiError } from "../services/crmClient.js";
import {
  CrearContratoInputSchema,
  ConsultarContratoInputSchema,
  RegistrarPagoInputSchema,
} from "../schemas/contratos.js";

type CrearContratoInput = z.infer<typeof CrearContratoInputSchema>;
type ConsultarContratoInput = z.infer<typeof ConsultarContratoInputSchema>;
type RegistrarPagoInput = z.infer<typeof RegistrarPagoInputSchema>;

interface CrearContratoResponse {
  numero_solicitud: string;
  venta_financiada_id: number;
  contrato_id?: number;
  pdf_url: string | null;
  estado_inscripcion: string;
  saldo_inscripcion_pendiente: number;
  creado_en: string;
  error_pdf?: string;
}

interface ConsultarContratoResponse {
  numero_solicitud: string;
  contrato_id: number;
  cliente_nombre: string;
  tipo_contrato: string;
  estado: string;
  estado_inscripcion: string;
  saldo_inscripcion_pendiente: number;
  pdf_url: string;
  creado_en: string;
  venta_financiada_id: number | null;
  historial_pagos: Array<{ monto: number; fecha_pago: string; notas: string }>;
}

interface RegistrarPagoResponse {
  ok: boolean;
  numero_solicitud: string;
  monto_registrado: number;
  saldo_inscripcion_pendiente: number;
  estado_inscripcion: string;
  recibo_pdf_url: string | null;
  error_recibo?: string;
}

export function registerContratosTools(server: McpServer): void {
  server.registerTool(
    "ecofiver_crear_contrato",
    {
      title: "Crear contrato EcoFiver",
      description: `Crea una venta financiada nueva, asigna el número de solicitud de forma ATÓMICA (nunca se repite, aunque dos canales llamen al mismo tiempo) y genera el PDF real del contrato.

Esta es la ÚNICA vía correcta para dar de alta un contrato — nunca calcules ni asignes un número de solicitud vos mismo.

Args: ver el schema de entrada (cliente, producto, financiación, entrega opcional, pago_registrado opcional, origen).

Returns (JSON):
{
  "numero_solicitud": string,      // ej. "000-13860162"
  "venta_financiada_id": number,
  "pdf_url": string | null,        // ruta relativa del PDF en el CRM, o null si falló la generación (la venta igual quedó registrada)
  "estado_inscripcion": "pendiente" | "parcial" | "completa",
  "saldo_inscripcion_pendiente": number,
  "creado_en": string (ISO 8601)
}

Errores:
- Si el DNI ya tiene una solicitud activa sin resolver, devuelve el número de solicitud existente en el mensaje de error — no bloquea, reintentá con forzar=true si corresponde crear una nueva de todos modos.
- Si pago_registrado.monto supera financiacion.valor_mercado, error de validación.`,
      inputSchema: CrearContratoInputSchema.shape,
      annotations: {
        readOnlyHint: false,
        destructiveHint: false,
        idempotentHint: false,
        openWorldHint: true,
      },
    },
    async (params: CrearContratoInput) => {
      try {
        const data = await crmRequest<CrearContratoResponse>("/api/contratos", "POST", params);
        return {
          content: [{ type: "text", text: JSON.stringify(data, null, 2) }],
          structuredContent: data as unknown as Record<string, unknown>,
        };
      } catch (error) {
        return { content: [{ type: "text", text: handleApiError(error) }] };
      }
    }
  );

  server.registerTool(
    "ecofiver_consultar_contrato",
    {
      title: "Consultar contrato EcoFiver",
      description: `Devuelve el estado completo de una solicitud existente: cliente, estado de inscripción, saldo pendiente, link al PDF y el historial completo de pagos registrados.

Usalo para responder preguntas tipo "¿cuánto le falta pagar a [cliente]?" o "¿cómo va la solicitud 000-13860162?".

Args:
  - numero_solicitud (string): ej. "000-13860162"

Returns (JSON): cliente_nombre, estado_inscripcion, saldo_inscripcion_pendiente, pdf_url, historial_pagos: [{monto, fecha_pago, notas}].

Errores: 404 si la solicitud no existe.`,
      inputSchema: ConsultarContratoInputSchema.shape,
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: true,
      },
    },
    async (params: ConsultarContratoInput) => {
      try {
        const data = await crmRequest<ConsultarContratoResponse>(
          `/api/contratos/solicitud/${encodeURIComponent(params.numero_solicitud)}`,
          "GET"
        );
        return {
          content: [{ type: "text", text: JSON.stringify(data, null, 2) }],
          structuredContent: data as unknown as Record<string, unknown>,
        };
      } catch (error) {
        return { content: [{ type: "text", text: handleApiError(error) }] };
      }
    }
  );

  server.registerTool(
    "ecofiver_registrar_pago",
    {
      title: "Registrar pago sobre un contrato EcoFiver",
      description: `Registra un pago posterior (a cuenta, saldo final, etc.) sobre una solicitud YA EXISTENTE, recalcula el saldo pendiente y genera el recibo real en PDF automáticamente (verde si cancela la inscripción, ámbar si queda saldo pendiente).

Para el pago INICIAL de un contrato nuevo, no uses esta tool — pasá pago_registrado directamente en ecofiver_crear_contrato.

Args:
  - numero_solicitud (string)
  - monto (number)
  - modalidad: "transferencia" | "efectivo" | "mercadopago"
  - concepto: "seña" | "pago_a_cuenta" | "pago_inicial_completo"
  - comprobante_numero_operacion (string, opcional)

Returns (JSON): monto_registrado, saldo_inscripcion_pendiente, estado_inscripcion, recibo_pdf_url.

Errores: 404 si la solicitud no existe. Si falla la generación del PDF, el pago igual queda registrado (recibo_pdf_url viene null y error_recibo con el detalle).`,
      inputSchema: RegistrarPagoInputSchema.shape,
      annotations: {
        readOnlyHint: false,
        destructiveHint: false,
        idempotentHint: false,
        openWorldHint: true,
      },
    },
    async (params: RegistrarPagoInput) => {
      try {
        const { numero_solicitud, ...pago_registrado } = params;
        const data = await crmRequest<RegistrarPagoResponse>(
          `/api/contratos/${encodeURIComponent(numero_solicitud)}/pagos`,
          "POST",
          { pago_registrado }
        );
        return {
          content: [{ type: "text", text: JSON.stringify(data, null, 2) }],
          structuredContent: data as unknown as Record<string, unknown>,
        };
      } catch (error) {
        return { content: [{ type: "text", text: handleApiError(error) }] };
      }
    }
  );
}
