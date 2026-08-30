/**
 * Generador de guías digitales en HTML.
 * Dado un producto con su metadata, produce un HTML completo,
 * print-ready (CSS @media print), en español.
 *
 * El HTML puede:
 *  - Abrirse en el browser y guardarse como PDF con Ctrl+P
 *  - Incluirse en un ZIP como guia.html
 */

interface ProductData {
  id: string;
  sku: string;
  name: string;
  description?: string | null;
  productType: string;
  level?: string | null;
  durationWeeks?: number | null;
  objective?: string | null;
  category?: { name: string } | null;
}

// ── Helpers ──────────────────────────────────────────────────────────

function levelLabel(level?: string | null) {
  const map: Record<string, string> = {
    principiante: "Principiante",
    intermedio: "Intermedio",
    avanzado: "Avanzado",
  };
  return map[level?.toLowerCase() ?? ""] ?? "Todos los niveles";
}

function weeks(n?: number | null) {
  return n ? `${n} semanas` : "Programa completo";
}

function weekPlan(totalWeeks: number, type: "lower_body" | "core" | "full_body" | "upper_body" | "flexibility" | "nutrition") {
  const plans: Record<string, (w: number) => string[]> = {
    lower_body: (w) => Array.from({ length: w }, (_, i) => {
      const week = i + 1;
      const intensity = week <= 2 ? "Base — Activación muscular" : week <= w / 2 ? "Desarrollo — Carga progresiva" : "Peak — Intensidad máxima";
      const sets = week <= 2 ? "3 series" : week <= w / 2 ? "4 series" : "4-5 series";
      const exercises = [
        "Sentadillas sumo",
        "Hip thrust con barra o bandas",
        "Peso muerto rumano",
        "Lunges alternados",
        "Patada de glúteo en cuadrupedia",
        "Abducción lateral con banda",
        "Sentadilla búlgara",
        "Extensión de cadera en suelo",
      ];
      return `Semana ${week}: ${intensity} — ${sets} × 12-15 reps. Ejercicios: ${exercises.slice(0, 4 + (week > w / 2 ? 2 : 0)).join(", ")}.`;
    }),
    core: (w) => Array.from({ length: w }, (_, i) => {
      const week = i + 1;
      const ex = [
        "Plancha frontal (30s→60s progresivo)",
        "Crunch abdominal controlado",
        "Elevación de piernas",
        "Bicicleta abdominal",
        "Plancha lateral",
        "Dead bug",
        "Mountain climbers",
        "Russian twists",
      ];
      return `Semana ${week}: ${ex.slice(0, 3 + Math.min(week, 5)).join(" · ")} — 3 series cada uno.`;
    }),
    full_body: (w) => Array.from({ length: w }, (_, i) => {
      const week = i + 1;
      const phases = ["Acondicionamiento general", "Fuerza base", "Hipertrofia funcional", "Peak de rendimiento", "Definición"];
      const phase = phases[Math.min(Math.floor((week / w) * 5), 4)];
      return `Semana ${week}: ${phase} — Lunes/Miércoles/Viernes full body + Martes/Jueves cardio activo (30 min).`;
    }),
    upper_body: (w) => Array.from({ length: w }, (_, i) => {
      const week = i + 1;
      return `Semana ${week}: Empuje + tirón + hombros — ${week <= 2 ? "3×12" : week <= w - 2 ? "4×10" : "5×8"} reps. Press, remo, elevaciones laterales, curl, tríceps.`;
    }),
    flexibility: (w) => Array.from({ length: w }, (_, i) => {
      const week = i + 1;
      const topics = ["Movilidad de cadera y columna", "Flexibilidad de isquiotibiales y pantorrillas", "Apertura de hombros y pecho", "Cadena posterior completa", "Integración y flow"];
      return `Semana ${week}: ${topics[Math.min(week - 1, topics.length - 1)]} — Rutina de 30-40 minutos, mantener cada postura 30-60 segundos.`;
    }),
    nutrition: (w) => Array.from({ length: Math.min(w, 4) }, (_, i) => {
      const week = i + 1;
      const phases = [
        "Limpieza y reset: Eliminar azúcares procesados, hidratación 2L/día, 5 comidas regulares",
        "Balanceo de macros: Proteína 1.6g/kg peso, carbohidratos complejos, grasas saludables",
        "Timing nutricional: Pre y post entreno, distribución de carbohidratos en el día",
        "Hábitos sostenibles: Meal prep, lectura de etiquetas, comer sin culpa",
      ];
      return `Semana ${week}: ${phases[Math.min(week - 1, phases.length - 1)]}`;
    }),
  };
  const fn = plans[type] ?? plans.full_body;
  return fn(totalWeeks);
}

function exerciseLibrary(category: string) {
  const libraries: Record<string, Array<{ name: string; desc: string; sets: string; tip: string }>> = {
    gluteos: [
      { name: "Hip Thrust", desc: "Apoyá la parte superior de la espalda en un banco. Con barra o banda sobre las caderas, empujá hacia arriba contrayendo glúteos al máximo.", sets: "4 × 12-15 reps", tip: "Mantené la barbilla pegada al pecho. El movimiento es en la cadera, no en la columna." },
      { name: "Sentadilla Sumo", desc: "Pies más separados que el ancho de hombros, puntillas hacia afuera. Bajá manteniendo la espalda recta y rodillas alineadas con los pies.", sets: "3 × 15 reps", tip: "El peso en los talones, no en la punta de los pies. Apretá glúteos al subir." },
      { name: "Peso Muerto Rumano", desc: "De pie, mancuernas delante del cuerpo. Inclinate hacia adelante con espalda recta, bajando las pesas por la pierna hasta sentir estiramiento en isquiotibiales.", sets: "3 × 12 reps", tip: "La espalda nunca redonda. El movimiento es empujar las caderas hacia atrás, no doblar la cintura." },
      { name: "Patada de Glúteo", desc: "En cuadrupedia, llevá una pierna hacia atrás y arriba, manteniendo la rodilla en 90°. Apretá el glúteo al final del movimiento.", sets: "3 × 20 reps c/lado", tip: "No arquees la lumbar. El core activo todo el tiempo." },
      { name: "Abducción con Banda", desc: "Sentada o de pie con banda elástica en los muslos. Abrí las rodillas hacia afuera contra la resistencia de la banda.", sets: "3 × 20 reps", tip: "La banda debe estar justo arriba de las rodillas para máxima activación del glúteo medio." },
      { name: "Sentadilla Búlgara", desc: "Un pie apoyado atrás en un banco, el otro adelante. Bajá hasta que la rodilla trasera casi toque el suelo.", sets: "3 × 10 reps c/lado", tip: "El pie delantero suficientemente adelante para que la rodilla no pase la punta del pie al bajar." },
    ],
    core: [
      { name: "Plancha Frontal", desc: "Apoyada en codos y puntas de pie, cuerpo recto como tabla. Activá core, glúteos y cuádriceps simultáneamente.", sets: "3 × 30-60 segundos", tip: "Si la cadera cae o sube, es hora de parar. Calidad sobre duración." },
      { name: "Crunch con Control", desc: "Tumbada boca arriba, rodillas dobladas. Llevá los hombros hacia las rodillas sin tirar del cuello. Bajá lentamente.", sets: "3 × 15-20 reps", tip: "Exhalá al subir, inhalá al bajar. El movimiento es pequeño pero intenso." },
      { name: "Dead Bug", desc: "Tumbada boca arriba, brazos al techo, caderas y rodillas a 90°. Extendé brazo derecho + pierna izquierda sin que la lumbar se despegue del suelo.", sets: "3 × 10 reps c/lado", tip: "Si la lumbar se arquea, reducí el rango de movimiento hasta ganar más control." },
      { name: "Mountain Climbers", desc: "En posición de plancha alta, llevá rodillas al pecho de forma alternada y rápida.", sets: "3 × 30 segundos", tip: "Las caderas abajo y estables. El core es el que trabaja, no la inercia." },
      { name: "Russian Twist", desc: "Sentada con rodillas dobladas y espalda inclinada 45°. Rotá el torso de lado a lado con o sin peso.", sets: "3 × 20 reps totales", tip: "Respirá de forma continua. Si usás peso, empezá liviano." },
      { name: "Elevación de Piernas", desc: "Tumbada boca arriba, llevá las piernas juntas de 0° a 90° manteniendo la lumbar en el suelo.", sets: "3 × 12-15 reps", tip: "Si la lumbar se despega, doblá ligeramente las rodillas hasta fortalecer más el core." },
    ],
    upper_body: [
      { name: "Press con Mancuernas", desc: "Tumbada boca arriba, mancuernas a la altura del pecho. Empujá hacia arriba extendiendo los codos completamente.", sets: "3 × 12 reps", tip: "Controlá la bajada (2-3 segundos). No las dejes caer." },
      { name: "Remo con Mancuerna", desc: "Apoyada en un banco con una mano y una rodilla. La otra mano agarra la mancuerna y la sube hacia la cadera.", sets: "3 × 12 reps c/lado", tip: "El codo cerca del cuerpo, no hacia afuera. El movimiento es del codo, no de la mano." },
      { name: "Curl de Bíceps", desc: "De pie o sentada, mancuernas colgando. Doblá los codos llevando las mancuernas hacia los hombros.", sets: "3 × 12-15 reps", tip: "No balanceés el cuerpo. Si necesitás impulso, el peso es muy pesado." },
      { name: "Extensión de Tríceps", desc: "Sentada, mancuerna con ambas manos sobre la cabeza. Doblá los codos llevando la pesa hacia la nuca.", sets: "3 × 12 reps", tip: "Los codos apuntan al techo todo el tiempo. Solo los antebrazos se mueven." },
      { name: "Elevaciones Laterales", desc: "De pie, mancuernas a los lados. Subí los brazos lateralmente hasta la altura de los hombros.", sets: "3 × 15 reps", tip: "Los codos ligeramente doblados. No balanceés el cuerpo para subir." },
    ],
    flexibility: [
      { name: "Paloma (Pigeon Pose)", desc: "Una rodilla doblada adelante, pierna trasera extendida. Mantenela mientras respirás profundo.", sets: "60 segundos c/lado", tip: "Si la cadera no llega al suelo, ponete un almohadón debajo." },
      { name: "Perro Boca Abajo", desc: "Manos y pies en el suelo, caderas al techo, formando una V invertida. Alterná los talones para calentar.", sets: "5 respiraciones profundas", tip: "Rodillas ligeramente dobladas si los isquiotibiales están muy tensos." },
      { name: "Estiramiento de Cuádriceps", desc: "De pie, doblá una rodilla llevando el pie hacia la cola. Mantené el equilibrio.", sets: "45 segundos c/lado", tip: "Las rodillas juntas y la cadera empujada ligeramente hacia adelante para mayor intensidad." },
      { name: "Cat-Cow", desc: "En cuadrupedia, alternando arqueo y redondeo de columna con la respiración.", sets: "10 repeticiones lentas", tip: "El movimiento empieza desde la pelvis y ondula hacia el cuello. Nunca forzado." },
    ],
  };
  return libraries[category] ?? libraries.gluteos;
}

function nutritionGuide(level: string) {
  return `
<h3>Guía Nutricional</h3>
<h4>Principios Básicos</h4>
<ul>
  <li><strong>Proteína:</strong> 1.4–1.8 g por kg de peso corporal. Priorizar pollo, pavo, huevos, atún, legumbres.</li>
  <li><strong>Carbohidratos:</strong> Elegir complejos: arroz integral, avena, batata, quinoa, frutas. Evitar azúcares procesados.</li>
  <li><strong>Grasas saludables:</strong> Palta, aceite de oliva, frutos secos, semillas. Necesarias para hormonas y energía.</li>
  <li><strong>Hidratación:</strong> 2–2.5 litros de agua por día. Más en días de entrenamiento.</li>
</ul>
<h4>Distribución de Comidas</h4>
<table class="nutrition-table">
  <tr><th>Comida</th><th>Timing</th><th>Qué incluir</th></tr>
  <tr><td>Desayuno</td><td>7:00 – 9:00 h</td><td>Proteína + carbohidratos + grasa saludable</td></tr>
  <tr><td>Pre-entreno</td><td>60-90 min antes</td><td>Carbohidrato de rápida absorción + proteína liviana</td></tr>
  <tr><td>Post-entreno</td><td>Dentro de 45 min</td><td>Proteína + carbohidrato (ventana anabólica)</td></tr>
  <tr><td>Almuerzo</td><td>12:00 – 14:00 h</td><td>La comida más completa del día</td></tr>
  <tr><td>Merienda</td><td>16:00 – 17:00 h</td><td>Snack saludable: fruta + proteína</td></tr>
  <tr><td>Cena</td><td>19:00 – 21:00 h</td><td>Más liviana, priorizar proteína y vegetales</td></tr>
</table>
${level === "avanzado" ? `
<h4>Estrategias Avanzadas</h4>
<ul>
  <li><strong>Ciclado de carbohidratos:</strong> Más CHO los días de entrenamiento intenso, menos en descanso.</li>
  <li><strong>Déficit calórico controlado:</strong> No más del 20% por debajo de tu TDEE para preservar músculo.</li>
  <li><strong>Meal prep semanal:</strong> Cocinás una vez y tenés comida lista toda la semana.</li>
</ul>` : ""}`;
}

function trackingSheet(productName: string, totalWeeks: number) {
  const rows = Array.from({ length: totalWeeks }, (_, i) => `
    <tr>
      <td class="week-cell">Semana ${i + 1}</td>
      <td class="input-cell"></td>
      <td class="input-cell"></td>
      <td class="input-cell"></td>
      <td class="input-cell"></td>
      <td class="input-cell"></td>
    </tr>`).join("");

  return `<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Seguimiento — ${productName}</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: Arial, sans-serif; font-size: 12px; color: #1a1a1a; padding: 20px; }
  h1 { font-size: 18px; margin-bottom: 4px; color: #1a1a1a; }
  h2 { font-size: 13px; margin-bottom: 16px; color: #555; font-weight: 400; }
  table { width: 100%; border-collapse: collapse; margin-bottom: 24px; }
  th { background: #1a1a1a; color: white; padding: 8px 12px; text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; }
  td { border: 1px solid #ddd; padding: 10px 12px; }
  .week-cell { background: #f5f5f5; font-weight: 700; width: 80px; }
  .input-cell { width: auto; min-height: 32px; }
  .notes-section { margin-top: 20px; }
  .note-line { border-bottom: 1px solid #ccc; margin-bottom: 18px; width: 100%; height: 1px; }
  @media print { body { padding: 10mm; } }
</style>
</head>
<body>
<h1>📊 Planilla de Seguimiento</h1>
<h2>${productName}</h2>

<table>
  <thead>
    <tr>
      <th>Semana</th>
      <th>Peso (kg)</th>
      <th>Energía (1-10)</th>
      <th>Sesiones completadas</th>
      <th>Logro de la semana</th>
      <th>Meta siguiente semana</th>
    </tr>
  </thead>
  <tbody>${rows}</tbody>
</table>

<div class="notes-section">
  <h2>📝 Notas y Observaciones</h2>
  ${Array.from({ length: 8 }, () => '<div class="note-line"></div>').join("\n  ")}
</div>

<div style="margin-top:30px; padding: 12px; background: #f9f9f9; border-left: 3px solid #333; font-size: 11px; color: #555;">
  💡 Tomá fotos de progreso al inicio, mitad y fin del programa. Los cambios visuales muchas veces superan a los del pesaje.
</div>
</body>
</html>`;
}

function buildReadme(productName: string, sku: string) {
  return `PRODUCTO: ${productName}
SKU: ${sku}

CONTENIDO DEL PAQUETE:
- guia.html ........... Guía completa del programa (abrí en Chrome y guardá como PDF con Ctrl+P)
- seguimiento.html .... Planilla de seguimiento semanal (imprimible)
- README.txt .......... Este archivo

CÓMO USAR LA GUÍA:
1. Abrí guia.html en tu navegador (Chrome, Firefox o Safari)
2. Para guardarlo como PDF: Ctrl+P (o Cmd+P en Mac) → Destino: Guardar como PDF
3. Margen: Mínimo · Gráficos de fondo: Activado

SOPORTE:
Ante cualquier consulta, respondemos por WhatsApp o email dentro de las 24 horas.

---
Generado automáticamente · Fitness Business OS
`;
}

// ── Generadores por tipo ─────────────────────────────────────────────

function generatePDFGuide(product: ProductData): string {
  const totalWeeks = product.durationWeeks ?? 8;
  const level = product.level ?? "intermedio";
  const category = product.category?.name?.toLowerCase() ?? "";

  const isGluteos = /gl[uú]teo|pierna|inferior/i.test(category + " " + product.name);
  const isCore = /core|abdomen|abdominal/i.test(category + " " + product.name);
  const isUpper = /superior|brazo|espalda|pecho|hombro/i.test(category + " " + product.name);
  const isFlexibility = /yoga|flexibil|movilidad|stretching/i.test(category + " " + product.name);
  const isMen = /hombre|masculin|hipertrofia|fuerza/i.test(category + " " + product.name);

  const planType = isGluteos ? "lower_body"
    : isCore ? "core"
    : isUpper || isMen ? "upper_body"
    : isFlexibility ? "flexibility"
    : "full_body";

  const exerciseCat = isGluteos ? "gluteos"
    : isCore ? "core"
    : isUpper || isMen ? "upper_body"
    : isFlexibility ? "flexibility"
    : "gluteos";

  const plan = weekPlan(totalWeeks, planType as Parameters<typeof weekPlan>[1]);
  const exercises = exerciseLibrary(exerciseCat);

  const planHtml = plan.map((week, i) => `
    <div class="week-block">
      <div class="week-header">📅 ${week.split(":")[0]}</div>
      <p>${week.split(":").slice(1).join(":")}</p>
    </div>`).join("");

  const exerciseHtml = exercises.map(ex => `
    <div class="exercise-card">
      <h4>${ex.name}</h4>
      <p class="exercise-desc">${ex.desc}</p>
      <div class="exercise-meta">
        <span class="sets">${ex.sets}</span>
        <span class="tip">💡 ${ex.tip}</span>
      </div>
    </div>`).join("");

  return `
<section class="section">
  <h2>🎯 Bienvenida</h2>
  <p>${product.description ?? "Este programa fue diseñado para ayudarte a alcanzar tus objetivos de manera progresiva, segura y efectiva."}</p>
  <div class="info-grid">
    <div class="info-card"><span class="icon">⏱</span><div><strong>Duración</strong><br>${weeks(product.durationWeeks)}</div></div>
    <div class="info-card"><span class="icon">📊</span><div><strong>Nivel</strong><br>${levelLabel(level)}</div></div>
    <div class="info-card"><span class="icon">🏋️</span><div><strong>Frecuencia</strong><br>3-4 días / semana</div></div>
    <div class="info-card"><span class="icon">⏰</span><div><strong>Duración sesión</strong><br>40-60 minutos</div></div>
  </div>
</section>

<section class="section">
  <h2>🎒 Materiales Necesarios</h2>
  <ul>
    <li>Colchoneta de ejercicio o yoga mat</li>
    <li>Bandas elásticas (resistencia media y alta)</li>
    <li>Mancuernas (opcional — 2 a 10 kg según nivel)</li>
    <li>Silla o banco resistente</li>
    <li>Botella de agua y toalla</li>
    <li>Ropa cómoda que permita el movimiento</li>
  </ul>
</section>

<section class="section">
  <h2>📋 Plan Semana a Semana</h2>
  <p class="intro-text">Cada semana es progresiva. Respetá los descansos y escuchá tu cuerpo.</p>
  ${planHtml}
</section>

<section class="section">
  <h2>💪 Biblioteca de Ejercicios</h2>
  <p class="intro-text">Descripción detallada de cada ejercicio con técnica correcta.</p>
  ${exerciseHtml}
</section>

<section class="section">
  ${nutritionGuide(level)}
</section>

<section class="section">
  <h2>📈 Cómo Medir tu Progreso</h2>
  <ul>
    <li><strong>Fotos de progreso:</strong> Tomá una foto al inicio, a la mitad y al final. Siempre a la misma hora y con la misma ropa.</li>
    <li><strong>Medidas corporales:</strong> Medí cintura, caderas, muslos y brazos al inicio y final del programa.</li>
    <li><strong>Peso:</strong> Pesate una vez por semana, siempre en las mismas condiciones (mañana en ayunas).</li>
    <li><strong>Rendimiento:</strong> Registrá cuántos reps podés hacer de cada ejercicio. ¡El progreso en fuerza es el mejor indicador!</li>
    <li><strong>Energía y bienestar:</strong> Notá cómo te sentís al levantarte, tu calidad de sueño y tu estado de ánimo.</li>
  </ul>
</section>

<section class="section motivacion">
  <h2>✨ Recordá Siempre</h2>
  <blockquote>"La consistencia supera siempre a la perfección. Un entrenamiento imperfecto que hacés vale infinitamente más que el entrenamiento perfecto que te quedó en el plan."</blockquote>
  <p>Los resultados llegan cuando repetís el proceso, incluso cuando no tenés ganas. Cada entrenamiento es una decisión por vos misma. ¡Estás haciendo algo increíble!</p>
</section>`;
}

function generateChallenge(product: ProductData): string {
  const days30 = Array.from({ length: 30 }, (_, i) => {
    const day = i + 1;
    const isRest = day % 7 === 0;
    const squats = isRest ? "DESCANSO ACTIVO" : Math.min(20 + (day * 2), 150) + " sentadillas";
    const extra = isRest ? "Caminata 30 min o yoga suave" : day % 3 === 0 ? " + 30 hip thrust" : day % 2 === 0 ? " + plancha 30s" : " + 20 patadas de glúteo c/lado";
    return `<div class="day-card ${isRest ? "rest-day" : ""}">
      <div class="day-num">Día ${day}</div>
      <div class="day-content">${squats}${isRest ? "" : extra}</div>
    </div>`;
  }).join("");

  return `
<section class="section">
  <h2>🔥 ¡Bienvenida al Desafío!</h2>
  <p>${product.description ?? "30 días de compromiso con vos misma. Cada día suma."}</p>
  <div class="challenge-rules">
    <h3>📜 Las Reglas</h3>
    <ul>
      <li>Completá cada día sin saltear (los descansos activos también cuentan)</li>
      <li>Tomá agua antes, durante y después</li>
      <li>Calentá siempre 5 minutos antes de empezar</li>
      <li>Compartí tu progreso en redes con #FitnessChallenge</li>
    </ul>
  </div>
</section>

<section class="section">
  <h2>📅 Los 30 Días</h2>
  <div class="days-grid">
    ${days30}
  </div>
</section>

<section class="section">
  <h2>🔄 Calentamiento (5 min)</h2>
  <ul>
    <li>Círculos de cadera — 30 segundos</li>
    <li>Sentadillas sin peso — 10 reps</li>
    <li>Lunges en el lugar — 10 reps c/lado</li>
    <li>Patadas laterales — 10 reps c/lado</li>
    <li>Marcha elevada — 30 segundos</li>
  </ul>
</section>

<section class="section motivacion">
  <h2>💪 Vos Podés</h2>
  <p>Cuando no tengas ganas, acordate por qué empezaste. 30 días. Una decisión a la vez.</p>
</section>`;
}

function generateRecipeBook(product: ProductData): string {
  const recipes = [
    { name: "Tazón de Avena con Frutas", cat: "Desayunos", prep: "5 min", cals: "320 kcal", desc: "1 taza de avena + leche descremada + plátano + frutillas + 1 cdita de miel. Nutrientes: 45g CHO, 14g Prot, 6g Grasas." },
    { name: "Omelette de Espinaca y Queso", cat: "Desayunos", prep: "10 min", cals: "280 kcal", desc: "3 huevos + 1 taza espinaca + 30g queso cremoso light + especias. Alta proteína para empezar el día." },
    { name: "Smoothie Verde Proteico", cat: "Desayunos", prep: "5 min", cals: "240 kcal", desc: "1 banana + 1 taza espinaca + 1 cda proteína vainilla + 1 taza leche de almendras. Batir y listo." },
    { name: "Ensalada de Pollo a la Plancha", cat: "Almuerzos", prep: "20 min", cals: "380 kcal", desc: "150g pechuga + mix de verdes + cherry + pepino + 1 cda aceite oliva + limón. Proteína completa." },
    { name: "Arroz Integral con Salmón", cat: "Almuerzos", prep: "25 min", cals: "450 kcal", desc: "150g salmón + 1 taza arroz integral + brócoli al vapor + jengibre. Rico en omega-3." },
    { name: "Bowl de Quinoa Vegana", cat: "Almuerzos", prep: "20 min", cals: "350 kcal", desc: "1 taza quinoa + garbanzos + pepino + tomate + palta + limón + comino. Proteína completa vegetal." },
    { name: "Pechuga con Batata", cat: "Cenas", prep: "30 min", cals: "400 kcal", desc: "150g pechuga + 1 batata mediana + judías verdes. Comida completa de nutrientes." },
    { name: "Tortilla Española Fit", cat: "Cenas", prep: "20 min", cals: "300 kcal", desc: "4 huevos + 2 papas medianas + cebolla + pimiento. Versión saludable del clásico." },
    { name: "Wok de Vegetales con Tofu", cat: "Cenas", prep: "15 min", cals: "280 kcal", desc: "Tofu firme + pimiento + brócoli + zanahoria + salsa de soja baja en sodio + sésamo." },
    { name: "Yogur Griego con Nueces", cat: "Snacks", prep: "2 min", cals: "180 kcal", desc: "200g yogur griego 0% + 5 nueces + 1 cdita miel. 20g proteína, saciante." },
    { name: "Huevo Duro + Fruta", cat: "Snacks", prep: "10 min", cals: "150 kcal", desc: "2 huevos duros + 1 fruta de estación. Combo perfecto de proteína y fructosa de recuperación." },
    { name: "Licuado de Proteína Casero", cat: "Snacks", prep: "5 min", cals: "200 kcal", desc: "1 taza leche descremada + 1 cda mantequilla de maní + 1 plátano + hielo. Sin proteína en polvo." },
  ];

  const byCategory = recipes.reduce((acc: Record<string, typeof recipes>, r) => {
    if (!acc[r.cat]) acc[r.cat] = [];
    acc[r.cat].push(r);
    return acc;
  }, {});

  const recipesHtml = Object.entries(byCategory).map(([cat, recs]) => `
    <h3>🍽️ ${cat}</h3>
    ${recs.map(r => `
    <div class="recipe-card">
      <div class="recipe-header">
        <span class="recipe-name">${r.name}</span>
        <span class="recipe-meta">⏱ ${r.prep} · 🔥 ${r.cals}</span>
      </div>
      <p>${r.desc}</p>
    </div>`).join("")}`).join("");

  return `
<section class="section">
  <h2>📖 Sobre Este Recetario</h2>
  <p>${product.description ?? "Recetas saludables, deliciosas y prácticas para acompañar tu estilo de vida activo."}</p>
</section>
<section class="section">${recipesHtml}</section>`;
}

function generateDiary(product: ProductData): string {
  const dayTemplate = (n: number) => `
  <div class="diary-day">
    <div class="day-header">DÍA ${n}</div>
    <div class="diary-field"><label>¿Cómo me desperté hoy? (energía 1-10): </label><div class="line"></div></div>
    <div class="diary-field"><label>Mi intención del día: </label><div class="line"></div></div>
    <div class="diary-field"><label>Entrenamiento completado: ☐ Sí ☐ No | ¿Cuál? </label><div class="line"></div></div>
    <div class="diary-field"><label>Agua tomada (vasos): ☐☐☐☐☐☐☐☐</label></div>
    <div class="diary-field"><label>Lo mejor del día: </label><div class="line"></div></div>
    <div class="diary-field"><label>Gratitud: </label><div class="line"></div></div>
    <div class="diary-field"><label>Mañana voy a: </label><div class="line"></div></div>
  </div>`;

  return `
<section class="section">
  <h2>📓 Tu Diario de Transformación</h2>
  <p>${product.description ?? "90 días para construir la versión más fuerte y feliz de vos misma."}</p>
</section>
<section class="section">
  <h2>🌅 Semana 1 — Días 1 al 7</h2>
  ${Array.from({ length: 7 }, (_, i) => dayTemplate(i + 1)).join("")}
</section>
<section class="section">
  <h2>Continuá el diario en las semanas siguientes...</h2>
  <p>Descargá la versión completa de 90 días en tu panel de cliente.</p>
</section>`;
}

function generateBundle(product: ProductData): string {
  return `
<section class="section">
  <h2>🎁 Bienvenida a tu Pack Completo</h2>
  <p>${product.description ?? "Todo lo que necesitás para tu transformación en un solo lugar."}</p>
</section>
<section class="section">
  <h2>📦 Qué Incluye</h2>
  <div class="bundle-items">
    <div class="bundle-item">✅ Plan de entrenamiento completo (${weeks(product.durationWeeks)})</div>
    <div class="bundle-item">✅ Guía nutricional personalizable</div>
    <div class="bundle-item">✅ Recetario saludable</div>
    <div class="bundle-item">✅ Planilla de seguimiento semanal</div>
    <div class="bundle-item">✅ Diario de hábitos y mindset</div>
    <div class="bundle-item">✅ Guía de suplementación básica</div>
    <div class="bundle-item">✅ Soporte por WhatsApp</div>
  </div>
</section>
<section class="section">
  <h2>🚀 Por Dónde Empezar</h2>
  <ol>
    <li><strong>Semana 0:</strong> Leé la guía completa sin apurarte. Entendé el programa antes de empezar.</li>
    <li><strong>Día -2:</strong> Hacé las fotos de antes. Medite. Pesate.</li>
    <li><strong>Día -1:</strong> Preparate: comprá lo necesario, organizá tus entrenamientos en el calendario.</li>
    <li><strong>Día 1:</strong> ¡Empezá! No esperes el lunes ni el mes perfecto. Hoy es el día.</li>
  </ol>
</section>
${nutritionGuide(product.level ?? "intermedio")}`;
}

function generatePostparto(product: ProductData): string {
  return `
<section class="section warning-box">
  <h2>⚠️ Importante antes de empezar</h2>
  <p>Este programa está diseñado para el postparto, pero cada cuerpo es diferente. <strong>Consultá con tu médico o obstétrica antes de comenzar cualquier ejercicio.</strong> El clearance médico es obligatorio. No empieces antes de las 6 semanas del parto vaginal o 8 semanas de cesárea sin autorización médica.</p>
</section>
<section class="section">
  <h2>🤱 Sobre Este Programa</h2>
  <p>${product.description ?? "Recuperación progresiva, segura y amorosa para tu cuerpo postparto."}</p>
  <div class="info-grid">
    <div class="info-card"><span class="icon">💚</span><div><strong>Enfoque</strong><br>Terapéutico y progresivo</div></div>
    <div class="info-card"><span class="icon">⏱</span><div><strong>Duración</strong><br>${weeks(product.durationWeeks)}</div></div>
    <div class="info-card"><span class="icon">⏰</span><div><strong>Sesión</strong><br>20-40 minutos</div></div>
  </div>
</section>
<section class="section">
  <h2>📋 Fases del Programa</h2>
  ${Array.from({ length: product.durationWeeks ?? 8 }, (_, i) => {
    const week = i + 1;
    const phases = [
      { title: "Reconexión", desc: "Respiración diafragmática, activación suave del suelo pélvico, movilidad articular." },
      { title: "Activación Profunda", desc: "Ejercicios hipopresivos, activación de suelo pélvico, core profundo (transverso)." },
      { title: "Fortalecimiento Inicial", desc: "Puente de glúteos, sentadillas suaves, caminata progresiva." },
      { title: "Progresión", desc: "Añadir carga progresiva, aumentar duración de sesiones, introducir cardio suave." },
      { title: "Funcional", desc: "Movimientos funcionales del día a día. Integración de trabajo con el bebé." },
      { title: "Retorno al Ejercicio", desc: "Introducción a ejercicios más dinámicos con control total." },
      { title: "Consolidación", desc: "Rutinas completas de 40 minutos, trabajo de fuerza y cardio moderado." },
      { title: "Independencia", desc: "Ya tenés las herramientas para seguir sola o con cualquier programa." },
    ];
    const phase = phases[Math.min(week - 1, phases.length - 1)];
    return `<div class="week-block"><div class="week-header">Semana ${week}: ${phase.title}</div><p>${phase.desc}</p></div>`;
  }).join("")}
</section>`;
}

// ── Ensamblador principal ────────────────────────────────────────────

export function generateGuideHTML(product: ProductData): string {
  const type = product.productType;
  const name = product.name;
  const level = levelLabel(product.level);
  const duration = weeks(product.durationWeeks);

  const isPostparto = /postparto|diástasis|diastasis/i.test(name + (product.category?.name ?? ""));
  const isRecipe = /receta|nutri|ebook/i.test(type + " " + name);
  const isChallenge = type === "CHALLENGE";
  const isDiary = type === "TEMPLATE";
  const isBundle = type === "BUNDLE";

  let bodyContent = "";
  if (isPostparto) bodyContent = generatePostparto(product);
  else if (isRecipe || type === "EBOOK") bodyContent = generateRecipeBook(product);
  else if (isChallenge) bodyContent = generateChallenge(product);
  else if (isDiary) bodyContent = generateDiary(product);
  else if (isBundle) bodyContent = generateBundle(product);
  else bodyContent = generatePDFGuide(product);

  return `<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${name}</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: 'Georgia', serif;
    font-size: 15px;
    line-height: 1.7;
    color: #1a1a1a;
    background: #fff;
    max-width: 820px;
    margin: 0 auto;
    padding: 20px 30px;
  }

  /* ── Portada ─────────────────────────────────────────── */
  .cover {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    justify-content: center;
    background: linear-gradient(135deg, #1a1a1a 0%, #333 100%);
    color: white;
    padding: 60px;
    margin: -20px -30px 40px;
    page-break-after: always;
  }
  .cover .brand { font-family: Arial, sans-serif; font-size: 11px; letter-spacing: 0.2em; text-transform: uppercase; color: rgba(255,255,255,0.5); margin-bottom: 40px; }
  .cover h1 { font-size: 2.8rem; line-height: 1.2; margin-bottom: 20px; }
  .cover .subtitle { font-size: 1.1rem; color: rgba(255,255,255,0.75); margin-bottom: 40px; }
  .cover .badges { display: flex; gap: 12px; flex-wrap: wrap; }
  .cover .badge { background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.3); color: white; padding: 6px 14px; border-radius: 20px; font-size: 12px; font-family: Arial, sans-serif; }

  /* ── Secciones ───────────────────────────────────────── */
  .section { margin-bottom: 40px; page-break-inside: avoid; }
  .section h2 { font-size: 1.4rem; color: #1a1a1a; border-bottom: 2px solid #1a1a1a; padding-bottom: 8px; margin-bottom: 16px; }
  .section h3 { font-size: 1.1rem; color: #333; margin: 20px 0 10px; }
  .section h4 { font-size: 0.95rem; color: #555; margin: 14px 0 6px; }
  .section p { margin-bottom: 12px; }
  .section ul, .section ol { padding-left: 24px; margin-bottom: 12px; }
  .section li { margin-bottom: 6px; }
  .intro-text { color: #555; font-style: italic; margin-bottom: 16px; }

  /* ── Info grid ───────────────────────────────────────── */
  .info-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin: 20px 0; }
  .info-card { background: #f5f5f5; border-left: 3px solid #1a1a1a; padding: 14px; display: flex; align-items: center; gap: 10px; }
  .info-card .icon { font-size: 1.5rem; }
  .info-card strong { display: block; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: #888; margin-bottom: 2px; }

  /* ── Plan semanas ────────────────────────────────────── */
  .week-block { background: #f9f9f9; border-left: 4px solid #1a1a1a; padding: 14px 18px; margin-bottom: 10px; }
  .week-header { font-weight: 700; font-family: Arial, sans-serif; font-size: 0.9rem; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 4px; }

  /* ── Ejercicios ──────────────────────────────────────── */
  .exercise-card { border: 1px solid #e0e0e0; border-radius: 8px; padding: 16px; margin-bottom: 14px; }
  .exercise-card h4 { color: #1a1a1a; font-size: 1rem; margin-bottom: 6px; }
  .exercise-desc { color: #444; margin-bottom: 8px; }
  .exercise-meta { display: flex; gap: 16px; flex-wrap: wrap; }
  .sets { font-weight: 700; font-family: Arial, sans-serif; font-size: 0.85rem; background: #1a1a1a; color: white; padding: 2px 8px; border-radius: 4px; }
  .tip { font-size: 0.85rem; color: #666; font-style: italic; flex: 1; }

  /* ── Nutrición ───────────────────────────────────────── */
  .nutrition-table { width: 100%; border-collapse: collapse; margin: 12px 0; }
  .nutrition-table th { background: #1a1a1a; color: white; padding: 8px 12px; text-align: left; font-size: 0.85rem; }
  .nutrition-table td { border: 1px solid #ddd; padding: 8px 12px; font-size: 0.9rem; }
  .nutrition-table tr:nth-child(even) td { background: #f9f9f9; }

  /* ── Motivación ──────────────────────────────────────── */
  .motivacion { background: linear-gradient(135deg, #1a1a1a, #333); color: white; padding: 30px; border-radius: 8px; }
  .motivacion h2 { color: white; border-color: rgba(255,255,255,0.3); }
  .motivacion p { color: rgba(255,255,255,0.85); }
  blockquote { border-left: 4px solid rgba(255,255,255,0.4); padding-left: 20px; font-style: italic; font-size: 1.1rem; margin: 16px 0; color: rgba(255,255,255,0.9); }

  /* ── Challenge ───────────────────────────────────────── */
  .challenge-rules { background: #f5f5f5; border: 1px solid #e0e0e0; border-radius: 8px; padding: 20px; margin: 16px 0; }
  .days-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; }
  .day-card { background: #f5f5f5; border: 1px solid #e0e0e0; border-radius: 6px; padding: 10px; text-align: center; }
  .day-card.rest-day { background: #1a1a1a; color: white; border-color: #1a1a1a; }
  .day-num { font-weight: 700; font-size: 0.8rem; font-family: Arial, sans-serif; margin-bottom: 4px; }
  .day-content { font-size: 0.75rem; }

  /* ── Bundle ──────────────────────────────────────────── */
  .bundle-items { display: flex; flex-direction: column; gap: 8px; }
  .bundle-item { background: #f5f5f5; padding: 12px 16px; border-radius: 6px; font-family: Arial, sans-serif; }

  /* ── Recetas ─────────────────────────────────────────── */
  .recipe-card { border: 1px solid #e0e0e0; border-radius: 6px; padding: 14px; margin-bottom: 10px; }
  .recipe-header { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px; flex-wrap: wrap; gap: 8px; }
  .recipe-name { font-weight: 700; font-size: 1rem; }
  .recipe-meta { font-size: 0.8rem; color: #888; font-family: Arial, sans-serif; }

  /* ── Diario ──────────────────────────────────────────── */
  .diary-day { border: 1px solid #e0e0e0; border-radius: 8px; padding: 16px; margin-bottom: 14px; }
  .day-header { background: #1a1a1a; color: white; padding: 6px 12px; border-radius: 4px; font-family: Arial, sans-serif; font-size: 0.85rem; font-weight: 700; letter-spacing: 0.08em; display: inline-block; margin-bottom: 12px; }
  .diary-field { margin-bottom: 10px; }
  .diary-field label { font-size: 0.85rem; color: #555; display: block; margin-bottom: 4px; }
  .line { border-bottom: 1px solid #ccc; width: 100%; height: 24px; }

  /* ── Warning ─────────────────────────────────────────── */
  .warning-box { background: #fff3cd; border: 2px solid #ffc107; border-radius: 8px; padding: 20px; }
  .warning-box h2 { border-color: #ffc107; }

  /* ── Print ───────────────────────────────────────────── */
  @media print {
    @page { margin: 15mm 20mm; size: A4; }
    body { font-size: 13px; padding: 0; }
    .cover { margin: -15mm -20mm; padding: 40mm 30mm; min-height: 100vh; }
    .section { page-break-inside: avoid; }
    .days-grid { grid-template-columns: repeat(5, 1fr); }
  }
</style>
</head>
<body>

<!-- PORTADA -->
<div class="cover">
  <div class="brand">Fitness Business OS</div>
  <h1>${name}</h1>
  <p class="subtitle">${product.description ? product.description.substring(0, 120) + (product.description.length > 120 ? "…" : "") : "Tu guía completa de transformación"}</p>
  <div class="badges">
    <span class="badge">📊 ${level}</span>
    ${product.durationWeeks ? `<span class="badge">⏱ ${duration}</span>` : ""}
    ${product.category ? `<span class="badge">🏷️ ${product.category.name}</span>` : ""}
    <span class="badge">📄 ${product.sku}</span>
  </div>
</div>

<!-- CONTENIDO GENERADO POR TIPO -->
${bodyContent}

<!-- PIE DE PÁGINA -->
<div style="margin-top: 60px; padding-top: 20px; border-top: 1px solid #e0e0e0; text-align: center; color: #aaa; font-size: 11px; font-family: Arial, sans-serif;">
  © Fitness Business OS · ${product.sku} · Todos los derechos reservados
</div>

</body>
</html>`;
}

export function generateTrackingHTML(product: ProductData): string {
  return trackingSheet(product.name, product.durationWeeks ?? 8);
}

export function generateReadme(product: ProductData): string {
  return buildReadme(product.name, product.sku);
}
