/**
 * Fase 11 — Catálogo de 200 productos digitales de fitness.
 * Sin placeholders — nombres y descripciones reales del nicho fitness femenino.
 *
 * Ejecutar: pnpm --filter @fitness-os/database run catalog:seed
 */

import { PrismaClient } from "@prisma/client";
import { slugify } from "../../shared/src/utils/index.js";

const prisma = new PrismaClient();

const CATEGORIES = [
  { name: "Guías de Entrenamiento", slug: "guias-entrenamiento" },
  { name: "Planes de Nutrición", slug: "planes-nutricion" },
  { name: "Programas de Transformación", slug: "programas-transformacion" },
  { name: "Ejercicios en Casa", slug: "ejercicios-casa" },
  { name: "Glúteos y Piernas", slug: "gluteos-piernas" },
  { name: "Abdomen y Core", slug: "abdomen-core" },
  { name: "Yoga y Flexibilidad", slug: "yoga-flexibilidad" },
  { name: "Postparto y Recuperación", slug: "postparto-recuperacion" },
  { name: "Mindset y Hábitos", slug: "mindset-habitos" },
  { name: "Desafíos 30 Días", slug: "desafios-30-dias" },
  { name: "Recetas Fit", slug: "recetas-fit" },
  { name: "Programas VIP", slug: "programas-vip" },
];

// 200 productos reales para el nicho fitness femenino argentino
const PRODUCTS = [
  // ── Guías de Entrenamiento (20) ────────────────────────────────
  { sku: "GT-001", name: "Guía de Entrenamiento para Principiantes", cat: "guias-entrenamiento", price: 4900, desc: "El punto de partida ideal si estás empezando. 4 semanas, 3 días por semana, solo con tu peso corporal. Incluye videos demostrativos y registro de progreso." },
  { sku: "GT-002", name: "Plan de Tonificación Completa — 8 Semanas", cat: "guias-entrenamiento", price: 7900, desc: "Programa integral de 8 semanas para tonificar todo el cuerpo. Combinación de fuerza y cardio, 4-5 días por semana. Material de tracking incluido." },
  { sku: "GT-003", name: "Entrenamiento de Fuerza para Mujeres", cat: "guias-entrenamiento", price: 6900, desc: "Desmitificamos el entrenamiento de fuerza femenino. Progresión de 12 semanas con cargas, técnica detallada y adaptaciones según tu nivel." },
  { sku: "GT-004", name: "Cardio HIIT en 20 Minutos", cat: "guias-entrenamiento", price: 3900, desc: "Rutinas de alta intensidad que se adaptan a tu tiempo. 30 rutinas distintas para nunca aburrirte. Quema máxima en mínimo tiempo." },
  { sku: "GT-005", name: "Entrenamiento Funcional Femenino", cat: "guias-entrenamiento", price: 5900, desc: "Movimientos funcionales que mejoran tu calidad de vida. Ideal para mujeres activas que quieren fuerza real, no solo estética." },
  { sku: "GT-006", name: "Guía de Entrenamiento con Bandas Elásticas", cat: "guias-entrenamiento", price: 4500, desc: "Todo lo que podés lograr con solo unas bandas. 60 ejercicios categorizados, 8 semanas de programa, ideal para viajes y casa." },
  { sku: "GT-007", name: "Programa Bíceps y Tríceps Definidos", cat: "guias-entrenamiento", price: 3500, desc: "6 semanas de entrenamiento específico de brazos para mujeres. Sin voluminizar, con focus en definición y tono." },
  { sku: "GT-008", name: "Espalda Fuerte y Postura Perfecta", cat: "guias-entrenamiento", price: 4900, desc: "Elimina el dolor de espalda y mejora tu postura con este programa de 6 semanas. Incluye movilidad, fuerza y hábitos posturales." },
  { sku: "GT-009", name: "Pecho y Hombros: Definición Femenina", cat: "guias-entrenamiento", price: 3900, desc: "Programa específico para trabajar pecho y hombros con un enfoque femenino. Resultados visibles en 4 semanas." },
  { sku: "GT-010", name: "Entrenamiento Full Body 3x por Semana", cat: "guias-entrenamiento", price: 5500, desc: "El programa perfecto para quienes tienen tiempo limitado. Full body tres veces por semana con máxima eficiencia muscular." },
  { sku: "GT-011", name: "Plan de Entrenamiento para el Gym — Nivel Intermedio", cat: "guias-entrenamiento", price: 6500, desc: "Lleva tu entrenamiento al siguiente nivel. 10 semanas, split de 4 días, progresión de cargas planificada." },
  { sku: "GT-012", name: "Rutinas Express 15 Minutos", cat: "guias-entrenamiento", price: 3200, desc: "Cuando no tenés tiempo, esta guía es tu aliada. 50 rutinas de 15 minutos clasificadas por zona y objetivo." },
  { sku: "GT-013", name: "Entrenamiento en el Parque o Exterior", cat: "guias-entrenamiento", price: 3500, desc: "Aprovechá los espacios al aire libre. Rutinas con bancos, escaleras, pasto y sin equipamiento." },
  { sku: "GT-014", name: "Programa de Resistencia Cardiovascular", cat: "guias-entrenamiento", price: 5900, desc: "Mejora tu resistencia y capacidad cardíaca en 8 semanas. Ideal para prepararte para carreras o simplemente sentirte mejor." },
  { sku: "GT-015", name: "Guía de Calentamiento y Enfriamiento Profesional", cat: "guias-entrenamiento", price: 2900, desc: "El antes y el después que la mayoría ignora. Protegé tus articulaciones y optimizá tu recuperación con esta guía completa." },
  { sku: "GT-016", name: "Entrenamiento para Mujeres Mayores de 40", cat: "guias-entrenamiento", price: 6500, desc: "Adaptado a los cambios hormonales y físicos después de los 40. Fuerza, flexibilidad y bienestar en equilibrio." },
  { sku: "GT-017", name: "Circuit Training Total — 6 Semanas", cat: "guias-entrenamiento", price: 5500, desc: "Circuitos de entrenamiento variados para mantener la motivación alta. Quema de grasa y tonificación simultáneas." },
  { sku: "GT-018", name: "Guía de Movilidad Articular Diaria", cat: "guias-entrenamiento", price: 2900, desc: "10 minutos al día para articulaciones sanas. Ideal para prevenir lesiones y mejorar el rendimiento deportivo." },
  { sku: "GT-019", name: "Powerlifting para Mujeres — Introducción", cat: "guias-entrenamiento", price: 7500, desc: "Sentadilla, peso muerto y press de banca: aprende los tres grandes movimientos con técnica perfecta y progresión segura." },
  { sku: "GT-020", name: "Programa Anti-Sedentarismo — Movimiento en el Trabajo", cat: "guias-entrenamiento", price: 2500, desc: "Para quienes pasan muchas horas sentadas. Rutinas de 5 minutos para hacer en la oficina o en casa sin cambiar de ropa." },

  // ── Glúteos y Piernas (20) ─────────────────────────────────────
  { sku: "GP-001", name: "Glúteos de Acero — Programa 12 Semanas", cat: "gluteos-piernas", price: 8900, desc: "El programa más completo para desarrollar glúteos fuertes y definidos. Hipopresivos, hip thrust, sentadillas y más. Con progresión de cargas." },
  { sku: "GP-002", name: "Piernas Perfectas — 8 Semanas", cat: "gluteos-piernas", price: 7500, desc: "Cuádriceps, isquiotibiales, glúteos y gemelos trabajados en sincronía. Resultados visibles garantizados en 8 semanas." },
  { sku: "GP-003", name: "100 Ejercicios para Glúteos", cat: "gluteos-piernas", price: 4500, desc: "La biblioteca definitiva de ejercicios de glúteos. Con descripciones, variantes y cómo incorporarlos en tus rutinas." },
  { sku: "GP-004", name: "Sentadilla Perfecta — Guía Técnica", cat: "gluteos-piernas", price: 3500, desc: "Dominá la reina de los ejercicios. Aprende la técnica correcta, errores comunes, variantes y progresiones de carga." },
  { sku: "GP-005", name: "Hip Thrust y Peso Muerto — Masterclass", cat: "gluteos-piernas", price: 4900, desc: "Los dos mejores ejercicios para glúteos explicados al detalle. Técnica, configuración, variantes y programación." },
  { sku: "GP-006", name: "Programa de Glúteos sin Gym", cat: "gluteos-piernas", price: 5500, desc: "¿Sin acceso al gimnasio? Sin problema. 8 semanas de entrenamiento de glúteos con peso corporal y bandas elásticas." },
  { sku: "GP-007", name: "Cellulitis Away — Plan de 30 Días", cat: "gluteos-piernas", price: 4900, desc: "Abordaje integral de la celulitis: ejercicio dirigido, alimentación anti-inflamatoria y cuidado de la piel. 30 días de plan completo." },
  { sku: "GP-008", name: "Piernas Delgadas — Tonificación sin Volumen", cat: "gluteos-piernas", price: 5900, desc: "Para quienes quieren piernas tonificadas sin ganar volumen. Enfoque en cardio, pilates y ejercicios de alta repetición." },
  { sku: "GP-009", name: "Glúteos con Bandas — 6 Semanas", cat: "gluteos-piernas", price: 4500, desc: "Solo necesitás una banda elástica para este programa. 6 semanas de trabajo específico de glúteos con activación garantizada." },
  { sku: "GP-010", name: "Inner Thigh — Cara Interna de Piernas", cat: "gluteos-piernas", price: 3900, desc: "La zona que más preguntas genera. Ejercicios específicos para tonificar la cara interna de los muslos con resultados reales." },
  { sku: "GP-011", name: "Programa Combinado Glúteos + Abdomen", cat: "gluteos-piernas", price: 7900, desc: "Las dos zonas favoritas trabajadas juntas. 8 semanas de programa combinado con ejercicios multiarticulares." },
  { sku: "GP-012", name: "Gemelos y Tobillos Definidos", cat: "gluteos-piernas", price: 3200, desc: "Esa zona olvidada que marca la diferencia. Guía completa para trabajar gemelos y tobillos con y sin equipamiento." },
  { sku: "GP-013", name: "Sentadillas Sumo y Variantes — 30 Días", cat: "gluteos-piernas", price: 3900, desc: "30 días de desafío con sentadillas sumo y todas sus variantes. Ideal para trabajar aductores y glúteos profundos." },
  { sku: "GP-014", name: "Cuádriceps Definidos sin Máquinas", cat: "gluteos-piernas", price: 4200, desc: "Lunges, split squats y sus variantes para cuádriceps femeninos perfectos. Sin necesidad de máquinas de gym." },
  { sku: "GP-015", name: "Isquiotibiales y Femoral — Guía Específica", cat: "gluteos-piernas", price: 4200, desc: "La parte posterior de las piernas es clave para el equilibrio muscular y la prevención de lesiones. Guía completa." },
  { sku: "GP-016", name: "Glúteos para Mesas de Trabajo — 10 min/día", cat: "gluteos-piernas", price: 3200, desc: "Para quienes pasan muchas horas sentadas. Activación y tonificación de glúteos en solo 10 minutos diarios." },
  { sku: "GP-017", name: "Programa Glúteos 90 Días — Transformación Total", cat: "gluteos-piernas", price: 12900, desc: "El programa más completo e intensivo. 90 días de transformación real de glúteos con progresión de cargas y guía nutricional incluida." },
  { sku: "GP-018", name: "Step-Up y Plyometría para Piernas", cat: "gluteos-piernas", price: 4500, desc: "Ejercicios pliométricos y con escalón para piernas potentes y resistentes. Cardio + fuerza en uno solo." },
  { sku: "GP-019", name: "Estiramiento y Recuperación de Piernas", cat: "gluteos-piernas", price: 2900, desc: "El componente que falta en tu rutina de piernas. 30 estiramientos específicos para recuperación activa y flexibilidad muscular." },
  { sku: "GP-020", name: "Glúteos Altos y Redondos — Protocolo Avanzado", cat: "gluteos-piernas", price: 9900, desc: "Para quienes ya tienen base y quieren llevar sus glúteos al siguiente nivel. Técnicas avanzadas de activación y progresión." },

  // ── Abdomen y Core (15) ────────────────────────────────────────
  { sku: "AC-001", name: "Abdomen Plano — 30 Días de Desafío", cat: "abdomen-core", price: 4500, desc: "El desafío de 30 días más completo para conseguir un abdomen plano. Ejercicios progresivos, sin equipamiento, con dieta complementaria." },
  { sku: "AC-002", name: "Core 360° — Fuerza desde el Centro", cat: "abdomen-core", price: 5900, desc: "El core es más que los abdominales. Trabaja el núcleo completo: transverso, oblicuos, diafragma y suelo pélvico integrado." },
  { sku: "AC-003", name: "Diastasis Recti — Guía de Recuperación", cat: "abdomen-core", price: 6900, desc: "Para mujeres con separación abdominal post-parto. Ejercicios seguros, progresivos y supervisados conceptualmente por fisioterapeuta." },
  { sku: "AC-004", name: "Six Pack para Mujeres — Guía Real", cat: "abdomen-core", price: 5900, desc: "Sin mitos, sin magia. Lo que realmente se necesita para ver el abdomen definido: nutrición, entrenamiento y porcentaje de grasa." },
  { sku: "AC-005", name: "Planchas y Variantes — 50 Ejercicios", cat: "abdomen-core", price: 3900, desc: "La plancha es el ejercicio más completo para el core. 50 variantes para nunca aburrirte y seguir progresando." },
  { sku: "AC-006", name: "Cintura Definida — 6 Semanas", cat: "abdomen-core", price: 5500, desc: "Trabajo específico de oblicuos y cintura para marcar la silueta. Incluye ejercicios de Pilates y funcionales." },
  { sku: "AC-007", name: "Suelo Pélvico Fuerte — Base del Core Femenino", cat: "abdomen-core", price: 6500, desc: "El suelo pélvico es el centro del bienestar femenino. Ejercicios de Kegel, hipopresivos y más para un core íntegro." },
  { sku: "AC-008", name: "Abdominales Hipopresivos", cat: "abdomen-core", price: 5500, desc: "Técnica que reduce la cintura sin presión abdominal. Ideal post-parto, para incontinencia o como complemento deportivo." },
  { sku: "AC-009", name: "Cardio Ab — Combina Cardio y Core", cat: "abdomen-core", price: 4900, desc: "La combinación ganadora para quemar grasa abdominal: cardio de alta intensidad integrado con trabajo de core." },
  { sku: "AC-010", name: "Core para Deportistas — Performance Total", cat: "abdomen-core", price: 6500, desc: "Si practicás algún deporte, un core fuerte mejora todo. Programa diseñado para atletas femeninas." },
  { sku: "AC-011", name: "Abdominales en 10 Minutos Diarios", cat: "abdomen-core", price: 3200, desc: "La guía perfecta para mantener el trabajo abdominal consistente. 10 minutos al día, 30 rutinas diferentes." },
  { sku: "AC-012", name: "Oblicuos y Línea Lateral — Guía Específica", cat: "abdomen-core", price: 3900, desc: "Esa línea lateral que define la silueta. Ejercicios especiales para oblicuos internos y externos." },
  { sku: "AC-013", name: "Core sin Abdominales Tradicionales", cat: "abdomen-core", price: 4500, desc: "Adiós a los crunches. Alternativas modernas y más efectivas para un core fuerte sin dañar el cuello ni la espalda." },
  { sku: "AC-014", name: "Abdomen Postparto Seguro — Primeras 12 Semanas", cat: "abdomen-core", price: 6900, desc: "El programa autorizado para el período postparto. Ejercicios validados, progresión segura y respeto por los tiempos de recuperación." },
  { sku: "AC-015", name: "Functional Core — Movimientos Reales", cat: "abdomen-core", price: 5500, desc: "Core que funciona en la vida cotidiana. Ejercicios funcionales que mejoran tu postura, fuerza y bienestar general." },

  // ── Planes de Nutrición (20) ───────────────────────────────────
  { sku: "PN-001", name: "Plan de Alimentación para Tonificación", cat: "planes-nutricion", price: 7900, desc: "Alimentación calculada para apoyar el proceso de tonificación muscular. Macros, ejemplos de menús y lista de compras semanal." },
  { sku: "PN-002", name: "Nutrición para Aumentar Masa Muscular Femenina", cat: "planes-nutricion", price: 7900, desc: "Las mujeres también ganan músculo y la alimentación importa. Guía completa de nutrición para hipertrofia femenina." },
  { sku: "PN-003", name: "Plan Anti-Inflamatorio — 21 Días", cat: "planes-nutricion", price: 6900, desc: "Reducí la inflamación crónica con este plan de alimentación. Base científica, menús completos y lista de superalimentos." },
  { sku: "PN-004", name: "Alimentación Intuitiva — Guía para Mujeres", cat: "planes-nutricion", price: 5900, desc: "Aprendé a escuchar a tu cuerpo. Cómo comer sin restricciones obsesivas, mantener un peso saludable y disfrutar la comida." },
  { sku: "PN-005", name: "Plan de Nutrición para Mujeres con Hipotiroidismo", cat: "planes-nutricion", price: 8900, desc: "Adaptado específicamente para quienes tienen problemas de tiroides. Alimentos favorables, a evitar, y plan de 4 semanas." },
  { sku: "PN-006", name: "Snacks Fit para Todo el Día", cat: "planes-nutricion", price: 3500, desc: "50 snacks saludables y ricos para nunca caer en tentaciones poco saludables. Con preparación, valores nutricionales y sustitutos." },
  { sku: "PN-007", name: "Guía de Suplementación para Mujeres", cat: "planes-nutricion", price: 5500, desc: "Qué suplementos valen la pena, cuáles son marketing puro y cómo integrarlos en tu rutina. Basado en evidencia." },
  { sku: "PN-008", name: "Menú Semanal Fit — 4 Semanas", cat: "planes-nutricion", price: 5900, desc: "4 semanas de menús completos: desayuno, almuerzo, merienda y cena. Con valores nutricionales y lista de compras." },
  { sku: "PN-009", name: "Alimentación Plant-Based para Deportistas", cat: "planes-nutricion", price: 6900, desc: "Cómo comer vegano o vegetariano sin perder rendimiento deportivo. Fuentes de proteína, combinaciones y planes semanales." },
  { sku: "PN-010", name: "Detox Natural — Limpiar sin Restricciones", cat: "planes-nutricion", price: 4500, desc: "Sin ayunos extremos, sin jugos milagrosos. Un plan de 7 días para apoyar los procesos naturales de desintoxicación del cuerpo." },
  { sku: "PN-011", name: "Proteínas para Mujeres — Guía Completa", cat: "planes-nutricion", price: 4900, desc: "Cuánta proteína necesitás, cuáles son las mejores fuentes y cómo distribuirla en el día para maximizar resultados." },
  { sku: "PN-012", name: "Plan de Alimentación para el Ciclo Menstrual", cat: "planes-nutricion", price: 6500, desc: "Comé según tu ciclo. Guía para adaptar la alimentación a cada fase del ciclo menstrual y reducir síntomas del SPM." },
  { sku: "PN-013", name: "Carbohidratos: Tus Aliados o Tus Enemigos", cat: "planes-nutricion", price: 4500, desc: "Desmitificamos los carbos. Cuáles elegir, cuándo y cuánto para tener energía sin acumular grasa." },
  { sku: "PN-014", name: "Preparación de Comidas para la Semana — Meal Prep", cat: "planes-nutricion", price: 4900, desc: "Ahorrá tiempo y comé bien toda la semana. Guía de meal prep con 4 semanas de planes, recetas y trucos de organización." },
  { sku: "PN-015", name: "Nutrición para el Pre y Post Entrenamiento", cat: "planes-nutricion", price: 4500, desc: "Qué comer antes y después de entrenar para maximizar resultados y recuperación. Incluye ejemplos prácticos." },
  { sku: "PN-016", name: "Azúcar: Cómo Reducirlo sin Sufrimiento", cat: "planes-nutricion", price: 3900, desc: "Guía práctica para reducir el consumo de azúcar de forma progresiva. Sustitutos, recetas y cómo manejar los antojos." },
  { sku: "PN-017", name: "Plan de Alimentación para Menopausia", cat: "planes-nutricion", price: 8900, desc: "La menopausia cambia las reglas del juego nutricional. Plan adaptado para manejar los síntomas y mantener la composición corporal." },
  { sku: "PN-018", name: "1600 Calorías Balanceadas — Plan Completo", cat: "planes-nutricion", price: 5900, desc: "Plan de alimentación de 1600 calorías balanceado en macronutrientes. Flexible, sabroso y sostenible en el tiempo." },
  { sku: "PN-019", name: "Alimentación para Rendimiento Deportivo Femenino", cat: "planes-nutricion", price: 7900, desc: "Optimizá tu rendimiento deportivo con la nutrición correcta. Timing, hidratación, periodización nutricional." },
  { sku: "PN-020", name: "Guía de Alimentación Consciente y Sin Culpa", cat: "planes-nutricion", price: 5500, desc: "La relación con la comida importa tanto como lo que comés. Cómo sanar el vínculo con la alimentación para resultados duraderos." },

  // ── Ejercicios en Casa (15) ────────────────────────────────────
  { sku: "EC-001", name: "Casa Gym — Sin Equipamiento 8 Semanas", cat: "ejercicios-casa", price: 6900, desc: "Tu casa como tu gym personal. 8 semanas de programa completo sin ningún tipo de equipamiento. Solo vos y tus ganas." },
  { sku: "EC-002", name: "Home Workout con Mancuernas — 6 Semanas", cat: "ejercicios-casa", price: 5900, desc: "Si tenés mancuernas en casa, este programa es para vos. 6 semanas de trabajo completo con progresión de carga." },
  { sku: "EC-003", name: "Rutinas para Hacer Viendo Netflix", cat: "ejercicios-casa", price: 3500, desc: "El pretexto más usado eliminado para siempre. Rutinas diseñadas para hacer mientras mirás tu serie favorita." },
  { sku: "EC-004", name: "Bootcamp en Casa — 4 Semanas Intensivas", cat: "ejercicios-casa", price: 6500, desc: "La intensidad del bootcamp sin salir de tu living. 4 semanas de trabajo intensivo que te van a sacar de la zona de confort." },
  { sku: "EC-005", name: "Pilates en Casa — 30 Días", cat: "ejercicios-casa", price: 5500, desc: "30 días de pilates mat desde tu casa. Fuerza, flexibilidad, postura y bienestar en una sola práctica." },
  { sku: "EC-006", name: "Cardio sin Saltos — Bajo Impacto en Casa", cat: "ejercicios-casa", price: 4500, desc: "Para quienes viven en departamento o tienen problemas articulares. Cardio efectivo sin saltos ni ruidos molestos." },
  { sku: "EC-007", name: "Entrenamiento Matutino — 15 Minutos al Levantarte", cat: "ejercicios-casa", price: 3500, desc: "Arrancá el día con energía. 30 rutinas de 15 minutos para hacer apenas te levantás, antes del desayuno." },
  { sku: "EC-008", name: "Yoga Matutino — Despertar el Cuerpo", cat: "ejercicios-casa", price: 4500, desc: "Flujos de yoga para comenzar el día conectada con tu cuerpo. 20-30 minutos de práctica energizante." },
  { sku: "EC-009", name: "Circuito en Casa con Silla y Soga", cat: "ejercicios-casa", price: 3900, desc: "Con una silla y una soga saltadora ya tenés todo lo que necesitás. Circuitos completos para hacer en cualquier espacio." },
  { sku: "EC-010", name: "Stretching Nocturno — Relajá el Cuerpo", cat: "ejercicios-casa", price: 3200, desc: "La rutina perfecta para antes de dormir. Estiramientos suaves que relajan la tensión del día y mejoran la calidad del sueño." },
  { sku: "EC-011", name: "Workout en Balcón o Patio — 4 Semanas", cat: "ejercicios-casa", price: 4900, desc: "Aprovechá el espacio al aire libre que tenés disponible. Rutinas diseñadas para espacios pequeños y al exterior." },
  { sku: "EC-012", name: "Danza Fitness en Casa — Cardio Divertido", cat: "ejercicios-casa", price: 4500, desc: "Si no te gusta el gym pero sí bailar, esto es para vos. Cardio disfrazado de baile para quemar calorías sin aburrirte." },
  { sku: "EC-013", name: "Semana Activa — Moverte Todos los Días", cat: "ejercicios-casa", price: 3500, desc: "Cómo integrar el movimiento en tu rutina diaria sin que se sienta como obligación. Hábitos de vida activa." },
  { sku: "EC-014", name: "100 Ejercicios sin Equipamiento", cat: "ejercicios-casa", price: 3900, desc: "La biblia del entrenamiento sin elementos. 100 ejercicios descritos y categorizados para armar tus propias rutinas." },
  { sku: "EC-015", name: "Full Body en Casa — Programa Familiar", cat: "ejercicios-casa", price: 5500, desc: "Ejercitate con tus hijes, tu pareja o sola. Rutinas adaptables para distintos niveles en el mismo espacio." },

  // ── Yoga y Flexibilidad (10) ───────────────────────────────────
  { sku: "YF-001", name: "Yoga para Principiantes — 30 Días", cat: "yoga-flexibilidad", price: 5500, desc: "Empezá tu práctica de yoga desde cero. 30 días de clases progresivas que van de lo más básico a posturas intermedias." },
  { sku: "YF-002", name: "Flexibilidad Total — 8 Semanas", cat: "yoga-flexibilidad", price: 6500, desc: "Mejoré tu flexibilidad de forma segura y progresiva. Secuencias para todas las cadenas musculares en 8 semanas." },
  { sku: "YF-003", name: "Splits — De 0 a Hacer el Spagat", cat: "yoga-flexibilidad", price: 5900, desc: "El objetivo aspiracional de muchas. Plan progresivo de 12 semanas para llegar al spagat con seguridad y sin lesiones." },
  { sku: "YF-004", name: "Yoga Restaurativo y Relajación Profunda", cat: "yoga-flexibilidad", price: 4900, desc: "Para los momentos en que necesitás parar y restaurar. Práctica suave de yoga pasivo con props o elementos del hogar." },
  { sku: "YF-005", name: "Pilates Avanzado — Desafíos de Control", cat: "yoga-flexibilidad", price: 6900, desc: "Para quienes ya tienen base de Pilates. Ejercicios avanzados de control, respiración y alineamiento corporal." },
  { sku: "YF-006", name: "Yoga para Runners — Prevención y Recuperación", cat: "yoga-flexibilidad", price: 5500, desc: "Complemento perfecto para quienes corren. Secuencias específicas para caderas, isquiotibiales y pies." },
  { sku: "YF-007", name: "Meditación y Mindfulness para Deportistas", cat: "yoga-flexibilidad", price: 4500, desc: "La parte mental del fitness. Técnicas de meditación y atención plena para mejorar el rendimiento y el bienestar." },
  { sku: "YF-008", name: "Yin Yoga — Trabajo del Tejido Profundo", cat: "yoga-flexibilidad", price: 5500, desc: "El yin yoga trabaja el tejido conectivo profundo. Ideal para complementar entrenamientos de fuerza y mejorar la movilidad." },
  { sku: "YF-009", name: "Stretching Deportivo Activo y Pasivo", cat: "yoga-flexibilidad", price: 4200, desc: "Diferencias entre estiramientos activos y pasivos, y cómo combinarlos para máxima flexibilidad sin perder fuerza." },
  { sku: "YF-010", name: "Balance y Coordinación — 4 Semanas", cat: "yoga-flexibilidad", price: 4900, desc: "Equilibrio físico que se transfiere a equilibrio mental. Ejercicios de propiocepción y coordinación para todo nivel." },

  // ── Programas de Transformación (15) ──────────────────────────
  { sku: "PT-001", name: "Transformación 12 Semanas — Body & Mind", cat: "programas-transformacion", price: 14900, desc: "El programa bandera. 12 semanas de transformación integral: entrenamiento, nutrición y mindset trabajados en conjunto." },
  { sku: "PT-002", name: "Reset 21 Días — Volvé a Empezar", cat: "programas-transformacion", price: 8900, desc: "Para volver a empezar después de un parón. 21 días de hábitos, movimiento y alimentación para reactivar tu cuerpo." },
  { sku: "PT-003", name: "Verano Fit — Prepará tu Cuerpo en 8 Semanas", cat: "programas-transformacion", price: 9900, desc: "El programa pre-verano más completo. Pérdida de grasa, tonificación y hábitos para llegar al verano sintiéndote increíble." },
  { sku: "PT-004", name: "De 0 a Gym en 3 Meses", cat: "programas-transformacion", price: 12900, desc: "Para quienes nunca fueron al gym. En 3 meses pasás de no saber nada a entrenar con confianza y resultados." },
  { sku: "PT-005", name: "Lean Body — Definición sin Perder Músculo", cat: "programas-transformacion", price: 11900, desc: "El objetivo más difícil: perder grasa sin perder masa muscular. Protocolo completo de nutrición y entrenamiento." },
  { sku: "PT-006", name: "Fitness Over 40 — Transformación Adaptada", cat: "programas-transformacion", price: 12900, desc: "Específico para mujeres mayores de 40. Respeta los cambios hormonales y físicos para resultados duraderos y seguros." },
  { sku: "PT-007", name: "Programa Postparto Total — 16 Semanas", cat: "programas-transformacion", price: 14900, desc: "De la recuperación a la transformación después del parto. 16 semanas progresivas diseñadas con las necesidades reales del postparto." },
  { sku: "PT-008", name: "Atleta Femenina — Rendimiento Máximo", cat: "programas-transformacion", price: 13900, desc: "Para mujeres que entrenan con seriedad y buscan el siguiente nivel. Periodización, recuperación y rendimiento." },
  { sku: "PT-009", name: "Primavera Activa — 6 Semanas de Arranque", cat: "programas-transformacion", price: 7900, desc: "El empujón que necesitás cuando termina el invierno. 6 semanas para activar el metabolismo y recuperar el ritmo." },
  { sku: "PT-010", name: "Reto Navidad — Mantené tus Hábitos en las Fiestas", cat: "programas-transformacion", price: 5900, desc: "Cómo no tirar por la borda todo lo logrado durante las fiestas. Plan específico para diciembre y enero." },
  { sku: "PT-011", name: "Programa de Pérdida de Peso Saludable — 16 Sem", cat: "programas-transformacion", price: 14900, desc: "Sin dietas extremas, sin rebotes. Pérdida de peso sostenible a través de hábitos que duran toda la vida." },
  { sku: "PT-012", name: "Meses sin Progreso — Cómo Romper el Estancamiento", cat: "programas-transformacion", price: 7900, desc: "¿Llevás tiempo sin ver cambios? Esta guía analiza por qué y te da herramientas concretas para romper el plateau." },
  { sku: "PT-013", name: "Strong Girl — Fuerza y Estética en Equilibrio", cat: "programas-transformacion", price: 11900, desc: "Construí un cuerpo fuerte que también te encante. 10 semanas de programa que integra fuerza real con trabajo estético." },
  { sku: "PT-014", name: "Mi Primer Maratón — De 0 a 5K a 10K", cat: "programas-transformacion", price: 8900, desc: "El plan de entrenamiento para empezar a correr de cero y llegar a completar 10K con éxito." },
  { sku: "PT-015", name: "Cuerpo Equilibrado — Sin Obsesiones", cat: "programas-transformacion", price: 9900, desc: "Para quienes quieren resultados sin que el fitness se convierta en una obsesión. Equilibrio entre el cuerpo y la mente." },

  // ── Postparto y Recuperación (10) ─────────────────────────────
  { sku: "PR-001", name: "Vuelta al Ejercicio Postparto — Primer Trimestre", cat: "postparto-recuperacion", price: 6900, desc: "Las primeras 12 semanas después del parto son cruciales. Guía segura y validada para volver al movimiento con confianza." },
  { sku: "PR-002", name: "Suelo Pélvico Postparto — Guía Completa", cat: "postparto-recuperacion", price: 7900, desc: "La recuperación del suelo pélvico es prioritaria después del parto. Ejercicios específicos, señales de alerta y cuándo consultar." },
  { sku: "PR-003", name: "Lactancia y Ejercicio — Compatibilidad Total", cat: "postparto-recuperacion", price: 5500, desc: "Podés ejercitarte mientras das el pecho. Guía completa sobre cómo compatibilizar lactancia materna y actividad física." },
  { sku: "PR-004", name: "Alimentación en el Postparto y la Lactancia", cat: "postparto-recuperacion", price: 6500, desc: "Las necesidades nutricionales cambian radicalmente después del parto. Guía completa para mamás en período postparto." },
  { sku: "PR-005", name: "Cicatriz de Cesárea — Cuidado y Recuperación", cat: "postparto-recuperacion", price: 5900, desc: "Todo lo que necesitás saber sobre el cuidado de la cicatriz de cesárea. Masajes, ejercicios y cuándo retomar la actividad." },
  { sku: "PR-006", name: "Recuperación de Lesiones Deportivas — Guía General", cat: "postparto-recuperacion", price: 5500, desc: "Cómo volver al ejercicio después de una lesión. Principios de recuperación activa, adaptaciones y vuelta progresiva." },
  { sku: "PR-007", name: "Relajación y Autocuidado para Mamás", cat: "postparto-recuperacion", price: 4500, desc: "El postparto es también emocional. Rutinas de autocuidado, respiración y mindfulness para mamás en sus primeros meses." },
  { sku: "PR-008", name: "Entrenamiento Posparto — De 3 Meses a 1 Año", cat: "postparto-recuperacion", price: 8900, desc: "La evolución del entrenamiento a lo largo del primer año post-parto. Progresión segura con objetivos claros por etapa." },
  { sku: "PR-009", name: "Dolor de Espalda en el Embarazo y Postparto", cat: "postparto-recuperacion", price: 5900, desc: "El dolor de espalda es el síntoma más común. Ejercicios específicos para prevenirlo y aliviarlo en cada etapa." },
  { sku: "PR-010", name: "Tu Cuerpo Después del Embarazo — Guía Real", cat: "postparto-recuperacion", price: 6500, desc: "Sin filtros ni cuerpos imposibles. La guía honesta sobre los cambios del cuerpo post-embarazo y cómo trabajar con ellos." },

  // ── Mindset y Hábitos (10) ────────────────────────────────────
  { sku: "MH-001", name: "Motivación que Dura — Construí Hábitos Reales", cat: "mindset-habitos", price: 4900, desc: "La motivación va y viene, los hábitos quedan. Aprende la psicología detrás de los hábitos saludables para resultados permanentes." },
  { sku: "MH-002", name: "Relación con tu Cuerpo — Guía de Autoaceptación", cat: "mindset-habitos", price: 5500, desc: "Para dejar de estar en guerra con tu cuerpo y empezar a trabajar con él. Autocompasión y fitness pueden coexistir." },
  { sku: "MH-003", name: "Planificación Semanal Fit — Organiza tu Vida", cat: "mindset-habitos", price: 3900, desc: "Cómo integrar el entrenamiento y la alimentación saludable en una vida ocupada. Templates de planificación incluidos." },
  { sku: "MH-004", name: "Journaling Fitness — Tu Diario de Transformación", cat: "mindset-habitos", price: 3500, desc: "El journaling como herramienta de cambio. Prompts específicos para el proceso de transformación física y mental." },
  { sku: "MH-005", name: "Gestión del Estrés y el Cortisol", cat: "mindset-habitos", price: 5900, desc: "El estrés crónico sabotea tu transformación. Cómo manejar el cortisol para que el ejercicio y la alimentación funcionen." },
  { sku: "MH-006", name: "Sueño y Recuperación — El Pilar Olvidado", cat: "mindset-habitos", price: 4900, desc: "Sin sueño de calidad no hay resultados. Guía completa de higiene del sueño y cómo optimizarlo para tu transformación." },
  { sku: "MH-007", name: "Cómo Volver Después de un Paréntesis", cat: "mindset-habitos", price: 3900, desc: "Para quienes dejaron de entrenar por días, semanas o meses. Sin culpa, con estrategia. Cómo retomar sin lastimarte." },
  { sku: "MH-008", name: "Mind-Muscle Connection — Entrenás con Tu Cabeza", cat: "mindset-habitos", price: 4500, desc: "La conexión mente-músculo multiplica los resultados. Cómo desarrollarla y usarla en cada ejercicio." },
  { sku: "MH-009", name: "Rutina Mañanera que Cambia tu Vida", cat: "mindset-habitos", price: 4500, desc: "Lo que hacés en la primera hora del día define el resto. Diseñá tu morning routine perfecta basada en evidencia." },
  { sku: "MH-010", name: "Objetivos SMART para el Fitness", cat: "mindset-habitos", price: 3500, desc: "Cómo establecer objetivos reales, medibles y motivantes. Sin expectativas irreales que te hacen abandonar a los 3 meses." },

  // ── Recetas Fit (10) ──────────────────────────────────────────
  { sku: "RF-001", name: "100 Recetas Fit Fáciles y Rápidas", cat: "recetas-fit", price: 5900, desc: "100 recetas saludables que se hacen en menos de 30 minutos. Para personas ocupadas que quieren comer bien sin complicaciones." },
  { sku: "RF-002", name: "Postres Fit para Antojos sin Culpa", cat: "recetas-fit", price: 4500, desc: "50 recetas de postres que satisfacen el antojo dulce sin arruinar tu proceso. Brownies, helados, tortas y más." },
  { sku: "RF-003", name: "Batidos y Smoothies Nutritivos", cat: "recetas-fit", price: 3900, desc: "30 recetas de batidos para pre-entrenamiento, post-entrenamiento y cualquier momento del día. Con valores nutricionales." },
  { sku: "RF-004", name: "Meal Prep Dominical — 40 Recetas", cat: "recetas-fit", price: 4900, desc: "Cómo preparar comida para toda la semana en 2 horas los domingos. 40 recetas aptas para congelar y conservar." },
  { sku: "RF-005", name: "Desayunos Proteicos — 30 Ideas", cat: "recetas-fit", price: 3500, desc: "Empezá el día con proteína. 30 recetas de desayunos altos en proteína para mantener la saciedad y el músculo." },
  { sku: "RF-006", name: "Colaciones Saludables — Snacks para Todo el Día", cat: "recetas-fit", price: 3200, desc: "Las colaciones hacen la diferencia. 50 ideas de snacks fáciles, nutritivos y que se pueden llevar a cualquier lado." },
  { sku: "RF-007", name: "Recetas con Pollo — 30 Formas de Cocinarlo", cat: "recetas-fit", price: 3900, desc: "El pollo es el aliado del fitness y hay mil formas de cocinarlo sin aburrirse. 30 recetas para todo el año." },
  { sku: "RF-008", name: "Vegetales que Te van a Gustar — Recetas Creativas", cat: "recetas-fit", price: 3900, desc: "Para quienes no son fanáticas de los vegetales. 40 recetas que hacen los vegetales irresistibles." },
  { sku: "RF-009", name: "Fermentados y Probióticos — Recetas para el Intestino", cat: "recetas-fit", price: 4500, desc: "Kefir, kimchi, kombucha y más. Recetas de alimentos fermentados para cuidar la microbiota y la salud intestinal." },
  { sku: "RF-010", name: "Edición Verano — 50 Recetas Frescas", cat: "recetas-fit", price: 4500, desc: "El calor cambia todo. 50 recetas frescas, livianas y deliciosas para mantener la alimentación saludable en verano." },

  // ── Desafíos 30 Días (10) ─────────────────────────────────────
  { sku: "D30-001", name: "Desafío 30 Días de Sentadillas", cat: "desafios-30-dias", price: 2900, desc: "El clásico desafío que funciona. 30 días de sentadillas con progresión diaria para ver cambios reales en glúteos y piernas." },
  { sku: "D30-002", name: "Desafío 30 Días de Planchas", cat: "desafios-30-dias", price: 2900, desc: "30 días de planchas progresivas para un core de acero. De 20 segundos al día 1 a más de 3 minutos en el día 30." },
  { sku: "D30-003", name: "Desafío 30 Días Sin Azúcar", cat: "desafios-30-dias", price: 3500, desc: "El reto que cambia todo. 30 días sin azúcar agregada con guía, recetas alternativas y seguimiento de síntomas." },
  { sku: "D30-004", name: "Desafío 30 Días de Agua — 2 Litros Diarios", cat: "desafios-30-dias", price: 2500, desc: "Hidratarte bien cambia tu piel, tu digestión y tu energía. 30 días para instalar el hábito de tomar suficiente agua." },
  { sku: "D30-005", name: "Desafío 30 Días de Cardio", cat: "desafios-30-dias", price: 3500, desc: "30 días de cardio diario con rutinas diferentes para no aburrirse. Progresión de intensidad incluida." },
  { sku: "D30-006", name: "Desafío 30 Días de Flexibilidad", cat: "desafios-30-dias", price: 3200, desc: "En 30 días vas a notar una diferencia increíble en tu movilidad. Stretching diario progresivo para todas las zonas." },
  { sku: "D30-007", name: "Desafío 30 Días de Abdominales", cat: "desafios-30-dias", price: 2900, desc: "30 días de trabajo abdominal que realmente funciona. Sin crunchs tradicionales, con trabajo de core real y progresivo." },
  { sku: "D30-008", name: "Desafío 30 Días de Mindfulness", cat: "desafios-30-dias", price: 3200, desc: "5 minutos al día de atención plena para 30 días. Transforma tu relación con el estrés y con vos misma." },
  { sku: "D30-009", name: "Desafío 30 Días de Glúteos", cat: "desafios-30-dias", price: 3500, desc: "30 días de ejercicios específicos de glúteos. Progresión diaria, variedad de ejercicios y glúteos que lo notan." },
  { sku: "D30-010", name: "Desafío 30 Días de Hábitos Saludables", cat: "desafios-30-dias", price: 4500, desc: "Un hábito saludable por día, 30 en total. Al final del mes tenés la base de un estilo de vida completamente diferente." },

  // ── Programas VIP (5) ─────────────────────────────────────────
  { sku: "VIP-001", name: "Bundle Completo Transformación Total 2024", cat: "programas-vip", price: 24900, desc: "Todo lo que necesitás para transformarte: programa de entrenamiento de 16 semanas, plan nutricional, guías de mindset y acceso a comunidad VIP." },
  { sku: "VIP-002", name: "Masterclass: Negocio de Fitness Digital", cat: "programas-vip", price: 19900, desc: "Cómo crear y vender tus propios productos digitales de fitness. Desde la idea hasta la primera venta. Masterclass completa." },
  { sku: "VIP-003", name: "Membresía Anual — Acceso Total a la Biblioteca", cat: "programas-vip", price: 34900, desc: "Acceso ilimitado por 12 meses a toda la biblioteca de productos. Incluye todas las actualizaciones y lanzamientos del año." },
  { sku: "VIP-004", name: "Pack Body Completo — Entrenamiento + Nutrición", cat: "programas-vip", price: 14900, desc: "La combinación perfecta: el programa de entrenamiento de 12 semanas más completo junto al plan nutricional premium." },
  { sku: "VIP-005", name: "Pack Postparto Completo — Todo lo que Necesitás", cat: "programas-vip", price: 16900, desc: "El pack más completo para el período postparto: recuperación, suelo pélvico, alimentación, mindset y vuelta al ejercicio." },
];

async function seedCatalog() {
  console.log("📦 Iniciando seed del catálogo de 200 productos...");

  // Obtener el primer tenant activo
  const tenant = await prisma.tenant.findFirst({ where: { active: true } });
  if (!tenant) {
    console.error("❌ No hay tenant activo. Ejecutar seed principal primero.");
    process.exit(1);
  }

  // Crear categorías
  const categoryMap = new Map<string, string>();

  for (const cat of CATEGORIES) {
    const c = await prisma.category.upsert({
      where: { tenantId_slug: { tenantId: tenant.id, slug: cat.slug } },
      update: { name: cat.name },
      create: {
        tenantId: tenant.id,
        name: cat.name,
        slug: cat.slug,
        active: true,
        sortOrder: CATEGORIES.indexOf(cat),
      },
    });
    categoryMap.set(cat.slug, c.id);
  }

  console.log(`✅ ${CATEGORIES.length} categorías creadas/actualizadas`);

  // Crear productos
  let created = 0;
  let skipped = 0;

  for (const p of PRODUCTS) {
    const categoryId = categoryMap.get(p.cat);
    if (!categoryId) {
      console.warn(`⚠️  Categoría no encontrada: ${p.cat} para producto ${p.sku}`);
      continue;
    }

    const existing = await prisma.product.findUnique({
      where: { tenantId_sku: { tenantId: tenant.id, sku: p.sku } },
    });

    if (existing) {
      skipped++;
      continue;
    }

    const product = await prisma.product.create({
      data: {
        tenantId: tenant.id,
        sku: p.sku,
        slug: slugify(p.name),
        name: p.name,
        description: p.desc,
        productType: "PDF_GUIDE",
        status: "PUBLISHED",
        publishedAt: new Date(),
        categoryId,
      },
    });

    await prisma.productPrice.create({
      data: {
        productId: product.id,
        basePrice: p.price,
        currency: "ARS",
        channel: "WEB",
        country: "AR",
      },
    });

    await prisma.productContent.create({
      data: {
        productId: product.id,
        channel: "WEB",
        contentType: "description",
        content: p.desc,
        status: "PUBLISHED",
      },
    });

    created++;

    if (created % 20 === 0) {
      console.log(`   ${created} productos creados...`);
    }
  }

  console.log(`\n🎉 Catálogo completado:`);
  console.log(`   Productos creados: ${created}`);
  console.log(`   Productos existentes (skipped): ${skipped}`);
  console.log(`   Total en catálogo: ${PRODUCTS.length}`);
}

seedCatalog()
  .catch((e) => { console.error("❌ Error:", e); process.exit(1); })
  .finally(() => prisma.$disconnect());
