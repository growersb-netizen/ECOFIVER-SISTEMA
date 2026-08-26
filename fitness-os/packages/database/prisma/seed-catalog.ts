/**
 * Seed del catálogo de productos — 20 productos de muestra publicados.
 * Ejecución: tsx prisma/seed-catalog.ts
 * Requiere: FITNESS_API_URL + FITNESS_ADMIN_TOKEN en env
 */

const API_URL = process.env["FITNESS_API_URL"] ?? "https://fitness-api-production-fff4.up.railway.app";
const TOKEN = process.env["FITNESS_ADMIN_TOKEN"] ?? "";

if (!TOKEN) {
  console.error("❌ FITNESS_ADMIN_TOKEN requerido");
  process.exit(1);
}

const headers = {
  "Content-Type": "application/json",
  "Authorization": `Bearer ${TOKEN}`,
  "X-Tenant-Slug": "fitness-business-os",
};

async function post(path: string, body: unknown) {
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  const data = await res.json() as Record<string, unknown>;
  if (!res.ok) throw new Error(`POST ${path}: ${JSON.stringify(data)}`);
  return data;
}

async function patch(path: string, body: unknown) {
  const res = await fetch(`${API_URL}${path}`, {
    method: "PATCH",
    headers,
    body: JSON.stringify(body),
  });
  const data = await res.json() as Record<string, unknown>;
  if (!res.ok) throw new Error(`PATCH ${path}: ${JSON.stringify(data)}`);
  return data;
}

async function get(path: string) {
  const res = await fetch(`${API_URL}${path}`, { headers });
  return res.json() as Promise<Record<string, unknown>>;
}

// ── Categorías — slugs reales generados por el servidor ────────────
// (obtenidos de GET /api/v1/categories el 2026-08-26)
const CATEGORY_SLUG_MAP: Record<string, string> = {
  // slugs del seed definidos en este archivo → slug real en BD
  "gluteos-piernas":  "gluteos-y-piernas",
  "core-abdomen":     "core-y-abdomen",
  "tren-superior":    "tren-superior",
  "nutricion-recetas":"nutricion-y-recetas",
  "yoga-flexibilidad":"yoga-y-flexibilidad",
  "postparto":        "postparto",
  "desafios-30-dias": "desafios-30-dias",
  "mindset-bienestar":"mindset-y-bienestar",
  "packs-bundles":    "packs-y-bundles",
  "hombres":          "hombres",
};

const CATEGORIES = [
  { name: "Glúteos y Piernas", slug: "gluteos-y-piernas", description: "Programas enfocados en tren inferior, glúteos y piernas" },
  { name: "Core y Abdomen", slug: "core-y-abdomen", description: "Trabajo de abdomen, core y zona lumbar" },
  { name: "Tren Superior", slug: "tren-superior", description: "Brazos, pecho, espalda y hombros" },
  { name: "Nutrición y Recetas", slug: "nutricion-y-recetas", description: "Planes nutricionales y recetarios saludables" },
  { name: "Yoga y Flexibilidad", slug: "yoga-y-flexibilidad", description: "Yoga, stretching y movilidad" },
  { name: "Postparto", slug: "postparto", description: "Recuperación y fitness después del parto" },
  { name: "Desafíos 30 Días", slug: "desafios-30-dias", description: "Retos de transformación de 30 días" },
  { name: "Mindset y Bienestar", slug: "mindset-y-bienestar", description: "Mentalidad, motivación y bienestar integral" },
  { name: "Packs y Bundles", slug: "packs-y-bundles", description: "Combos y paquetes completos a precio especial" },
  { name: "Hombres", slug: "hombres", description: "Programas diseñados especialmente para hombres" },
];

// ── Productos ──────────────────────────────────────────────────────

interface ProductDef {
  sku: string;
  name: string;
  description: string;
  type: string;
  categorySlug: string;
  priceARS: number;
  tags: string[];
  weeks?: number;
  level: string;
}

const PRODUCTS: ProductDef[] = [
  // Glúteos
  {
    sku: "GT-001", name: "Plan Glúteos Perfectos 8 Semanas", categorySlug: "gluteos-y-piernas",
    description: "Plan intensivo de 8 semanas para levantar, tonificar y dar forma a tus glúteos. Incluye plan de entrenamiento, guía nutricional y tracking semanal.",
    type: "PDF_GUIDE", priceARS: 4900, tags: ["Para Mujeres"], weeks: 8, level: "intermedio",
  },
  {
    sku: "GT-002", name: "Glúteos desde Cero — 4 Semanas", categorySlug: "gluteos-y-piernas",
    description: "El programa ideal para principiantes. 4 semanas de entrenamiento progresivo sin necesidad de equipo especial.",
    type: "PDF_GUIDE", priceARS: 2900, tags: ["Para Mujeres"], weeks: 4, level: "principiante",
  },
  {
    sku: "GP-001", name: "Piernas de Fuego 6 Semanas", categorySlug: "gluteos-y-piernas",
    description: "Trabajo completo de tren inferior: cuádriceps, isquiotibiales, glúteos y pantorrillas. Con bandas elásticas.",
    type: "PDF_GUIDE", priceARS: 3900, tags: ["Para Mujeres"], weeks: 6, level: "intermedio",
  },
  // Core
  {
    sku: "AC-001", name: "Abdomen Plano 30 Días", categorySlug: "core-y-abdomen",
    description: "Plan de 30 días de trabajo de core para tonificar el abdomen y fortalecer la zona lumbar. Sin equipamiento.",
    type: "PDF_GUIDE", priceARS: 2900, tags: ["Para Todos"], weeks: 4, level: "principiante",
  },
  {
    sku: "AC-002", name: "Core Funcional Avanzado", categorySlug: "core-y-abdomen",
    description: "Entrenamiento funcional de core para nivel avanzado. Incluye ejercicios de estabilización y fuerza.",
    type: "PDF_GUIDE", priceARS: 4500, tags: ["Para Todos"], weeks: 8, level: "avanzado",
  },
  // Nutrición
  {
    sku: "PN-001", name: "Plan Nutricional Semana Santa Fit", categorySlug: "nutricion-y-recetas",
    description: "Guía nutricional de 4 semanas con recetario de 50 recetas saludables, lista de compras y macros.",
    type: "PDF_GUIDE", priceARS: 3900, tags: ["Para Mujeres"], level: "principiante",
  },
  {
    sku: "PN-002", name: "Recetario Fit 100 Recetas", categorySlug: "nutricion-y-recetas",
    description: "100 recetas saludables organizadas por desayuno, almuerzo, cena y snacks. Incluye valores nutricionales.",
    type: "EBOOK", priceARS: 2500, tags: ["Para Todos"], level: "principiante",
  },
  {
    sku: "PN-003", name: "Plan Definición 12 Semanas", categorySlug: "nutricion-y-recetas",
    description: "Plan nutricional de definición para 12 semanas con seguimiento de macros y estrategias avanzadas.",
    type: "PDF_GUIDE", priceARS: 5900, tags: ["Para Mujeres"], weeks: 12, level: "avanzado",
  },
  // Yoga
  {
    sku: "YF-001", name: "Yoga para Principiantes", categorySlug: "yoga-flexibilidad",
    description: "Guía completa de yoga para principiantes. 28 posturas explicadas con instrucciones claras y rutinas semanales.",
    type: "PDF_GUIDE", priceARS: 2900, tags: ["Para Mujeres"], weeks: 4, level: "principiante",
  },
  {
    sku: "YF-002", name: "Movilidad y Flexibilidad Total", categorySlug: "yoga-flexibilidad",
    description: "Programa de 6 semanas para mejorar la movilidad articular y la flexibilidad de todo el cuerpo.",
    type: "PDF_GUIDE", priceARS: 3500, tags: ["Para Todos"], weeks: 6, level: "principiante",
  },
  // Postparto
  {
    sku: "PT-001", name: "Recuperación Postparto Segura", categorySlug: "postparto",
    description: "Programa especializado de 8 semanas para la recuperación física después del parto. Seguro y progresivo.",
    type: "PDF_GUIDE", priceARS: 4900, tags: ["Para Mujeres"], weeks: 8, level: "principiante",
  },
  {
    sku: "PT-002", name: "Abdomen Diástasis — Recuperación", categorySlug: "postparto",
    description: "Guía específica para cerrar la diástasis abdominal postparto. Con ejercicios terapéuticos y progresión.",
    type: "PDF_GUIDE", priceARS: 3900, tags: ["Para Mujeres"], weeks: 6, level: "principiante",
  },
  // Desafíos
  {
    sku: "D30-001", name: "Desafío 30 Días Squat Challenge", categorySlug: "desafios-30-dias",
    description: "El famoso squat challenge: 30 días progresivos para transformar tus glúteos y piernas.",
    type: "CHALLENGE", priceARS: 1900, tags: ["Para Mujeres"], level: "principiante",
  },
  {
    sku: "D30-002", name: "Desafío 30 Días Full Body", categorySlug: "desafios-30-dias",
    description: "30 días de entrenamiento full body para transformar tu cuerpo. Una sesión diaria de 30-45 minutos.",
    type: "CHALLENGE", priceARS: 2500, tags: ["Para Todos"], level: "intermedio",
  },
  // Mindset
  {
    sku: "MH-001", name: "Diario de Bienestar y Hábitos", categorySlug: "mindset-y-bienestar",
    description: "Diario digital de 90 días para construir hábitos saludables, mejorar el mindset y mantener la motivación.",
    type: "TEMPLATE", priceARS: 1900, tags: ["Para Todos"], level: "principiante",
  },
  // Hombres
  {
    sku: "MASC-001", name: "Plan Hipertrofia Hombres 12 Semanas", categorySlug: "hombres",
    description: "Plan de 12 semanas de hipertrofia muscular para hombres. Periodización, nutrición y suplementación.",
    type: "PDF_GUIDE", priceARS: 6900, tags: ["Para Hombres"], weeks: 12, level: "intermedio",
  },
  {
    sku: "MASC-002", name: "Fuerza y Definición Hombres", categorySlug: "hombres",
    description: "Programa de 8 semanas para ganar fuerza y perder grasa simultáneamente. Para hombres intermedios.",
    type: "PDF_GUIDE", priceARS: 5900, tags: ["Para Hombres"], weeks: 8, level: "intermedio",
  },
  // Bundles
  {
    sku: "VIP-001", name: "Pack VIP Transformación Total", categorySlug: "packs-y-bundles",
    description: "El pack más completo: Plan de entrenamiento 12 sem + Nutrición + Recetario + Mentalidad + Diario de hábitos. TODO lo que necesitás para tu transformación.",
    type: "BUNDLE", priceARS: 14900, tags: ["Para Mujeres"], weeks: 12, level: "intermedio",
  },
  {
    sku: "VIP-002", name: "Pack Principiante Completo", categorySlug: "packs-y-bundles",
    description: "Todo para empezar: Programa 4 semanas + Nutrición básica + Guía de inicio. El pack ideal para dar el primer paso.",
    type: "BUNDLE", priceARS: 5900, tags: ["Para Todos"], weeks: 4, level: "principiante",
  },
  {
    sku: "FM-001", name: "Plan Femenino 360° — 8 Semanas", categorySlug: "gluteos-y-piernas",
    description: "El programa femenino más completo: Entrenamiento, nutrición, mentalidad y tracking integrado. Una experiencia de transformación 360°.",
    type: "PDF_GUIDE", priceARS: 8900, tags: ["Para Mujeres"], weeks: 8, level: "intermedio",
  },
];

// ── Main ───────────────────────────────────────────────────────────

async function main() {
  console.log(`\n🌱 SEED DEL CATÁLOGO — ${API_URL}\n`);

  // 1. Crear categorías
  console.log("📁 Creando categorías...");
  const catMap: Record<string, string> = {};
  // Primero traer todas las categorías existentes
  const existingCats = await get("/api/v1/categories") as { data?: Array<{ id: string; slug: string; name: string }> };
  const catBySlug = new Map<string, string>();
  for (const c of existingCats.data ?? []) catBySlug.set(c.slug, c.id);

  for (const cat of CATEGORIES) {
    if (catBySlug.has(cat.slug)) {
      catMap[cat.slug] = catBySlug.get(cat.slug)!;
      console.log(`  ⚠️  ${cat.name} ya existe → ${catMap[cat.slug]}`);
      continue;
    }
    try {
      const res = await post("/api/v1/categories", { name: cat.name, description: cat.description }) as { data?: { id: string; slug: string }; id?: string; slug?: string };
      const id = (res.data?.id ?? res.id) as string;
      const slug = (res.data?.slug ?? res.slug ?? cat.slug) as string;
      catMap[slug] = id;
      catMap[cat.slug] = id; // map both ways
      console.log(`  ✅ ${cat.name} → ${id}`);
    } catch (e) {
      console.log(`  ❌ ${cat.name}: ${(e as Error).message}`);
    }
  }

  // 2. Crear + publicar productos
  console.log("\n📦 Creando productos...");
  let created = 0, skipped = 0, errors = 0;

  for (const prod of PRODUCTS) {
    const categoryId = catMap[prod.categorySlug];
    if (!categoryId) {
      console.log(`  ❌ ${prod.sku}: categoría ${prod.categorySlug} no encontrada`);
      errors++;
      continue;
    }

    try {
      // Crear
      const res = await post("/api/v1/products", {
        sku: prod.sku,
        name: prod.name,
        description: prod.description,
        type: prod.type,
        categoryId,
        tags: prod.tags,
        level: prod.level,
        ...(prod.weeks && { durationWeeks: prod.weeks }),
        prices: [
          {
            basePrice: prod.priceARS,
            currency: "ARS",
            channel: "WEB",
          },
        ],
        content: {
          shortDescription: prod.description.substring(0, 200),
          targetAudience: prod.tags[0] ?? "Para Todos",
          whatYouGet: [
            "PDF descargable de alta calidad",
            "Plan semanal detallado",
            "Soporte por email",
            prod.weeks ? `Programa de ${prod.weeks} semanas` : "Contenido completo",
          ],
        },
      }) as { data?: { id: string }; id?: string };

      const productId = ((res.data?.id ?? res.id) as string);

      // Publicar
      await post(`/api/v1/products/${productId}/publish`, {});

      console.log(`  ✅ [${prod.sku}] ${prod.name} → PUBLISHED`);
      created++;
    } catch (e) {
      const msg = (e as Error).message;
      if (msg.includes("SKU ya existe")) {
        console.log(`  ⏭  [${prod.sku}] Ya existe, saltando`);
        skipped++;
      } else {
        console.log(`  ❌ [${prod.sku}] ${prod.name}: ${msg}`);
        errors++;
      }
    }
  }

  console.log(`\n📊 RESULTADO: ${created} creados | ${skipped} saltados | ${errors} errores`);
  console.log("\n✨ Seed completado\n");
}

main().catch((e) => {
  console.error("Fatal:", e);
  process.exit(1);
});
