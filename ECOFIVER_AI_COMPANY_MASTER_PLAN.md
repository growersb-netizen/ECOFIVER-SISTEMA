# ECOFIVER AI COMPANY: MASTER PLAN

> Documento vivo. Se actualiza después de cada entrega importante. Permite retomar el trabajo en otra sesión sin perder contexto.
> Última actualización: 31/10/2026 (noche). Fases 1 a 6 PROBADAS; Fase 7 preparada; Fase 8 en `docs/ai-company/DESPLIEGUE_Y_VALIDACION.md`.

## 0. Cómo leer este documento
Cada funcionalidad se clasifica en uno de estos niveles: **NO IMPLEMENTADA · IMPLEMENTADA · PROBADA · DESPLEGADA · VERIFICADA EN PRODUCCIÓN**. Nada pasa a DESPLEGADA sin la aprobación explícita del propietario.

Ramas y PRs (ninguno fusionado):

| PR | Rama | Base | Contenido |
|---|---|---|---|
| #10 | `ccr-b6d2e636-iqq5ux-integracion-fase-0-5` | `main` | Fase 0.5: seguridad, autenticación y reparto Meta (incluye los PRs #7 y #9) |
| #11 | `ccr-b6d2e636-iqq5ux-fase-1-motor` | rama del PR #10 | Fases 1 a 6 (motor, control, circuito comercial, dirección, profesionalización, oficina virtual) |

## 1. Estado inicial (31/10/2026)
- **Producción:** CRM (FastAPI + PostgreSQL, Railway), multiagente (FastAPI, Railway), Worker de Cloudflare, MCP de contratos y web en Vercel (`eco-modulos-web`).
- **`main` = `161f81c`:** incluye el reparto Meta de Codex (round robin, organizaciones, SSO de socios).
- **Agentes:** 16 de la empresa más Valentín (asistente personal, fuera de la empresa).
- **Antes de este plan:**
  - `/api/comando` solo registraba la orden;
  - Control IA marcaba "ENVIADO" sin ejecución;
  - no existían tareas persistentes, aprobaciones, controles por agente ni horarios.
- **Trabajo local de Codex** (`fix/chat-session-isolation` `cc35e4b`, `fix/chat-session-proxy` `dc2012d`, `fix/crm-socio-token-isolation`, informes de Fase 0 y de auditoría integral): **no están en GitHub**. Procedimiento de recuperación: `docs/ai-company/RECUPERACION_RAMAS_CODEX.md`.

## 2. Arquitectura existente (se reutiliza, no se reemplaza)
| Componente | Rol | Se reutiliza para |
|---|---|---|
| `eco-crm` (PostgreSQL) | Fuente de verdad de leads, ventas, cobranzas, socios, reparto | Tareas, eventos, aprobaciones, estados de agentes, circuito comercial y comisiones |
| `eco-multiagente` | 16 agentes, router, canales WhatsApp/Meta/email/Telegram, scheduler | Worker del motor, ejecución con el agente real |
| `tools/action_policy.py` | Matriz de permisos por agente, canal y nivel (OPERATIVA/SENSIBLE/PROHIBIDA) | Toda acción del motor pasa por ella |
| `comandos_agente` (CRM) | Registro de órdenes de Control IA | Ampliada como tabla de tareas (no se creó otra) |
| `tools/ai_metrics.py` | Costo y tokens por proceso | Costo por tarea (`proceso = tarea:<id>`) |

## 3. Fases, estado y evidencia

### Fase 0: recuperación del trabajo de Codex · **BLOQUEADA** (requiere acción del propietario)
- **Entorno:** sesión remota (Linux en la nube) sin acceso a la PC con Windows.
- **Desbloqueo:** seguir `docs/ai-company/RECUPERACION_RAMAS_CODEX.md`, que incluye la revisión de secretos (los repos son públicos).
- **Al desbloquear:** comparar contra el PR #10 e integrar lo que falte.

### Fase 0.5: consolidación de seguridad · **PROBADA** (PR #10)
- Contrato central de sesiones JWT (un token de socio ya no funciona como sesión del CRM); incompatibilidad del reparto Meta resuelta.
- Control IA solo para ADMIN; Worker con token; stock atómico; validación de pagos; backup consistente; canal de Franco.
- Detalle: `docs/ai-company/FASE_0_5_INTEGRACION.md`.

### Fase 1: motor operativo de agentes · **PROBADA** (rama `fase-1-motor`)
| Requisito | Estado | Dónde |
|---|---|---|
| Identificador, agente, estado, prioridad, fecha, resultado, evidencia, historial | PROBADA | `comandos_agente` + `tareas_eventos` (migración 0040) |
| Ejecución persistente y recuperación ante reinicios | PROBADA | Lease de 5 min; tarea recuperada si el proceso muere (`test_reinicio_del_proceso_no_pierde_la_tarea`) |
| Idempotencia | PROBADA | `clave_idempotencia` única |
| Reintentos y control de errores | PROBADA | Backoff de 60, 120 y 240 s; FALLIDO al agotar los intentos |
| Cancelación segura | PROBADA | Cancela en cascada; una tarea en curso termina CANCELADO por latido |
| Delegación con límites | PROBADA | Solo Máximo, Aurora y Tomás; profundidad ≤ 2; ≤ 10 subtareas; presupuesto por orden (US$ 0,50, configurable) |
| Auditoría | PROBADA | Eventos inmutables por tarea |
| Lenguaje natural sin escalada de permisos | PROBADA | `test_instruccion_en_lenguaje_natural_no_otorga_permisos` |
| Acciones sensibles con aprobación humana | PROBADA | `aprobaciones_accion`; solo un admin humano decide |
| `/api/comando` ya no simula ejecución | PROBADA | Encola y despierta al motor |
| Concurrencia real (12 workers) | PROBADA | PostgreSQL 16 local |
| Interfaz para ver tareas y aprobar | PROBADA en Chromium | `/operaciones-ia` |

### Fase 2: control empresarial · **PROBADA**
| Requisito | Estado | Dónde |
|---|---|---|
| Activar, pausar o desactivar por agente y por departamento | PROBADA | `agentes_control` + historial (migración 0041) |
| Horario de salientes L-S 09–21 (Argentina) | PROBADA | `utils/control_agentes.en_horario`; los salientes comerciales lo exigen confirmado por el CRM |
| WhatsApp entrante 24/7 | PROBADA | Si el asignado está pausado, atiende Valentina; sin agentes activos, respuesta sin IA y registro |
| Guardias autorizadas | PROBADA | `guardias_operativas` (todos, departamento o agente; máximo 72 h; con motivo) |
| Estado administrativo distinto de la actividad real | PROBADA | La actividad real se calcula desde el motor |
| Vista 2D de operaciones | PROBADA en Chromium | `/operaciones-ia` (agentes, órdenes, aprobaciones, tareas, guardias; XSS escapado) |

### Circuito comercial, Admisión y comisiones · **PROBADA** (backend)
| Requisito | Estado |
|---|---|
| La IA cierra contado (Camila: piscinas; Luciano: viviendas/módulos) | PROBADA |
| La IA no registra cobros ni confirma entregas | PROBADA (403/401 en el CRM; acciones prohibidas en la política) |
| La IA abre financiación, deriva y agenda | PROBADA (hasta `EN_ADMISION`) |
| La IA no aprueba, rechaza, formaliza ni cambia estados reservados | PROBADA (con intentos auditados) |
| Solo Admisión humana decide (rol `ADMISION` estricto, sin bypass de ADMIN) | PROBADA |
| 23 endpoints financieros cerrados a la identidad del multiagente | PROBADA |
| Comisión de contado: 10 % del producto al entregar; sin duplicados aunque llegue por tres vías | PROBADA |
| Comisión financiada: 2 cuotas iniciales con aprobación, suscripción y pago | PROBADA |
| Panel personal del propietario (generadas, cobradas, pendientes, proyectadas, publicidad, objetivos versionados) | PROBADA (API + `/panel-propietario` en Chromium) |
| Interfaz de Admisión | PROBADA en Chromium (`/admision`) |

### Piscinas de contado (reglas del 31/10) + servicio de distancias · **PROBADA**
| Regla | Estado | Dónde |
|---|---|---|
| Apertura mínima (modelo, medidas, localidad) | IMPLEMENTADA (prompt) | `agents/camila.py` |
| Cotización desde el catálogo vigente + traslado por km de ida | PROBADA | `utils/cotizacion.py` |
| $3.000/km general, $5.000/km especiales, configurables en el panel | PROBADA | `flete_precio_km`, `flete_km_especial`, `flete_modelos_especiales` |
| Distancia real por ruta (Google Routes), sin línea recta ni distancias inventadas | PROBADA con proveedor simulado | `utils/rutas.py` |
| Caché con origen, destino, km, proveedor, fecha, ruta y estado; verificación humana prevalece; cambio de origen recalcula | PROBADA | `distancias_localidades` (migración 0043) |
| Localidades ambiguas: pide provincia | PROBADA | |
| Falla del proveedor: sin precio final; reintento o verificación humana | PROBADA | |
| Precio final único (sin desglosar el flete) | PROBADA | `[COTIZAR:…]` en el chat |
| Promociones 0/50/70/100 % solo sobre el traslado; la de 50 % exige reservar fecha en la semana; sin seña | PROBADA | `promociones_comerciales` (solo el propietario las crea) |
| Autoportantes ≤ 4,10 m; excavación incluida en enterradas | PROBADA | |
| Cierre que registra cliente, teléfono, modelo, color, localidad, domicilio, precio, condiciones y fecha | PROBADA | |
| Venta pendiente de entrega y cobro; comisión al entregar sobre el producto | PROBADA | |
| Misma herramienta para vendedores (panel de socios y CRM) | IMPLEMENTADA (botón "Calcular por ruta"; sin prueba en navegador) | |

### Fase 3: Máximo como CEO · **PROBADA**
| Requisito | Estado | Dónde |
|---|---|---|
| Instrucciones por capas: 1 seguridad (fija) > 2 políticas activas > 3 puesto + manual > contexto | PROBADA | `eco-multiagente/tools/capas.py` |
| Políticas versionadas: Máximo propone, solo el propietario aprueba; suspender/revertir a la versión anterior | PROBADA | `politicas_empresariales` (migración 0045) |
| Una política no puede tocar precios, descuentos, crédito, comisiones, contratos ni permisos | PROBADA (422) | `utils/politicas.py` |
| Objetivos económicos desde el chat solo con pedido del propietario en su canal | PROBADA | `/api/motor/objetivos` |
| Máximo encarga tareas desde el chat (con autoría) y lee el panel económico | PROBADA | `crear_tarea`, `/api/motor/propietario/panel` |
| Máximo sigue cargando ventas, contratos y pagos en el canal del propietario (decisión A: "como antes") | PROBADA | `0d0c867` |

### Fase 4: correcciones del circuito comercial · **PROBADA**
- Ventana de 24 h de WhatsApp: los salientes fuera de ventana no se envían como texto libre y quedan registrados (`ContactoProactivo`).
- Seguimientos sin duplicar (20 h); bajas respetadas; memoria aislada por lead en los lotes (se reprodujo y corrigió la fuga Ana→Beto).
- Las entregas reales disparan el circuito (logística, instalación, socios).

### Profesionalización de los 16 agentes · **PROBADA** (evaluaciones sin ejecutar)
- Manual del puesto para los 16 (misión, dominio, modelo de decisión, metodología, procedimientos, casos complejos, colaboración, autonomía, prohibiciones, indicadores, mejora continua): `eco-multiagente/agents/manuales/`, cargado en la capa 3.
- Nicolás y Mateo registran aperturas (`abrir_financiacion`); Luciano cierra contado de módulos.
- Harness `eco-multiagente/evals/` (14 casos con verificación determinística). **No se corrió contra el modelo** porque tiene costo.
- Auditoría por agente y decisiones: `docs/ai-company/AUDITORIA_AGENTES.md`.

### Fase 6: oficina virtual 3D · **PROBADA en Chromium**
- `/oficina-ia` (solo ADMIN humano): 16 agentes en sus puestos (Valentín excluido), oficina ejecutiva de Máximo y sala de Admisión (personas, solo números agregados).
- Estados reales del motor: trabajando, espera aprobación, en cola, disponible, pausado, desactivado. Sin conexión todo queda "sin datos".
- Día y noche según el horario de salientes. La ficha permite activar, pausar o desactivar con la misma API.
- Alternativa 2D: lista accesible en la página y `/operaciones-ia`; si no hay WebGL, cae a la lista.
- Geometría procedural; Three.js r160 (MIT), vendorizado y verificado contra npm. Captura: `docs/ai-company/img/oficina-virtual.png`.

### Fase 7: preparación del despliegue · **PREPARADA** (no ejecutada)
Orden, migraciones, variables (solo nombres), verificación y reversión: `docs/ai-company/DESPLIEGUE_Y_VALIDACION.md`.

### Fase 8: validación final · ver la tabla de clasificación en `docs/ai-company/DESPLIEGUE_Y_VALIDACION.md` §7

## 4. Bloqueos y decisiones pendientes del propietario
| # | Tema | Tipo |
|---|---|---|
| A | ~~Máximo como herramienta de carga por WhatsApp~~ | **RESUELTA:** "como antes", en el canal confiable del propietario (`0d0c867`) |
| B | **Clave de Google Maps Platform** (Geocoding + Routes) | Sin ella no hay cotización automática |
| C | Dirección exacta de la fábrica (`fabrica_direccion`) | Configuración |
| D | Asignar roles `PROPIETARIO` (vos) y `ADMISION` (personal de admisión) | Datos de usuarios |
| E | `flete_miniportante_km` ($2.000) existe en el panel pero no se usa: ¿regla vieja o vigente? | Regla de negocio |
| F | ¿Las piscinas enterradas tienen la excavación incluida en el precio de catálogo? (Se asumió que sí) | Confirmar |
| G | Inconsistencia del catálogo: nombres de modelos (ej. "Minideck Chico") distintos de las claves de precios ("Minideck") | Datos |
| H | "Nunca revelás que sos IA": en Camila se cambió a "no lo niegues si te preguntan directamente". ¿Aplicarlo a todos? | Decisión (riesgo legal) |
| I | Ventas viejas: ¿generar comisiones retroactivas de entregas anteriores al despliegue? (Hoy: no) | Decisión |
| J | "Aprobación el mismo día" en Nicolás y Mateo: promete el tiempo de una decisión humana | Decisión (texto comercial) |
| K | Flete bonificado y pérgola de regalo en financiadas (Valentina, Nicolás): ¿vigentes? | Confirmar |
| L | Correr las 14 evaluaciones contra el modelo real (costo bajo, pero pago) | Aprobación |
| M | Cargar `AGENTES_IA_API_KEY` propia para la IA (identidad no cooperativa) | Recomendado antes de desplegar |
| N | Aprobar el despliegue: PR #10 → verificación → PR #11 → verificación | Aprobación |
| 1 | Subir las ramas locales de Codex | Acción del propietario |
| 2 | El backup no cubre PostgreSQL (producción) | Infraestructura |
| 3 | Repositorios públicos (`ECOFIVER-SISTEMA`, `eco-modulos-web`) | Decisión |
| 4 | Quién puede registrar pagos | Regla de negocio |
| 5 | Socios administradores por SSO con ADMIN global | Regla de negocio |
| 6 | Qué leads ve cada rol | Regla de negocio |
| 7 | Plantillas de WhatsApp para seguimientos | Meta + textos |
| 8 | Fecha de exigibilidad y liquidación de comisiones de financiación | No inventar: definir |

## 5. Reglas comerciales y económicas confirmadas (obligatorias)
- **Contado (piscinas y viviendas/módulos):**
  - la IA puede cerrar comercialmente, con pago en domicilio contra entrega;
  - estados separados: `CIERRE_COMERCIAL_CONFIRMADO → ENTREGA_PENDIENTE → ENTREGA_CONFIRMADA → COBRO_PENDIENTE → COBRO_CONFIRMADO`;
  - no registrar cobros ni entregas sin evidencia.
- **Financiación:**
  - la IA solo hace apertura, información, calificación preliminar, agenda de videollamada y derivación;
  - aprobar, rechazar y cerrar corresponde **exclusivamente a Admisión humana**;
  - estados: `CONSULTA_RECIBIDA, APERTURA_EN_PROCESO, PRECALIFICADO, VIDEOLLAMADA_PENDIENTE, EN_ADMISION, DOCUMENTACION_PENDIENTE, APROBADO_POR_ADMISION, RECHAZADO_POR_ADMISION, CIERRE_HUMANO_CONFIRMADO`;
  - los tres últimos solo los cambian usuarios humanos de Admisión, verificado en el servidor.
- **Comisiones del propietario:**
  - **Contado:** 10 % del valor del producto. Se **genera solo al confirmarse la entrega**. Una venta cerrada sin entregar es comisión **proyectada**. No se duplica si el evento de entrega se procesa más de una vez.
  - **Financiación:** el 100 % de las **dos cuotas iniciales**. Se genera solo con Admisión aprobada, la suscripción formalizada y las dos cuotas pagas.
  - Se distinguen: proyectada / generada / cobrada.
  - Gastos publicitarios: presupuesto separado de gasto real, sin costos de fabricación.
  - Indicadores personales del propietario separados de la contabilidad de la cooperativa.

## 6. Pruebas (estado en la rama `fase-1-motor`, 31/10 noche)
| Suite | Resultado |
|---|---|
| CRM (incluye motor e2e y circuito e2e con worker real) | 291 passed, 2 skipped |
| Multiagente (incluye manuales, evaluaciones e importación de los 17 agentes) | 398 passed |
| Oficina virtual: lógica de estados (`node --test eco-crm/tests/js/oficina_estado.test.mjs`) | 7 passed |
| Oficina virtual en Chromium (escritorio 1440 px y móvil 390 px) | Sin errores de JS ni scroll horizontal |
| Migraciones 0039–0045 en PostgreSQL 16 | OK |

## 7. Riesgos
- Al desplegar el motor, cualquier tarea creada por un administrador **se ejecuta de verdad**. Se puede apagar con `MOTOR_TAREAS=off`.
- El costo por tarea depende de la tabla de precios de OpenRouter. El presupuesto por orden limita las delegaciones.
- La sesión remota no ve Railway: lo de producción se verifica con los endpoints `/health*`.

## 8. Próximas acciones
1. **Propietario:** decisiones B, C, D, H, J, K, M y N (ver §4). Con B (clave de Google) y C, la cotización automática queda operativa.
2. **Propietario:** subir las ramas de Codex. Cuando estén, se integran contra el PR #10 (Fase 0).
3. Después de aprobar: desplegar en dos pasos según `DESPLIEGUE_Y_VALIDACION.md`, con el motor en `off`, verificar y luego encender.
4. Con aprobación: correr las evaluaciones (L) y ajustar los manuales según los resultados.
5. Plantillas de WhatsApp para seguimientos fuera de la ventana de 24 h.

## 9. Registro de commits (rama `fase-1-motor`)
- `1f1fb22` Fase 6: oficina virtual 3D conectada a los estados reales del motor
- `46378d8` Profesionalización de los 16 agentes: manuales del puesto en capa 3 y harness de evaluaciones
- `da30f0c` feat(direccion): Máximo CEO (políticas versionadas, capas de instrucciones, tareas y objetivos)
- `0c1bfa5` feat(ui): páginas de Admisión y panel económico del propietario
- `551ff29` fix(comercial): ventana de 24 h, seguimientos sin duplicar, memoria aislada por lead, entregas reales
- `0d0c867` fix(politica): Máximo sigue cargando ventas, contratos y pagos en el canal del propietario
- `c0abe70` feat(control): estado por agente/departamento, horario de salientes y guardias
- `fe2304a` feat(ui): Operaciones IA (vista 2D)
- `2ab95ed` feat(comercial): contado y financiación con Admisión humana y comisiones del propietario
- `fa9f1c0` feat(cotizacion): piscinas de contado con precio único, distancias por ruta y promociones
- `ca79ba8` feat(motor): tareas persistentes en el CRM (lease, reintentos, cancelación, delegación, aprobaciones)
- `9d5ed23` feat(motor): worker del multiagente con resultado y evidencia
