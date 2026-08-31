/**
 * Generador de PDFs para Fitness Business OS.
 * Genera guías profesionales en PDF para cada uno de los 205 productos.
 * Usa pdfkit — sin dependencias de headless browser ni binarios nativos.
 */

import PDFDocument from "pdfkit";

// ─── Paleta ────────────────────────────────────────────────────────────────
const C = {
  bg:      "#0A0C18",   // fondo oscuro
  card:    "#0E1120",
  border:  "#1A1F35",
  neon:    "#00FF87",   // verde neon
  cyan:    "#00F5FF",
  purple:  "#7C4DFF",
  pink:    "#FF2D9C",
  yellow:  "#FFE234",
  white:   "#FFFFFF",
  silver:  "#C0C8E0",
  muted:   "#6B7494",
  dark:    "#06080F",
};

// Hex → [r, g, b]
function hex(h: string): [number, number, number] {
  const c = h.replace("#", "");
  return [
    parseInt(c.substring(0, 2), 16),
    parseInt(c.substring(2, 4), 16),
    parseInt(c.substring(4, 6), 16),
  ];
}

// ─── Tipos ─────────────────────────────────────────────────────────────────
export interface ProductForPDF {
  id:            string;
  sku:           string;
  name:          string;
  description?:  string | null;
  productType:   string;
  level?:        string | null;
  durationWeeks?: number | null;
  category?:     { name: string } | null;
  prices?:       Array<{ basePrice: number; currency: string }> | null;
}

// ─── Helpers de contenido por categoría ────────────────────────────────────

interface WeekBlock { week: number; days: string[]; focus: string }

function getWeekPlan(sku: string, cat: string, level: string, weeks: number): WeekBlock[] {
  const lvl = level.toLowerCase();
  const isAdvanced = lvl.includes("avanz");
  const isBeginner = lvl.includes("princ") || lvl.includes("beg");

  const patterns: Record<string, { days: string[]; focus: string }[]> = {
    glut: [
      { days: ["Hip thrust 4×12","Sentadilla búlgara 3×10","Patada trasera 3×15","Descanso activo"],
        focus: "Activación y base" },
      { days: ["Peso muerto rumano 4×10","Sentadilla sumo 4×12","Abductores cable 3×15","Cardio 20 min"],
        focus: "Fuerza posterior" },
      { days: ["Hip thrust con banda 5×10","Zancadas 4×12","Glúteo cuadrupedia 3×20","Core 15 min"],
        focus: "Volumen e hipertrofia" },
      { days: ["Sentadilla hack 4×10","Good morning 3×12","Patada lateral 4×15","Foam roller"],
        focus: "Integración y movilidad" },
    ],
    core: [
      { days: ["Plancha 4×45s","Crunch bici 3×20","Elevación piernas 3×15","Respiración diafragmática"],
        focus: "Activación profunda" },
      { days: ["Plancha lateral 3×30s","Rueda abdominal 3×10","Pallof press 3×12","Cardio 15 min"],
        focus: "Estabilidad anti-rotacional" },
      { days: ["Dragon flag negativa 3×5","V-up 3×15","Hollow body 3×30s","Movilidad lumbar"],
        focus: "Fuerza avanzada" },
      { days: ["Plancha compleja 4×40s","Rollout 3×12","Side bend 3×20","Stretching completo"],
        focus: "Integración funcional" },
    ],
    nutri: [
      { days: ["Cálculo TDEE personal","Macros base proteína","Lista de compras semana 1","Prep meals domingo"],
        focus: "Configuración inicial" },
      { days: ["Desayunos high-protein","Almuerzos equilibrados","Cenas ligeras","Snacks inteligentes"],
        focus: "Estructura alimentaria" },
      { days: ["Ajuste de calorías","Semana de recarga","Manejo de salidas","Hidratación optimizada"],
        focus: "Periodización nutricional" },
      { days: ["Suplementación básica","Timing pre/post workout","Comida social","Plan de mantenimiento"],
        focus: "Sostenibilidad y hábitos" },
    ],
    yoga: [
      { days: ["Saludo al sol 5 rondas","Guerrero I-II-III","Torsión sentada","Shavasana 10 min"],
        focus: "Fundamentos y conexión" },
      { days: ["Luna descendente","Posturas de cadera","Balance en pie","Pranayama 15 min"],
        focus: "Apertura de caderas" },
      { days: ["Serie de equilibrio","Inversiones suaves","Flexiones de espalda","Nidra yoga"],
        focus: "Equilibrio y fuerza" },
      { days: ["Flujo creativo 45 min","Posturas restaurativas","Meditación guiada","Diario de práctica"],
        focus: "Integración mente-cuerpo" },
    ],
    post: [
      { days: ["Respiración hipopresiva","Kegel × 20 reps","Puente glúteo suave","Caminata 15 min"],
        focus: "Recuperación y suelo pélvico" },
      { days: ["Core profundo (transverso)","Sentadilla con soporte","Marcha funcional","Auto-masaje abdominal"],
        focus: "Reintegración del core" },
      { days: ["Peso corporal progresivo","Sentadilla libre","Plancha modificada","Yoga restaurativo"],
        focus: "Progresión funcional" },
      { days: ["Retorno al ejercicio pleno","Hip thrust progresivo","Cardio de bajo impacto","Check postural"],
        focus: "Alta funcional" },
    ],
    default: [
      { days: ["Ejercicio A — 4×12","Ejercicio B — 3×15","Movilidad 10 min","Descanso activo"],
        focus: "Semana de base" },
      { days: ["Ejercicio A — 4×10 (+carga)","Ejercicio C — 3×12","HIIT 15 min","Flexibilidad"],
        focus: "Progresión de carga" },
      { days: ["Superset A+B — 3 rondas","Ejercicio D — 4×15","Cardio 20 min","Foam roller"],
        focus: "Volumen e intensidad" },
      { days: ["Deload — 50% carga","Técnica refinada","Evaluación de progreso","Plan siguiente mes"],
        focus: "Recuperación activa" },
    ],
  };

  const key = cat.toLowerCase().includes("glut") || sku.startsWith("GP") ? "glut"
    : cat.toLowerCase().includes("core") || sku.startsWith("AC") ? "core"
    : cat.toLowerCase().includes("nutri") || sku.startsWith("PN") ? "nutri"
    : cat.toLowerCase().includes("yoga") || sku.startsWith("YF") ? "yoga"
    : cat.toLowerCase().includes("post") || sku.startsWith("PR") ? "post"
    : "default";

  const base = patterns[key]!;
  const result: WeekBlock[] = [];

  for (let w = 1; w <= weeks; w++) {
    const phase = base[(w - 1) % base.length]!;
    const extra = isAdvanced ? " (+intensidad avanzada)" : isBeginner ? " (modificaciones incluidas)" : "";
    result.push({
      week: w,
      days: phase.days,
      focus: phase.focus + extra,
    });
  }
  return result;
}

function getExercises(sku: string, cat: string): Array<{ name: string; sets: string; rep: string; tip: string }> {
  const isGlut = cat.toLowerCase().includes("glut") || sku.startsWith("GP");
  const isCore = cat.toLowerCase().includes("core") || sku.startsWith("AC");
  const isYoga = cat.toLowerCase().includes("yoga") || sku.startsWith("YF");
  const isPost = sku.startsWith("PR");

  if (isGlut) return [
    { name: "Hip Thrust con Barra",      sets: "4", rep: "10-12", tip: "Apoya escápulas en banco, empuja con talones. Pausa 1s arriba." },
    { name: "Sentadilla Búlgara",        sets: "3", rep: "10 c/l", tip: "Rodilla trasera no toca el piso. Torso levemente inclinado." },
    { name: "Peso Muerto Rumano",        sets: "4", rep: "10-12", tip: "Barra pegada a las piernas, cadera hacia atrás. Espalda neutral." },
    { name: "Sentadilla Sumo",           sets: "4", rep: "12",    tip: "Pies a 45°, rodillas siguen la punta del pie." },
    { name: "Patada Trasera en Cable",   sets: "3", rep: "15 c/l", tip: "Contraer glúteo al final del recorrido, no balancear cadera." },
    { name: "Abductores en Máquina",     sets: "3", rep: "15-20", tip: "Movimiento controlado. No usar impulso." },
    { name: "Puente de Glúteo",          sets: "4", rep: "15",    tip: "Banda encima de rodillas para mayor activación lateral." },
    { name: "Step-up con Mancuernas",    sets: "3", rep: "12 c/l", tip: "El peso cae en el talón del pie adelantado." },
  ];

  if (isCore) return [
    { name: "Plancha Frontal",           sets: "4", rep: "45-60s", tip: "Cuerpo en línea recta. Activa glúteos y transverso." },
    { name: "Plancha Lateral",           sets: "3", rep: "30s c/l", tip: "Cadera elevada. Evitar rotación del torso." },
    { name: "Crunch de Bicicleta",       sets: "3", rep: "20",    tip: "Codo a rodilla contraria. Velocidad controlada." },
    { name: "Elevación de Piernas",      sets: "4", rep: "15",    tip: "Espalda baja pegada al suelo durante todo el recorrido." },
    { name: "Rueda Abdominal",           sets: "3", rep: "10-12", tip: "Extender hasta horizontales. Activar core antes de extender." },
    { name: "Pallof Press",              sets: "3", rep: "12 c/l", tip: "Resistir la rotación. Clave: anti-rotación isométrica." },
    { name: "V-Up",                      sets: "3", rep: "15",    tip: "Estirar brazos y piernas simultáneamente. Tocar dedos arriba." },
    { name: "Hollow Body Hold",          sets: "3", rep: "30s",   tip: "Espalda baja pegada al suelo. Brazos y piernas extendidos." },
  ];

  if (isYoga) return [
    { name: "Saludo al Sol A",           sets: "5", rep: "rondas", tip: "Sincronizar respiración con cada movimiento. Inhala-exhala." },
    { name: "Guerrero I",                sets: "3", rep: "45s c/l", tip: "Cadera cuadrada hacia adelante. Brazos activos." },
    { name: "Guerrero II",               sets: "3", rep: "45s c/l", tip: "Rodilla sobre tobillo. Mirada sobre el dedo medio." },
    { name: "Triángulo Extendido",       sets: "2", rep: "40s c/l", tip: "Alargar la columna antes de inclinar. No colapsar costado." },
    { name: "Perro Boca Abajo",          sets: "4", rep: "30s",   tip: "Talones buscan el piso. Cabeza entre los brazos." },
    { name: "Paloma (Pigeon Pose)",      sets: "2", rep: "60s c/l", tip: "Postura de apertura de cadera profunda. Respirar en la tensión." },
    { name: "Puente de Yoga",            sets: "3", rep: "10 respiraciones", tip: "Elevar vértebra por vértebra. Activa el core." },
    { name: "Shavasana Final",           sets: "1", rep: "10 min", tip: "Soltar completamente. Integrar la práctica." },
  ];

  if (isPost) return [
    { name: "Respiración Diafragmática", sets: "3", rep: "10 respir", tip: "Mano en abdomen. Inhala expandiendo, exhala contrayendo." },
    { name: "Kegel Progresivo",          sets: "4", rep: "15 rep",  tip: "Contraer 3s, liberar 3s. Aumentar progresivamente el tiempo." },
    { name: "Puente Glúteo Suave",       sets: "3", rep: "12",     tip: "Sin forzar. Parar si hay presión en perineal." },
    { name: "Bird-Dog",                  sets: "3", rep: "10 c/l",  tip: "Extender brazo y pierna opuesta. Pelvis estable." },
    { name: "Marcha Supina",             sets: "3", rep: "10 c/l",  tip: "Espalda baja neutral. Levantar pie sin perder apoyo lumbar." },
    { name: "Sentadilla Asistida",       sets: "3", rep: "10",     tip: "Sostener de una silla si es necesario. Rodillas sobre pies." },
    { name: "Plancha Modificada",        sets: "3", rep: "20s",    tip: "En rodillas. Línea cabeza-rodillas-muñecas." },
    { name: "Estiramiento de Cadera",    sets: "2", rep: "60s c/l", tip: "Suave, sin rebote. Respirar profundo." },
  ];

  // default
  return [
    { name: "Sentadilla Goblet",         sets: "4", rep: "12",    tip: "Mancuerna al pecho. Profundidad completa si es posible." },
    { name: "Press de Pecho",            sets: "4", rep: "10-12", tip: "Escápulas retraídas. Bajar controlado 3 segundos." },
    { name: "Remo con Barra",            sets: "3", rep: "10-12", tip: "Codo cerca del cuerpo. Contraer escápula en la cima." },
    { name: "Peso Muerto Convencional",  sets: "4", rep: "8",     tip: "Barra sobre mediopiés. Barra pegada al cuerpo al subir." },
    { name: "Press Militar",             sets: "3", rep: "10",    tip: "Core activo. No hiper-extender lumbar al presionar." },
    { name: "Dominadas Asistidas",       sets: "3", rep: "6-8",   tip: "Empujar la barra hacia abajo, no el cuerpo hacia arriba." },
    { name: "Extensión de Tríceps",      sets: "3", rep: "12-15", tip: "Solo mueve el antebrazo. Codos fijos junto a la cabeza." },
    { name: "Curl de Bíceps",            sets: "3", rep: "12-15", tip: "Supinación completa. Sin balanceo de torso." },
  ];
}

function getNutritionTips(sku: string, cat: string, level: string): string[] {
  const isNutri = cat.toLowerCase().includes("nutri") || sku.startsWith("PN") || sku.startsWith("RF");
  const isAdv = level.toLowerCase().includes("avanz");

  const base = [
    "Proteína: 1.6–2.2 g por kg de peso corporal por día. Priorizar fuentes de calidad.",
    "Hidratación: mínimo 35 ml por kg de peso. Aumentar 500 ml por hora de entrenamiento.",
    "Carbohidratos: mayor ingesta en torno al entrenamiento (pre y post-workout).",
    "Grasas saludables: aguacate, frutos secos, aceite de oliva. Al menos 20% del total calórico.",
    "Timing: consumir proteína + carbs dentro de las 2 horas post-entrenamiento.",
    "Fibra: 25–35 g diarios. Verduras, legumbres y cereales integrales.",
    "Evitar ultraprocesados los 6 días de entrenamiento. La comida social no arruina el progreso.",
  ];

  if (isNutri) return [
    "TDEE base: peso (kg) × 22 (sedentario) a × 37 (muy activo). Ajustar según objetivo.",
    "Déficit para bajar grasa: -300 a -500 kcal/día. Déficit mayor destruye músculo.",
    "Superávit para ganar músculo: +200 a +350 kcal/día. Más no es más.",
    ...base,
    isAdv ? "Carb cycling: alto en días de piernas/espalda, moderado en hombro/brazo, bajo en descanso."
           : "Empezar con 3 comidas + 1 snack. No hace falta comer cada 2 horas.",
    "Prep del domingo: cocinar 2 proteínas + 3 vegetales + 2 carbohidratos base. Ahorras 6 horas semanales.",
  ];

  return base;
}

// ─── Helpers de layout PDF ─────────────────────────────────────────────────

function drawRect(doc: PDFKit.PDFDocument, x: number, y: number, w: number, h: number, color: string, radius = 0) {
  const [r, g, b] = hex(color);
  doc.save().fillColor([r, g, b] as unknown as string);
  if (radius > 0) doc.roundedRect(x, y, w, h, radius).fill();
  else doc.rect(x, y, w, h).fill();
  doc.restore();
}

function drawText(doc: PDFKit.PDFDocument, text: string, x: number, y: number, opts: {
  size?: number; color?: string; bold?: boolean; align?: "left" | "center" | "right"; width?: number;
} = {}) {
  const [r, g, b] = hex(opts.color ?? C.white);
  doc.fontSize(opts.size ?? 11)
     .fillColor([r, g, b] as unknown as string)
     .text(text, x, y, {
       align: opts.align ?? "left",
       width: opts.width,
       lineBreak: true,
     });
}

function pageHeader(doc: PDFKit.PDFDocument, title: string) {
  // Fondo del header
  drawRect(doc, 0, 0, doc.page.width, 50, C.bg);
  // Línea neon inferior
  drawRect(doc, 0, 48, doc.page.width, 2, C.neon);
  // Título
  drawText(doc, title, 40, 15, { size: 10, color: C.muted });
  // Número de página
  const pg = `Pág. ${(doc as unknown as { _pageBuffer: unknown[] })._pageBuffer?.length ?? 1}`;
  drawText(doc, pg, doc.page.width - 80, 17, { size: 9, color: C.muted, align: "right", width: 60 });
}

function sectionTitle(doc: PDFKit.PDFDocument, text: string, y: number, accentColor = C.neon): number {
  drawRect(doc, 40, y, 4, 20, accentColor);
  drawText(doc, text.toUpperCase(), 52, y + 2, { size: 12, color: C.white, bold: true });
  return y + 32;
}

function pill(doc: PDFKit.PDFDocument, label: string, x: number, y: number, color: string) {
  const [r, g, b] = hex(color);
  doc.save()
     .fillColor([r, g, b] as unknown as string)
     .roundedRect(x, y, label.length * 6.5 + 14, 18, 4)
     .fill()
     .fillColor(hex(C.dark) as unknown as string)
     .fontSize(8)
     .text(label, x + 7, y + 5, { lineBreak: false })
     .restore();
}

// ─── Generador principal ───────────────────────────────────────────────────

export async function generateProductPDF(product: ProductForPDF): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    const doc = new PDFDocument({
      size: "A4",
      margin: 0,
      info: {
        Title: product.name,
        Author: "Fitness Business OS",
        Subject: `Guía de ${product.category?.name ?? "Fitness"}`,
        Keywords: `fitness, ${product.level ?? ""}, ${product.sku}`,
      },
    });

    doc.on("data", (c: Buffer) => chunks.push(c));
    doc.on("end", () => resolve(Buffer.concat(chunks)));
    doc.on("error", reject);

    const W = doc.page.width;   // 595
    const catName = product.category?.name ?? "Fitness";
    const level   = product.level ?? "Todos los niveles";
    const weeks   = product.durationWeeks ?? 8;
    const price   = product.prices?.[0];
    const sku     = product.sku;

    // ── PORTADA ────────────────────────────────────────────────────────────
    {
      // Fondo degradado simulado con rectángulos
      drawRect(doc, 0, 0, W, 842, C.bg);
      drawRect(doc, 0, 0, W, 3, C.neon);     // línea superior neon
      drawRect(doc, 0, 839, W, 3, C.purple); // línea inferior purple

      // Patrón de puntos decorativo (esquina superior derecha)
      for (let i = 0; i < 6; i++) {
        for (let j = 0; j < 6; j++) {
          doc.save()
             .fillColor(hex(C.neon) as unknown as string)
             .opacity(0.08)
             .circle(W - 60 + i * 12, 60 + j * 12, 2)
             .fill()
             .restore();
        }
      }

      // Logo / Brand mark
      drawRect(doc, 40, 40, 120, 28, C.neon, 4);
      doc.fontSize(11).fillColor(hex(C.dark) as unknown as string)
         .text("FITNESS  OS", 52, 48, { lineBreak: false });

      // SKU badge
      const skuLabel = `  ${sku}  `;
      drawRect(doc, W - 40 - skuLabel.length * 7, 40, skuLabel.length * 7, 28, C.border, 4);
      doc.fontSize(9).fillColor(hex(C.muted) as unknown as string)
         .text(sku, W - 35 - skuLabel.length * 7, 49, { lineBreak: false });

      // Categoría eyebrow
      doc.fontSize(11).fillColor(hex(C.cyan) as unknown as string)
         .text(catName.toUpperCase(), 40, 200, { letterSpacing: 3, lineBreak: false });

      // Título grande
      doc.fontSize(product.name.length > 45 ? 28 : 34)
         .fillColor(hex(C.white) as unknown as string)
         .font("Helvetica-Bold")
         .text(product.name, 40, 225, { width: W - 80, lineBreak: true });

      // Descripción corta
      if (product.description) {
        doc.fontSize(12).font("Helvetica")
           .fillColor(hex(C.silver) as unknown as string)
           .text(product.description.substring(0, 200), 40, doc.y + 16, { width: W - 80, lineBreak: true });
      }

      // Pills de metadata
      const pillY = 400;
      pill(doc, `NIVEL: ${level.toUpperCase()}`, 40, pillY, C.neon);
      pill(doc, `${weeks} SEMANAS`, 40 + level.length * 6.5 + 60, pillY, C.cyan);
      pill(doc, product.productType.replace("_", " "), 40 + level.length * 6.5 + 145, pillY, C.purple);

      // Separador
      drawRect(doc, 40, pillY + 32, W - 80, 1, C.border);

      // Contenido incluido (lista)
      const includes = [
        `✦  Programa de ${weeks} semanas estructurado`,
        "✦  Biblioteca de ejercicios con técnica detallada",
        "✦  Plan nutricional personalizado",
        "✦  Tabla de seguimiento de progreso semanal",
        "✦  Tips de recuperación y descanso",
        "✦  Modificaciones por nivel de fitness",
      ];
      doc.fontSize(11).font("Helvetica").fillColor(hex(C.silver) as unknown as string);
      includes.forEach((line, i) => {
        doc.text(line, 40, pillY + 48 + i * 22, { lineBreak: false });
      });

      // Precio si existe
      if (price) {
        drawRect(doc, 40, 700, W - 80, 60, C.card, 8);
        drawRect(doc, 40, 700, 4, 60, C.neon);
        doc.fontSize(10).fillColor(hex(C.muted) as unknown as string)
           .text("PRECIO DE REFERENCIA", 56, 714, { lineBreak: false });
        doc.fontSize(26).font("Helvetica-Bold").fillColor(hex(C.neon) as unknown as string)
           .text(`$${Number(price.basePrice).toLocaleString("es-AR")} ${price.currency}`, 56, 728, { lineBreak: false });
      }

      // Footer portada
      drawRect(doc, 0, 800, W, 42, C.card);
      doc.fontSize(9).font("Helvetica").fillColor(hex(C.muted) as unknown as string)
         .text("Este documento es de uso exclusivo del adquirente. Prohibida su reproducción sin autorización.", 40, 817, {
           width: W - 80, align: "center", lineBreak: false,
         });
    }

    // ── PÁGINA 2: INTRODUCCIÓN + OBJETIVO ─────────────────────────────────
    doc.addPage();
    {
      drawRect(doc, 0, 0, W, 842, C.bg);
      pageHeader(doc, product.name);

      let y = 70;
      y = sectionTitle(doc, "Bienvenida y Presentación", y, C.cyan);

      doc.fontSize(11).font("Helvetica").fillColor(hex(C.silver) as unknown as string)
         .text(
           `Bienvenida a ${product.name}. Este programa ha sido diseñado para guiarte paso a paso durante ` +
           `${weeks} semanas con un enfoque progresivo y adaptable a tu nivel actual (${level}).`,
           40, y, { width: W - 80, lineBreak: true }
         );

      y = doc.y + 20;
      doc.text(
        `El programa combina entrenamiento de fuerza, movilidad funcional y estrategias nutricionales ` +
        `respaldadas por evidencia científica. Cada semana encontrarás una variación progresiva de carga, ` +
        `volumen e intensidad para garantizar adaptaciones continuas sin llegar al sobreentrenamiento.`,
        40, y, { width: W - 80, lineBreak: true }
      );

      y = doc.y + 28;
      y = sectionTitle(doc, "Objetivos del programa", y, C.neon);

      const objetivos = [
        { icon: "→", text: "Desarrollar fuerza funcional y potencia muscular de forma progresiva" },
        { icon: "→", text: "Mejorar la composición corporal a través de entrenamiento inteligente" },
        { icon: "→", text: "Establecer hábitos nutricionales sostenibles y sin restricciones extremas" },
        { icon: "→", text: "Aumentar la conciencia corporal, movilidad y calidad de movimiento" },
        { icon: "→", text: "Construir una rutina de entrenamiento que puedas mantener de por vida" },
      ];

      objetivos.forEach(o => {
        drawRect(doc, 40, y, W - 80, 34, C.card, 4);
        doc.fontSize(11).fillColor(hex(C.neon) as unknown as string)
           .text(o.icon, 54, y + 11, { lineBreak: false });
        doc.fillColor(hex(C.silver) as unknown as string)
           .text(o.text, 72, y + 11, { width: W - 120, lineBreak: false });
        y += 42;
      });

      y += 12;
      y = sectionTitle(doc, "¿Cómo usar esta guía?", y, C.purple);

      const pasos = [
        { n: "01", t: "Leer completo antes de empezar", d: "Familiarizate con el programa antes de la semana 1." },
        { n: "02", t: "Registrar medidas iniciales", d: "Peso, medidas y foto de progreso en el día 0." },
        { n: "03", t: "Preparar el entorno", d: "Lista de compras, equipamiento y horarios definidos." },
        { n: "04", t: "Seguir la tabla semanal", d: "Respetar los días de descanso es parte del programa." },
        { n: "05", t: "Registrar en la planilla", d: "Anotar cargas y repeticiones para ajustar progresión." },
      ];

      pasos.forEach(p => {
        drawRect(doc, 40, y, 38, 38, C.neon, 4);
        doc.fontSize(14).font("Helvetica-Bold").fillColor(hex(C.dark) as unknown as string)
           .text(p.n, 40, y + 9, { width: 38, align: "center", lineBreak: false });
        doc.font("Helvetica").fontSize(11).fillColor(hex(C.white) as unknown as string)
           .text(p.t, 88, y + 4, { lineBreak: false });
        doc.fontSize(10).fillColor(hex(C.muted) as unknown as string)
           .text(p.d, 88, y + 18, { width: W - 136, lineBreak: false });
        y += 48;
      });
    }

    // ── PÁGINAS 3+: PLAN SEMANAL ───────────────────────────────────────────
    const weekPlan = getWeekPlan(sku, catName, level, weeks);
    const weeksPerPage = 3;

    for (let page = 0; page < Math.ceil(weeks / weeksPerPage); page++) {
      doc.addPage();
      drawRect(doc, 0, 0, W, 842, C.bg);
      pageHeader(doc, product.name);

      let y = 70;
      const pageLabel = `Semanas ${page * weeksPerPage + 1}–${Math.min((page + 1) * weeksPerPage, weeks)}`;
      y = sectionTitle(doc, `Plan semanal — ${pageLabel}`, y, C.neon);

      const pageWeeks = weekPlan.slice(page * weeksPerPage, (page + 1) * weeksPerPage);

      pageWeeks.forEach((wk) => {
        // Encabezado de semana
        drawRect(doc, 40, y, W - 80, 32, C.card, 4);
        drawRect(doc, 40, y, 4, 32, C.neon);
        doc.fontSize(13).font("Helvetica-Bold").fillColor(hex(C.neon) as unknown as string)
           .text(`SEMANA ${wk.week}`, 52, y + 9, { lineBreak: false });
        doc.fontSize(10).font("Helvetica").fillColor(hex(C.muted) as unknown as string)
           .text(`Focus: ${wk.focus}`, 200, y + 11, { lineBreak: false });
        y += 38;

        // Días
        wk.days.forEach((day, di) => {
          const rowBg = di % 2 === 0 ? C.bg : "#0D0F1E";
          drawRect(doc, 40, y, W - 80, 26, rowBg);
          doc.fontSize(9).fillColor(hex(C.cyan) as unknown as string)
             .text(`Día ${di + 1}`, 48, y + 8, { lineBreak: false, width: 35 });
          doc.fillColor(hex(C.silver) as unknown as string)
             .text(day, 90, y + 8, { lineBreak: false, width: W - 140 });
          y += 26;
        });
        y += 16;

        if (y > 760) {
          doc.addPage();
          drawRect(doc, 0, 0, W, 842, C.bg);
          pageHeader(doc, product.name);
          y = 70;
        }
      });
    }

    // ── PÁGINA: BIBLIOTECA DE EJERCICIOS ──────────────────────────────────
    doc.addPage();
    {
      drawRect(doc, 0, 0, W, 842, C.bg);
      pageHeader(doc, product.name);

      let y = 70;
      y = sectionTitle(doc, "Biblioteca de Ejercicios", y, C.cyan);

      const exercises = getExercises(sku, catName);

      // Encabezado de tabla
      drawRect(doc, 40, y, W - 80, 24, C.card);
      ["EJERCICIO", "SERIES", "REPS", "INDICACIÓN TÉCNICA"].forEach((h, i) => {
        const xPos = [40, 230, 285, 345][i]!;
        const wPos = [185, 50, 55, W - 385][i]!;
        doc.fontSize(8).font("Helvetica-Bold").fillColor(hex(C.muted) as unknown as string)
           .text(h, xPos + 4, y + 8, { width: wPos, lineBreak: false });
      });
      y += 24;

      exercises.forEach((ex, idx) => {
        const rowH = 36;
        const rowBg = idx % 2 === 0 ? "#0A0C18" : "#0D0F1E";
        drawRect(doc, 40, y, W - 80, rowH, rowBg);

        // Número
        doc.fontSize(9).font("Helvetica-Bold").fillColor(hex(C.neon) as unknown as string)
           .text(`${idx + 1 < 10 ? "0" : ""}${idx + 1}`, 44, y + 13, { lineBreak: false, width: 20 });

        // Nombre
        doc.font("Helvetica").fillColor(hex(C.white) as unknown as string)
           .text(ex.name, 68, y + 5, { width: 158, lineBreak: true });

        // Series
        doc.fillColor(hex(C.cyan) as unknown as string)
           .text(ex.sets, 234, y + 13, { width: 46, align: "center", lineBreak: false });

        // Reps
        doc.fillColor(hex(C.yellow) as unknown as string)
           .text(ex.rep, 289, y + 13, { width: 50, align: "center", lineBreak: false });

        // Tip
        doc.fillColor(hex(C.muted) as unknown as string).fontSize(8.5)
           .text(ex.tip, 349, y + 4, { width: W - 393, lineBreak: true });

        y += rowH;

        if (y > 780) {
          doc.addPage();
          drawRect(doc, 0, 0, W, 842, C.bg);
          pageHeader(doc, product.name);
          y = 70;
        }
      });
    }

    // ── PÁGINA: NUTRICIÓN ─────────────────────────────────────────────────
    doc.addPage();
    {
      drawRect(doc, 0, 0, W, 842, C.bg);
      pageHeader(doc, product.name);

      let y = 70;
      y = sectionTitle(doc, "Guía Nutricional", y, C.yellow);

      const tips = getNutritionTips(sku, catName, level);

      tips.forEach((tip, i) => {
        drawRect(doc, 40, y, W - 80, 44, C.card, 4);
        drawRect(doc, 40, y, 4, 44, C.yellow);
        doc.fontSize(8).font("Helvetica-Bold").fillColor(hex(C.yellow) as unknown as string)
           .text(`${i + 1 < 10 ? "0" : ""}${i + 1}`, 50, y + 8, { lineBreak: false });
        doc.fontSize(10).font("Helvetica").fillColor(hex(C.silver) as unknown as string)
           .text(tip, 65, y + 8, { width: W - 120, lineBreak: true });
        y += 52;
      });

      y += 10;

      // Macros tabla
      y = sectionTitle(doc, "Distribución de Macronutrientes", y, C.neon);

      const macros = [
        { macro: "PROTEÍNA",     pct: "30–35%", g: "1.6–2.2 g/kg", fuentes: "Pollo, carne magra, huevo, legumbres, yogur griego" },
        { macro: "CARBOHIDRATOS", pct: "40–50%", g: "3–5 g/kg",    fuentes: "Arroz, avena, batata, banana, frutas, pan integral" },
        { macro: "GRASAS",       pct: "20–25%", g: "0.8–1.2 g/kg", fuentes: "Palta, nueces, aceite de oliva, salmón, semillas" },
      ];

      // Encabezado
      drawRect(doc, 40, y, W - 80, 22, C.card);
      ["MACRO", "%", "G/KG", "FUENTES RECOMENDADAS"].forEach((h, i) => {
        const xs = [44, 132, 200, 280][i]!;
        doc.fontSize(8).font("Helvetica-Bold").fillColor(hex(C.muted) as unknown as string)
           .text(h, xs, y + 7, { lineBreak: false });
      });
      y += 22;

      macros.forEach((m, idx) => {
        const colors = [C.cyan, C.neon, C.yellow];
        drawRect(doc, 40, y, W - 80, 36, idx % 2 === 0 ? C.bg : "#0D0F1E");
        doc.fontSize(10).font("Helvetica-Bold").fillColor(hex(colors[idx]!) as unknown as string)
           .text(m.macro, 44, y + 11, { lineBreak: false });
        doc.font("Helvetica").fillColor(hex(C.white) as unknown as string)
           .text(m.pct, 132, y + 11, { lineBreak: false });
        doc.fillColor(hex(C.silver) as unknown as string)
           .text(m.g, 200, y + 11, { lineBreak: false });
        doc.fontSize(9).fillColor(hex(C.muted) as unknown as string)
           .text(m.fuentes, 280, y + 7, { width: W - 325, lineBreak: true });
        y += 36;
      });

      // Tip de hidratación
      y += 16;
      drawRect(doc, 40, y, W - 80, 56, C.card, 8);
      drawRect(doc, 40, y, W - 80, 4, C.cyan, 8);
      doc.fontSize(10).font("Helvetica-Bold").fillColor(hex(C.cyan) as unknown as string)
         .text("💧 Hidratación", 56, y + 14, { lineBreak: false });
      doc.fontSize(10).font("Helvetica").fillColor(hex(C.silver) as unknown as string)
         .text(
           "Mínimo 35 ml por kg de peso corporal. En días de entrenamiento agregar 500 ml por hora de actividad. " +
           "El agua es el suplemento más subestimado y más efectivo.",
           56, y + 28, { width: W - 112, lineBreak: true }
         );
    }

    // ── PÁGINA: SEGUIMIENTO DE PROGRESO ───────────────────────────────────
    doc.addPage();
    {
      drawRect(doc, 0, 0, W, 842, C.bg);
      pageHeader(doc, product.name);

      let y = 70;
      y = sectionTitle(doc, "Tabla de Seguimiento Semanal", y, C.purple);

      doc.fontSize(10).font("Helvetica").fillColor(hex(C.muted) as unknown as string)
         .text("Completá esta tabla cada semana. La honestidad con los registros es la clave del progreso real.", 40, y, {
           width: W - 80, lineBreak: true
         });
      y = doc.y + 14;

      // Tabla de seguimiento
      const cols = ["SEMANA", "PESO (kg)", "CINTURA (cm)", "CADERAS (cm)", "ENERGÍA /10", "CUMPLIMIENTO %"];
      const colW = (W - 80) / cols.length;

      // Encabezado
      drawRect(doc, 40, y, W - 80, 26, C.purple + "66");
      cols.forEach((col, i) => {
        doc.fontSize(7.5).font("Helvetica-Bold").fillColor(hex(C.white) as unknown as string)
           .text(col, 40 + i * colW + 4, y + 9, { width: colW - 8, align: "center", lineBreak: false });
      });
      y += 26;

      for (let w = 1; w <= Math.min(weeks, 16); w++) {
        const rowBg = w % 2 === 0 ? "#0D0F1E" : C.bg;
        drawRect(doc, 40, y, W - 80, 28, rowBg);

        // Número de semana
        doc.fontSize(9).font("Helvetica-Bold").fillColor(hex(C.neon) as unknown as string)
           .text(`Semana ${w}`, 44, y + 9, { width: colW - 8, align: "center", lineBreak: false });

        // Celdas vacías para escribir
        for (let c = 1; c < cols.length; c++) {
          doc.save()
             .strokeColor(hex(C.border) as unknown as string)
             .lineWidth(0.5)
             .moveTo(40 + c * colW, y + 4)
             .lineTo(40 + c * colW, y + 24)
             .stroke()
             .restore();
          // Línea para escribir
          doc.save()
             .strokeColor(hex(C.muted) as unknown as string)
             .lineWidth(0.3)
             .moveTo(40 + c * colW + 6, y + 20)
             .lineTo(40 + (c + 1) * colW - 6, y + 20)
             .stroke()
             .restore();
        }
        y += 28;

        if (y > 800 && w < weeks) {
          doc.addPage();
          drawRect(doc, 0, 0, W, 842, C.bg);
          pageHeader(doc, product.name);
          y = 70;
        }
      }

      y += 16;
      // Sección de notas
      y = sectionTitle(doc, "Notas y Observaciones", y, C.muted);
      for (let i = 0; i < 8; i++) {
        doc.save()
           .strokeColor(hex(C.border) as unknown as string)
           .lineWidth(0.5)
           .moveTo(40, y + i * 28 + 14)
           .lineTo(W - 40, y + i * 28 + 14)
           .stroke()
           .restore();
      }
    }

    // ── PÁGINA FINAL: TIPS Y CIERRE ────────────────────────────────────────
    doc.addPage();
    {
      drawRect(doc, 0, 0, W, 842, C.bg);
      drawRect(doc, 0, 0, W, 3, C.neon);

      let y = 60;
      y = sectionTitle(doc, "Tips de Recuperación y Descanso", y, C.cyan);

      const recovery = [
        { t: "Sueño 7–9 horas", d: "El músculo crece durante el descanso. El sueño es parte del entrenamiento." },
        { t: "Foam roller pre y post", d: "5 minutos antes activa la circulación. 10 minutos después reduce DOMS." },
        { t: "Semana de deload (semana 4 y 8)", d: "Reducir volumen al 50%. El cuerpo supercompensa en el descanso." },
        { t: "Temperatura contrastada", d: "Ducha fría 2 minutos post-entreno reduce inflamación muscular." },
        { t: "Movilidad articular diaria", d: "10 minutos de movilidad en articulaciones clave: caderas, hombros, tobillo." },
      ];

      recovery.forEach(r => {
        drawRect(doc, 40, y, W - 80, 48, C.card, 4);
        doc.fontSize(11).font("Helvetica-Bold").fillColor(hex(C.cyan) as unknown as string)
           .text(`→ ${r.t}`, 54, y + 10, { lineBreak: false });
        doc.fontSize(10).font("Helvetica").fillColor(hex(C.muted) as unknown as string)
           .text(r.d, 54, y + 26, { width: W - 108, lineBreak: false });
        y += 56;
      });

      y += 8;
      y = sectionTitle(doc, "Preguntas Frecuentes", y, C.purple);

      const faqs = [
        { q: "¿Qué hago si me salteo un día?", a: "Continuá con el día siguiente. No recuperes sesiones perdidas — avanzá." },
        { q: "¿Puedo hacer cardio extra?", a: "Sí, pero extra-liviano (caminata, bici suave). Priorizá la recuperación muscular." },
        { q: "¿Cuándo veré resultados?", a: "Cambios funcionales: semana 2–3. Cambios visuales: semana 4–6. Mantené el proceso." },
        { q: "¿Puedo adaptar los ejercicios?", a: "Sí. Cada ejercicio tiene una versión modificada. Escuchá tu cuerpo." },
      ];

      faqs.forEach(f => {
        doc.fontSize(11).font("Helvetica-Bold").fillColor(hex(C.white) as unknown as string)
           .text(`P: ${f.q}`, 40, y, { lineBreak: false });
        y = doc.y + 2;
        doc.fontSize(10).font("Helvetica").fillColor(hex(C.silver) as unknown as string)
           .text(`R: ${f.a}`, 40, y, { width: W - 80, lineBreak: true });
        y = doc.y + 14;
      });

      // Cierre / motivación
      drawRect(doc, 40, y + 10, W - 80, 80, C.neon + "18", 8);
      drawRect(doc, 40, y + 10, W - 80, 3, C.neon, 8);
      doc.fontSize(15).font("Helvetica-Bold").fillColor(hex(C.neon) as unknown as string)
         .text("El progreso no es lineal. El proceso sí.", 40, y + 26, { width: W - 80, align: "center", lineBreak: false });
      doc.fontSize(10).font("Helvetica").fillColor(hex(C.silver) as unknown as string)
         .text(
           "Cada semana que completás es un paso irreversible. La consistencia supera a la perfección.",
           40, y + 48, { width: W - 80, align: "center", lineBreak: false }
         );

      // Footer final
      drawRect(doc, 0, 800, W, 42, C.card);
      drawRect(doc, 0, 800, W, 1, C.border);
      doc.fontSize(8).font("Helvetica").fillColor(hex(C.muted) as unknown as string)
         .text(`${product.name}  ·  SKU: ${sku}  ·  Fitness Business OS`, 40, 816, {
           width: W - 80, align: "center", lineBreak: false
         });
    }

    doc.end();
  });
}

/**
 * Genera un PDF de seguimiento descargable por separado (versión de 1 página imprimible).
 */
export async function generateTrackingPDF(product: ProductForPDF): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    const doc = new PDFDocument({ size: "A4", margin: 40, info: { Title: `Seguimiento — ${product.name}` } });

    doc.on("data", (c: Buffer) => chunks.push(c));
    doc.on("end", () => resolve(Buffer.concat(chunks)));
    doc.on("error", reject);

    const W = doc.page.width;
    const weeks = product.durationWeeks ?? 8;

    // Header
    doc.fontSize(8).font("Helvetica").fillColor("#888888")
       .text("FITNESS BUSINESS OS", 40, 40, { lineBreak: false });
    doc.fontSize(16).font("Helvetica-Bold").fillColor("#000000")
       .text(`Seguimiento — ${product.name}`, 40, 55, { width: W - 80, lineBreak: true });
    doc.fontSize(9).font("Helvetica").fillColor("#666666")
       .text(`SKU: ${product.sku}  ·  ${product.durationWeeks ?? 8} semanas  ·  Nivel: ${product.level ?? "General"}`,
             40, doc.y + 4, { lineBreak: false });

    doc.moveTo(40, doc.y + 12).lineTo(W - 40, doc.y + 12).strokeColor("#CCCCCC").lineWidth(0.8).stroke();

    let y = doc.y + 20;

    // Tabla
    const cols = ["Sem.", "Fecha", "Peso (kg)", "Cintura", "Caderas", "Energía /10", "Cumplim.%", "Notas"];
    const colW = [32, 58, 60, 55, 55, 60, 60, 95];
    let x = 40;

    // Encabezado
    doc.fontSize(7.5).font("Helvetica-Bold").fillColor("#333333");
    cols.forEach((col, i) => {
      doc.text(col, x + 2, y, { width: colW[i]! - 4, lineBreak: false });
      x += colW[i]!;
    });
    y += 14;
    doc.moveTo(40, y).lineTo(W - 40, y).strokeColor("#999999").lineWidth(0.5).stroke();
    y += 4;

    for (let w = 1; w <= weeks; w++) {
      x = 40;
      const isShaded = w % 2 === 0;
      if (isShaded) {
        doc.save().fillColor("#F5F5F5").rect(40, y - 2, W - 80, 22).fill().restore();
      }
      doc.fontSize(8).font("Helvetica-Bold").fillColor("#333333").text(`S${w}`, x + 2, y, { lineBreak: false });
      x += colW[0]!;
      colW.slice(1).forEach((cw, ci) => {
        doc.strokeColor("#DDDDDD").lineWidth(0.3).moveTo(x, y - 2).lineTo(x, y + 18).stroke();
        // Línea de escritura para celdas
        if (ci < 6) {
          doc.strokeColor("#CCCCCC").lineWidth(0.3).moveTo(x + 3, y + 14).lineTo(x + cw - 3, y + 14).stroke();
        }
        x += cw;
      });
      doc.moveTo(40, y + 20).lineTo(W - 40, y + 20).strokeColor("#EEEEEE").lineWidth(0.3).stroke();
      y += 22;
    }

    // Notas
    y += 12;
    doc.fontSize(10).font("Helvetica-Bold").fillColor("#222222")
       .text("Notas del programa:", 40, y, { lineBreak: false });
    y += 16;
    for (let i = 0; i < 6; i++) {
      doc.moveTo(40, y + i * 22).lineTo(W - 40, y + i * 22).strokeColor("#CCCCCC").lineWidth(0.4).stroke();
    }

    // Footer
    doc.fontSize(7).font("Helvetica").fillColor("#AAAAAA")
       .text(`${product.name}  ·  Fitness Business OS`, 40, doc.page.height - 40, {
         width: W - 80, align: "center", lineBreak: false
       });

    doc.end();
  });
}
