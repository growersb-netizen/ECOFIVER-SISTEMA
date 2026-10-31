# ECOFIVER AI COMPANY: MASTER PLAN

> Documento vivo. Se actualiza después de cada entrega importante. Permite retomar el trabajo en otra sesión sin perder contexto.
> Última actualización: 31/10/2026.

## 0. Cómo leer este documento
Cada funcionalidad se clasifica en uno de estos niveles: **NO IMPLEMENTADA · IMPLEMENTADA · PROBADA · DESPLEGADA · VERIFICADA EN PRODUCCIÓN**. Nada pasa a DESPLEGADA sin la aprobación explícita del propietario.

Ramas y PRs (ninguno fusionado):

| PR | Rama | Base | Contenido |
|---|---|---|---|
| #10 | `ccr-b6d2e636-iqq5ux-integracion-fase-0-5` | `main` | Fase 0.5: seguridad, autenticación y reparto Meta (incluye los PRs #7 y #9) |
| (nuevo) | `ccr-b6d2e636-iqq5ux-fase-1-motor` | rama del PR #10 | Fase 1 en adelante (motor de tareas y siguientes) |

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
| Interfaz para ver tareas y aprobar | **NO IMPLEMENTADA** | Pendiente (va con la Fase 2) |

### Fase 2: control empresarial (agentes, departamentos, horarios) · **EN CURSO**
- **Decisiones:**
  - Activar/pausar/desactivar por agente y por departamento.
  - Salientes comerciales: lunes a sábado de 09:00 a 21:00 (America/Argentina/Buenos_Aires).
  - WhatsApp entrante: 24/7.
  - Guardias autorizadas.
  - El estado administrativo se distingue de la actividad real.
- **Departamentos:**
  - Dirección (Máximo);
  - Comercial (Aurora, Tomás, Valentina, Camila, Nicolás, Luciano, Mateo);
  - Marketing (Renata);
  - Operaciones (Bruno);
  - Administración y Finanzas (Ezequiel, Elena, Ignacio);
  - Postventa (Sebastián);
  - Reputación (Daniela);
  - Socios (Franco).

### Fase 3: coordinación empresarial (Máximo CEO, políticas versionadas) · NO IMPLEMENTADA
### Fase 4: automatización comercial y correcciones · NO IMPLEMENTADA
Errores conocidos, confirmados en el código:
- **Memoria compartida entre clientes:** las tareas programadas reutilizan una sola instancia de Valentina para todos los leads de un lote.
- **Envíos fallidos registrados como exitosos:** Meta responde 200 y la falla (`131047`, fuera de la ventana de 24 h) llega después, solo al log.
- **Seguimientos fuera de la ventana de 24 h:** requieren plantillas aprobadas.

### Circuito comercial contado/financiación + Admisión + comisiones · NO IMPLEMENTADA
- **Reglas confirmadas por el propietario:** ver la sección 5.

### Fase 5: administración y finanzas · NO IMPLEMENTADA
- Las "cuatro pruebas financieras con fallos esperados" están en el trabajo local de Codex: **no disponibles**.

### Profesionalización de los 16 agentes + evaluaciones · NO IMPLEMENTADA
- **Prompts actuales:** entre 44 líneas (Ezequiel) y 333 (Máximo).
- **Evaluaciones con modelo real:** requieren `OPENROUTER_API_KEY`, que no está en este entorno. Lo que se construya acá se valida de forma determinística; la calificación con el modelo real se corre con autorización.

### Fase 6: oficina virtual 3D · NO IMPLEMENTADA
### Fase 7: integración y despliegue · NO IMPLEMENTADA (requiere aprobación)
### Fase 8: validación final · NO IMPLEMENTADA

## 4. Bloqueos y decisiones pendientes del propietario
| # | Tema | Tipo |
|---|---|---|
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

## 6. Pruebas (estado en la rama `fase-1-motor`)
| Suite | Resultado |
|---|---|
| CRM | 166 passed, 2 skipped (PostgreSQL: corridas aparte, OK) |
| Multiagente | 317 passed |
| Motor e2e (worker real ↔ CRM real, IA simulada) | 8 passed |
| Migraciones 0039/0040 en PostgreSQL 16 | OK |

## 7. Riesgos
- Al desplegar el motor, cualquier tarea creada por un administrador **se ejecuta de verdad**. Se puede apagar con `MOTOR_TAREAS=off`.
- El costo por tarea depende de la tabla de precios de OpenRouter. El presupuesto por orden limita las delegaciones.
- La sesión remota no ve Railway: lo de producción se verifica con los endpoints `/health*`.

## 8. Próximas acciones
1. Fase 2: estados de agentes y departamentos, horarios, guardias, panel de operaciones (tareas y aprobaciones).
2. Circuito comercial contado/financiación + Admisión + comisiones (backend y pruebas).
3. Fase 4: corregir la memoria compartida en los lotes, el registro de envíos fallidos (statuses de Meta) y la deduplicación de seguimientos.
4. Fase 3: políticas versionadas y objetivos económicos de Máximo.
5. Profesionalización por agente (manuales y evaluaciones).
6. Oficina 3D sobre los endpoints reales.

## 9. Registro de commits (rama `fase-1-motor`)
- `ca79ba8` feat(motor): tareas persistentes en el CRM (lease, reintentos, cancelación, delegación, aprobaciones)
- `9d5ed23` feat(motor): worker del multiagente con resultado y evidencia
