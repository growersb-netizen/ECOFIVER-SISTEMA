/*
 * Oficina virtual EcoFiver AI Company — lógica pura (sin DOM ni WebGL).
 *
 * Traduce el estado REAL del backend (/api/agentes/control, /api/aprobaciones,
 * /api/admision/resumen) a lo que se dibuja. Regla: nada se muestra como
 * "trabajando" sin una tarea en ejecución registrada por el motor; si no hay
 * conexión, todo queda en "sin datos" (no se muestra un estado viejo como actual).
 */

export const NOMBRES = {
  maximo: "Máximo", aurora: "Aurora", tomas: "Tomás", valentina: "Valentina", camila: "Camila",
  nicolas: "Nicolás", luciano: "Luciano", mateo: "Mateo", renata: "Renata", bruno: "Bruno",
  ezequiel: "Ezequiel", elena: "Elena", ignacio: "Ignacio", sebastian: "Sebastián",
  daniela: "Daniela", franco: "Franco",
};

export const ROLES = {
  maximo: "CEO · Dirección", aurora: "Gerente comercial", tomas: "Supervisor de ventas",
  valentina: "Primer contacto", camila: "Piscinas contado", nicolas: "Financiación piscinas",
  luciano: "Módulos contado", mateo: "Financiación módulos", renata: "Marketing y web",
  bruno: "Operaciones y logística", ezequiel: "Administración", elena: "Finanzas",
  ignacio: "Cobranza", sebastian: "Postventa", daniela: "RRPP y crisis", franco: "Socios comerciales",
};

// Salas (x, z = centro; w, d = tamaño) y puestos (posición del escritorio, orientación).
export const SALAS = {
  direccion:      {titulo: "Dirección · Oficina ejecutiva", x: -13, z: -8, w: 10, d: 8, color: 0x6b4f3a},
  comercial:      {titulo: "Comercial", x: 1, z: -6, w: 16, d: 12, color: 0x2d6a4f},
  marketing:      {titulo: "Marketing", x: 14, z: -9, w: 8, d: 6, color: 0x7b2cbf},
  reputacion:     {titulo: "Reputación", x: 14, z: -3, w: 8, d: 6, color: 0xb5179e},
  administracion: {titulo: "Administración", x: -13, z: 5, w: 10, d: 10, color: 0x1d4e89},
  admision:       {titulo: "Admisión · personas", x: -1, z: 7, w: 8, d: 6, color: 0x8d6e63, humana: true},
  postventa:      {titulo: "Postventa", x: 6.5, z: 7, w: 5, d: 6, color: 0x00838f},
  socios:         {titulo: "Socios", x: 11.5, z: 7, w: 5, d: 6, color: 0xc77d00},
  operaciones:    {titulo: "Operaciones", x: 16.5, z: 7, w: 5, d: 6, color: 0x5d4037},
};

export const PUESTOS = {
  maximo:    {sala: "direccion", x: -13, z: -9, ejecutivo: true},
  aurora:    {sala: "comercial", x: 1, z: -10.5},
  tomas:     {sala: "comercial", x: -4.5, z: -7},
  valentina: {sala: "comercial", x: 0, z: -7},
  camila:    {sala: "comercial", x: 4.5, z: -7},
  nicolas:   {sala: "comercial", x: -4.5, z: -2.5},
  luciano:   {sala: "comercial", x: 0, z: -2.5},
  mateo:     {sala: "comercial", x: 4.5, z: -2.5},
  renata:    {sala: "marketing", x: 14, z: -9.5},
  daniela:   {sala: "reputacion", x: 14, z: -3.5},
  ezequiel:  {sala: "administracion", x: -13, z: 2.5},
  elena:     {sala: "administracion", x: -15.5, z: 6.5},
  ignacio:   {sala: "administracion", x: -10.5, z: 6.5},
  sebastian: {sala: "postventa", x: 6.5, z: 6.5},
  franco:    {sala: "socios", x: 11.5, z: 6.5},
  bruno:     {sala: "operaciones", x: 16.5, z: 6.5},
};

export const COLORES = {
  trabajando: 0x22c55e, aprobacion: 0x3b82f6, en_cola: 0xeab308, disponible: 0x94a3b8,
  pausado: 0xf59e0b, desactivado: 0xef4444, sin_datos: 0x4b5563,
};

/**
 * @param {object|null} a  fila de /api/agentes/control (o null si no vino)
 * @param {number} aprobaciones  aprobaciones PENDIENTES de ese agente
 * @param {boolean} conectado  la última lectura del backend fue exitosa
 */
export function estadoVisual(a, aprobaciones = 0, conectado = true) {
  if (!conectado || !a) {
    return {modo: "sin_datos", etiqueta: "Sin datos", icono: "…", sentado: false, visible: true, alerta: false};
  }
  const act = a.actividad || {};
  const alerta = (act.fallidas_hoy || 0) > 0;
  if (a.estado === "DESACTIVADO") {
    return {modo: "desactivado", etiqueta: "Desactivado", icono: "⛔", sentado: false, visible: false, alerta};
  }
  if (a.estado === "PAUSADO") {
    return {modo: "pausado", etiqueta: "Pausado", icono: "⏸", sentado: false, visible: true, alerta};
  }
  if (act.tarea_en_curso) {
    return {modo: "trabajando", etiqueta: `Trabajando en #${act.tarea_en_curso.id}`, icono: "⚙", sentado: true,
            visible: true, alerta, tarea: act.tarea_en_curso};
  }
  if (aprobaciones > 0) {
    return {modo: "aprobacion", etiqueta: `${aprobaciones} esperando tu aprobación`, icono: "✋", sentado: true,
            visible: true, alerta};
  }
  if ((act.pendientes || 0) > 0) {
    return {modo: "en_cola", etiqueta: `${act.pendientes} en cola`, icono: "⏳", sentado: true, visible: true, alerta};
  }
  return {modo: "disponible", etiqueta: "Disponible", icono: "", sentado: true, visible: true, alerta};
}

export function aprobacionesPorAgente(lista) {
  const out = {};
  for (const x of lista || []) {
    if (x.estado === "PENDIENTE") out[x.agente] = (out[x.agente] || 0) + 1;
  }
  return out;
}

// Expedientes que esperan una decisión de las personas de Admisión
const EN_CURSO_ADMISION = ["EN_ADMISION", "DOCUMENTACION_PENDIENTE"];

export function resumenAdmision(porEstado) {
  if (!porEstado) return null;
  let enCurso = 0, total = 0;
  for (const [estado, n] of Object.entries(porEstado)) {
    total += n;
    if (EN_CURSO_ADMISION.includes(estado)) enCurso += n;
  }
  return {enCurso, total, aprobados: porEstado.APROBADO_POR_ADMISION || 0, cerrados: porEstado.CIERRE_HUMANO_CONFIRMADO || 0};
}

/** Agentes que se dibujan: solo los que manda el backend y tienen puesto (Valentín nunca). */
export function agentesDibujables(tablero) {
  return (tablero?.agentes || []).filter(a => PUESTOS[a.agente]);
}
