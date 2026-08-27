/**
 * bundle-zips.ts — Empaquetador de ZIPs para descarga manual
 *
 * Uso:
 *   # Un producto individual:
 *   pnpm bundle-zips GT-001
 *
 *   # Grupo de productos (por prefijo):
 *   pnpm bundle-zips GT
 *   pnpm bundle-zips GP
 *   pnpm bundle-zips MASC
 *
 *   # Grupo personalizado (lista de SKUs):
 *   pnpm bundle-zips GT-001,GT-002,GT-003
 *
 *   # Todos los productos:
 *   pnpm bundle-zips ALL
 *
 * Output: fitness-os/generated/bundles/<nombre>.zip
 *
 * El archivo generado puede adjuntarse manualmente a una venta o
 * enviarse por email. Para adjuste automático post-venta, usar R2.
 */

import fs from "fs";
import path from "path";
import archiver from "archiver";

const ZIPS_DIR = path.resolve(process.cwd(), "generated/zips");
const BUNDLES_DIR = path.resolve(process.cwd(), "generated/bundles");

// ── Grupos predefinidos ───────────────────────────────────────────────
const GROUPS: Record<string, { label: string; skus: string[] }> = {
  GT: { label: "Guias-Entrenamiento", skus: [] },
  GP: { label: "Gluteos-Piernas", skus: [] },
  AC: { label: "Abdomen-Core", skus: [] },
  EC: { label: "Ejercicios-Casa", skus: [] },
  PN: { label: "Planes-Nutricion", skus: [] },
  YF: { label: "Yoga-Flexibilidad", skus: [] },
  PT: { label: "Programas-Transformacion", skus: [] },
  PR: { label: "Postparto-Recuperacion", skus: [] },
  MH: { label: "Mindset-Habitos", skus: [] },
  RF: { label: "Recetas-Fit", skus: [] },
  D30: { label: "Desafios-30-Dias", skus: [] },
  MASC: { label: "Para-Hombres", skus: [] },
  FM: { label: "Fuerza-Musculacion", skus: [] },
  RD: { label: "Rendimiento-Deportivo", skus: [] },
  VIP: { label: "Packs-VIP", skus: [] },
};

// Poblar los grupos desde el directorio de ZIPs
function populateGroups() {
  const files = fs.readdirSync(ZIPS_DIR).filter(f => f.endsWith(".zip"));
  for (const file of files) {
    const sku = file.replace(".zip", "");
    // Extraer prefijo (todo antes del último guion + número)
    const prefix = sku.replace(/-\d+$/, "");
    if (GROUPS[prefix]) {
      GROUPS[prefix].skus.push(sku);
    }
  }
  // Ordenar cada grupo
  for (const g of Object.values(GROUPS)) {
    g.skus.sort();
  }
}

// ── ZIP helper ────────────────────────────────────────────────────────
async function createBundleZip(skus: string[], outputPath: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const output = fs.createWriteStream(outputPath);
    const archive = archiver("zip", { zlib: { level: 6 } });
    output.on("close", resolve);
    archive.on("error", reject);
    archive.pipe(output);

    let added = 0;
    for (const sku of skus) {
      const zipPath = path.join(ZIPS_DIR, `${sku}.zip`);
      if (fs.existsSync(zipPath)) {
        archive.file(zipPath, { name: `${sku}.zip` });
        added++;
      } else {
        console.warn(`  ⚠ ZIP no encontrado: ${sku}.zip (ignorado)`);
      }
    }

    if (added === 0) {
      archive.destroy();
      reject(new Error("No se encontraron ZIPs para empaquetar"));
      return;
    }
    archive.finalize();
  });
}

// ── Resolver argumento ────────────────────────────────────────────────
function resolveArgument(arg: string): { label: string; skus: string[] } {
  const upper = arg.toUpperCase();

  // "ALL" — todos los productos
  if (upper === "ALL") {
    const all = Object.values(GROUPS).flatMap(g => g.skus).sort();
    return { label: "Todos-los-Productos", skus: all };
  }

  // Grupo por prefijo (ej: "GT", "MASC")
  if (GROUPS[upper]) {
    return { label: GROUPS[upper].label, skus: GROUPS[upper].skus };
  }

  // SKU individual (ej: "GT-001")
  if (/^[A-Z]+-\d+$/i.test(arg)) {
    return { label: arg.toUpperCase(), skus: [arg.toUpperCase()] };
  }

  // Lista separada por comas (ej: "GT-001,GT-002,GT-003")
  if (arg.includes(",")) {
    const skus = arg.split(",").map(s => s.trim().toUpperCase()).filter(Boolean);
    const label = skus.length <= 3 ? skus.join("-") : `${skus[0]}-y-${skus.length - 1}-mas`;
    return { label, skus };
  }

  throw new Error(`Argumento no reconocido: "${arg}"\nUso: pnpm bundle-zips [SKU|GRUPO|SKU1,SKU2,...|ALL]`);
}

// ── Main ──────────────────────────────────────────────────────────────
async function main() {
  const arg = process.argv[2];

  if (!arg) {
    console.log(`
FITNESS BUSINESS OS — Empaquetador de ZIPs para descarga manual
════════════════════════════════════════════════════════════════

Uso:
  pnpm bundle-zips <argumento>

Argumentos:
  ALL               → Todos los 205 productos en un único ZIP
  GT                → Todos los productos de Guías de Entrenamiento
  GP                → Todos los productos de Glúteos y Piernas
  AC                → Abdomen y Core
  EC                → Ejercicios en Casa
  PN                → Planes Nutricionales
  YF                → Yoga y Flexibilidad
  PT                → Programas de Transformación
  PR                → Postparto y Recuperación
  MH                → Mindset y Hábitos
  RF                → Recetarios Fit
  D30               → Desafíos 30 Días
  MASC              → Productos para Hombres
  FM                → Fuerza y Musculación
  RD                → Rendimiento Deportivo
  VIP               → Packs VIP y Bundles
  GT-001            → Producto individual
  GT-001,GT-002     → Lista personalizada de SKUs

Output: fitness-os/generated/bundles/

Grupos disponibles con sus SKUs:
`);
    populateGroups();
    for (const [prefix, { label, skus }] of Object.entries(GROUPS)) {
      if (skus.length > 0) {
        console.log(`  ${prefix.padEnd(6)} (${label}) — ${skus.length} productos`);
      }
    }
    console.log("");
    process.exit(0);
  }

  populateGroups();

  if (!fs.existsSync(BUNDLES_DIR)) {
    fs.mkdirSync(BUNDLES_DIR, { recursive: true });
  }

  let resolved: { label: string; skus: string[] };
  try {
    resolved = resolveArgument(arg);
  } catch (err) {
    console.error(`❌ ${(err as Error).message}`);
    process.exit(1);
  }

  const { label, skus } = resolved;
  const timestamp = new Date().toISOString().slice(0, 10); // YYYY-MM-DD
  const outputName = `FitnessBusinessOS-${label}-${timestamp}.zip`;
  const outputPath = path.join(BUNDLES_DIR, outputName);

  console.log(`\n📦 Creando bundle: ${outputName}`);
  console.log(`   ${skus.length} productos incluidos:`);
  if (skus.length <= 10) {
    skus.forEach(s => console.log(`   · ${s}`));
  } else {
    skus.slice(0, 5).forEach(s => console.log(`   · ${s}`));
    console.log(`   · ... y ${skus.length - 5} más`);
  }
  console.log("");

  const start = Date.now();
  try {
    await createBundleZip(skus, outputPath);
    const elapsed = ((Date.now() - start) / 1000).toFixed(1);
    const size = (fs.statSync(outputPath).size / 1024 / 1024).toFixed(1);
    console.log(`✅ Listo en ${elapsed}s — ${size} MB`);
    console.log(`📁 Guardado en: ${outputPath}`);
    console.log("");
    console.log("Este archivo puede:");
    console.log("  · Adjuntarse manualmente a una venta (email, DM, etc.)");
    console.log("  · Subirse a Google Drive / Dropbox para compartir el link");
    console.log("  · Usarse como entrega física de respaldo");
    console.log("  · Para entrega AUTOMÁTICA post-venta: subir ZIPs individuales a R2");
  } catch (err) {
    console.error(`❌ Error: ${(err as Error).message}`);
    process.exit(1);
  }
}

main().catch(err => {
  console.error("Error fatal:", err);
  process.exit(1);
});
