# Despliegue y validación final (Fases 7 y 8)

> **Nada de esto se ejecutó en producción.** Es el procedimiento preparado para que el propietario lo apruebe.
> Desplegar, correr migraciones productivas y cargar secretos requiere su autorización explícita.

## 1. Qué se despliega
| Servicio | Rama | Cambios principales |
|---|---|---|
| `eco-crm` (Railway, PostgreSQL) | PR #10 y luego PR #11 | Sesiones, motor de tareas, control de agentes, circuito comercial, Admisión, comisiones, cotizador por ruta, políticas, Operaciones IA, Oficina virtual |
| `eco-multiagente` (Railway) | ídem | Worker del motor, capas de instrucciones y manuales, acciones de circuito, bajas, ventana de 24 h, memoria aislada por lead |
| `eco-worker` (Cloudflare) | PR #10 | Token opcional (`WORKER_TOKEN`) |

Orden recomendado: **PR #10 → verificación → PR #11 → verificación**. Son dos pasos chicos y reversibles, no uno grande.

## 2. Migraciones (CRM, Alembic)
`0039` exclusiones comerciales · `0040` motor de tareas · `0041` control de agentes · `0042` circuito comercial · `0043` cotización de contado y distancias · `0044` contactos proactivos · `0045` políticas empresariales.

- Todas son **aditivas**: crean tablas y columnas, y no borran ni reescriben datos existentes.
- Se probaron en PostgreSQL 16 partiendo del estado equivalente a producción (`0038`).
- Los downgrades que borrarían datos auditados están **bloqueados a propósito**. Si hay que revertir, se vuelve al código anterior y las tablas nuevas quedan sin uso.
- **Antes de migrar:** backup de PostgreSQL. El backup actual del CRM **no cubre PostgreSQL** (decisión pendiente). Se puede usar el snapshot de Railway o `pg_dump`.

## 3. Variables de entorno nuevas (solo nombres; los valores los carga el propietario)
| Variable | Servicio | Si falta |
|---|---|---|
| `MOTOR_TAREAS` | multiagente | `on` por defecto. **Recomendado desplegar con `off`** y encenderlo después de verificar |
| `MOTOR_PRESUPUESTO_RAIZ_USD` | CRM | 0,50 por orden |
| `MOTOR_TIMEOUT_S`, `MOTOR_INTERVALO_S` | multiagente | 180 s / 15 s |
| `AGENTES_IA_API_KEY` | CRM (+ el multiagente la usa como clave) | La identidad de la IA depende solo del encabezado que manda el multiagente. **Recomendado:** sin esta clave propia, una clave robada podría operar sin la marca de IA |
| `WEB_SESSION_SECRET` | multiagente | Secreto temporal por proceso: las sesiones del widget se pierden en cada reinicio |
| `GOOGLE_MAPS_API_KEY` (o `google_maps_api_key` en Configuración) | CRM | Sin cotización automática por ruta. El sistema **no da precio** (no inventa distancias) |
| `ECO_WORKER_TOKEN` (CRM) = `WORKER_TOKEN` (Cloudflare) | CRM + Worker | El Worker queda abierto como hoy |
| `FRANCO_WA_PHONE_ID` | multiagente | Franco usa el emisor por defecto |

Configuración desde el panel del CRM, sin redeploy: `fabrica_direccion`, `flete_precio_km`, `flete_km_especial`, `flete_modelos_especiales`.
Roles a asignar: `PROPIETARIO` (Rodrigo) y `ADMISION` (personal de Admisión).

## 4. Qué NO cambia con el despliegue
- Líneas de WhatsApp, coexistencia, Embedded Signup y números: sin cambios. La línea supervisada de Rodrigo sigue sin respuesta automática.
- Precios, promociones y condiciones: no se crean ni modifican; el cotizador usa el catálogo y la configuración vigentes.
- Nexxum: no se toca.

## 5. Verificación posterior (smoke tests, sin contactar clientes)
1. `GET /health`, `/health/motor` y `/health/whatsapp` del multiagente responden.
2. CRM: login de ADMIN; `/operaciones-ia` y `/oficina-ia` cargan, y los 16 agentes aparecen como "Disponible".
3. Con `MOTOR_TAREAS=off`, una orden creada en Operaciones IA queda **PENDIENTE** (nada se ejecuta).
4. Encender el motor y dar una orden interna inocua a Aurora, por ejemplo: "resumí el embudo de la semana".
   - Debe terminar COMPLETADO, con evidencia.
   - El costo se ve en las métricas de IA.
5. Pausar un agente y verificar que en la Oficina virtual aparezca de pie, con anillo naranja.
6. Un token de socio **no** abre páginas del CRM (401/403).
7. `/admision` solo abre con el rol ADMISION, y `/panel-propietario` solo con PROPIETARIO.
8. WhatsApp entrante: un mensaje de prueba **desde un número propio** a la línea de Agentes tiene que recibir respuesta. La línea supervisada no debe responder.

## 6. Reversión
- **Código:** redeploy del commit anterior en Railway. Las tablas nuevas no molestan al código viejo.
- **Motor:** `MOTOR_TAREAS=off` lo detiene sin redeploy. Las tareas en curso se recuperan por lease cuando se reactiva.
- **Agentes:** pausa por agente, por departamento o general, desde Operaciones IA o la Oficina virtual.

---

## 7. Validación final: clasificación por funcionalidad (31/10/2026)
Ninguna funcionalidad llega todavía a **DESPLEGADA** ni a **VERIFICADA EN PRODUCCIÓN**, porque no hubo autorización para desplegar.

| Funcionalidad | Estado | Evidencia |
|---|---|---|
| Contrato de sesiones (socio ≠ CRM), Control IA solo ADMIN, Worker con token, stock atómico | PROBADA | PR #10; matriz de autorización |
| Widget sin suplantación; bajas permanentes; clientes solo con agentes de atención | PROBADA | PR #9 integrado en #10 |
| Motor de tareas (lease, reintentos, cancelación, delegación, aprobaciones, idempotencia) | PROBADA | e2e worker real ↔ CRM real; 12 workers en PG 16 |
| Control por agente y departamento, horario de salientes, guardias | PROBADA | `test_control_agentes.py` |
| Contado: cierre IA → entrega → cobro, con confirmación humana | PROBADA | `test_circuito_comercial.py` y e2e |
| Financiación: la IA abre y deriva; Admisión humana decide (estados reservados) | PROBADA | intentos rechazados y auditados |
| Comisiones del propietario (proyectada, generada y cobrada; sin duplicar) | PROBADA | `test_circuito_comercial.py`, `test_circuito_e2e.py` |
| Cotizador de piscinas con distancia por ruta, caché y promociones de flete | PROBADA con proveedor simulado | Falta la clave real de Google |
| Ventana de 24 h, seguimientos sin duplicar, memoria aislada por lead | PROBADA | Fase 4 |
| Páginas de Admisión y del panel del propietario | PROBADA en Chromium | |
| Políticas versionadas y objetivos de Máximo (capa 2) | PROBADA | `test_politicas.py`, `test_direccion_maximo.py` |
| Manuales de los 16 puestos (capa 3) | PROBADA | `test_manuales.py` |
| Evaluaciones de agentes contra el modelo real | IMPLEMENTADA, **NO EJECUTADA** | Requiere aprobación (llamadas pagas) |
| Oficina virtual 3D con estados reales | PROBADA en Chromium (escritorio y móvil) | `docs/ai-company/img/oficina-virtual.png` |
| Botón "Calcular por ruta" en el panel de socios | IMPLEMENTADA | Sin prueba en navegador |
| Recuperación del trabajo local de Codex | BLOQUEADA | Depende de que el propietario suba las ramas |
| Plantillas de WhatsApp para fuera de la ventana de 24 h | NO IMPLEMENTADA | Requiere aprobación de Meta y textos |
| Backup de PostgreSQL | NO IMPLEMENTADA | Decisión de infraestructura |
