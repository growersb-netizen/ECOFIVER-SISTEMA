import { z } from "zod";

export const ClienteSchema = z.object({
  nombre: z.string().min(1).describe("Nombre del cliente"),
  apellido: z.string().min(1).describe("Apellido del cliente"),
  dni: z.string().min(1).describe("DNI, solo dígitos"),
  cuil: z.string().optional().describe("CUIL, formato NN-XXXXXXXX-N"),
  fecha_nacimiento: z.string().optional().describe("Fecha de nacimiento, YYYY-MM-DD"),
  lugar_nacimiento: z.string().optional(),
  estado_civil: z.string().optional(),
  ocupacion: z.string().optional(),
  email: z.string().optional(),
  telefono: z.string().optional(),
  telefono_alt: z.string().optional(),
  domicilio: z.string().optional(),
  piso: z.string().optional(),
  depto: z.string().optional(),
  localidad: z.string().optional(),
  provincia: z.string().optional(),
});

export const ConyugeSchema = z.object({
  nombre: z.string().optional(),
  apellido: z.string().optional(),
  dni: z.string().optional(),
  fecha_nacimiento: z.string().optional(),
  telefono: z.string().optional(),
  email: z.string().optional(),
  ocupacion: z.string().optional(),
});

export const ProductoSchema = z.object({
  tipo: z.enum(["pileta", "modulo", "combo", "exterior"]).describe("Tipo de producto"),
  modelo: z.string().min(1).describe("Nombre del modelo, ej. 'Arco Romano Mediano C/Desnivel'"),
  medida_especial: z.boolean().optional().default(false),
  largo_m: z.number().optional().describe("Requerido si tipo=pileta o combo"),
  ancho_m: z.number().optional().describe("Requerido si tipo=pileta o combo"),
  profundidad_min_m: z.number().optional(),
  profundidad_max_m: z.number().optional(),
  sistema: z.string().optional().default("C-6"),
  superficie_m2: z.number().optional().describe("Requerido si tipo=modulo"),
  incluye: z.string().optional().describe("Extras: gazebo, luces, losetas, etc."),
  color: z.string().optional(),
});

export const FinanciacionSchema = z.object({
  valor_mercado: z.number().positive().describe("Precio de lista/contado del producto"),
  pago_inicial: z.number().nonnegative().describe("Monto objetivo de la entrada/inscripción"),
  cant_cuotas: z.number().int().positive(),
  valor_cuota: z.number().positive(),
  indexacion: z.enum(["fija", "ICC"]).optional().default("fija"),
});

export const EntregaSchema = z.object({
  mes: z.string().optional().describe("Ej: 'Noviembre'"),
  anio: z.number().int().optional(),
  observacion_libre: z
    .string()
    .optional()
    .describe(
      "Si no hay mes definido, usar: 'La fecha de instalación se asignará conforme al plan de producción vigente'"
    ),
});

export const PagoRegistradoSchema = z.object({
  monto: z.number().nonnegative().optional().describe("Si viene, se registra como cobranza inicial"),
  modalidad: z.enum(["transferencia", "efectivo", "mercadopago"]).optional(),
  concepto: z.enum(["seña", "pago_a_cuenta", "pago_inicial_completo"]).optional(),
  comprobante_numero_operacion: z.string().optional(),
  comprobante_cbu_destino: z.string().optional(),
  fecha_hora: z.string().optional().describe("ISO 8601, default now()"),
});

export const OrigenSchema = z.object({
  canal: z.enum(["claude_chat", "whatsapp_maximo", "frontend"]),
  operador: z.string().optional().describe("Quién cargó el dato, ej. 'Tefi', 'Rodo'"),
});

export const CrearContratoInputSchema = z.object({
  cliente: ClienteSchema,
  conyuge: ConyugeSchema.optional(),
  producto: ProductoSchema,
  financiacion: FinanciacionSchema,
  entrega: EntregaSchema.optional(),
  pago_registrado: PagoRegistradoSchema.optional(),
  origen: OrigenSchema,
  forzar: z
    .boolean()
    .optional()
    .default(false)
    .describe("Si true, crea la venta igual aunque el DNI ya tenga una solicitud activa"),
});

export const ConsultarContratoInputSchema = z.object({
  numero_solicitud: z.string().min(1).describe("Ej: '000-13860162'"),
});

export const RegistrarPagoInputSchema = z.object({
  numero_solicitud: z.string().min(1).describe("Ej: '000-13860162'"),
  monto: z.number().positive(),
  modalidad: z.enum(["transferencia", "efectivo", "mercadopago"]),
  concepto: z.enum(["seña", "pago_a_cuenta", "pago_inicial_completo"]),
  comprobante_numero_operacion: z.string().optional(),
});
