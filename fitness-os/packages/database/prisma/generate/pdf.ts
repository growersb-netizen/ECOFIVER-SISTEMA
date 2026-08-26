/**
 * Módulo de generación de PDFs con pdfkit.
 * Crea documentos con diseño profesional para Fitness Business OS.
 */

import PDFDocument from "pdfkit";
import fs from "fs";
import path from "path";
import type { Exercise } from "./exercises.js";
import type { Recipe } from "./recipes.js";

// ── Paleta de colores ─────────────────────────────────────────────
const COLORS = {
  primary:    "#0B1120",    // fondo oscuro del header
  accent:     "#00CC6A",    // verde principal
  accentDark: "#009950",    // verde oscuro
  pink:       "#FF2D78",    // acento rosa (para mujeres)
  blue:       "#2D9CDB",    // azul deportivo
  light:      "#F7F9FC",    // fondo página
  white:      "#FFFFFF",
  gray:       "#64748B",
  grayLight:  "#E2E8F0",
  text:       "#1A202C",    // texto principal
  textLight:  "#4A5568",    // texto secundario
};

// Tipos de acento según audiencia
export type AccentType = "default" | "women" | "men" | "sports";
function getAccent(t: AccentType = "default"): string {
  if (t === "women") return COLORS.pink;
  if (t === "sports") return COLORS.blue;
  if (t === "men") return "#FF6B35";
  return COLORS.accent;
}

// ── Helpers internos ──────────────────────────────────────────────
function drawHeaderBar(doc: PDFKit.PDFDocument, title: string, subtitle: string, accent: string) {
  const W = doc.page.width;
  // Fondo oscuro
  doc.rect(0, 0, W, 110).fill(COLORS.primary);
  // Barra de acento
  doc.rect(0, 108, W, 4).fill(accent);

  doc.fillColor(COLORS.white)
    .font("Helvetica-Bold")
    .fontSize(22)
    .text(title, 50, 30, { width: W - 100 });

  doc.fillColor(accent)
    .font("Helvetica")
    .fontSize(12)
    .text(subtitle, 50, 58, { width: W - 100 });

  doc.fillColor(COLORS.white)
    .fontSize(9)
    .text("FITNESS BUSINESS OS  |  fitnessbusiness.com", 50, 82, { width: W - 100, align: "left" });

  doc.moveDown(2);
}

function drawSectionTitle(doc: PDFKit.PDFDocument, text: string, accent: string) {
  const y = doc.y + 8;
  doc.rect(50, y, 4, 18).fill(accent);
  doc.fillColor(COLORS.text)
    .font("Helvetica-Bold")
    .fontSize(14)
    .text(text, 62, y + 2);
  doc.moveDown(0.6);
}

function drawDivider(doc: PDFKit.PDFDocument) {
  doc.moveTo(50, doc.y)
    .lineTo(doc.page.width - 50, doc.y)
    .lineWidth(0.5)
    .strokeColor(COLORS.grayLight)
    .stroke();
  doc.moveDown(0.4);
}

function drawBodyText(doc: PDFKit.PDFDocument, text: string) {
  doc.fillColor(COLORS.text)
    .font("Helvetica")
    .fontSize(10.5)
    .text(text, 50, doc.y, { width: doc.page.width - 100, lineGap: 3 });
  doc.moveDown(0.4);
}

function drawBulletList(doc: PDFKit.PDFDocument, items: string[], accent: string) {
  for (const item of items) {
    const y = doc.y;
    doc.rect(50, y + 4, 5, 5).fill(accent);
    doc.fillColor(COLORS.text)
      .font("Helvetica")
      .fontSize(10.5)
      .text(item, 63, y, { width: doc.page.width - 113, lineGap: 3 });
    doc.moveDown(0.25);
  }
}

function drawNumberedList(doc: PDFKit.PDFDocument, items: string[]) {
  for (let i = 0; i < items.length; i++) {
    const y = doc.y;
    doc.fillColor(COLORS.gray)
      .font("Helvetica-Bold")
      .fontSize(10)
      .text(`${i + 1}.`, 50, y, { width: 18 });
    doc.fillColor(COLORS.text)
      .font("Helvetica")
      .fontSize(10.5)
      .text(items[i], 70, y, { width: doc.page.width - 120, lineGap: 3 });
    doc.moveDown(0.25);
  }
}

function drawInfoBox(doc: PDFKit.PDFDocument, label: string, value: string, accent: string) {
  const y = doc.y;
  doc.roundedRect(50, y, doc.page.width - 100, 38, 4)
    .fill(COLORS.light);
  doc.fillColor(accent)
    .font("Helvetica-Bold")
    .fontSize(9)
    .text(label.toUpperCase(), 62, y + 7);
  doc.fillColor(COLORS.text)
    .font("Helvetica")
    .fontSize(11)
    .text(value, 62, y + 19, { width: doc.page.width - 124 });
  doc.moveDown(1.2);
}

function drawCalloutBox(doc: PDFKit.PDFDocument, title: string, body: string, accent: string) {
  const textH = body.length > 200 ? 70 : 50;
  const y = doc.y;
  doc.roundedRect(50, y, doc.page.width - 100, textH + 16, 4).fill(accent);
  doc.fillColor(COLORS.white)
    .font("Helvetica-Bold")
    .fontSize(10)
    .text(title, 62, y + 8);
  doc.fillColor(COLORS.white)
    .font("Helvetica")
    .fontSize(9.5)
    .text(body, 62, y + 21, { width: doc.page.width - 124, lineGap: 2 });
  doc.moveDown(1.5);
}

function drawPageFooter(doc: PDFKit.PDFDocument, productName: string) {
  const W = doc.page.width;
  const H = doc.page.height;
  doc.rect(0, H - 30, W, 30).fill(COLORS.primary);
  doc.fillColor(COLORS.gray)
    .font("Helvetica")
    .fontSize(8)
    .text(`${productName}  —  © Fitness Business OS`, 50, H - 21, { width: W - 100 });
  doc.text(`Pág. ${doc.bufferedPageRange().start + 1}`, 50, H - 21, { width: W - 50, align: "right" });
}

function addPage(doc: PDFKit.PDFDocument) {
  doc.addPage({ margin: 50, size: "A4" });
}

function checkPageSpace(doc: PDFKit.PDFDocument, needed = 80) {
  if (doc.y > doc.page.height - needed - 30) {
    addPage(doc);
    doc.y = 130;
  }
}

// ── Tabla de ejercicios ───────────────────────────────────────────
function drawExerciseTable(doc: PDFKit.PDFDocument, exercises: Exercise[], accent: string) {
  const W = doc.page.width - 100;
  const col = [0, W * 0.35, W * 0.55, W * 0.7, W * 0.85];
  const headers = ["Ejercicio", "Músculos", "Series × Reps", "Descanso", "Equipo"];

  // Header row
  const hy = doc.y;
  doc.rect(50, hy, W, 20).fill(accent);
  doc.fillColor(COLORS.white).font("Helvetica-Bold").fontSize(8.5);
  headers.forEach((h, i) => {
    doc.text(h, 50 + col[i] + 4, hy + 6, { width: (col[i + 1] ?? W) - col[i] - 4 });
  });
  doc.y = hy + 24;

  for (let r = 0; r < exercises.length; r++) {
    const ex = exercises[r];
    checkPageSpace(doc, 35);
    const ry = doc.y;
    const bg = r % 2 === 0 ? COLORS.white : COLORS.light;
    doc.rect(50, ry, W, 22).fill(bg);

    doc.fillColor(COLORS.text).font("Helvetica-Bold").fontSize(8);
    doc.text(ex.name, 50 + col[0] + 4, ry + 4, { width: col[1] - col[0] - 8, ellipsis: true });

    doc.fillColor(COLORS.textLight).font("Helvetica").fontSize(7.5);
    doc.text(ex.muscles, 50 + col[1] + 4, ry + 4, { width: col[2] - col[1] - 8, ellipsis: true });

    doc.fillColor(COLORS.text).font("Helvetica-Bold").fontSize(8.5);
    doc.text(ex.intermediate, 50 + col[2] + 4, ry + 7, { width: col[3] - col[2] - 8 });

    doc.fillColor(COLORS.textLight).font("Helvetica").fontSize(8);
    doc.text(ex.rest + " seg", 50 + col[3] + 4, ry + 7, { width: col[4] - col[3] - 8 });
    doc.text(ex.equipment, 50 + col[4] + 4, ry + 4, { width: W - col[4] - 8, ellipsis: true });

    doc.y = ry + 26;
  }
  doc.moveDown(0.5);
}

// ── Tabla de recetas ──────────────────────────────────────────────
function drawRecipeCard(doc: PDFKit.PDFDocument, recipe: Recipe, accent: string) {
  checkPageSpace(doc, 160);
  const W = doc.page.width - 100;
  const y = doc.y;

  // Card header
  doc.rect(50, y, W, 30).fill(accent);
  doc.fillColor(COLORS.white)
    .font("Helvetica-Bold")
    .fontSize(12)
    .text(recipe.name, 62, y + 8, { width: W - 120 });

  // Macros badges
  if (recipe.calories) {
    const badges = [
      `🔥 ${recipe.calories} kcal`,
      `💪 ${recipe.protein}g prot`,
      `🌾 ${recipe.carbs}g carbs`,
    ];
    doc.fillColor(COLORS.white)
      .font("Helvetica")
      .fontSize(9)
      .text(badges.join("   |   "), W - 130, y + 12, { width: 140, align: "right" });
  }
  doc.y = y + 36;

  // Meta info
  doc.roundedRect(50, doc.y, W, 22, 3).fill(COLORS.light);
  doc.fillColor(COLORS.textLight)
    .font("Helvetica")
    .fontSize(8.5)
    .text(`⏱ Preparación: ${recipe.prepTime}   👥 Porciones: ${recipe.servings}   🏷 ${recipe.category}`, 62, doc.y + 7, { width: W - 24 });
  doc.y += 28;

  // Two columns: ingredients | steps
  const colW = (W - 10) / 2;

  doc.fillColor(accent).font("Helvetica-Bold").fontSize(10).text("INGREDIENTES", 50, doc.y);
  doc.fillColor(accent).font("Helvetica-Bold").fontSize(10).text("PREPARACIÓN", 50 + colW + 10, doc.y);
  doc.moveDown(0.4);

  const startY = doc.y;
  let leftY = startY;
  let rightY = startY;

  // Ingredients column
  for (const ing of recipe.ingredients) {
    doc.rect(50, leftY + 4, 4, 4).fill(accent);
    doc.fillColor(COLORS.text).font("Helvetica").fontSize(9)
      .text(ing, 58, leftY, { width: colW - 18, lineGap: 2 });
    leftY = doc.y + 2;
  }

  doc.y = startY;
  // Steps column
  for (let i = 0; i < recipe.steps.length; i++) {
    doc.fillColor(COLORS.gray).font("Helvetica-Bold").fontSize(9)
      .text(`${i + 1}.`, 50 + colW + 10, rightY, { width: 12 });
    doc.fillColor(COLORS.text).font("Helvetica").fontSize(9)
      .text(recipe.steps[i], 50 + colW + 24, rightY, { width: colW - 34, lineGap: 2 });
    rightY = doc.y + 2;
  }

  doc.y = Math.max(leftY, rightY) + 6;

  if (recipe.tip) {
    doc.roundedRect(50, doc.y, W, 28, 3).fill("#FFF9E6");
    doc.fillColor("#7A6000").font("Helvetica-Bold").fontSize(8.5).text("💡 Consejo:", 60, doc.y + 7);
    doc.fillColor(COLORS.text).font("Helvetica").fontSize(8.5)
      .text(recipe.tip, 60, doc.y + 7, { width: W - 20 });
    doc.y += 34;
  }

  doc.moveDown(1);
}

// ── Tracker / calendario ──────────────────────────────────────────
function drawWeeklyTracker(doc: PDFKit.PDFDocument, week: number, days: string[], accent: string) {
  const W = doc.page.width - 100;
  const cellW = W / 7;
  const y = doc.y;

  doc.fillColor(COLORS.text).font("Helvetica-Bold").fontSize(12)
    .text(`SEMANA ${week}`, 50, y);
  doc.y += 22;

  // Day headers
  const hy = doc.y;
  doc.rect(50, hy, W, 22).fill(accent);
  doc.fillColor(COLORS.white).font("Helvetica-Bold").fontSize(9);
  days.forEach((day, i) => {
    doc.text(day, 50 + i * cellW, hy + 7, { width: cellW, align: "center" });
  });
  doc.y = hy + 22;

  // Rows for tracking
  for (let row = 0; row < 3; row++) {
    const labels = ["Entreno", "Nutrición", "Agua (L)"];
    const rowY = doc.y;
    doc.rect(50, rowY, W, 26).fill(row % 2 === 0 ? COLORS.white : COLORS.light);
    doc.fillColor(COLORS.textLight).font("Helvetica").fontSize(8)
      .text(labels[row], 52, rowY + 9, { width: 48 });
    for (let col = 0; col < 7; col++) {
      doc.rect(50 + col * cellW + 2, rowY + 5, cellW - 4, 16).lineWidth(0.5)
        .strokeColor(COLORS.grayLight).stroke();
    }
    doc.y = rowY + 28;
  }
  doc.moveDown(1);
}

// ══════════════════════════════════════════════════════════════════
// FUNCIONES PÚBLICAS — cada tipo de PDF
// ══════════════════════════════════════════════════════════════════

export interface GeneratePDFOptions {
  outputPath: string;
  productName: string;
  productSku: string;
  description: string;
  tagline: string;
  accent?: AccentType;
  exercises?: Exercise[];
  recipes?: Recipe[];
  weeks?: number;
  extraSections?: Array<{ title: string; body: string }>;
}

/** PDF principal de programa de entrenamiento */
export async function generateWorkoutPDF(opts: GeneratePDFOptions): Promise<void> {
  const accent = getAccent(opts.accent);
  return new Promise((resolve, reject) => {
    const doc = new PDFDocument({ size: "A4", margin: 50, bufferPages: true });
    const stream = fs.createWriteStream(opts.outputPath);
    doc.pipe(stream);

    // ── Portada ──────────────────────────────────────────────────
    const W = doc.page.width;
    const H = doc.page.height;
    doc.rect(0, 0, W, H).fill(COLORS.primary);
    doc.rect(0, H - 6, W, 6).fill(accent);
    doc.rect(W - 6, 0, 6, H).fill(accent);

    doc.fillColor(accent)
      .font("Helvetica-Bold")
      .fontSize(11)
      .text("FITNESS BUSINESS OS", 50, 60);

    doc.fillColor(COLORS.white)
      .font("Helvetica-Bold")
      .fontSize(36)
      .text(opts.productName, 50, 100, { width: W - 100, lineGap: 5 });

    doc.fillColor(COLORS.grayLight)
      .font("Helvetica")
      .fontSize(16)
      .text(opts.tagline, 50, 200, { width: W - 100 });

    // Separador
    doc.rect(50, 260, 80, 3).fill(accent);

    doc.fillColor(COLORS.grayLight)
      .font("Helvetica")
      .fontSize(11)
      .text(opts.description, 50, 280, { width: W - 100, lineGap: 4 });

    // Meta
    const weeks = opts.weeks ?? 4;
    const exCount = opts.exercises?.length ?? 0;
    const metaItems = [
      { label: "DURACIÓN", value: `${weeks} Semanas` },
      { label: "EJERCICIOS", value: `${exCount} movimientos` },
      { label: "SKU", value: opts.productSku },
    ];
    let mx = 50;
    for (const item of metaItems) {
      doc.roundedRect(mx, H - 120, 150, 60, 4).fill("#1a2744");
      doc.fillColor(accent).font("Helvetica-Bold").fontSize(8)
        .text(item.label, mx + 12, H - 108);
      doc.fillColor(COLORS.white).font("Helvetica-Bold").fontSize(18)
        .text(item.value, mx + 12, H - 95, { width: 126 });
      mx += 165;
    }

    // ── Página índice ────────────────────────────────────────────
    addPage(doc);
    drawHeaderBar(doc, opts.productName, opts.tagline, accent);
    doc.y = 130;
    drawSectionTitle(doc, "CONTENIDO DEL PROGRAMA", accent);
    drawDivider(doc);
    const toc = [
      "Introducción al programa",
      "Cómo usar este programa",
      "Equipamiento necesario",
      "Plan de entrenamiento semanal",
      ...(Array.from({ length: weeks }, (_, i) => `Semana ${i + 1} — Rutina detallada`)),
      "Progresión y ajuste de cargas",
      "Nutrición básica",
      "Registro de progreso",
      "Preguntas frecuentes",
    ];
    drawNumberedList(doc, toc);

    // ── Introducción ─────────────────────────────────────────────
    addPage(doc);
    drawHeaderBar(doc, "Introducción", opts.productName, accent);
    doc.y = 130;
    drawSectionTitle(doc, "BIENVENIDA AL PROGRAMA", accent);
    drawBodyText(doc, `¡Felicitaciones por elegir ${opts.productName}! Esta guía fue diseñada para darte resultados reales con un plan estructurado, progresivo y adaptado a tu nivel.`);
    drawBodyText(doc, "El entrenamiento físico no es sólo cuestión de esfuerzo — es ciencia aplicada. Cada ejercicio, cada serie y cada período de descanso fue seleccionado estratégicamente para maximizar tus resultados en el menor tiempo posible.");
    drawCalloutBox(doc, "🎯 TU COMPROMISO", "Este programa requiere consistencia más que perfección. No importa si un día no podés completar todo — lo que importa es volver al día siguiente y seguir adelante.", accent);

    drawSectionTitle(doc, "CÓMO FUNCIONA ESTE PROGRAMA", accent);
    drawBulletList(doc, [
      `Duración total: ${weeks} semanas de entrenamiento progresivo`,
      "Frecuencia: 3-5 sesiones semanales según el programa",
      "Cada semana aumenta levemente la intensidad o el volumen",
      "Incluye días de descanso activo y recuperación",
      "El registro de progreso es FUNDAMENTAL — hacelo cada sesión",
    ], accent);

    drawSectionTitle(doc, "PRINCIPIOS CLAVE", accent);
    drawBulletList(doc, [
      "PROGRESIÓN: cada semana hay que hacer un poco más que la anterior",
      "TÉCNICA PRIMERO: nunca sacrifiques la forma por el peso",
      "DESCANSO: es cuando el músculo crece, no durante el entreno",
      "NUTRICIÓN: el entrenamiento es el estímulo, la comida es la construcción",
      "CONSISTENCIA: los resultados llegan con el tiempo, no de un día para el otro",
    ], accent);

    // ── Plan semanal ─────────────────────────────────────────────
    addPage(doc);
    drawHeaderBar(doc, "Plan de Entrenamiento", `${weeks} semanas de progresión`, accent);
    doc.y = 130;

    drawSectionTitle(doc, "RESUMEN DEL PLAN SEMANAL", accent);
    drawDivider(doc);

    const dayNames = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];
    const schedule = [
      "Tren inferior", "Tren superior", "DESCANSO ACTIVO", "Glúteos y piernas", "Full body", "DESCANSO", "DESCANSO",
    ];
    const W2 = doc.page.width - 100;
    const cW = W2 / 7;
    const hy2 = doc.y;
    doc.rect(50, hy2, W2, 24).fill(accent);
    doc.fillColor(COLORS.white).font("Helvetica-Bold").fontSize(9);
    dayNames.forEach((d, i) => doc.text(d, 50 + i * cW, hy2 + 8, { width: cW, align: "center" }));
    doc.y = hy2 + 24;

    const sy = doc.y;
    doc.rect(50, sy, W2, 40).fill(COLORS.light);
    schedule.forEach((s, i) => {
      const isRest = s.includes("DESCANSO");
      doc.fillColor(isRest ? COLORS.gray : COLORS.text)
        .font(isRest ? "Helvetica" : "Helvetica-Bold")
        .fontSize(8)
        .text(s, 50 + i * cW + 3, sy + 12, { width: cW - 6, align: "center" });
    });
    doc.y = sy + 48;
    doc.moveDown(0.5);

    // ── Ejercicios por semana ─────────────────────────────────────
    if (opts.exercises && opts.exercises.length > 0) {
      for (let w = 1; w <= Math.min(weeks, 4); w++) {
        addPage(doc);
        drawHeaderBar(doc, `Semana ${w}`, `Rutina detallada — ${opts.productName}`, accent);
        doc.y = 130;
        drawSectionTitle(doc, `SEMANA ${w} — EJERCICIOS`, accent);

        // Divide exercises across days
        const half = Math.ceil(opts.exercises.length / 2);
        const lower = opts.exercises.slice(0, half);
        const upper = opts.exercises.slice(half);

        doc.fillColor(COLORS.textLight).font("Helvetica-Bold").fontSize(10).text("DÍA A — TREN INFERIOR", 50, doc.y);
        doc.moveDown(0.3);
        drawExerciseTable(doc, lower, accent);

        checkPageSpace(doc, 120);
        doc.fillColor(COLORS.textLight).font("Helvetica-Bold").fontSize(10).text("DÍA B — TREN SUPERIOR", 50, doc.y);
        doc.moveDown(0.3);
        drawExerciseTable(doc, upper, accent);

        // Progresión badge
        if (w > 1) {
          drawCalloutBox(doc, `⚡ PROGRESIÓN SEMANA ${w}`, `Aumentá 2-5% el peso en los ejercicios principales respecto a la semana anterior. Si no podés completar todas las series con buena técnica, mantenés el mismo peso.`, accent);
        }
      }
    }

    // ── Registro de progreso ──────────────────────────────────────
    addPage(doc);
    drawHeaderBar(doc, "Registro de Progreso", "Tracking semanal", accent);
    doc.y = 130;

    drawSectionTitle(doc, "TRACKER SEMANAL", accent);
    drawBodyText(doc, "Completá este registro cada semana. Lo que se mide, se mejora.");
    doc.moveDown(0.5);

    for (let w = 1; w <= Math.min(weeks, 2); w++) {
      drawWeeklyTracker(doc, w, dayNames, accent);
    }

    // ── Secciones extra ───────────────────────────────────────────
    for (const section of opts.extraSections ?? []) {
      addPage(doc);
      drawHeaderBar(doc, section.title, opts.productName, accent);
      doc.y = 130;
      drawBodyText(doc, section.body);
    }

    // ── Nutrición rápida ──────────────────────────────────────────
    addPage(doc);
    drawHeaderBar(doc, "Nutrición Básica", "Guía de alimentación complementaria", accent);
    doc.y = 130;
    drawSectionTitle(doc, "PRINCIPIOS NUTRICIONALES", accent);
    drawBulletList(doc, [
      "Come proteína en cada comida: carnes magras, huevos, lácteos, legumbres",
      "Hidratate: mínimo 2-3 litros de agua por día (más los días de entreno)",
      "No salteés comidas — el cuerpo necesita combustible constante",
      "Priorizá alimentos reales sobre productos procesados",
      "El timing no es crítico — lo importante es el total del día",
    ], accent);

    drawSectionTitle(doc, "ANTES Y DESPUÉS DEL ENTRENO", accent);
    drawInfoBox(doc, "PRE-ENTRENO (30-60 min antes)", "Carbohidratos + proteína leve. Ej: tostada integral con huevo, banana con maní, avena con fruta.", accent);
    drawInfoBox(doc, "POST-ENTRENO (primeros 30 min)", "Proteína + carbohidrato. Ej: licuado de proteína, pollo con arroz, yogur griego con granola.", accent);

    // ── Página final ──────────────────────────────────────────────
    addPage(doc);
    doc.rect(0, 0, W, H).fill(COLORS.primary);
    doc.fillColor(COLORS.white).font("Helvetica-Bold").fontSize(28)
      .text("¡Éxito en el programa!", 50, H / 2 - 60, { width: W - 100, align: "center" });
    doc.fillColor(accent).font("Helvetica").fontSize(14)
      .text("El único mal entreno es el que no se hizo.", 50, H / 2, { width: W - 100, align: "center" });
    doc.fillColor(COLORS.grayLight).font("Helvetica").fontSize(10)
      .text(`${opts.productName}  |  Fitness Business OS  |  fitnessbusiness.com`, 50, H - 80, { width: W - 100, align: "center" });

    doc.flushPages();
    doc.end();
    stream.on("finish", resolve);
    stream.on("error", reject);
  });
}

/** PDF de plan nutricional */
export async function generateNutritionPDF(opts: GeneratePDFOptions): Promise<void> {
  const accent = getAccent(opts.accent);
  return new Promise((resolve, reject) => {
    const doc = new PDFDocument({ size: "A4", margin: 50, bufferPages: true });
    const stream = fs.createWriteStream(opts.outputPath);
    doc.pipe(stream);

    const W = doc.page.width;
    const H = doc.page.height;

    // Portada
    doc.rect(0, 0, W, H).fill(COLORS.primary);
    doc.rect(0, H - 6, W, 6).fill(accent);
    doc.fillColor(accent).font("Helvetica-Bold").fontSize(11).text("PLAN NUTRICIONAL — FITNESS BUSINESS OS", 50, 60);
    doc.fillColor(COLORS.white).font("Helvetica-Bold").fontSize(34)
      .text(opts.productName, 50, 100, { width: W - 100 });
    doc.fillColor(COLORS.grayLight).font("Helvetica").fontSize(14)
      .text(opts.tagline, 50, 190, { width: W - 100 });
    doc.rect(50, 240, 80, 3).fill(accent);
    doc.fillColor(COLORS.grayLight).font("Helvetica").fontSize(11)
      .text(opts.description, 50, 260, { width: W - 100, lineGap: 4 });

    // Contenido
    addPage(doc);
    drawHeaderBar(doc, opts.productName, "Plan de alimentación personalizado", accent);
    doc.y = 130;
    drawSectionTitle(doc, "INTRODUCCIÓN", accent);
    drawBodyText(doc, "Una alimentación saludable no es una dieta — es un estilo de vida. Este plan fue diseñado para ser sostenible, variado y delicioso. No se trata de restricciones extremas sino de aprender a comer bien para siempre.");
    drawCalloutBox(doc, "🎯 OBJETIVO DEL PLAN", opts.description, accent);

    // Macros explicación
    drawSectionTitle(doc, "ENTENDIENDO LOS MACRONUTRIENTES", accent);
    drawInfoBox(doc, "PROTEÍNAS (4 kcal/g)", "Construyen y reparan músculo. Fuentes: carnes, huevos, lácteos, legumbres. OBJETIVO: 1.6-2.2g por kg de peso corporal.", accent);
    drawInfoBox(doc, "CARBOHIDRATOS (4 kcal/g)", "Tu principal fuente de energía. Priorizá complejos: arroz integral, avena, batata, frutas, verduras.", accent);
    drawInfoBox(doc, "GRASAS (9 kcal/g)", "Esenciales para hormonas y absorción de vitaminas. Fuentes: palta, aceite de oliva, nueces, pescado azul.", accent);

    // Plan semanal de menús
    addPage(doc);
    drawHeaderBar(doc, "Menú Semanal", "7 días de alimentación balanceada", accent);
    doc.y = 130;

    const weekMenu = [
      { day: "Lunes", meals: ["Desayuno: Avena con fruta", "Almuerzo: Pollo con quinoa y ensalada", "Merienda: Yogur griego", "Cena: Salmón con verduras al vapor"] },
      { day: "Martes", meals: ["Desayuno: Tostadas integrales con palta", "Almuerzo: Lentejas con verduras", "Merienda: Fruta + nueces", "Cena: Revuelto de claras con vegetales"] },
      { day: "Miércoles", meals: ["Desayuno: Smoothie verde + huevos", "Almuerzo: Ensalada de atún completa", "Merienda: Energy balls", "Cena: Pollo al horno con batata"] },
      { day: "Jueves", meals: ["Desayuno: Pancakes de banana", "Almuerzo: Bowl de pollo y arroz", "Merienda: Hummus + verduras crudas", "Cena: Tortilla de papas + ensalada"] },
      { day: "Viernes", meals: ["Desayuno: Yogur griego con granola", "Almuerzo: Tapa de asado con ensalada", "Merienda: Banana + mantequilla maní", "Cena: Wok de pollo con vegetales"] },
      { day: "Sábado", meals: ["Desayuno: Avena + fruta de temporada", "Almuerzo: Milanesa al horno + puré de zapallo", "Merienda: Licuado de proteínas", "Cena: Cazuela de vegetales con arroz"] },
      { day: "Domingo", meals: ["Desayuno: Budín de chía + café", "Almuerzo: Asado familiar (proteína + ensalada)", "Merienda: Fruta + infusión", "Cena: Revuelto de vegetales con tostadas"] },
    ];

    for (const day of weekMenu) {
      checkPageSpace(doc, 90);
      const dy = doc.y;
      doc.rect(50, dy, doc.page.width - 100, 20).fill(accent);
      doc.fillColor(COLORS.white).font("Helvetica-Bold").fontSize(10).text(day.day.toUpperCase(), 62, dy + 6);
      doc.y = dy + 24;
      for (const meal of day.meals) {
        doc.fillColor(COLORS.text).font("Helvetica").fontSize(9.5)
          .text(`• ${meal}`, 62, doc.y, { width: doc.page.width - 124, lineGap: 2 });
        doc.y += 14;
      }
      doc.moveDown(0.5);
    }

    // Recetas si las hay
    if (opts.recipes && opts.recipes.length > 0) {
      addPage(doc);
      drawHeaderBar(doc, "Recetas Incluidas", `${opts.recipes.length} recetas saludables`, accent);
      doc.y = 130;
      drawSectionTitle(doc, "RECETARIO", accent);
      for (const recipe of opts.recipes) {
        checkPageSpace(doc, 200);
        drawRecipeCard(doc, recipe, accent);
      }
    }

    doc.flushPages();
    doc.end();
    stream.on("finish", resolve);
    stream.on("error", reject);
  });
}

/** PDF de recetario */
export async function generateRecipeBookPDF(opts: GeneratePDFOptions): Promise<void> {
  const accent = getAccent(opts.accent);
  return new Promise((resolve, reject) => {
    const doc = new PDFDocument({ size: "A4", margin: 50, bufferPages: true });
    const stream = fs.createWriteStream(opts.outputPath);
    doc.pipe(stream);

    const W = doc.page.width;
    const H = doc.page.height;
    doc.rect(0, 0, W, H).fill(COLORS.primary);
    doc.fillColor(accent).font("Helvetica-Bold").fontSize(11).text("RECETARIO SALUDABLE — FITNESS BUSINESS OS", 50, 60);
    doc.fillColor(COLORS.white).font("Helvetica-Bold").fontSize(34)
      .text(opts.productName, 50, 100, { width: W - 100 });
    doc.fillColor(COLORS.grayLight).font("Helvetica").fontSize(14).text(opts.tagline, 50, 190, { width: W - 100 });

    const categories = ["desayuno", "almuerzo", "cena", "snack", "postre", "bebida"] as const;
    for (const cat of categories) {
      const catRecipes = opts.recipes?.filter(r => r.category === cat) ?? [];
      if (!catRecipes.length) continue;
      addPage(doc);
      drawHeaderBar(doc, cat.toUpperCase(), opts.productName, accent);
      doc.y = 130;
      drawSectionTitle(doc, `${catRecipes.length} RECETAS DE ${cat.toUpperCase()}`, accent);
      for (const recipe of catRecipes) {
        checkPageSpace(doc, 200);
        drawRecipeCard(doc, recipe, accent);
      }
    }

    doc.flushPages();
    doc.end();
    stream.on("finish", resolve);
    stream.on("error", reject);
  });
}

/** PDF de desafío de 30 días */
export async function generateChallengePDF(opts: GeneratePDFOptions): Promise<void> {
  const accent = getAccent(opts.accent);
  return new Promise((resolve, reject) => {
    const doc = new PDFDocument({ size: "A4", margin: 50, bufferPages: true });
    const stream = fs.createWriteStream(opts.outputPath);
    doc.pipe(stream);

    const W = doc.page.width;
    const H = doc.page.height;

    // Portada
    doc.rect(0, 0, W, H).fill(COLORS.primary);
    doc.fillColor(accent).font("Helvetica-Bold").fontSize(48).text("30", 50, 80, { width: 100 });
    doc.fillColor(COLORS.white).font("Helvetica-Bold").fontSize(30).text("DÍAS", 130, 94);
    doc.fillColor(COLORS.white).font("Helvetica-Bold").fontSize(28)
      .text(opts.productName, 50, 160, { width: W - 100 });
    doc.fillColor(COLORS.grayLight).font("Helvetica").fontSize(13).text(opts.tagline, 50, 240, { width: W - 100 });

    // Calendario de 30 días
    addPage(doc);
    drawHeaderBar(doc, "Calendario del Desafío", "30 días de transformación", accent);
    doc.y = 130;
    drawSectionTitle(doc, "TUS 30 DÍAS", accent);

    const cellW = (doc.page.width - 100) / 7;
    const cellH = 38;
    const dayLabels = ["L", "M", "X", "J", "V", "S", "D"];
    const hy = doc.y;
    doc.rect(50, hy, doc.page.width - 100, 22).fill(accent);
    doc.fillColor(COLORS.white).font("Helvetica-Bold").fontSize(10);
    dayLabels.forEach((d, i) => doc.text(d, 50 + i * cellW, hy + 7, { width: cellW, align: "center" }));
    doc.y = hy + 22;

    // 5 semanas = 35 celdas
    for (let row = 0; row < 5; row++) {
      const rowY = doc.y;
      for (let col = 0; col < 7; col++) {
        const dayNum = row * 7 + col + 1;
        const bg = dayNum <= 30 ? (dayNum % 2 === 0 ? COLORS.white : COLORS.light) : "#f0f0f0";
        doc.rect(50 + col * cellW, rowY, cellW, cellH).fill(bg);
        if (dayNum <= 30) {
          doc.fillColor(accent).font("Helvetica-Bold").fontSize(10)
            .text(`${dayNum}`, 50 + col * cellW, rowY + 4, { width: cellW, align: "center" });
          doc.fillColor(COLORS.textLight).font("Helvetica").fontSize(7.5)
            .text("□ Completado", 50 + col * cellW + 4, rowY + 22, { width: cellW - 8 });
        } else {
          doc.fillColor(COLORS.grayLight).font("Helvetica").fontSize(8)
            .text("-", 50 + col * cellW, rowY + 14, { width: cellW, align: "center" });
        }
      }
      doc.y = rowY + cellH;
    }
    doc.moveDown(1);

    // Plan diario
    addPage(doc);
    drawHeaderBar(doc, "Plan Diario", "Qué hacer cada día", accent);
    doc.y = 130;
    drawSectionTitle(doc, "ESTRUCTURA DE CADA DÍA", accent);
    drawInfoBox(doc, "MAÑANA (al despertar)", "Vaso de agua con limón + 5 min de respiración o meditación + revisá tu objetivo del día", accent);
    drawInfoBox(doc, "EJERCICIO DIARIO", "Duración: 20-45 min según el día. Siempre empezá con 5 min de calentamiento y terminá con 5 min de estiramiento.", accent);
    drawInfoBox(doc, "NUTRICIÓN", "Seguí las pautas del plan nutricional incluido. 3 comidas principales + 1-2 colaciones.", accent);
    drawInfoBox(doc, "NOCHE", "Anotá tu estado de ánimo, qué comiste y cómo te sentiste. Esto es CLAVE para tu progreso.", accent);

    if (opts.exercises && opts.exercises.length > 0) {
      addPage(doc);
      drawHeaderBar(doc, "Ejercicios del Desafío", "30 días de movimiento", accent);
      doc.y = 130;
      drawSectionTitle(doc, "EJERCICIOS PRINCIPALES", accent);
      drawExerciseTable(doc, opts.exercises, accent);
    }

    doc.flushPages();
    doc.end();
    stream.on("finish", resolve);
    stream.on("error", reject);
  });
}

/** PDF genérico para mindset / guías / otros */
export async function generateGuidePDF(opts: GeneratePDFOptions): Promise<void> {
  const accent = getAccent(opts.accent);
  return new Promise((resolve, reject) => {
    const doc = new PDFDocument({ size: "A4", margin: 50, bufferPages: true });
    const stream = fs.createWriteStream(opts.outputPath);
    doc.pipe(stream);

    const W = doc.page.width;
    const H = doc.page.height;
    doc.rect(0, 0, W, H).fill(COLORS.primary);
    doc.fillColor(accent).font("Helvetica-Bold").fontSize(11).text("FITNESS BUSINESS OS", 50, 60);
    doc.fillColor(COLORS.white).font("Helvetica-Bold").fontSize(34)
      .text(opts.productName, 50, 100, { width: W - 100 });
    doc.fillColor(COLORS.grayLight).font("Helvetica").fontSize(14).text(opts.tagline, 50, 190, { width: W - 100 });
    doc.fillColor(COLORS.grayLight).font("Helvetica").fontSize(11).text(opts.description, 50, 240, { width: W - 100, lineGap: 4 });

    addPage(doc);
    drawHeaderBar(doc, opts.productName, opts.tagline, accent);
    doc.y = 130;

    for (const section of opts.extraSections ?? []) {
      checkPageSpace(doc, 80);
      drawSectionTitle(doc, section.title, accent);
      drawBodyText(doc, section.body);
      drawDivider(doc);
    }

    if (opts.exercises && opts.exercises.length > 0) {
      addPage(doc);
      drawHeaderBar(doc, "Ejercicios Incluidos", opts.productName, accent);
      doc.y = 130;
      drawExerciseTable(doc, opts.exercises, accent);
    }

    if (opts.recipes && opts.recipes.length > 0) {
      addPage(doc);
      drawHeaderBar(doc, "Recetas Recomendadas", opts.productName, accent);
      doc.y = 130;
      for (const recipe of opts.recipes.slice(0, 6)) {
        checkPageSpace(doc, 180);
        drawRecipeCard(doc, recipe, accent);
      }
    }

    doc.flushPages();
    doc.end();
    stream.on("finish", resolve);
    stream.on("error", reject);
  });
}

/** PDF de registro de entrenamiento (planilla en blanco) */
export async function generateTrackingSheetPDF(productName: string, outputPath: string, accent: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const doc = new PDFDocument({ size: "A4", margin: 50, bufferPages: true });
    const stream = fs.createWriteStream(outputPath);
    doc.pipe(stream);

    for (let week = 1; week <= 4; week++) {
      if (week > 1) addPage(doc);
      drawHeaderBar(doc, `Registro — Semana ${week}`, productName, accent);
      doc.y = 130;

      // Table per day
      for (let session = 1; session <= 3; session++) {
        checkPageSpace(doc, 120);
        const dy = doc.y;
        const W2 = doc.page.width - 100;
        doc.rect(50, dy, W2, 20).fill(accent);
        doc.fillColor(COLORS.white).font("Helvetica-Bold").fontSize(9)
          .text(`SESIÓN ${session}  —  Fecha: _____________  Hora: _______  Peso corporal: _______kg`, 62, dy + 6);
        doc.y = dy + 22;

        // Exercise rows
        const rowH = 22;
        const cols = [0, W2 * 0.35, W2 * 0.55, W2 * 0.72, W2 * 0.87];
        const hRow = doc.y;
        doc.rect(50, hRow, W2, rowH).fill(COLORS.grayLight);
        ["Ejercicio", "Kg", "Serie 1", "Serie 2", "Serie 3"].forEach((h, i) => {
          doc.fillColor(COLORS.text).font("Helvetica-Bold").fontSize(8)
            .text(h, 50 + cols[i] + 3, hRow + 7, { width: (cols[i + 1] ?? W2) - cols[i] - 6 });
        });
        doc.y = hRow + rowH;

        for (let row = 0; row < 6; row++) {
          const ry = doc.y;
          doc.rect(50, ry, W2, rowH).fill(row % 2 === 0 ? COLORS.white : COLORS.light);
          cols.forEach((x, i) => {
            const w2 = (cols[i + 1] ?? W2) - x - 6;
            doc.rect(50 + x + 2, ry + 4, w2 + 2, 13).lineWidth(0.3)
              .strokeColor(COLORS.grayLight).stroke();
          });
          doc.y = ry + rowH;
        }
        doc.moveDown(0.8);
      }
    }

    doc.flushPages();
    doc.end();
    stream.on("finish", resolve);
    stream.on("error", reject);
  });
}

/** PDF de lista de compras (en blanco con categorías) */
export async function generateShoppingListPDF(productName: string, outputPath: string, accent: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const doc = new PDFDocument({ size: "A4", margin: 50, bufferPages: true });
    const stream = fs.createWriteStream(outputPath);
    doc.pipe(stream);

    drawHeaderBar(doc, "Lista de Compras", productName, accent);
    doc.y = 130;

    const categories = [
      { name: "🥩 Proteínas", items: ["Pechuga de pollo", "Carne picada magra", "Merluza / salmón", "Huevos", "Atún en lata", "Yogur griego"] },
      { name: "🥦 Verduras y Hortalizas", items: ["Espinaca", "Brócoli", "Pimiento", "Zapallito", "Zanahoria", "Tomate", "Pepino", "Lechuga"] },
      { name: "🍓 Frutas", items: ["Banana", "Manzana", "Naranja", "Frutillas", "Kiwi", "Arándanos"] },
      { name: "🌾 Carbohidratos", items: ["Avena arrollada", "Arroz integral", "Batata", "Pan integral", "Quinoa", "Papa"] },
      { name: "🥑 Grasas Saludables", items: ["Palta", "Aceite de oliva", "Nueces / almendras", "Semillas de chía", "Mantequilla de maní"] },
      { name: "🧴 Lácteos / Otros", items: ["Leche descremada o vegetal", "Queso cottage", "Caldo de verduras", "Aceitunas"] },
    ];

    const W2 = doc.page.width - 100;
    const colW = (W2 - 10) / 2;

    let col = 0;
    let startY = doc.y;
    let colY = [startY, startY];

    for (const cat of categories) {
      const targetCol = col % 2;
      const x = 50 + targetCol * (colW + 10);
      let y = colY[targetCol];

      if (y > doc.page.height - 150) {
        addPage(doc);
        colY = [130, 130];
        y = 130;
        drawHeaderBar(doc, "Lista de Compras (cont.)", productName, accent);
      }

      doc.rect(x, y, colW, 20).fill(accent);
      doc.fillColor(COLORS.white).font("Helvetica-Bold").fontSize(9)
        .text(cat.name, x + 6, y + 6, { width: colW - 12 });
      y += 22;

      for (const item of cat.items) {
        doc.rect(x, y, colW, 18).fill(y % 36 === 0 ? COLORS.white : COLORS.light);
        doc.rect(x + 6, y + 6, 10, 10).lineWidth(0.5).strokeColor(accent).stroke();
        doc.fillColor(COLORS.text).font("Helvetica").fontSize(9)
          .text(item, x + 22, y + 5, { width: colW - 30 });
        y += 18;
      }
      y += 8;
      colY[targetCol] = y;
      col++;
    }

    doc.flushPages();
    doc.end();
    stream.on("finish", resolve);
    stream.on("error", reject);
  });
}
