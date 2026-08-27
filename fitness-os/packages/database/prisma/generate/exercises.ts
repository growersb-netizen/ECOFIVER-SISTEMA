/**
 * Base de datos de ejercicios — 100+ ejercicios en español rioplatense.
 * Usados por el generador de PDFs para crear contenido real de entrenamiento.
 */

export interface Exercise {
  name: string;
  muscles: string;
  equipment: string;
  instructions: string;
  beginner: string;  // sets x reps
  intermediate: string;
  advanced: string;
  rest: string;      // segundos
  tips?: string;
}

// ── GLÚTEOS Y PIERNAS ─────────────────────────────────────────────
export const GLUTE_EXERCISES: Exercise[] = [
  {
    name: "Hip Thrust con Barra",
    muscles: "Glúteo mayor, glúteo medio, isquiotibiales",
    equipment: "Barra, banco plano, discos",
    instructions: "Apoyá la espalda alta en el banco, colocá la barra sobre las caderas con protector. Empujá las caderas hacia arriba hasta que el torso quede paralelo al piso. Contraé los glúteos al máximo en la cima. Bajá controlado.",
    beginner: "3 × 12", intermediate: "4 × 10", advanced: "5 × 8",
    rest: "90", tips: "Mentón hacia el pecho para no hiperfletexionar el cuello.",
  },
  {
    name: "Sentadilla Libre con Barra",
    muscles: "Cuádriceps, glúteos, isquiotibiales, core",
    equipment: "Barra, rack de sentadillas",
    instructions: "Pies al ancho de hombros, puntas ligeramente hacia afuera. Barra sobre trapecios. Bajá como si fueras a sentarte, rodillas alineadas con los pies, pecho arriba. Profundidad al menos paralela al piso.",
    beginner: "3 × 12", intermediate: "4 × 10", advanced: "5 × 6",
    rest: "120", tips: "No dejes caer el talón. Empujá el suelo alejándolo de vos al subir.",
  },
  {
    name: "Peso Muerto Rumano",
    muscles: "Isquiotibiales, glúteo mayor, erector de la columna",
    equipment: "Barra o mancuernas",
    instructions: "De pie, pies al ancho de caderas, rodillas ligeramente flexionadas. Empujá las caderas hacia atrás mientras bajás la barra por las piernas. Sentís estiramiento en los isquios. Volvé apretando glúteos.",
    beginner: "3 × 12", intermediate: "4 × 10", advanced: "4 × 8",
    rest: "90", tips: "La espalda recta siempre. La barra roza las piernas durante todo el movimiento.",
  },
  {
    name: "Bulgarian Split Squat",
    muscles: "Cuádriceps, glúteo mayor, gemelos",
    equipment: "Banco, mancuernas opcionales",
    instructions: "Pie trasero elevado en el banco. Bajá el cuerpo hasta que la rodilla trasera casi toque el piso. El torso ligeramente inclinado hacia adelante. Subí empujando con el talón delantero.",
    beginner: "3 × 10/lado", intermediate: "3 × 12/lado", advanced: "4 × 10/lado",
    rest: "90", tips: "La distancia correcta al banco: la rodilla delantera no debe pasar la punta del pie.",
  },
  {
    name: "Patada Trasera en Polea (Kickback)",
    muscles: "Glúteo mayor",
    equipment: "Polea baja, tobillera",
    instructions: "De pie frente a la polea con tobillera en el pie de trabajo. Ligeramente inclinado hacia adelante. Empujá la pierna hacia atrás y arriba contrayendo el glúteo. No arquees la espalda.",
    beginner: "3 × 15/lado", intermediate: "4 × 12/lado", advanced: "4 × 15/lado",
    rest: "60", tips: "El movimiento viene del glúteo, no de la espalda.",
  },
  {
    name: "Abducción en Máquina",
    muscles: "Glúteo medio, glúteo menor, TFL",
    equipment: "Máquina de abducción",
    instructions: "Sentada en la máquina, pies apoyados. Separás las piernas contra la resistencia contrayendo los glúteos laterales. Controlás el regreso. No uses rebote.",
    beginner: "3 × 15", intermediate: "4 × 12", advanced: "4 × 15",
    rest: "60", tips: "Para mayor activación del glúteo medio, inclinarse ligeramente hacia adelante.",
  },
  {
    name: "Sentadilla Sumo con Mancuerna",
    muscles: "Aductores, glúteos, cuádriceps internos",
    equipment: "Mancuerna pesada",
    instructions: "Pies más anchos que los hombros, puntas hacia afuera 45°. Mancuerna sostenida con ambas manos colgando al centro. Bajá en sentadilla profunda manteniendo el torso erguido.",
    beginner: "3 × 12", intermediate: "4 × 10", advanced: "4 × 12",
    rest: "75", tips: "Rodillas en línea con los pies en todo momento.",
  },
  {
    name: "Hip Thrust Unilateral",
    muscles: "Glúteo mayor (unilateral), estabilizadores",
    equipment: "Banco, peso corporal o mancuerna",
    instructions: "Igual que el hip thrust pero con una sola pierna. La pierna libre la mantenés en el aire a 90°. Empujás con el talón de apoyo. Excelente para corregir asimetrías.",
    beginner: "3 × 10/lado", intermediate: "3 × 12/lado", advanced: "4 × 10/lado",
    rest: "75",
  },
  {
    name: "Step-Up con Mancuernas",
    muscles: "Glúteos, cuádriceps, femoral",
    equipment: "Banco o caja, mancuernas",
    instructions: "De pie frente al banco. Subís con un pie, empujás desde el talón para subir todo el cuerpo. Bajás controlado. El pie que baja no toca para ayudar.",
    beginner: "3 × 10/lado", intermediate: "3 × 12/lado", advanced: "4 × 12/lado",
    rest: "75",
  },
  {
    name: "Puente de Glúteos en el Suelo",
    muscles: "Glúteo mayor, isquiotibiales, core",
    equipment: "Colchoneta, peso opcional",
    instructions: "Acostada boca arriba, rodillas flexionadas, pies apoyados. Empujás las caderas hacia el techo apretando glúteos. Mantenés 2 segundos arriba. Bajás sin apoyar.",
    beginner: "3 × 15", intermediate: "4 × 12", advanced: "4 × 15 + peso",
    rest: "60", tips: "Si es fácil, colocá una mancuerna o disco sobre las caderas.",
  },
  {
    name: "Clamshell con Banda",
    muscles: "Glúteo medio, rotadores externos de cadera",
    equipment: "Banda elástica",
    instructions: "Acostada de lado, rodillas y caderas flexionadas 45°. Banda sobre los muslos. Abrís la rodilla superior hacia el techo como una almeja, sin mover la cadera.",
    beginner: "3 × 15/lado", intermediate: "3 × 20/lado", advanced: "4 × 20/lado",
    rest: "45",
  },
  {
    name: "Curl de Piernas en Máquina",
    muscles: "Isquiotibiales, gemelos",
    equipment: "Máquina curl femoral",
    instructions: "Boca abajo en la máquina, rodillas al borde. Flexionás las piernas trayendo los talones hacia los glúteos. Bajás muy lento (3-4 segundos) para aprovechar la fase excéntrica.",
    beginner: "3 × 12", intermediate: "4 × 10", advanced: "4 × 8 + drop set",
    rest: "75",
  },
];

// ── CORE Y ABDOMEN ────────────────────────────────────────────────
export const CORE_EXERCISES: Exercise[] = [
  {
    name: "Plancha Frontal",
    muscles: "Core completo, transverso abdominal, hombros",
    equipment: "Colchoneta",
    instructions: "Apoyada en antebrazos y puntas de pies. Cuerpo en línea recta de cabeza a talones. Contraés el abdomen empujando el ombligo hacia la columna. Respiración normal.",
    beginner: "3 × 20 seg", intermediate: "3 × 40 seg", advanced: "4 × 60 seg",
    rest: "45",
  },
  {
    name: "Plancha Lateral",
    muscles: "Oblicuos, glúteo medio, estabilizadores",
    equipment: "Colchoneta",
    instructions: "Apoyo en un antebrazo y el borde externo del pie. Caderas arriba, cuerpo en línea recta. No dejes caer la cadera.",
    beginner: "3 × 15 seg/lado", intermediate: "3 × 30 seg/lado", advanced: "4 × 45 seg/lado",
    rest: "45",
  },
  {
    name: "Dead Bug",
    muscles: "Core profundo, transverso, psoas",
    equipment: "Colchoneta",
    instructions: "Boca arriba, brazos extendidos hacia el techo, rodillas en 90°. Bajás simultáneamente brazo derecho y pierna izquierda sin que la espalda baja se despegue del piso. Alternás lados.",
    beginner: "3 × 8/lado", intermediate: "3 × 12/lado", advanced: "4 × 12/lado",
    rest: "60", tips: "La espalda baja siempre en contacto con el piso.",
  },
  {
    name: "Bird Dog",
    muscles: "Erector, core, glúteos, hombros",
    equipment: "Colchoneta",
    instructions: "En cuadrupedia, espalda neutra. Extendés brazo derecho y pierna izquierda simultáneamente. Mantenés 2 segundos. Regresás con control. Alternás.",
    beginner: "3 × 8/lado", intermediate: "3 × 12/lado", advanced: "4 × 12/lado con banda",
    rest: "45",
  },
  {
    name: "Russian Twist",
    muscles: "Oblicuos, recto abdominal",
    equipment: "Colchoneta, disco o mancuerna opcional",
    instructions: "Sentada con torso a 45°, rodillas flexionadas. Rotás el torso de lado a lado. Para mayor dificultad, levantás los pies del piso o agregás peso.",
    beginner: "3 × 20 (total)", intermediate: "3 × 30", advanced: "4 × 30 con peso",
    rest: "45",
  },
  {
    name: "Elevación de Piernas Acostada",
    muscles: "Psoas, recto abdominal inferior",
    equipment: "Colchoneta",
    instructions: "Boca arriba, manos bajo los glúteos. Piernas extendidas o levemente flexionadas. Subís hasta 90° y bajás sin que los pies toquen el piso.",
    beginner: "3 × 10", intermediate: "3 × 15", advanced: "4 × 15",
    rest: "60",
  },
  {
    name: "Mountain Climbers",
    muscles: "Core, hombros, caderas, cardio",
    equipment: "Colchoneta",
    instructions: "Posición de plancha alta. Llevás una rodilla hacia el pecho alternando rápidamente. Caderas estables, sin subir ni bajar.",
    beginner: "3 × 20 seg", intermediate: "3 × 35 seg", advanced: "4 × 45 seg",
    rest: "45",
  },
  {
    name: "Hollow Body Hold",
    muscles: "Core completo, estabilizadores",
    equipment: "Colchoneta",
    instructions: "Boca arriba, brazos extendidos sobre la cabeza. Elevas hombros y piernas del piso manteniendo espalda baja en contacto. Posición de 'banana al revés'.",
    beginner: "3 × 15 seg", intermediate: "3 × 30 seg", advanced: "4 × 45 seg",
    rest: "45",
  },
  {
    name: "Plancha con Toque de Hombro",
    muscles: "Core anti-rotacional, hombros",
    equipment: "Colchoneta",
    instructions: "Plancha alta (brazos extendidos). Llevás una mano al hombro opuesto. La cadera no rota. Alternás lados.",
    beginner: "3 × 10 (5/lado)", intermediate: "3 × 16", advanced: "4 × 20",
    rest: "60",
  },
  {
    name: "Rollout con Rueda Abdominal",
    muscles: "Core completo, hombros, dorsales",
    equipment: "Rueda abdominal",
    instructions: "De rodillas, rueda en el suelo frente a vos. Rodás hacia adelante controlando la posición. Volvés contrayendo el core, no la espalda.",
    beginner: "3 × 8", intermediate: "3 × 12", advanced: "4 × 12 (de pie)",
    rest: "75", tips: "El movimiento más completo para el core. Dominá primero de rodillas.",
  },
];

// ── TREN SUPERIOR ─────────────────────────────────────────────────
export const UPPER_BODY_EXERCISES: Exercise[] = [
  {
    name: "Press de Banca con Barra",
    muscles: "Pectoral mayor, deltoides anterior, tríceps",
    equipment: "Barra, banco plano, rack",
    instructions: "Tumbado en banco, pies en el suelo. Agarre algo más ancho que hombros. Bajás la barra al pecho tocándolo suavemente. Empujás hasta extensión sin bloquear codos.",
    beginner: "3 × 12", intermediate: "4 × 10", advanced: "5 × 5",
    rest: "90",
  },
  {
    name: "Press Militar con Mancuernas",
    muscles: "Deltoides, tríceps, trapecios",
    equipment: "Mancuernas, banco con respaldo",
    instructions: "Sentado, mancuernas a la altura de los hombros. Empujás hacia arriba hasta casi extensión. Bajás controlado. Codos ligeramente por delante del cuerpo.",
    beginner: "3 × 12", intermediate: "4 × 10", advanced: "4 × 8",
    rest: "90",
  },
  {
    name: "Jalón al Pecho en Polea",
    muscles: "Dorsal ancho, bíceps, romboides",
    equipment: "Polea alta, barra de jalón",
    instructions: "Sentada, rodillas bajo el soporte. Agarre prono, algo más ancho que hombros. Jalás la barra hacia el pecho superior manteniendo el torso erguido y los codos apuntando al suelo.",
    beginner: "3 × 12", intermediate: "4 × 10", advanced: "4 × 8",
    rest: "75",
  },
  {
    name: "Dominadas (Pull-ups)",
    muscles: "Dorsal ancho, bíceps, core",
    equipment: "Barra de dominadas",
    instructions: "Colgada de la barra con agarre prono. Contraés el dorsal para llevar el pecho a la barra. Bajás completamente. Si no podés, usás banda elástica de asistencia.",
    beginner: "3 × máx (asistido)", intermediate: "3 × 5", advanced: "4 × 8",
    rest: "120",
  },
  {
    name: "Remo con Barra",
    muscles: "Dorsal ancho, romboides, trapecios, bíceps",
    equipment: "Barra, discos",
    instructions: "Inclinada hacia adelante, espalda recta. Barra colgando. Jalás hacia el ombligo contrayendo los omóplatos. Codos pegados al cuerpo.",
    beginner: "3 × 12", intermediate: "4 × 10", advanced: "4 × 8",
    rest: "90",
  },
  {
    name: "Curl de Bíceps con Barra",
    muscles: "Bíceps braquial, braquial",
    equipment: "Barra recta o EZ",
    instructions: "De pie, agarre supino al ancho de hombros. Flexionás el codo llevando la barra hacia los hombros. Codos fijos a los costados. Bajás en 3 segundos.",
    beginner: "3 × 12", intermediate: "3 × 10", advanced: "4 × 10",
    rest: "60",
  },
  {
    name: "Press Francés (Tríceps)",
    muscles: "Tríceps largo, lateral y medial",
    equipment: "Barra EZ o mancuerna, banco",
    instructions: "Acostada, barra sobre el pecho. Bajás la barra hacia la frente flexionando solo el codo. Los brazos permanecen verticales. Extendés volviendo a la posición inicial.",
    beginner: "3 × 12", intermediate: "3 × 10", advanced: "4 × 10",
    rest: "75",
  },
  {
    name: "Elevación Lateral con Mancuernas",
    muscles: "Deltoides lateral",
    equipment: "Mancuernas",
    instructions: "De pie, mancuernas a los costados. Elevás los brazos lateralmente hasta la altura de los hombros. Codos ligeramente flexionados. Bajás controlado.",
    beginner: "3 × 15", intermediate: "3 × 12", advanced: "4 × 12",
    rest: "60", tips: "No balancees el cuerpo. El movimiento es puro de hombro.",
  },
  {
    name: "Face Pull en Polea",
    muscles: "Deltoides posterior, rotadores externos, romboides",
    equipment: "Polea alta, cuerda",
    instructions: "Polea a la altura de la cabeza. Jalás la cuerda hacia tu cara separando las manos. Codos arriba y atrás. Excelente para la postura y la salud del hombro.",
    beginner: "3 × 15", intermediate: "3 × 15", advanced: "4 × 15",
    rest: "60",
  },
  {
    name: "Fondos en Paralelas",
    muscles: "Pectoral, tríceps, deltoides anterior",
    equipment: "Paralelas o silla",
    instructions: "Apoyada en paralelas, cuerpo erguido. Bajás flexionando los codos hasta 90°. Subís extendiendo los brazos. Para enfatizar pecho, inclinarse ligeramente hacia adelante.",
    beginner: "3 × máx (asistido)", intermediate: "3 × 8", advanced: "4 × 10",
    rest: "90",
  },
  {
    name: "Push-ups (Flexiones)",
    muscles: "Pectoral, tríceps, deltoides anterior, core",
    equipment: "Colchoneta",
    instructions: "Manos al ancho de hombros, cuerpo en línea recta. Bajás el pecho hasta casi tocar el suelo. Empujás volviendo. Modificación: rodillas en el suelo.",
    beginner: "3 × 8 (rodillas)", intermediate: "3 × 12", advanced: "4 × 15",
    rest: "60",
  },
];

// ── CARDIO / HIIT ─────────────────────────────────────────────────
export const CARDIO_EXERCISES: Exercise[] = [
  {
    name: "Burpees",
    muscles: "Cuerpo completo, cardio",
    equipment: "Ninguno",
    instructions: "De pie, bajás las manos al suelo, saltás los pies atrás (plancha), hacés una flexión opcional, saltás los pies al frente y finalizás con un salto con brazos arriba.",
    beginner: "3 × 8", intermediate: "3 × 12", advanced: "4 × 15",
    rest: "60",
  },
  {
    name: "Jumping Jacks",
    muscles: "Cardio, piernas, hombros",
    equipment: "Ninguno",
    instructions: "De pie. Saltás abriendo piernas y brazos simultáneamente. Cerrás volviendo a la posición inicial. Ritmo constante.",
    beginner: "3 × 30 seg", intermediate: "3 × 45 seg", advanced: "4 × 60 seg",
    rest: "30",
  },
  {
    name: "High Knees",
    muscles: "Cardio, psoas, gemelos",
    equipment: "Ninguno",
    instructions: "Corrés en el lugar elevando las rodillas lo más alto posible. Los brazos se mueven como al correr. Caderas estables.",
    beginner: "3 × 20 seg", intermediate: "3 × 40 seg", advanced: "4 × 60 seg",
    rest: "30",
  },
  {
    name: "Box Jumps",
    muscles: "Glúteos, cuádriceps, gemelos, potencia",
    equipment: "Caja o plataforma",
    instructions: "De pie frente a la caja. Brazos atrás, sentadilla rápida y salto explosivo. Aterrizás sobre la caja con ambos pies en sentadilla suave. Bajás caminando.",
    beginner: "3 × 6", intermediate: "3 × 8", advanced: "4 × 10",
    rest: "90",
  },
  {
    name: "Salto a Comba (Cuerda)",
    muscles: "Cardio, gemelos, coordinación",
    equipment: "Cuerda de saltar",
    instructions: "Comba a los costados. Saltás con ambos pies al mismo tiempo manteniendo el ritmo. Aterrizás suave en la planta del pie.",
    beginner: "3 × 30 seg", intermediate: "3 × 60 seg", advanced: "5 × 60 seg",
    rest: "30",
  },
];

// ── YOGA Y FLEXIBILIDAD ───────────────────────────────────────────
export const YOGA_EXERCISES: Exercise[] = [
  {
    name: "Perro Boca Abajo (Downward Dog)",
    muscles: "Isquiotibiales, gemelos, hombros, dorsal",
    equipment: "Mat de yoga",
    instructions: "Manos y pies en el suelo, caderas arriba formando una V invertida. Intentás acercar los talones al suelo. Relax en el cuello. Respiración profunda.",
    beginner: "3 × 30 seg", intermediate: "5 × 30 seg", advanced: "5 × 60 seg",
    rest: "15",
  },
  {
    name: "Guerrero I (Warrior I)",
    muscles: "Cuádriceps, cadera flexora, hombros",
    equipment: "Mat de yoga",
    instructions: "Pie delantero al frente, pie trasero a 45°. Flexionás la rodilla delantera a 90°. Brazos arriba, pecho abierto hacia adelante. Caderas cuadradas.",
    beginner: "3 × 30 seg/lado", intermediate: "3 × 45 seg/lado", advanced: "5 × 60 seg/lado",
    rest: "15",
  },
  {
    name: "Guerrero II (Warrior II)",
    muscles: "Piernas, caderas, hombros, concentración",
    equipment: "Mat de yoga",
    instructions: "Pie delantero al frente, pie trasero a 90°. Rodilla delantera sobre el tobillo. Brazos extendidos paralelos al suelo. Mirada sobre la mano delantera.",
    beginner: "3 × 30 seg/lado", intermediate: "3 × 45 seg/lado", advanced: "5 × 60 seg/lado",
    rest: "15",
  },
  {
    name: "Postura del Niño (Child's Pose)",
    muscles: "Espalda baja, cadera, hombros (estiramiento)",
    equipment: "Mat de yoga",
    instructions: "Arrodillada, glúteos hacia los talones, brazos extendidos adelante. Frente en el suelo. Respiración profunda. Postura de descanso y relajación.",
    beginner: "3 × 60 seg", intermediate: "3 × 90 seg", advanced: "3 × 120 seg",
    rest: "0",
  },
  {
    name: "Paloma (Pigeon Pose)",
    muscles: "Cadera, piriforme, flexores de cadera",
    equipment: "Mat de yoga",
    instructions: "Una pierna delantera cruzada frente al cuerpo, pierna trasera extendida. Inclinarte hacia adelante sobre la pierna delantera. Uno de los mejores estiramientos de cadera.",
    beginner: "3 × 45 seg/lado", intermediate: "3 × 60 seg/lado", advanced: "3 × 90 seg/lado",
    rest: "15",
  },
  {
    name: "Gato-Vaca (Cat-Cow)",
    muscles: "Columna, core, cuello",
    equipment: "Mat de yoga",
    instructions: "En cuadrupedia. Arqueas la espalda hacia arriba (gato) al exhalar. Hundes la espalda (vaca) al inhalar. Movimiento fluido y rítmico con la respiración.",
    beginner: "3 × 10 respiraciones", intermediate: "3 × 15 respiraciones", advanced: "3 × 20 respiraciones",
    rest: "15",
  },
  {
    name: "Puente Yoga (Bridge Pose)",
    muscles: "Glúteos, isquiotibiales, core",
    equipment: "Mat de yoga",
    instructions: "Boca arriba, rodillas flexionadas. Elevás las caderas hacia el techo apretando glúteos. Brazos extendidos en el suelo a los costados. Hombros en el piso.",
    beginner: "3 × 30 seg", intermediate: "3 × 45 seg", advanced: "3 × 60 seg o dinámico",
    rest: "30",
  },
  {
    name: "Torsión Espinal Sentada (Seated Spinal Twist)",
    muscles: "Columna, oblicuos, caderas",
    equipment: "Mat de yoga",
    instructions: "Sentada con piernas extendidas. Flexionás una rodilla y cruzás el pie al otro lado. Rotás el torso hacia el lado de la rodilla flexionada. Respiración profunda.",
    beginner: "3 × 30 seg/lado", intermediate: "3 × 45 seg/lado", advanced: "3 × 60 seg/lado",
    rest: "15",
  },
  {
    name: "Mariposa (Butterfly Pose)",
    muscles: "Aductores, ingles, cadera interna",
    equipment: "Mat de yoga",
    instructions: "Sentada, plantas de los pies unidas frente a vos. Sujetás los pies con las manos. Dejás caer las rodillas hacia el suelo. Podés inclinarte levemente hacia adelante.",
    beginner: "3 × 45 seg", intermediate: "3 × 60 seg", advanced: "3 × 90 seg",
    rest: "15",
  },
];

// ── POSTPARTO ─────────────────────────────────────────────────────
export const POSTPARTUM_EXERCISES: Exercise[] = [
  {
    name: "Respiración Diafragmática",
    muscles: "Diafragma, transverso abdominal",
    equipment: "Ninguno",
    instructions: "Acostada boca arriba. Inhalás lentamente por la nariz, expandiendo el abdomen (no el pecho). Exhalás lentamente por la boca. Esta es la base de toda recuperación postparto.",
    beginner: "5 × 10 respiraciones", intermediate: "5 × 10", advanced: "5 × 10",
    rest: "30", tips: "Hacé esto ANTES de cualquier otro ejercicio postparto.",
  },
  {
    name: "Kegel",
    muscles: "Suelo pélvico",
    equipment: "Ninguno",
    instructions: "Contraés los músculos del suelo pélvico como si estuvieras cortando el flujo de orina. Mantenés 5 segundos, relajás 10 segundos. Progresivamente aumentás el tiempo de contracción.",
    beginner: "3 × 10 contracciones", intermediate: "4 × 15", advanced: "5 × 20",
    rest: "30", tips: "No contraigas glúteos ni muslos. Solo el suelo pélvico.",
  },
  {
    name: "Inclinación Pélvica Suave",
    muscles: "Core profundo, espalda baja",
    equipment: "Colchoneta",
    instructions: "Acostada boca arriba, rodillas flexionadas. Aplanás la espalda baja contra el suelo empujando con el abdomen. Mantenés 5 seg. Liberás.",
    beginner: "3 × 10", intermediate: "3 × 15", advanced: "4 × 15",
    rest: "30",
  },
  {
    name: "Marcha en el Lugar (Boca Arriba)",
    muscles: "Core, psoas, coordinación",
    equipment: "Colchoneta",
    instructions: "Acostada boca arriba, rodillas flexionadas. Levantás una rodilla hacia el pecho manteniendo la espalda baja en el piso. Alternás lentamente. Respiración constante.",
    beginner: "3 × 8/lado", intermediate: "3 × 12/lado", advanced: "4 × 15/lado",
    rest: "45",
  },
  {
    name: "Puente de Glúteos Suave",
    muscles: "Glúteos, core",
    equipment: "Colchoneta",
    instructions: "Igual que el puente clásico pero sin forzar. Sólo subís hasta donde el cuerpo lo permita sin dolor ni presión. Priorizás la activación consciente de los glúteos.",
    beginner: "3 × 10", intermediate: "3 × 15", advanced: "4 × 15",
    rest: "45",
  },
  {
    name: "Bird Dog Modificado",
    muscles: "Core, erector, glúteos",
    equipment: "Colchoneta",
    instructions: "En cuadrupedia. Extendés un brazo hacia adelante. Sin levantar la pierna opuesta todavía. Cuando sea cómodo, agregás la extensión de pierna.",
    beginner: "3 × 8/lado (solo brazo)", intermediate: "3 × 10/lado (brazo+pierna)", advanced: "4 × 12/lado",
    rest: "45",
  },
  {
    name: "Sentadilla en Silla",
    muscles: "Cuádriceps, glúteos, core",
    equipment: "Silla",
    instructions: "De pie frente a la silla. Bajás como para sentarte pero tocás levemente el asiento y volvés a pararte. Progresivamente evolucionás a sentadilla libre.",
    beginner: "3 × 10", intermediate: "3 × 15", advanced: "3 × 20 sin silla",
    rest: "60",
  },
];

// ── CALISTENIA / PESO CORPORAL ────────────────────────────────────
export const BODYWEIGHT_EXERCISES: Exercise[] = [
  {
    name: "Sentadilla con Peso Corporal",
    muscles: "Cuádriceps, glúteos, isquiotibiales, core",
    equipment: "Ninguno",
    instructions: "Pies al ancho de hombros. Bajás con el torso recto hasta que los muslos estén paralelos. Subís empujando a través de los talones.",
    beginner: "3 × 15", intermediate: "4 × 20", advanced: "4 × 25 o a una pierna",
    rest: "60",
  },
  {
    name: "Zancada Caminando",
    muscles: "Cuádriceps, glúteos, isquiotibiales",
    equipment: "Espacio libre",
    instructions: "Paso largo hacia adelante, rodilla trasera casi toca el suelo. Empujás con el pie delantero para avanzar con la pierna trasera.",
    beginner: "3 × 10 pasos", intermediate: "3 × 16 pasos", advanced: "4 × 20 pasos",
    rest: "60",
  },
  {
    name: "Flexiones de Rodillas (Push-up Modificada)",
    muscles: "Pectoral, tríceps, deltoides",
    equipment: "Colchoneta",
    instructions: "Manos al ancho de hombros, rodillas en el suelo. Bajás el pecho hacia el suelo. Empujás volviendo. Cuerpo en línea recta de rodillas a cabeza.",
    beginner: "3 × 8", intermediate: "3 × 15", advanced: "4 × 20 (pies en suelo)",
    rest: "60",
  },
  {
    name: "Dips en Silla",
    muscles: "Tríceps, pectoral inferior",
    equipment: "Silla o banco",
    instructions: "Sentada al borde de la silla, manos al borde. Deslizás el cuerpo hacia adelante. Bajás flexionando codos hasta 90°. Subís empujando.",
    beginner: "3 × 8", intermediate: "3 × 12", advanced: "4 × 15",
    rest: "75",
  },
  {
    name: "Superman",
    muscles: "Erector espinal, glúteos, dorsales",
    equipment: "Colchoneta",
    instructions: "Boca abajo, brazos extendidos. Elevás simultáneamente brazos y piernas del suelo. Mantenés 2-3 segundos. Bajás con control.",
    beginner: "3 × 10", intermediate: "3 × 15", advanced: "4 × 15",
    rest: "45",
  },
  {
    name: "Sentadilla con Salto",
    muscles: "Cuádriceps, glúteos, gemelos, potencia",
    equipment: "Ninguno",
    instructions: "Sentadilla completa y al subir, en lugar de pararte, saltás con los brazos hacia arriba. Aterrizás suave volviendo a la sentadilla.",
    beginner: "3 × 8", intermediate: "3 × 12", advanced: "4 × 15",
    rest: "75",
  },
  {
    name: "Bear Crawl",
    muscles: "Core, hombros, cuádriceps, coordinación",
    equipment: "Espacio libre",
    instructions: "En cuadrupedia con rodillas levantadas a 5 cm del suelo. Avanzás moviendo el brazo y la pierna opuesta simultáneamente. Caderas estables.",
    beginner: "3 × 15 seg", intermediate: "3 × 30 seg", advanced: "4 × 45 seg",
    rest: "60",
  },
];

// ── FUERZA / GYM ──────────────────────────────────────────────────
export const STRENGTH_EXERCISES: Exercise[] = [
  {
    name: "Sentadilla con Barra (Back Squat)",
    muscles: "Cuádriceps, glúteos, isquiotibiales, core",
    equipment: "Barra, rack",
    instructions: "Barra en la espalda alta o baja. Pies al ancho de hombros. Descenso controlado hasta paralelo o más profundo. Ascenso explosivo.",
    beginner: "3 × 5", intermediate: "4 × 4", advanced: "5 × 3",
    rest: "180", tips: "El rey de los ejercicios. La técnica perfecta primero.",
  },
  {
    name: "Peso Muerto Convencional",
    muscles: "Isquiotibiales, glúteos, erector, cuádriceps, core",
    equipment: "Barra, discos",
    instructions: "Pies al ancho de caderas. Agarrás la barra. Espalda recta. Empujás el suelo alejándolo de vos. La barra sube pegada a las piernas. Bloqueo completo arriba.",
    beginner: "3 × 5", intermediate: "4 × 4", advanced: "5 × 3",
    rest: "180", tips: "El ejercicio más completo que existe. Aprende la técnica con peso vacío.",
  },
  {
    name: "Press de Banca Inclinado",
    muscles: "Pectoral superior, deltoides anterior, tríceps",
    equipment: "Banco inclinado (45°), barra o mancuernas",
    instructions: "Banco a 30-45°. Descenso al pecho superior. Empujás manteniendo los omóplatos juntos. Rango completo de movimiento.",
    beginner: "3 × 10", intermediate: "4 × 8", advanced: "4 × 6",
    rest: "90",
  },
  {
    name: "Swing con Kettlebell",
    muscles: "Glúteos, isquiotibiales, core, espalda",
    equipment: "Kettlebell",
    instructions: "Pies al ancho de hombros, KB entre los pies. Bisagra de cadera hacia atrás, swing explosivo hacia adelante. El movimiento es de las caderas, no de los brazos.",
    beginner: "3 × 12", intermediate: "4 × 15", advanced: "5 × 20",
    rest: "60", tips: "Las caderas son el motor. Los brazos solo guían.",
  },
  {
    name: "Press Militar con Barra",
    muscles: "Deltoides, tríceps, core",
    equipment: "Barra, rack o peso libre",
    instructions: "De pie, barra a la altura de los hombros, agarre prono. Empujás hacia arriba hasta extensión. Bajás controlado. Core activado durante todo el movimiento.",
    beginner: "3 × 8", intermediate: "4 × 6", advanced: "5 × 3",
    rest: "120",
  },
  {
    name: "Sentadilla Frontal",
    muscles: "Cuádriceps, core, dorsales",
    equipment: "Barra",
    instructions: "Barra sobre los deltoides delanteros con agarre cruzado o limpio. Codos arriba. Torso muy erguido. Sentadilla profunda.",
    beginner: "3 × 8", intermediate: "4 × 6", advanced: "4 × 4",
    rest: "120",
  },
];

// Export consolidado por categoría
export const EXERCISE_POOL = {
  glutes: GLUTE_EXERCISES,
  core: CORE_EXERCISES,
  upper: UPPER_BODY_EXERCISES,
  cardio: CARDIO_EXERCISES,
  yoga: YOGA_EXERCISES,
  postpartum: POSTPARTUM_EXERCISES,
  bodyweight: BODYWEIGHT_EXERCISES,
  strength: STRENGTH_EXERCISES,
};

/** Selecciona N ejercicios de un pool, con rotación basada en un seed string */
export function selectExercises(pool: Exercise[], count: number, seed: string): Exercise[] {
  const hash = seed.split("").reduce((a, c) => a + c.charCodeAt(0), 0);
  const shuffled = [...pool].sort((a, b) => {
    const ai = (pool.indexOf(a) * 31 + hash) % pool.length;
    const bi = (pool.indexOf(b) * 31 + hash) % pool.length;
    return ai - bi;
  });
  return shuffled.slice(0, count);
}
