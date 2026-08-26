/**
 * Generador de productos digitales — Fitness Business OS
 *
 * Genera PDFs + ZIPs para los ~205 productos del catálogo.
 * Ejecutar: pnpm --filter @fitness-os/database generate:products
 *
 * Output: packages/database/generated/products/<SKU>/
 *         packages/database/generated/zips/<SKU>.zip
 */

import fs from "fs";
import path from "path";
import archiver from "archiver";
import {
  EXERCISE_POOL, selectExercises,
  GLUTE_EXERCISES, CORE_EXERCISES, UPPER_BODY_EXERCISES,
  CARDIO_EXERCISES, YOGA_EXERCISES, POSTPARTUM_EXERCISES,
  BODYWEIGHT_EXERCISES, STRENGTH_EXERCISES,
} from "./exercises.js";
import { RECIPE_POOL, BREAKFAST_RECIPES, LUNCH_RECIPES, DINNER_RECIPES, SNACK_RECIPES, DESSERT_RECIPES, DRINK_RECIPES } from "./recipes.js";
import {
  generateWorkoutPDF, generateNutritionPDF, generateRecipeBookPDF,
  generateChallengePDF, generateGuidePDF, generateTrackingSheetPDF,
  generateShoppingListPDF,
  type GeneratePDFOptions, type AccentType,
} from "./pdf.js";

// ── Directorios de salida ─────────────────────────────────────────
const BASE_DIR = path.resolve(process.cwd(), "../../generated");
const PRODUCTS_DIR = path.join(BASE_DIR, "products");
const ZIPS_DIR = path.join(BASE_DIR, "zips");

function ensureDirs() {
  [BASE_DIR, PRODUCTS_DIR, ZIPS_DIR].forEach(d => {
    if (!fs.existsSync(d)) fs.mkdirSync(d, { recursive: true });
  });
}

// ── ZIP helper ────────────────────────────────────────────────────
async function createZip(sourceDir: string, outputZip: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const output = fs.createWriteStream(outputZip);
    const archive = archiver("zip", { zlib: { level: 9 } });
    output.on("close", resolve);
    archive.on("error", reject);
    archive.pipe(output);
    archive.directory(sourceDir, false);
    archive.finalize();
  });
}

// ── README helper ─────────────────────────────────────────────────
function writeReadme(dir: string, sku: string, name: string, description: string, files: string[]) {
  const content = `
FITNESS BUSINESS OS — Producto Digital
=======================================

SKU: ${sku}
Producto: ${name}

${description}

ARCHIVOS INCLUIDOS
------------------
${files.map(f => `• ${f}`).join("\n")}

USO Y LICENCIA
--------------
Este contenido digital es para uso personal exclusivo. Prohibida su
redistribución, venta o distribución sin autorización escrita de
Fitness Business OS.

Para soporte: soporte@fitnessbusiness.com
Website: https://fitnessbusiness.com

© Fitness Business OS — Todos los derechos reservados
`.trim();
  fs.writeFileSync(path.join(dir, "README.txt"), content, "utf-8");
}

// ── Tipos de producto y su generador ────────────────────────────────
type ProductType =
  | "workout" | "nutrition" | "recipe" | "challenge"
  | "mindset" | "yoga" | "postpartum" | "sports" | "transformation" | "bundle";

interface ProductDef {
  sku: string;
  name: string;
  tagline: string;
  description: string;
  type: ProductType;
  accent?: AccentType;
  weeks?: number;
  extraSections?: Array<{ title: string; body: string }>;
}

// ── Catálogo completo de productos ───────────────────────────────────
const CATALOG: ProductDef[] = [
  // ── GT — Glúteos y Tonificación (Para Mujeres) ───────────────────
  { sku: "GT-001", name: "Glúteos de Acero", tagline: "12 semanas para transformar tus glúteos", description: "Programa intensivo de glúteos con progresión científica. Hip thrusts, sentadillas, peso muerto y ejercicios de aislamiento para moldear y fortalecer los glúteos como nunca.", type: "workout", accent: "women", weeks: 12 },
  { sku: "GT-002", name: "Bootcamp Glúteos en Casa", tagline: "Glúteos firmes sin ir al gimnasio", description: "Programa completo de glúteos para hacer en casa sin equipamiento. Solo necesitás una banda elástica y 30 minutos por día.", type: "workout", accent: "women", weeks: 8 },
  { sku: "GT-003", name: "Sentadillas: La Guía Definitiva", tagline: "Dominá la reina de los ejercicios", description: "Todo lo que necesitás saber sobre sentadillas: técnica perfecta, variaciones, progresión de peso y los errores más comunes que te impiden crecer.", type: "workout", accent: "women", weeks: 6 },
  { sku: "GT-004", name: "Hip Thrust Mastery", tagline: "El ejercicio número 1 para glúteos", description: "Guía completa de hip thrust: setup correcto, variaciones avanzadas, progresión de peso y cómo integrarlo a tu rutina.", type: "workout", accent: "women", weeks: 4 },
  { sku: "GT-005", name: "Glúteos Redondos y Tonificados", tagline: "Forma y firmeza en 8 semanas", description: "Programa especializado para redondear y elevar los glúteos con una combinación de ejercicios compuestos y de aislamiento.", type: "workout", accent: "women", weeks: 8 },
  { sku: "GT-006", name: "Lower Body Revolution", tagline: "Transforma piernas y glúteos completos", description: "Programa completo de tren inferior que trabaja cuádriceps, isquiotibiales, glúteos y pantorrillas en armonía.", type: "workout", accent: "women", weeks: 10 },
  { sku: "GT-007", name: "Glúteos con Banda Elástica", tagline: "Máxima activación con mínimo equipo", description: "Las bandas elásticas son la herramienta secreta para la activación glútea. 6 semanas de rutinas progresivas solo con bandas.", type: "workout", accent: "women", weeks: 6 },
  { sku: "GT-008", name: "Piernas de Infarto", tagline: "Definición y tono para piernas perfectas", description: "Programa intensivo de piernas con enfoque en la separación muscular y la definición. Para quien ya tiene base y quiere dar el siguiente paso.", type: "workout", accent: "women", weeks: 8 },
  { sku: "GT-009", name: "Glúteos Express 30 Días", tagline: "Resultados visibles en un mes", description: "30 días de trabajo intenso y enfocado en glúteos. Cada día hay un entreno diferente, progresivo y diseñado para máximos resultados.", type: "workout", accent: "women", weeks: 4 },
  { sku: "GT-010", name: "Cuerpo Tonificado de la A a la Z", tagline: "Programa completo de tonificación corporal", description: "El programa más completo para tonificar y dar forma a todo el cuerpo, con énfasis en tren inferior y core.", type: "workout", accent: "women", weeks: 12 },
  { sku: "GT-011", name: "Abdomen Plano + Glúteos", tagline: "El combo más pedido", description: "Programa dual que trabaja simultáneamente el core y los glúteos, los dos puntos más demandados.", type: "workout", accent: "women", weeks: 8 },
  { sku: "GT-012", name: "Glúteos Avanzados con Pesas", tagline: "Para quienes ya tienen base", description: "Programa avanzado que usa técnicas como drop sets, super sets y series gigantes para maximizar el crecimiento glúteo.", type: "workout", accent: "women", weeks: 10 },
  { sku: "GT-013", name: "Glúteo Medio — La Clave Olvidada", tagline: "Ancho y redondez para glúteos perfectos", description: "El glúteo medio es el que da anchura y redondez pero casi nadie lo trabaja bien. Esta guía lo pone como protagonista.", type: "workout", accent: "women", weeks: 6 },
  { sku: "GT-014", name: "Programa Glúteos Gym Principiante", tagline: "Tu primer programa de glúteos en el gym", description: "Para quien se acaba de inscribir al gimnasio. Aprende todos los ejercicios básicos con técnica perfecta y un programa de 12 semanas.", type: "workout", accent: "women", weeks: 12 },
  { sku: "GT-015", name: "Fit en Casa — Glúteos y Core", tagline: "Entrena en tu living", description: "Rutinas diarias de 25-35 minutos para hacer en el living de tu casa. Glúteos y core como unidad.", type: "workout", accent: "women", weeks: 8 },

  // ── GP — Guías de Pérdida de Peso ───────────────────────────────
  { sku: "GP-001", name: "Déficit Calórico Inteligente", tagline: "Pierde grasa sin perder músculo", description: "La ciencia detrás de la pérdida de grasa explicada de forma simple. Aprende a calcular tu déficit calórico ideal y qué comer para mantener el músculo.", type: "nutrition", accent: "default", weeks: 12 },
  { sku: "GP-002", name: "Cardio Inteligente para Quemar Grasa", tagline: "El cardio que funciona de verdad", description: "No todo el cardio es igual. Esta guía te enseña qué tipos de cardio quemar más grasa en menos tiempo.", type: "workout", accent: "default", weeks: 8 },
  { sku: "GP-003", name: "HIIT para Principiantes", tagline: "Entrena menos, quema más", description: "El entrenamiento de intervalos de alta intensidad es el más eficiente para quemar grasa. Comenzá desde cero de forma segura.", type: "workout", accent: "default", weeks: 6 },
  { sku: "GP-004", name: "Guía Anti-Antojos", tagline: "Domina los antojos para siempre", description: "Los antojos son el mayor saboteador de cualquier plan. Esta guía te da herramientas psicológicas y nutricionales para manejarlos.", type: "mindset", accent: "women" },
  { sku: "GP-005", name: "Metabolismo en Acción", tagline: "Acelera tu metabolismo naturalmente", description: "Entiende cómo funciona tu metabolismo y las estrategias comprobadas para mantenerlo activo durante un proceso de pérdida de peso.", type: "nutrition", accent: "default" },
  { sku: "GP-006", name: "Plan de 90 Días para Perder Grasa", tagline: "12 semanas de transformación real", description: "El programa más completo: entrenamiento + nutrición + mentalidad. Todo integrado en un plan de 90 días con seguimiento semana a semana.", type: "transformation", weeks: 12 },
  { sku: "GP-007", name: "Nutrición sin Dieta", tagline: "Come bien sin prohibirte nada", description: "El enfoque flexible de la nutrición: cómo perder grasa sin dietas restrictivas usando el conteo de macros y la regla 80/20.", type: "nutrition", accent: "default" },
  { sku: "GP-008", name: "Grasa Abdominal — Cómo Eliminarla", tagline: "Olvida los mitos, aplica la ciencia", description: "Desmitificamos la grasa abdominal: por qué se acumula ahí, qué ejercicios realmente ayudan y cuál es el rol de la alimentación.", type: "mindset", accent: "default" },
  { sku: "GP-009", name: "Fat Loss Cardio Plan", tagline: "60 días de cardio estratégico", description: "Plan estructurado de cardio para los siguientes 60 días: qué hacer cada día, a qué intensidad y cómo combinar con el entrenamiento de fuerza.", type: "workout", weeks: 8 },
  { sku: "GP-010", name: "Ayuno Intermitente — Guía Completa", tagline: "El método que está cambiando todo", description: "Todo sobre el ayuno intermitente: protocolos 16:8, 5:2, OMAD. Cómo empezar, qué esperar y cómo combinarlo con el entrenamiento.", type: "nutrition", accent: "default" },

  // ── AC — Abdomen y Core ──────────────────────────────────────────
  { sku: "AC-001", name: "Core de Acero", tagline: "El core que siempre quisiste", description: "Programa progresivo de 8 semanas para fortalecer y definir el core completo: no solo el six-pack visible sino toda la musculatura profunda.", type: "workout", weeks: 8 },
  { sku: "AC-002", name: "Abdomen Plano en 30 Días", tagline: "Un mes de trabajo enfocado", description: "30 días de entrenamiento específico de core. Cada día es diferente para evitar la adaptación y maximizar los resultados.", type: "challenge" },
  { sku: "AC-003", name: "Six Pack para Todos", tagline: "La verdad sobre los abdominales visibles", description: "Conseguir un six pack tiene más que ver con la nutrición que con el entrenamiento. Esta guía te da ambos componentes.", type: "workout", weeks: 12 },
  { sku: "AC-004", name: "Core Funcional", tagline: "Fuerza de núcleo para la vida real", description: "El core no es solo para verse bien. Un core fuerte mejora tu postura, previene lesiones y mejora el rendimiento en todos los deportes.", type: "workout", weeks: 6 },
  { sku: "AC-005", name: "Pilates Core Fusión", tagline: "Lo mejor del pilates aplicado al fitness", description: "Ejercicios de pilates fusionados con entrenamiento funcional para un core profundo y una postura impecable.", type: "yoga", accent: "women" },

  // ── EC — Entrenamiento Cardiovascular ────────────────────────────
  { sku: "EC-001", name: "Running para Principiantes", tagline: "De 0 a 5km en 8 semanas", description: "El programa más recomendado para empezar a correr. Progresión gradual de walk/run hasta completar 5km sin parar.", type: "workout", weeks: 8 },
  { sku: "EC-002", name: "HIIT Avanzado 12 Semanas", tagline: "El programa más intenso del catálogo", description: "Para los que ya tienen base cardiovascular y quieren llevar su condición al siguiente nivel. Tabata, circuitos y protocolos de alta intensidad.", type: "workout", weeks: 12 },
  { sku: "EC-003", name: "Cardio en Casa sin Impacto", tagline: "Cuida tus articulaciones sin parar", description: "Rutinas de cardio de bajo impacto para quienes tienen problemas en rodillas, caderas o tobillos. Efectivas y seguras.", type: "workout", accent: "women", weeks: 6 },
  { sku: "EC-004", name: "Jump Rope Training", tagline: "La cuerda de saltar como jamás la usaste", description: "La cuerda de saltar es uno de los mejores instrumentos cardio. Aprende técnicas, rutinas y cómo progresar de básico a avanzado.", type: "workout", weeks: 8 },
  { sku: "EC-005", name: "Ciclismo Indoor: Plan Completo", tagline: "Maximizá cada sesión en la bici estática", description: "Plan de 10 semanas para la bici estática o spinning: intervalos, sprints, cadencia y cómo estructurar tus sesiones para quemar más grasa.", type: "workout", weeks: 10 },

  // ── PN — Planes Nutricionales ────────────────────────────────────
  { sku: "PN-001", name: "Plan Nutricional para Bajar de Peso", tagline: "Come rico y pierde grasa", description: "Plan de alimentación de 12 semanas con menús semanales, recetas y lista de compras. Sin contar calorías obsesivamente.", type: "nutrition", weeks: 12 },
  { sku: "PN-002", name: "Plan de Volumen — Gana Músculo", tagline: "Come para crecer", description: "Plan calórico para aumentar masa muscular sin ganar grasa en exceso. Superávit calórico inteligente con macros optimizados.", type: "nutrition", weeks: 12 },
  { sku: "PN-003", name: "Nutrición Vegana para Deportistas", tagline: "Rendir al máximo sin proteína animal", description: "Guía completa de nutrición vegana enfocada en el rendimiento deportivo: fuentes de proteína, suplementos y planificación práctica.", type: "nutrition" },
  { sku: "PN-004", name: "Meal Prep — Cocina 2 Horas, Come Sano 7 Días", tagline: "El sistema de preparación que te cambia la semana", description: "Aprende a preparar tus comidas de la semana en 2 horas de domingo. Recetas, organización y tips para que nunca más tengas excusa.", type: "nutrition" },
  { sku: "PN-005", name: "Anti-Inflamatorio — Plan de 4 Semanas", tagline: "Come para reducir la inflamación", description: "La inflamación crónica frena tus resultados. Este plan nutricional se enfoca en alimentos antiinflamatorios para mejorar la recuperación.", type: "nutrition", weeks: 4 },
  { sku: "PN-006", name: "Plan para Definición Muscular", tagline: "Come para marcar músculo", description: "Nutrición específica para la fase de definición: déficit moderado, alta proteína, timing de nutrientes y suplementación básica.", type: "nutrition", weeks: 12 },
  { sku: "PN-007", name: "Guía de Suplementación Básica", tagline: "Qué tomar, cuándo y por qué", description: "La verdad sobre los suplementos: cuáles tienen respaldo científico, cuáles son marketing, cómo usarlos y qué esperar de ellos.", type: "nutrition" },
  { sku: "PN-008", name: "Recetas High Protein", tagline: "50 recetas de alto contenido proteico", description: "50 recetas deliciosas con alto contenido de proteínas. Desayunos, almuerzos, cenas y snacks para cumplir tus macros sin aburrirte.", type: "recipe" },
  { sku: "PN-009", name: "Hidratación y Rendimiento", tagline: "El nutriente más ignorado", description: "La hidratación impacta directamente en el rendimiento, la recuperación y la composición corporal. Aprende a hidratarte bien.", type: "nutrition" },
  { sku: "PN-010", name: "Nutrición Pre y Post Entreno", tagline: "Come en el momento correcto", description: "Maximiza tus resultados comiendo lo correcto antes y después del entrenamiento. Timing, composición y estrategias prácticas.", type: "nutrition" },
  { sku: "PN-011", name: "Plan Bajo en Carbohidratos", tagline: "Low carb inteligente y sostenible", description: "Reducir carbohidratos puede ser una herramienta efectiva. Esta guía te muestra cómo hacerlo de forma inteligente y sostenible.", type: "nutrition", weeks: 8 },
  { sku: "PN-012", name: "Plan de Alimentación con Intolerancia a la Lactosa", tagline: "Come rico sin sufrimiento digestivo", description: "Plan nutricional completo adaptado para intolerantes a la lactosa: sustitutos, recetas y cómo asegurar el calcio sin lácteos.", type: "nutrition" },
  { sku: "PN-013", name: "Desayunos Fitness 30 Recetas", tagline: "Empieza el día con energía", description: "30 recetas de desayunos nutritivos, ricos y rápidos. Para todos los gustos y objetivos.", type: "recipe" },
  { sku: "PN-014", name: "Snacks Saludables — 40 Ideas", tagline: "Come entre comidas sin culpa", description: "40 ideas de snacks saludables para comer en cualquier momento. Fáciles, ricos y que te ayudan a llegar a tus macros.", type: "recipe" },
  { sku: "PN-015", name: "Recetario Completo Anual", tagline: "365 días de comida saludable", description: "El recetario más completo del catálogo: 100+ recetas organizadas por categoría, con valor nutricional y lista de compras.", type: "recipe" },

  // ── YF — Yoga y Flexibilidad ─────────────────────────────────────
  { sku: "YF-001", name: "Yoga para Principiantes", tagline: "Comenzá tu práctica desde cero", description: "8 semanas de yoga progresivo para quienes nunca practicaron. Posturas básicas, respiración, meditación y filosofía.", type: "yoga", accent: "women", weeks: 8 },
  { sku: "YF-002", name: "Yoga para Deportistas", tagline: "Recuperate mejor con yoga", description: "Yoga específicamente diseñado para complementar el entrenamiento físico. Mejora la flexibilidad, previene lesiones y acelera la recuperación.", type: "yoga", weeks: 6 },
  { sku: "YF-003", name: "Flexibilidad Extrema en 90 Días", tagline: "De rígido a flexible paso a paso", description: "Programa de 90 días para ganar flexibilidad real. Rutinas progresivas de stretching que funcionan para cualquier nivel.", type: "yoga", weeks: 12 },
  { sku: "YF-004", name: "Yoga Flow Energizante", tagline: "Empezá el día con energía", description: "Rutinas de yoga dinámico para la mañana. 15-20 minutos que te dejan activado, alerta y listo para el día.", type: "yoga", weeks: 4 },
  { sku: "YF-005", name: "Yin Yoga — Calma Profunda", tagline: "El yoga del descanso activo", description: "El yin yoga trabaja los tejidos profundos con posturas mantenidas por minutos. Reduce estrés, mejora sueño y flexibilidad profunda.", type: "yoga", accent: "women", weeks: 6 },
  { sku: "YF-006", name: "Yoga para Espalda Sana", tagline: "Alivia el dolor y mejora tu postura", description: "Programa específico para el dolor de espalda y la postura. Ejercicios probados para fortalecer la columna y aliviar tensiones.", type: "yoga" },
  { sku: "YF-007", name: "Meditación y Mindfulness para Deportistas", tagline: "El entrenamiento mental que potencia el físico", description: "Técnicas de meditación y mindfulness aplicadas al deporte: visualización, control del estrés y rendimiento mental.", type: "mindset" },
  { sku: "YF-008", name: "Stretching Post-Entreno", tagline: "El estiramiento que hace la diferencia", description: "Rutinas de estiramiento para después de cada tipo de entrenamiento. Acelera la recuperación y previene lesiones.", type: "yoga" },

  // ── PT — Programas de Transformación ────────────────────────────
  { sku: "PT-001", name: "Transformación Total 12 Semanas", tagline: "El programa más completo del catálogo", description: "El programa de transformación más completo: 12 semanas de entrenamiento progresivo + plan nutricional + soporte de mentalidad. Para quienes están listos para cambiar su vida.", type: "transformation", weeks: 12 },
  { sku: "PT-002", name: "Body Recomposition", tagline: "Pierde grasa y gana músculo al mismo tiempo", description: "La recomposición corporal es posible. Esta guía te muestra cómo lograrlo con los protocolos correctos de entrenamiento y nutrición.", type: "transformation", weeks: 16 },
  { sku: "PT-003", name: "Programa Beginner to Beast", tagline: "De principiante a atleta en 6 meses", description: "El programa de largo plazo para quienes empiezan desde cero y quieren construir una base sólida de fitness en 6 meses.", type: "transformation", weeks: 24 },
  { sku: "PT-004", name: "Transformación Femenina 90 Días", tagline: "El programa diseñado para el cuerpo femenino", description: "Programa específico para mujeres que quieren cambiar su cuerpo: glúteos, tonificación general y pérdida de grasa.", type: "transformation", accent: "women", weeks: 12 },
  { sku: "PT-005", name: "Summer Body Plan", tagline: "Preparate para el verano", description: "16 semanas antes del verano: un plan integrado de entrenamiento y nutrición para estar en tu mejor forma cuando llegue el calor.", type: "transformation", accent: "default", weeks: 16 },
  { sku: "PT-006", name: "Athletic Body Program", tagline: "Fuerza, velocidad y definición", description: "Programa de rendimiento atlético completo: fuerza, velocidad, resistencia y composición corporal óptima.", type: "transformation", weeks: 12 },
  { sku: "PT-007", name: "Reset Corporal de 4 Semanas", tagline: "Volvé a empezar con el pie derecho", description: "Cuando la motivación flaquea y los hábitos se perdieron, este programa de 4 semanas te devuelve al buen camino con un enfoque paso a paso.", type: "transformation", weeks: 4 },
  { sku: "PT-008", name: "Después de los 40", tagline: "El cuerpo que querés a cualquier edad", description: "Programa adaptado para personas de 40+ que quieren ponerse en forma respetando las limitaciones hormonales, de recuperación y de movilidad.", type: "transformation" },

  // ── PR — Postparto y Recuperación ───────────────────────────────
  { sku: "PR-001", name: "Vuelta al Entreno Postparto", tagline: "Tu recuperación, a tu ritmo", description: "Guía segura y progresiva para retomar el entrenamiento después del parto. Desde las primeras respiraciones hasta el entrenamiento completo.", type: "postpartum", accent: "women", weeks: 12 },
  { sku: "PR-002", name: "Suelo Pélvico para Deportistas", tagline: "La musculatura que nadie te enseñó", description: "El suelo pélvico es fundamental para cualquier mujer que haga ejercicio. Guía completa de ejercicios, señales de alerta y recuperación.", type: "postpartum", accent: "women" },
  { sku: "PR-003", name: "Core Postparto — Restauración", tagline: "Reconstruye tu centro de dentro hacia afuera", description: "Programa específico para restaurar el core después del embarazo, incluyendo la diástasis de recto y la conexión con el suelo pélvico.", type: "postpartum", accent: "women", weeks: 12 },
  { sku: "PR-004", name: "Yoga en el Embarazo", tagline: "Mové tu cuerpo con seguridad en cada trimestre", description: "Guía de yoga prenatal por trimestres. Posturas seguras, respiración para el parto y conexión mente-cuerpo durante la gestación.", type: "postpartum", accent: "women" },
  { sku: "PR-005", name: "Lactancia y Ejercicio", tagline: "Entrená sin afectar la lactancia", description: "Guía científica sobre cómo hacer ejercicio durante la lactancia: qué ejercicios son seguros, cuándo hacerlos y cómo mantener la producción de leche.", type: "postpartum", accent: "women" },

  // ── MH — Mentalidad y Hábitos ────────────────────────────────────
  { sku: "MH-001", name: "Mentalidad Fit", tagline: "El entrenamiento mental que hace posible el físico", description: "El 80% del éxito en fitness es mental. Esta guía te da herramientas prácticas de psicología del deporte para mantener la motivación.", type: "mindset" },
  { sku: "MH-002", name: "Hábitos que Transforman", tagline: "Crea rutinas de vida que duren", description: "Cómo construir hábitos saludables que se mantengan en el tiempo. Basado en neurociencia y psicología del comportamiento.", type: "mindset" },
  { sku: "MH-003", name: "Guía Anti-Procrastinación Fitness", tagline: "Deja de postergar y empieza hoy", description: "Las razones reales por las que postergamos el ejercicio y cómo superarlas con estrategias prácticas y comprobadas.", type: "mindset" },
  { sku: "MH-004", name: "Gestión del Estrés a través del Movimiento", tagline: "El ejercicio como terapia", description: "Cómo usar el ejercicio físico para manejar el estrés, la ansiedad y el estado de ánimo. Protocolos específicos para cada estado emocional.", type: "mindset" },
  { sku: "MH-005", name: "Sueño y Recuperación", tagline: "El arma secreta del rendimiento", description: "La falta de sueño destruye los resultados. Esta guía te enseña a optimizar el sueño para mejorar la composición corporal y el rendimiento.", type: "mindset" },
  { sku: "MH-006", name: "Diario de Entrenamiento + Metas", tagline: "Escribe tus metas, alcanza tus sueños", description: "Sistema de metas y diario de entrenamiento para trazar un plan claro y hacer seguimiento semanal de tu progreso.", type: "mindset" },
  { sku: "MH-007", name: "Imagen Corporal Positiva", tagline: "Amor propio y fitness van de la mano", description: "Entrena por amor a tu cuerpo, no por odio. Guía para desarrollar una relación sana con el ejercicio, la comida y tu imagen.", type: "mindset", accent: "women" },
  { sku: "MH-008", name: "Productividad del Atleta", tagline: "Organiza tu vida para entrenar sin excusas", description: "Cómo organizar tu agenda, prioridades y energía para que el entrenamiento tenga siempre lugar, sin importar cuán ocupado estés.", type: "mindset" },

  // ── RF — Recetarios ──────────────────────────────────────────────
  { sku: "RF-001", name: "Recetario Saludable 100 Recetas", tagline: "Un año de comida sana y deliciosa", description: "100 recetas saludables organizadas por categoría: desayunos, almuerzos, cenas, snacks y postres. Con valor nutricional y lista de compras.", type: "recipe" },
  { sku: "RF-002", name: "Recetas Sin Gluten", tagline: "Delicioso sin trigo", description: "50 recetas sin gluten para celíacos e intolerantes. Sin sacrificar sabor ni valor nutricional.", type: "recipe" },
  { sku: "RF-003", name: "Recetas con Pollo — 30 Formas", tagline: "El rey de las proteínas, 30 formas de cocinarlo", description: "30 recetas diferentes con pollo como protagonista. Nunca más vas a aburrirte del pollo en tus tuppers.", type: "recipe" },
  { sku: "RF-004", name: "Postres Fitness", tagline: "Dulce sin arrepentimiento", description: "30 recetas de postres saludables que parecen trampa pero están dentro de tu plan. Brownie de porotos, helado de banana, mousse de palta...", type: "recipe" },
  { sku: "RF-005", name: "Batidos y Smoothies", tagline: "25 recetas para cada momento", description: "25 recetas de batidos y smoothies para pre-entreno, post-entreno, desayuno y colaciones. Deliciosos y nutritivos.", type: "recipe" },

  // ── D30 — Desafíos de 30 Días ────────────────────────────────────
  { sku: "D30-001", name: "Desafío 30 Días Sentadillas", tagline: "Del día 1 al día 30, una sentadilla a la vez", description: "30 días de sentadillas con progresión diaria. Empieza fácil y termina siendo una máquina de sentadillas.", type: "challenge" },
  { sku: "D30-002", name: "Desafío 30 Días Planchas", tagline: "Core de acero en un mes", description: "30 días de planchas: empieza con 20 segundos y termina manteniendo más de 2 minutos. Progresión garantizada.", type: "challenge" },
  { sku: "D30-003", name: "Desafío 30 Días Sin Azúcar", tagline: "Reset completo de tu paladar", description: "30 días eliminando azúcares añadidos. Incluye guía de qué comer, cómo manejar los antojos y qué esperar en cada fase.", type: "challenge" },
  { sku: "D30-004", name: "Desafío Hidratación 30 Días", tagline: "2 litros por día, sin excusas", description: "30 días de hidratación consciente. Cómo calcular cuánto necesitás, cómo hacer el hábito y los beneficios reales de estar bien hidratado.", type: "challenge" },
  { sku: "D30-005", name: "Desafío Mindful Eating 30 Días", tagline: "Come con atención plena", description: "30 días para transformar tu relación con la comida. Sin dietas: solo conciencia, atención y hábitos que duran.", type: "challenge" },
  { sku: "D30-006", name: "Desafío Full Body 30 Días", tagline: "Un entreno diferente cada día", description: "30 entrenos de cuerpo completo, uno diferente cada día. Sin equipamiento. Sin excusas.", type: "challenge" },
  { sku: "D30-007", name: "Desafío Glúteos 30 Días", tagline: "30 días, 30 rutinas, 1 objetivo", description: "El desafío de glúteos más viral. 30 días de ejercicios progresivos para glúteos que funciona para todos los niveles.", type: "challenge", accent: "women" },
  { sku: "D30-008", name: "Desafío Flexibilidad 30 Días", tagline: "De rígido a flexible en un mes", description: "30 días de stretching progresivo. 10-15 minutos por día para transformar tu flexibilidad.", type: "challenge" },

  // ── MASC — Productos para Hombres ───────────────────────────────
  { sku: "MASC-001", name: "Hipertrofia Muscular Ciencia y Práctica", tagline: "El manual definitivo para ganar músculo", description: "Todo sobre la hipertrofia: principios científicos de crecimiento muscular, programación de volumen e intensidad, y aplicación práctica para cada grupo muscular.", type: "workout", accent: "men", weeks: 12 },
  { sku: "MASC-002", name: "PowerLifting para Todos", tagline: "Sentadilla, press y peso muerto", description: "Guía completa de los 3 grandes levantamientos: sentadilla, press de banca y peso muerto. Técnica, programación y competencia.", type: "workout", accent: "men", weeks: 12 },
  { sku: "MASC-003", name: "Pecho en V — Desarrolla tus Pectorales", tagline: "El pecho que hace la diferencia", description: "Programa específico para desarrollar el pecho desde todos los ángulos: press plano, inclinado, declinado y ejercicios de aislamiento.", type: "workout", accent: "men", weeks: 10 },
  { sku: "MASC-004", name: "Brazos de Acero", tagline: "Bíceps y tríceps que impresionan", description: "Programa especializado de brazos: anatomía, ejercicios clave, progresión y cómo combinarlos con el resto de tu rutina.", type: "workout", accent: "men", weeks: 8 },
  { sku: "MASC-005", name: "Hombros de Toro", tagline: "Amplitud y fuerza en los deltoides", description: "Guía completa de entrenamiento de hombros: los 3 haces del deltoides, ejercicios específicos y cómo evitar lesiones en el hombro.", type: "workout", accent: "men", weeks: 8 },
  { sku: "MASC-006", name: "Piernas que Impresionan", tagline: "No más síndrome de patas de pollo", description: "El programa de piernas más completo para hombres: cuádriceps, isquiotibiales, glúteos y gemelos trabajados con progresión científica.", type: "workout", accent: "men", weeks: 10 },
  { sku: "MASC-007", name: "Abdominales Visibles — El Método", tagline: "Six-pack: entrenamiento + nutrición", description: "La verdad sobre los abdominales visibles. Protocolo combinado de entrenamiento de core y nutrición para bajar el % de grasa.", type: "workout", accent: "men", weeks: 12 },
  { sku: "MASC-008", name: "Bulk Inteligente", tagline: "Gana músculo sin ganar grasa de más", description: "El bulk inteligente: superávit calórico controlado, nutrición anabólica y entrenamiento de hipertrofia para maximizar la ganancia muscular.", type: "nutrition", accent: "men", weeks: 16 },
  { sku: "MASC-009", name: "Cut Efectivo", tagline: "Define tu físico sin perder músculo", description: "Protocolo de definición para hombres: cómo reducir grasa al mínimo manteniendo la masa muscular ganada en el bulk.", type: "nutrition", accent: "men", weeks: 12 },
  { sku: "MASC-010", name: "Calistenia desde Cero", tagline: "Tu cuerpo es tu gimnasio", description: "Aprende dominadas, fondos, pistol squats y muscle-up de forma progresiva. El camino completo de la calistenia.", type: "workout", accent: "men", weeks: 12 },
  { sku: "MASC-011", name: "Nutrición para Masa Muscular", tagline: "Come para crecer", description: "Guía nutricional específica para ganar músculo: proteínas, carbohidratos, grasas, timing y suplementación básica.", type: "nutrition", accent: "men" },
  { sku: "MASC-012", name: "Definición Extrema", tagline: "Bajar al 10% de grasa corporal", description: "Protocolo avanzado de definición para llegar a niveles de grasa muy bajos de forma segura y sostenida.", type: "nutrition", accent: "men", weeks: 16 },
  { sku: "MASC-013", name: "Postura y Dolor de Espalda", tagline: "El problema #1 de los hombres en oficina", description: "Programa de corrección postural y prevención del dolor lumbar para hombres que pasan muchas horas sentados.", type: "workout", accent: "men", weeks: 8 },
  { sku: "MASC-014", name: "Running Masculino — De 5k a Media Maratón", tagline: "Construí resistencia real", description: "Plan de running progresivo para hombres. De 5km a 21km en 6 meses, con fuerza complementaria y nutrición.", type: "workout", accent: "men", weeks: 24 },
  { sku: "MASC-015", name: "Salud Hormonal Masculina", tagline: "Optimizá tu testosterona naturalmente", description: "Cómo el ejercicio, la nutrición y el estilo de vida impactan la testosterona y la salud hormonal masculina.", type: "mindset", accent: "men" },
  { sku: "MASC-016", name: "Espalda Ancha y Fuerte", tagline: "El dorsal que hace la diferencia", description: "Programa especializado de espalda: dorsales, trapecios, romboides y erector. Dominadas, remos y jalones en progresión.", type: "workout", accent: "men", weeks: 10 },
  { sku: "MASC-017", name: "Físico Atlético en 20 Semanas", tagline: "El cuerpo que siempre quisiste", description: "Programa de largo plazo para construir un físico atlético, fuerte y estético. La combinación perfecta de fuerza e hipertrofia.", type: "transformation", accent: "men", weeks: 20 },
  { sku: "MASC-018", name: "Guía de Suplementación para Hombres", tagline: "Qué tomar, qué evitar y por qué", description: "Revisión honesta y basada en ciencia de los suplementos más populares entre hombres: proteína, creatina, pre-entreno y más.", type: "nutrition", accent: "men" },
  { sku: "MASC-019", name: "Pack Transformación Total Masculina", tagline: "Todo lo que necesitás en un solo programa", description: "El pack más completo para hombres: entrenamiento, nutrición, mentalidad y suplementación integrados en un plan de 6 meses.", type: "transformation", accent: "men", weeks: 24 },
  { sku: "MASC-020", name: "Home Training Masculino", tagline: "Gana músculo desde casa", description: "Programa de hipertrofia diseñado para hacer en casa con equipamiento mínimo. Progresión real sin necesitar un gym.", type: "workout", accent: "men", weeks: 12 },

  // ── FM — Fuerza y Musculación ────────────────────────────────────
  { sku: "FM-001", name: "Los 5 Grandes Movimientos", tagline: "La base de todo programa de fuerza", description: "Sentadilla, peso muerto, press de banca, press militar y dominadas. Aprende a dominar los 5 movimientos fundamentales del entrenamiento de fuerza.", type: "workout", weeks: 12 },
  { sku: "FM-002", name: "Fuerza desde Cero", tagline: "Tu primer programa de fuerza", description: "Programa de iniciación al entrenamiento de fuerza. 16 semanas para construir una base sólida y aprender todos los movimientos clave.", type: "workout", weeks: 16 },
  { sku: "FM-003", name: "Progresión Lineal", tagline: "Más peso cada semana, garantizado", description: "El método más efectivo para el principiante: progresión lineal. Cómo agregar peso consistentemente y cuándo cambiar de programa.", type: "workout", weeks: 12 },
  { sku: "FM-004", name: "CrossFit y Fitness Funcional", tagline: "Fuerza, acondicionamiento, potencia", description: "Guía completa de CrossFit y fitness funcional: movimientos, WODs, programación y cómo adaptarlo a cualquier nivel.", type: "workout", weeks: 10 },
  { sku: "FM-005", name: "Kettlebell Training", tagline: "La herramienta más versátil del gym", description: "Aprende los movimientos fundamentales del kettlebell: swing, snatch, clean, press y turkish get-up. Programación completa.", type: "workout", weeks: 8 },
  { sku: "FM-006", name: "Hipertrofia Científica", tagline: "Construye músculo basado en evidencia", description: "La ciencia de la hipertrofia aplicada: volumen óptimo, frecuencia, intensidad y técnicas de intensificación para maximizar el crecimiento muscular.", type: "workout", weeks: 12 },
  { sku: "FM-007", name: "Programa en Pareja", tagline: "Entrenà con tu compañero/a", description: "Rutinas diseñadas para entrenar en pareja: ejercicios asistidos, competitivos y colaborativos para motivarte con quien querés.", type: "workout", weeks: 8 },
  { sku: "FM-008", name: "Fuerza para Adultos Mayores", tagline: "El músculo que te mantiene joven", description: "Programa de fuerza adaptado para personas de 60+. Cómo mantener masa muscular, densidad ósea y funcionalidad con el tiempo.", type: "workout", weeks: 12 },
  { sku: "FM-009", name: "De Principiante a Intermedio", tagline: "El salto que todos necesitan hacer", description: "Programa de transición del nivel principiante al intermedio. Cuándo hacer el cambio, cómo periodizar y cómo evitar el estancamiento.", type: "workout", weeks: 16 },
  { sku: "FM-010", name: "Press de Banca 100kg", tagline: "El objetivo de todo hombre en el gym", description: "Programa específico para llegar a 100kg de press de banca con programación en ondas, trabajo accesorio y técnica.", type: "workout", accent: "men", weeks: 16 },
  { sku: "FM-011", name: "Peso Muerto 150kg", tagline: "Construye la fuerza más primal", description: "Programa periodizado para llegar a 150kg de peso muerto. Técnica, variaciones, trabajo de espalda y cadenas posteriores.", type: "workout", accent: "men", weeks: 20 },
  { sku: "FM-012", name: "Sentadilla 120kg", tagline: "El rey de los ejercicios, dominado", description: "Programa para llegar a 120kg de sentadilla. Técnica perfecta, movilidad de cadera y tobillo, y programación inteligente.", type: "workout", weeks: 16 },
  { sku: "FM-013", name: "Entrenamiento Piramidal", tagline: "El método clásico que nunca falla", description: "El sistema piramidal clásico y sus variantes: ascendente, descendente y doble pirámide aplicados a todos los grupos musculares.", type: "workout", weeks: 8 },
  { sku: "FM-014", name: "Superseries y Drop Sets", tagline: "Técnicas avanzadas para romper mesetas", description: "Técnicas de intensificación para deportistas avanzados: superseries, drop sets, rest-pause y series gigantes.", type: "workout", weeks: 8 },
  { sku: "FM-015", name: "Entrenamiento Full Body 3 Días", tagline: "El programa más eficiente que existe", description: "Full body 3 veces por semana: el programa más eficiente para la mayoría de personas. Progresión, ejercicios y periodización.", type: "workout", weeks: 12 },

  // ── RD — Rendimiento Deportivo ───────────────────────────────────
  { sku: "RD-001", name: "Fuerza para Fútbol", tagline: "El gym que te hace mejor futbolista", description: "Programa de preparación física para futbolistas amateurs. Potencia de piernas, velocidad, agilidad y resistencia específica.", type: "sports", accent: "sports", weeks: 12 },
  { sku: "RD-002", name: "Preparación Física para Tenis y Pádel", tagline: "Dominá la cancha", description: "Programa de acondicionamiento físico para tenis y pádel: rotación de tronco, velocidad de reacción, resistencia aeróbica específica.", type: "sports", accent: "sports", weeks: 10 },
  { sku: "RD-003", name: "Natación — Entrenamiento en Seco", tagline: "Nada mejor fuera del agua", description: "Trabajo de fuerza y movilidad complementario para nadadores. Hombros, core, flexibilidad y potencia de brazada.", type: "sports", accent: "sports", weeks: 8 },
  { sku: "RD-004", name: "Ciclismo — Fuerza Complementaria", tagline: "Las piernas que hacen ganar carreras", description: "Programa de fuerza para ciclistas: cuádriceps, isquiotibiales, core y prevención de lesiones lumbares y de rodilla.", type: "sports", accent: "sports", weeks: 10 },
  { sku: "RD-005", name: "Artes Marciales — Acondicionamiento", tagline: "Fuerza y explosividad para el ring", description: "Preparación física para artes marciales: potencia, velocidad, resistencia anaeróbica y core funcional para pelea.", type: "sports", accent: "sports", weeks: 8 },
  { sku: "RD-006", name: "Velocidad y Explosividad", tagline: "Entrena rápido para ser rápido", description: "Programa de desarrollo de velocidad: sprints, pliométria, drills de aceleración y técnica de carrera para todos los deportistas.", type: "sports", accent: "sports", weeks: 8 },
  { sku: "RD-007", name: "Resistencia Aeróbica — Base 10 Semanas", tagline: "El motor que nunca para", description: "Desarrollo de la base aeróbica en 10 semanas. Para deportistas de cualquier disciplina que quieran mejorar su resistencia.", type: "sports", accent: "sports", weeks: 10 },
  { sku: "RD-008", name: "Prevención de Lesiones Deportivas", tagline: "El atleta que no se lesiona, siempre gana", description: "Programa de prevención de las lesiones más comunes en deportistas: rodilla, hombro, tobillo y zona lumbar.", type: "sports", accent: "sports", weeks: 8 },
  { sku: "RD-009", name: "Nutrición Deportiva en Competencia", tagline: "Come para ganar", description: "Guía nutricional específica para deportistas en período competitivo: periodización nutricional, hidratación y suplementación.", type: "nutrition", accent: "sports" },
  { sku: "RD-010", name: "Warm-Up y Cool-Down Profesional", tagline: "Los 10 minutos que marcan la diferencia", description: "Protocolos de calentamiento y enfriamiento para distintos deportes y tipos de entrenamiento. Previene lesiones y mejora el rendimiento.", type: "sports", accent: "sports" },

  // ── VIP Bundles ───────────────────────────────────────────────────
  { sku: "VIP-001", name: "Bundle Completo para Mujer Activa", tagline: "Todo lo que necesitás en un solo producto", description: "El bundle más completo para mujeres: programas de glúteos, nutrición, mentalidad y yoga en un solo paquete premium.", type: "bundle", accent: "women" },
  { sku: "VIP-002", name: "Bundle Hombre Atlético", tagline: "El pack definitivo para atletas masculinos", description: "El bundle para hombres que quieren un físico completo: fuerza, hipertrofia, nutrición y mentalidad atlética.", type: "bundle", accent: "men" },
  { sku: "VIP-003", name: "Bundle Salud Total", tagline: "Fitness, nutrición y bienestar integrados", description: "El paquete más completo del catálogo: entrenamiento, nutrición, yoga, mindset y recetario en un solo bundle premium.", type: "bundle" },
  { sku: "VIP-004", name: "Bundle Principiante Absoluto", tagline: "Todo lo que necesitás para empezar", description: "Para quienes comienzan desde cero: guía de inicio al gym, plan nutricional básico y guía de mentalidad para principiantes.", type: "bundle" },
  { sku: "VIP-005", name: "Bundle Mamá en Forma", tagline: "Para las mamás que quieren volver a entrenar", description: "Bundle especial: recuperación postparto, yoga prenatal, nutrición para la lactancia y el programa de vuelta al entrenamiento.", type: "bundle", accent: "women" },

  // ── GT extendido (016-020) ────────────────────────────────────────
  { sku: "GT-016", name: "Entrenamiento para Mujeres Mayores de 40", tagline: "El cuerpo que querés a cualquier edad", description: "Adaptado a los cambios hormonales y físicos después de los 40. Fuerza, flexibilidad y bienestar en equilibrio. Progresión segura respetando la recuperación hormonal.", type: "workout", accent: "women", weeks: 10 },
  { sku: "GT-017", name: "Circuit Training Total — 6 Semanas", tagline: "Quemá grasa y tonificá al mismo tiempo", description: "Circuitos de entrenamiento variados para mantener la motivación alta. Quema de grasa y tonificación simultáneas. Nunca el mismo entreno dos veces seguidas.", type: "workout", weeks: 6 },
  { sku: "GT-018", name: "Guía de Movilidad Articular Diaria", tagline: "10 minutos al día para articulaciones sanas", description: "10 minutos al día para articulaciones sanas. Ideal para prevenir lesiones y mejorar el rendimiento deportivo. Rutinas para hombros, caderas, rodillas y tobillo.", type: "yoga" },
  { sku: "GT-019", name: "Powerlifting para Mujeres — Introducción", tagline: "Los tres grandes levantamientos para ellas", description: "Sentadilla, peso muerto y press de banca: aprende los tres grandes movimientos con técnica perfecta y progresión segura. Desmitificamos el powerlifting femenino.", type: "workout", accent: "women", weeks: 12 },
  { sku: "GT-020", name: "Programa Anti-Sedentarismo — Movimiento en el Trabajo", tagline: "Mové tu cuerpo aunque no tengas tiempo", description: "Para quienes pasan muchas horas sentadas. Rutinas de 5 minutos para hacer en la oficina o en casa sin cambiar de ropa. Más de 30 rutinas diferentes.", type: "workout" },

  // ── GP extendido (011-020) ────────────────────────────────────────
  { sku: "GP-011", name: "Programa Combinado Glúteos + Abdomen", tagline: "Las dos zonas favoritas trabajadas juntas", description: "Las dos zonas favoritas trabajadas juntas. 8 semanas de programa combinado con ejercicios multiarticulares que activan glúteos y core simultáneamente.", type: "workout", accent: "women", weeks: 8 },
  { sku: "GP-012", name: "Gemelos y Tobillos Definidos", tagline: "Esa zona olvidada que marca la diferencia", description: "Esa zona olvidada que marca la diferencia. Guía completa para trabajar gemelos y tobillos con y sin equipamiento. Fortalecimiento y definición de pantorrillas.", type: "workout", accent: "women" },
  { sku: "GP-013", name: "Sentadillas Sumo y Variantes — 30 Días", tagline: "30 días de sentadillas sumo para glúteos profundos", description: "30 días de desafío con sentadillas sumo y todas sus variantes. Ideal para trabajar aductores y glúteos profundos. Progresión diaria garantizada.", type: "challenge", accent: "women" },
  { sku: "GP-014", name: "Cuádriceps Definidos sin Máquinas", tagline: "Lunges y variantes para piernas perfectas", description: "Lunges, split squats y sus variantes para cuádriceps femeninos perfectos. Sin necesidad de máquinas de gym. Todo con peso corporal y progresión planificada.", type: "workout", accent: "women", weeks: 6 },
  { sku: "GP-015", name: "Isquiotibiales y Femoral — Guía Específica", tagline: "La parte posterior de las piernas que más se ignora", description: "La parte posterior de las piernas es clave para el equilibrio muscular y la prevención de lesiones. Guía completa con ejercicios específicos y progresión de 8 semanas.", type: "workout", accent: "women", weeks: 8 },
  { sku: "GP-016", name: "Glúteos para Mesas de Trabajo — 10 min/día", tagline: "Activá los glúteos aunque estés sentada", description: "Para quienes pasan muchas horas sentadas. Activación y tonificación de glúteos en solo 10 minutos diarios. Rutinas para hacer en la silla, de pie y en el piso.", type: "workout", accent: "women" },
  { sku: "GP-017", name: "Programa Glúteos 90 Días — Transformación Total", tagline: "90 días para unos glúteos que nunca tuviste", description: "El programa más completo e intensivo. 90 días de transformación real de glúteos con progresión de cargas y guía nutricional incluida. Para resultados definitivos.", type: "transformation", accent: "women", weeks: 12 },
  { sku: "GP-018", name: "Step-Up y Plyometría para Piernas", tagline: "Piernas potentes y resistentes", description: "Ejercicios pliométricos y con escalón para piernas potentes y resistentes. Cardio + fuerza en uno solo. Mejora la potencia muscular y quema calorías de forma explosiva.", type: "workout", accent: "women", weeks: 6 },
  { sku: "GP-019", name: "Estiramiento y Recuperación de Piernas", tagline: "La recuperación que tus piernas necesitan", description: "El componente que falta en tu rutina de piernas. 30 estiramientos específicos para recuperación activa y flexibilidad muscular. Reduce el dolor post-entreno.", type: "yoga", accent: "women" },
  { sku: "GP-020", name: "Glúteos Altos y Redondos — Protocolo Avanzado", tagline: "Para quienes ya tienen base y quieren más", description: "Para quienes ya tienen base y quieren llevar sus glúteos al siguiente nivel. Técnicas avanzadas de activación y progresión con cargas altas y máxima intensidad.", type: "workout", accent: "women", weeks: 8 },

  // ── AC extendido (006-015) ────────────────────────────────────────
  { sku: "AC-006", name: "Cintura Definida — 6 Semanas", tagline: "La silueta que siempre quisiste", description: "Trabajo específico de oblicuos y cintura para marcar la silueta. Incluye ejercicios de Pilates y funcionales. 6 semanas de progresión para definir la cintura.", type: "workout", weeks: 6 },
  { sku: "AC-007", name: "Suelo Pélvico Fuerte — Base del Core Femenino", tagline: "El centro del bienestar femenino", description: "El suelo pélvico es el centro del bienestar femenino. Ejercicios de Kegel, hipopresivos y más para un core íntegro. Previene disfunciones y mejora el rendimiento.", type: "postpartum", accent: "women" },
  { sku: "AC-008", name: "Abdominales Hipopresivos", tagline: "Reduce la cintura sin presión abdominal", description: "Técnica que reduce la cintura sin presión abdominal. Ideal post-parto, para incontinencia o como complemento deportivo. Aprende la técnica correcta paso a paso.", type: "yoga", accent: "women" },
  { sku: "AC-009", name: "Cardio Ab — Combina Cardio y Core", tagline: "Quemá grasa y definí el abdomen a la vez", description: "La combinación ganadora para quemar grasa abdominal: cardio de alta intensidad integrado con trabajo de core. Rutinas de 20-30 minutos de máxima eficiencia.", type: "workout" },
  { sku: "AC-010", name: "Core para Deportistas — Performance Total", tagline: "El core que mejora todo tu rendimiento", description: "Si practicás algún deporte, un core fuerte mejora todo. Programa diseñado para atletas: estabilización dinámica, potencia y resistencia del núcleo.", type: "sports" },
  { sku: "AC-011", name: "Abdominales en 10 Minutos Diarios", tagline: "10 minutos que hacen la diferencia", description: "La guía perfecta para mantener el trabajo abdominal consistente. 10 minutos al día, 30 rutinas diferentes. Progresión semanal para seguir mejorando siempre.", type: "challenge" },
  { sku: "AC-012", name: "Oblicuos y Línea Lateral — Guía Específica", tagline: "La línea lateral que define tu silueta", description: "Esa línea lateral que define la silueta. Ejercicios especiales para oblicuos internos y externos. Planificación de 6 semanas para marcar la cintura desde todos los ángulos.", type: "workout", weeks: 6 },
  { sku: "AC-013", name: "Core sin Abdominales Tradicionales", tagline: "Adiós a los crunches de siempre", description: "Adiós a los crunches. Alternativas modernas y más efectivas para un core fuerte sin dañar el cuello ni la espalda. Más de 40 ejercicios alternativos organizados por nivel.", type: "workout" },
  { sku: "AC-014", name: "Abdomen Postparto Seguro — Primeras 12 Semanas", tagline: "Recuperá tu core con seguridad", description: "El programa autorizado para el período postparto. Ejercicios validados, progresión segura y respeto por los tiempos de recuperación abdominal y del suelo pélvico.", type: "postpartum", accent: "women", weeks: 12 },
  { sku: "AC-015", name: "Functional Core — Movimientos Reales", tagline: "Un core que funciona en la vida real", description: "Core que funciona en la vida cotidiana. Ejercicios funcionales que mejoran tu postura, fuerza y bienestar general. Para personas que buscan rendimiento más que estética.", type: "workout" },

  // ── EC extendido (006-015) ────────────────────────────────────────
  { sku: "EC-006", name: "Cardio sin Saltos — Bajo Impacto en Casa", tagline: "Cardio efectivo sin dañar tus articulaciones", description: "Para quienes viven en departamento o tienen problemas articulares. Cardio efectivo sin saltos ni ruidos molestos. Rutinas de 20-40 minutos de bajo impacto real.", type: "workout", accent: "women", weeks: 6 },
  { sku: "EC-007", name: "Entrenamiento Matutino — 15 Minutos al Levantarte", tagline: "Arrancá el día con energía real", description: "Arrancá el día con energía. 30 rutinas de 15 minutos para hacer apenas te levantás, antes del desayuno. Activa el cuerpo y prepara la mente para el día.", type: "workout" },
  { sku: "EC-008", name: "Yoga Matutino — Despertar el Cuerpo", tagline: "Flujos de yoga para empezar el día", description: "Flujos de yoga para comenzar el día conectada con tu cuerpo. 20-30 minutos de práctica energizante. Progresión de 4 semanas para construir una rutina matutina sólida.", type: "yoga", accent: "women", weeks: 4 },
  { sku: "EC-009", name: "Circuito en Casa con Silla y Soga", tagline: "Máximo aprovechamiento de lo que tenés", description: "Con una silla y una soga saltadora ya tenés todo lo que necesitás. Circuitos completos para hacer en cualquier espacio. Cardio y fuerza integrados en rutinas efectivas.", type: "workout" },
  { sku: "EC-010", name: "Stretching Nocturno — Relajá el Cuerpo", tagline: "La rutina de antes de dormir que te cambia", description: "La rutina perfecta para antes de dormir. Estiramientos suaves que relajan la tensión del día y mejoran la calidad del sueño. 10-15 minutos de bienestar nocturno.", type: "yoga" },
  { sku: "EC-011", name: "Workout en Balcón o Patio — 4 Semanas", tagline: "El aire libre como tu gym", description: "Aprovechá el espacio al aire libre que tenés disponible. Rutinas diseñadas para espacios pequeños y al exterior. 4 semanas de programa completo con luz natural.", type: "workout", weeks: 4 },
  { sku: "EC-012", name: "Danza Fitness en Casa — Cardio Divertido", tagline: "Quemá calorías bailando", description: "Si no te gusta el gym pero sí bailar, esto es para vos. Cardio disfrazado de baile para quemar calorías sin aburrirte. Ritmos variados y coreografías simples.", type: "workout", accent: "women" },
  { sku: "EC-013", name: "Semana Activa — Moverte Todos los Días", tagline: "Hábitos de vida activa sin esfuerzo", description: "Cómo integrar el movimiento en tu rutina diaria sin que se sienta como obligación. Hábitos de vida activa: escaleras, pasos, movilidad en la oficina y micro-ejercicios.", type: "mindset" },
  { sku: "EC-014", name: "100 Ejercicios sin Equipamiento", tagline: "La biblia del entrenamiento sin elementos", description: "La biblia del entrenamiento sin elementos. 100 ejercicios descritos y categorizados para armar tus propias rutinas. Con instrucciones de técnica, variantes y dificultad.", type: "workout" },
  { sku: "EC-015", name: "Full Body en Casa — Programa Familiar", tagline: "Ejercitate con toda la familia", description: "Ejercitate con tus hijes, tu pareja o sola. Rutinas adaptables para distintos niveles en el mismo espacio. Opción para adultos y adolescentes. 8 semanas de programa.", type: "workout", weeks: 8 },

  // ── PN extendido (016-020) ────────────────────────────────────────
  { sku: "PN-016", name: "Azúcar: Cómo Reducirlo sin Sufrimiento", tagline: "Menos azúcar, más vitalidad", description: "Guía práctica para reducir el consumo de azúcar de forma progresiva. Sustitutos, recetas y cómo manejar los antojos. Sin prohibiciones, con estrategia y mucho sabor.", type: "nutrition" },
  { sku: "PN-017", name: "Plan de Alimentación para Menopausia", tagline: "Nutrición que funciona en la menopausia", description: "La menopausia cambia las reglas del juego nutricional. Plan adaptado para manejar los síntomas y mantener la composición corporal. Alimentos clave, menús y estrategias.", type: "nutrition", accent: "women" },
  { sku: "PN-018", name: "1600 Calorías Balanceadas — Plan Completo", tagline: "Comer rico y nutritivo en 1600 calorías", description: "Plan de alimentación de 1600 calorías balanceado en macronutrientes. Flexible, sabroso y sostenible en el tiempo. Con menús diarios, recetas y lista de compras semanal.", type: "nutrition", weeks: 4 },
  { sku: "PN-019", name: "Alimentación para Rendimiento Deportivo Femenino", tagline: "Come para rendir más en cada entreno", description: "Optimizá tu rendimiento deportivo con la nutrición correcta. Timing, hidratación, periodización nutricional. Guía específica para mujeres que entrenan con intensidad.", type: "nutrition", accent: "women" },
  { sku: "PN-020", name: "Guía de Alimentación Consciente y Sin Culpa", tagline: "Sanar el vínculo con la comida", description: "La relación con la comida importa tanto como lo que comés. Cómo sanar el vínculo con la alimentación para resultados duraderos. Sin culpa, sin restricciones extremas.", type: "nutrition", accent: "women" },

  // ── YF extendido (009-010) ────────────────────────────────────────
  { sku: "YF-009", name: "Stretching Deportivo Activo y Pasivo", tagline: "Maximizá tu flexibilidad sin perder fuerza", description: "Diferencias entre estiramientos activos y pasivos, y cómo combinarlos para máxima flexibilidad sin perder fuerza. Programación para deportistas de cualquier disciplina.", type: "yoga", weeks: 4 },
  { sku: "YF-010", name: "Balance y Coordinación — 4 Semanas", tagline: "Equilibrio físico para equilibrio mental", description: "Equilibrio físico que se transfiere a equilibrio mental. Ejercicios de propiocepción y coordinación para todo nivel. 4 semanas de progresión para mejorar el control corporal.", type: "yoga", weeks: 4 },

  // ── PT extendido (009-015) ────────────────────────────────────────
  { sku: "PT-009", name: "Primavera Activa — 6 Semanas de Arranque", tagline: "El empujón para salir del invierno", description: "El empujón que necesitás cuando termina el invierno. 6 semanas para activar el metabolismo y recuperar el ritmo de entrenamiento perdido. Transición gradual y efectiva.", type: "transformation", weeks: 6 },
  { sku: "PT-010", name: "Reto Navidad — Mantené tus Hábitos en las Fiestas", tagline: "Las fiestas no frenan tu proceso", description: "Cómo no tirar por la borda todo lo logrado durante las fiestas. Plan específico para diciembre y enero: entrenos cortos, nutrición flexible y mentalidad antifragil.", type: "challenge" },
  { sku: "PT-011", name: "Programa de Pérdida de Peso Saludable — 16 Semanas", tagline: "Pérdida de peso sin rebote y para siempre", description: "Sin dietas extremas, sin rebotes. Pérdida de peso sostenible a través de hábitos que duran toda la vida. 16 semanas de entrenamiento progresivo y nutrición integrada.", type: "transformation", weeks: 16 },
  { sku: "PT-012", name: "Meses sin Progreso — Cómo Romper el Estancamiento", tagline: "Salí de la meseta de una vez", description: "¿Llevás tiempo sin ver cambios? Esta guía analiza por qué y te da herramientas concretas para romper el plateau. Ajustes de entrenamiento, nutrición y mentalidad.", type: "mindset" },
  { sku: "PT-013", name: "Strong Girl — Fuerza y Estética en Equilibrio", tagline: "Fuerte y hermosa, al mismo tiempo", description: "Construí un cuerpo fuerte que también te encante. 10 semanas de programa que integra fuerza real con trabajo estético. Para mujeres que no eligen entre rendimiento y forma.", type: "transformation", accent: "women", weeks: 10 },
  { sku: "PT-014", name: "Mi Primer Maratón — De 0 a 5K a 10K", tagline: "De no correr nada a cruzar la meta", description: "El plan de entrenamiento para empezar a correr de cero y llegar a completar 10K con éxito. Progresión semanal, complemento de fuerza y nutrición para corredores.", type: "sports", weeks: 12 },
  { sku: "PT-015", name: "Cuerpo Equilibrado — Sin Obsesiones", tagline: "Resultados sin que el fitness te consuma", description: "Para quienes quieren resultados sin que el fitness se convierta en una obsesión. Equilibrio entre el cuerpo y la mente: entrenar por placer, no por castigo.", type: "transformation", weeks: 12 },

  // ── PR extendido (006-010) ────────────────────────────────────────
  { sku: "PR-006", name: "Recuperación de Lesiones Deportivas — Guía General", tagline: "Volvé al ejercicio sin lastimarte de nuevo", description: "Cómo volver al ejercicio después de una lesión. Principios de recuperación activa, adaptaciones y vuelta progresiva al entrenamiento. Para lesiones de rodilla, hombro y espalda.", type: "sports", weeks: 6 },
  { sku: "PR-007", name: "Relajación y Autocuidado para Mamás", tagline: "El postparto también es emocional", description: "El postparto es también emocional. Rutinas de autocuidado, respiración y mindfulness para mamás en sus primeros meses. Herramientas para el bienestar mental postparto.", type: "postpartum", accent: "women" },
  { sku: "PR-008", name: "Entrenamiento Posparto — De 3 Meses a 1 Año", tagline: "La evolución del entrenamiento en el primer año", description: "La evolución del entrenamiento a lo largo del primer año post-parto. Progresión segura con objetivos claros por etapa: desde el suelo pélvico hasta el rendimiento atlético.", type: "postpartum", accent: "women", weeks: 12 },
  { sku: "PR-009", name: "Dolor de Espalda en el Embarazo y Postparto", tagline: "Alivio real para el dolor de espalda", description: "El dolor de espalda es el síntoma más común. Ejercicios específicos para prevenirlo y aliviarlo en cada etapa del embarazo y el postparto. Técnica correcta y progresión.", type: "postpartum", accent: "women" },
  { sku: "PR-010", name: "Tu Cuerpo Después del Embarazo — Guía Real", tagline: "Sin filtros sobre el cuerpo post-embarazo", description: "Sin filtros ni cuerpos imposibles. La guía honesta sobre los cambios del cuerpo post-embarazo y cómo trabajar con ellos. Expectativas reales y estrategias concretas.", type: "postpartum", accent: "women" },

  // ── MH extendido (009-010) ────────────────────────────────────────
  { sku: "MH-009", name: "Rutina Mañanera que Cambia tu Vida", tagline: "La primera hora del día lo define todo", description: "Lo que hacés en la primera hora del día define el resto. Diseñá tu morning routine perfecta basada en evidencia: movimiento, nutrición, mindset y productividad integrados.", type: "mindset" },
  { sku: "MH-010", name: "Objetivos SMART para el Fitness", tagline: "Metas que se cumplen de verdad", description: "Cómo establecer objetivos reales, medibles y motivantes. Sin expectativas irreales que te hacen abandonar a los 3 meses. Framework SMART aplicado al fitness y la salud.", type: "mindset" },

  // ── RF extendido (006-010) ────────────────────────────────────────
  { sku: "RF-006", name: "Colaciones Saludables — Snacks para Todo el Día", tagline: "50 snacks para nunca comer porquerías", description: "Las colaciones hacen la diferencia. 50 ideas de snacks fáciles, nutritivos y que se pueden llevar a cualquier lado. Con preparación, valores nutricionales y sustitutos.", type: "recipe" },
  { sku: "RF-007", name: "Recetas con Pollo — 30 Formas de Cocinarlo", tagline: "El pollo de siempre nunca fue tan rico", description: "El pollo es el aliado del fitness y hay mil formas de cocinarlo sin aburrirse. 30 recetas para todo el año: al horno, a la plancha, en guisos y mucho más.", type: "recipe" },
  { sku: "RF-008", name: "Vegetales que Te van a Gustar — Recetas Creativas", tagline: "Vegetales irresistibles para todos", description: "Para quienes no son fanáticas de los vegetales. 40 recetas que hacen los vegetales irresistibles. Técnicas de cocción, condimentos y combinaciones que transforman lo simple.", type: "recipe" },
  { sku: "RF-009", name: "Fermentados y Probióticos — Recetas para el Intestino", tagline: "Kefir, kimchi y más para tu microbiota", description: "Kefir, kimchi, kombucha y más. Recetas de alimentos fermentados para cuidar la microbiota y la salud intestinal. Instrucciones paso a paso para preparar en casa.", type: "recipe" },
  { sku: "RF-010", name: "Edición Verano — 50 Recetas Frescas", tagline: "Comer rico y sano cuando hace calor", description: "El calor cambia todo. 50 recetas frescas, livianas y deliciosas para mantener la alimentación saludable en verano. Sin horno, con muchos vegetales y sabor real.", type: "recipe" },

  // ── D30 extendido (009-010) ───────────────────────────────────────
  { sku: "D30-009", name: "Desafío Glúteos 30 Días", tagline: "30 días, 30 rutinas, glúteos que lo notan", description: "30 días de ejercicios específicos de glúteos. Progresión diaria, variedad de ejercicios y glúteos que lo notan. Sin equipamiento obligatorio, con opción de bandas elásticas.", type: "challenge", accent: "women" },
  { sku: "D30-010", name: "Desafío 30 Días de Hábitos Saludables", tagline: "Un hábito por día, una vida diferente", description: "Un hábito saludable por día, 30 en total. Al final del mes tenés la base de un estilo de vida completamente diferente. Pequeños cambios, grandes resultados a largo plazo.", type: "challenge" },
];

// ══════════════════════════════════════════════════════════════════
// GENERADOR POR TIPO
// ══════════════════════════════════════════════════════════════════

async function generateProduct(product: ProductDef, index: number, total: number): Promise<void> {
  const productDir = path.join(PRODUCTS_DIR, product.sku);
  if (!fs.existsSync(productDir)) fs.mkdirSync(productDir, { recursive: true });

  const accentStr = "#00CC6A"; // verde default para tracking sheets

  // Selección de ejercicios según tipo
  const exercisePool = (() => {
    if (product.type === "yoga" || product.type === "postpartum") return [...YOGA_EXERCISES, ...POSTPARTUM_EXERCISES, ...CORE_EXERCISES];
    if (product.type === "sports") return [...CARDIO_EXERCISES, ...STRENGTH_EXERCISES, ...BODYWEIGHT_EXERCISES, ...CORE_EXERCISES];
    if (product.accent === "men") return [...STRENGTH_EXERCISES, ...UPPER_BODY_EXERCISES, ...CORE_EXERCISES, ...BODYWEIGHT_EXERCISES];
    if (product.accent === "women" && product.type !== "mindset" && product.type !== "nutrition") return [...GLUTE_EXERCISES, ...CORE_EXERCISES, ...CARDIO_EXERCISES];
    return [...BODYWEIGHT_EXERCISES, ...CORE_EXERCISES, ...UPPER_BODY_EXERCISES];
  })();

  const exercises = selectExercises(exercisePool, Math.min(10, exercisePool.length), product.sku);

  // Selección de recetas según tipo
  const recipes = (() => {
    if (product.type === "recipe") return [...BREAKFAST_RECIPES, ...LUNCH_RECIPES, ...DINNER_RECIPES, ...SNACK_RECIPES, ...DESSERT_RECIPES, ...DRINK_RECIPES];
    if (product.type === "nutrition") return [...BREAKFAST_RECIPES.slice(0, 3), ...LUNCH_RECIPES.slice(0, 3), ...DINNER_RECIPES.slice(0, 3), ...SNACK_RECIPES.slice(0, 2)];
    return [...BREAKFAST_RECIPES.slice(0, 2), ...LUNCH_RECIPES.slice(0, 2)];
  })();

  const opts: GeneratePDFOptions = {
    outputPath: path.join(productDir, `${product.sku}.pdf`),
    productName: product.name,
    productSku: product.sku,
    description: product.description,
    tagline: product.tagline,
    accent: product.accent,
    exercises,
    recipes,
    weeks: product.weeks,
    extraSections: product.extraSections ?? buildExtraSections(product),
  };

  // Generar PDF principal según tipo
  switch (product.type) {
    case "workout":
      await generateWorkoutPDF(opts);
      break;
    case "nutrition":
    case "recipe":
      opts.outputPath = path.join(productDir, `${product.sku}.pdf`);
      if (product.type === "recipe") {
        await generateRecipeBookPDF({ ...opts, recipes });
      } else {
        await generateNutritionPDF({ ...opts, recipes });
      }
      break;
    case "challenge":
      await generateChallengePDF({ ...opts, exercises });
      break;
    case "transformation":
    case "bundle":
      await generateWorkoutPDF({ ...opts, weeks: product.weeks ?? 12 });
      break;
    case "mindset":
    case "yoga":
    case "postpartum":
    case "sports":
    default:
      await generateGuidePDF({ ...opts });
      break;
  }

  // Archivos suplementarios
  const pdfFiles: string[] = [`${product.sku}.pdf`];

  if (product.type === "workout" || product.type === "transformation") {
    await generateTrackingSheetPDF(product.name, path.join(productDir, "registro-de-entrenamiento.pdf"), accentStr);
    pdfFiles.push("registro-de-entrenamiento.pdf");
  }
  if (product.type === "nutrition") {
    await generateShoppingListPDF(product.name, path.join(productDir, "lista-de-compras.pdf"), accentStr);
    pdfFiles.push("lista-de-compras.pdf");
  }
  if (product.type === "challenge") {
    await generateTrackingSheetPDF(product.name, path.join(productDir, "calendario-tracker.pdf"), accentStr);
    pdfFiles.push("calendario-tracker.pdf");
  }

  // README
  writeReadme(productDir, product.sku, product.name, product.description, ["README.txt", ...pdfFiles]);
  pdfFiles.push("README.txt");

  // ZIP
  const zipPath = path.join(ZIPS_DIR, `${product.sku}.zip`);
  await createZip(productDir, zipPath);

  const pct = (((index + 1) / total) * 100).toFixed(1);
  console.log(`[${index + 1}/${total}] ✅ ${product.sku} — ${product.name} (${pct}%)`);
}

function buildExtraSections(product: ProductDef): Array<{ title: string; body: string }> {
  const sections: Array<{ title: string; body: string }> = [];
  if (product.type === "mindset") {
    sections.push(
      { title: "¿POR QUÉ LA MENTALIDAD LO ES TODO?", body: "El cuerpo siempre puede más de lo que la mente cree. Los estudios demuestran que hasta el 80% de las personas que comienzan un programa de fitness lo abandonan antes de los 3 meses. La diferencia entre los que llegan y los que no no es el talento ni la genética — es la mentalidad." },
      { title: "LOS 3 PILARES DE LA MENTALIDAD FIT", body: "1. CLARIDAD: saber exactamente por qué querés esto y visualizarlo con detalle.\n2. CONSISTENCIA: hacer lo que hay que hacer aunque no tengas ganas.\n3. COMPASIÓN: tratarte bien cuando fallás, porque todos fallamos, y la clave es volver." },
      { title: "HERRAMIENTAS PRÁCTICAS", body: "• Diario de metas: escribí tus objetivos cada mañana en presente (\"Soy una persona que entrena 4 veces por semana\").\n• Visualización: 5 minutos cada noche imaginando cómo te sentís cuando alcanzaste tu objetivo.\n• Anclaje de hábitos: une el nuevo hábito a uno que ya tenés (antes del café, después del trabajo, etc.).\n• Registro de victorias: anotá cada logro pequeño — tu cerebro necesita evidencia de que avanzás." },
    );
  }
  if (product.type === "yoga") {
    sections.push(
      { title: "RESPIRACIÓN: LA BASE DE TODO", body: "En yoga, la respiración (pranayama) es tan importante como las posturas. La respiración ujjayi — inhalar y exhalar por la nariz con una leve constricción en la garganta — crea calor interno, calma la mente y te mantiene presente durante la práctica." },
      { title: "CÓMO USAR ESTA GUÍA", body: "Practicá al menos 3 veces por semana para ver resultados en flexibilidad y bienestar. Siempre comenzá con posturas suaves y terminá con Savasana (postura del cadáver) aunque sean solo 2 minutos — es la postura más importante de la clase." },
    );
  }
  if (product.type === "postpartum") {
    sections.push(
      { title: "AVISO IMPORTANTE", body: "Este programa fue diseñado con los principios de la rehabilitación postparto basada en evidencia. Sin embargo, es FUNDAMENTAL que consultes con tu médico o ginecóloga antes de comenzar cualquier programa de ejercicios. Cada cuerpo y cada parto son diferentes. Si sentís dolor, presión pélvica o pierden orina durante los ejercicios, detené y consultá a un especialista en suelo pélvico." },
      { title: "RESPETÁ TU PROCESO", body: "Tu cuerpo acaba de hacer algo extraordinario. No te compares con cómo eras antes del embarazo. La recuperación postparto no es lineal — habrá días mejores y peores. Lo más importante es escuchar a tu cuerpo y ser amable con vos misma." },
    );
  }
  if (product.type === "sports") {
    sections.push(
      { title: "CÓMO INTEGRAR ESTE PROGRAMA CON TU DEPORTE", body: "Este programa es complementario a tu entrenamiento específico del deporte. Lo ideal es realizar el trabajo de fuerza y acondicionamiento los días de menor exigencia deportiva. Si entrenas tu deporte lunes, miércoles y viernes, hacé el gym martes y jueves." },
    );
  }
  return sections;
}

// ── Main ───────────────────────────────────────────────────────────
async function main() {
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
  console.log("  FITNESS BUSINESS OS — Generador de Productos Digitales  ");
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
  console.log(`📦 Total de productos a generar: ${CATALOG.length}`);
  console.log(`📁 Output: ${PRODUCTS_DIR}`);
  console.log(`🗜  ZIPs: ${ZIPS_DIR}`);
  console.log("");

  ensureDirs();

  const startTime = Date.now();
  let errors = 0;

  for (let i = 0; i < CATALOG.length; i++) {
    try {
      await generateProduct(CATALOG[i], i, CATALOG.length);
    } catch (err) {
      errors++;
      console.error(`[${i + 1}/${CATALOG.length}] ❌ ERROR en ${CATALOG[i].sku}: ${err}`);
    }
  }

  const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
  console.log("");
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
  console.log(`✅ Completado en ${elapsed}s — ${CATALOG.length - errors} OK, ${errors} errores`);
  console.log(`📁 Productos: ${PRODUCTS_DIR}`);
  console.log(`🗜  ZIPs listos para subir a R2: ${ZIPS_DIR}`);
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
}

main().catch(err => {
  console.error("Error fatal:", err);
  process.exit(1);
});
