# Fase 0.5: consolidación de seguridad, autenticación y reparto Meta

Fecha: 31/10/2026 · Rama: `ccr-b6d2e636-iqq5ux-integracion-fase-0-5`

## Estado por nivel

| Nivel | Estado |
|---|---|
| IMPLEMENTADO LOCALMENTE | Sí (todo lo de este documento) |
| PROBADO | Sí: aislado, con SQLite en memoria y PostgreSQL 16 local. Nunca contra bases productivas |
| PREPARADO PARA INTEGRAR | Sí: PR en borrador |
| FUSIONADO | **No** |
| DESPLEGADO | **No** |
| VERIFICADO EN PRODUCCIÓN | **No** |

## A. Rama y B. base
- Rama: `ccr-b6d2e636-iqq5ux-integracion-fase-0-5`.
- Base: `main` en `161f81c` (verificado el 31/10, después de `git fetch --all`).

## Referencias de la directiva que NO existen en ningún remoto
| Referencia | Resultado |
|---|---|
| Rama local `fix/chat-session-isolation` · `cc35e4b` | No está en GitHub (`git cat-file` sin objeto) |
| Frontend `fix/chat-session-proxy` · `dc2012d` | No está en `eco-modulos-web`, cuyas únicas ramas son `master` y `claude/tareas-pendientes-o809re` |
| `INFORME_ECOFIVER_AI_COMPANY_FASE_0.md` | No está en el repositorio |

Son trabajo local de Codex que no se subió. Esta sesión no tiene acceso a la computadora de Rodrigo. Para integrarlo: `git push origin fix/chat-session-isolation` (y la rama del frontend en `eco-modulos-web`). Cuando esté subido, se compara contra esta rama. Muchas de sus correcciones se cubren acá de forma equivalente (tabla del punto 7).

## Clasificación de las correcciones pedidas (punto 7)
A = integrable sin cambios · B = requirió adaptación · C = ya incorporada · D = bloqueada por dependencia · E = fuera del alcance de esta fase

| Corrección | Clase | Detalle |
|---|---|---|
| Autenticación / seguridad JWT / separación de sesiones | **B** | Contrato central nuevo sobre `main`; equivalente a la "audiencia" de la directiva |
| Incompatibilidad JWT de `require_reparto_actor` | **B** | Usa el contrato central |
| Propiedad de sesiones web | **C** | PR #9 (firma HMAC emitida por el servidor) |
| Restricción de agentes internos | **C** | PRs #8 y #9 |
| Validación de webhooks | **C** | WhatsApp: firma en `log` con métricas por línea. Meta leads: firma validada (Codex) |
| Seguridad del WhatsApp administrativo | **C** | El admin exige firma válida aunque el modo esté en `log` (Etapa 0) |
| Protección del MCP | **C** | `MCP_AUTH_TOKEN` (Etapa 0); `tsc` OK |
| Protección del Worker | **B** | Token opcional; se activa con la variable |
| Validación de pagos | **B** (parcial) + **D** | Validación técnica hecha; quién puede cobrar queda pendiente de regla de negocio |
| Concurrencia de inventario | **B** | `utils/stock.py` |
| Backup SQLite | **B** + **D** | Copia consistente hecha; el backup de PostgreSQL depende de infraestructura |
| Corrección del canal Franco | **B** + **D** | Emisor resuelto; el aviso a grupo necesita definir destinatarios |
| Control IA solo para ADMIN | **B** (nueva) | No estaba en la lista; apareció en la matriz |
| Commits locales de Codex no subidos | **D** | Ver arriba |
| Plantillas de WhatsApp, motor de tareas, nuevos agentes | **E** | Restricción final de la directiva |

## C. Commits

| Commit | Contenido |
|---|---|
| `2d013e0` | Notas de voz (PR #7) |
| `a917813`, `a5213d4` | Acceso de clientes, sesiones firmadas del widget, bajas comerciales (PR #9) |
| `8ebcc5b` | **Contrato central de sesiones JWT** (corrección crítica) |
| `7c0fafb` | Control IA solo para ADMIN, verificado en el servidor + matriz de autorización |
| `a3e5662` | Ajuste de prueba (secreto de sesión) |
| `8b928c2` | Autenticación del Worker |
| `bbf2824` | Validación de pagos y stock atómico |
| `41b7dff` | Backup SQLite consistente |
| `ce2bbf4` | Canal de Franco |

Merges: `046b814` (PR #9) y `6d6c482` (PR #7). Ninguno tuvo conflictos. El único conflicto de toda la integración fue al traer `main` a la rama del PR #9 (ver F).

## D. Archivos modificados
51 archivos, +2132 / −129. Del CRM: auth, socios, reparto_meta, control_agentes, agentes, pagos, stock (6 routers), backup, migración 0039 y 4 archivos de pruebas nuevos. Del multiagente: router, cron, canales, widget y herramientas. Además, el Worker. El detalle está en el PR.

## E. Correcciones incorporadas

### Críticas (encontradas en `main`, con probable impacto en producción)
1. **Un token de socio funcionaba como sesión del CRM.** Socios y CRM firman con el mismo `SECRET_KEY`, y el CRM no verificaba la clase del token. Un token del panel de socios con `sub = id del Aliado` se aceptaba como el **Usuario con ese mismo id**. Reproducido: el socio con id 1 entró como el ADMIN con id 1.
   - **Corrección:** `utils/sesiones.py`, con `typ` y `aud` por clase y verificación explícita de la audiencia. `python-jose` acepta tokens sin `aud` aunque se le pida una, así que la librería sola no alcanza.
   - `auth`, `socios` y `reparto_meta` usan el mismo contrato. Esto resuelve también la incompatibilidad `Invalid audience` de `require_reparto_actor`, que decodificaba por su cuenta.
   - **No se debilitó nada:**
     - un token con audiencia ajena, de otra clase o sin `exp` se rechaza;
     - los tokens anteriores, sin `aud`, se aceptan **solo en su propia clase**, para que nadie pierda la sesión al desplegar.
2. **Control IA:** cualquier usuario logueado podía mandarle órdenes a Máximo por el canal de confianza. La interfaz lo ocultaba, pero el servidor no lo exigía. Ahora exige ADMIN.
3. **Stock:** con 8 ventas simultáneas en PostgreSQL real, la versión de `main` **vendió 8 veces la última piscina**. Ahora el descuento es atómico y se concreta 1.
4. **Worker `eco-agentes`:** respondía sin autenticación (verificado contra la URL real). Cualquiera con la URL consumía créditos de OpenRouter.

### Otras
- **Pagos:** un monto negativo restaba del anticipo, un texto causaba un error 500 con el pago a medio guardar, y un concepto desconocido sumaba al anticipo. Ahora se valida antes de escribir.
- **Backup SQLite:** la copia no incluía lo que estaba en el WAL. Ahora usa la API de backup de SQLite y verifica la integridad.
- **Franco:** usaba el mismo valor como emisor (ID de Meta) y como destino. Esos envíos no podían funcionar.
- **Del PR #9:**
  - sesiones del widget firmadas por el servidor;
  - clientes atendidos solo por agentes de atención;
  - bajas comerciales persistentes.
- **Del PR #7:** notas de voz.

## F. Conflictos resueltos
Al traer `main` (reparto Meta de Codex) a la rama del PR #9 hubo dos conflictos:
1. `eco-crm/database/models.py`: los dos lados agregaron modelos al final del archivo. Se conservaron ambos.
2. Las dos migraciones se numeraban `0038`. La de bajas pasó a `0039`, encadenada después de `0038_meta_lead_reparto`.

No se eliminó ni reescribió código del reparto Meta. Sus pruebas (74 casos) pasan.

## G. Pruebas aprobadas
| Suite | Resultado |
|---|---|
| Multiagente (`pytest`) | **311 passed** |
| CRM (`pytest tests`) | **133 passed**, 1 omitida que requiere PostgreSQL (corrida aparte: OK) |
| Concurrencia de stock en PostgreSQL 16 local | 1 venta de 8 intentos (antes: 8 de 8) |
| Migración 0038 → 0039 en PostgreSQL 16 | OK; se puede re-ejecutar sin efectos; rollback bloqueado |
| Worker (`node eco-worker/test_auth.mjs`) | OK |
| Servidor MCP (`tsc --noEmit`) | OK |
| Widget en Chromium real | Sesión firmada y renovación tras 401 |

### Cobertura de la sección 8 de la directiva
| Pedido | Dónde |
|---|---|
| Login CRM / JWT correcto e incorrecto / vencidos | `test_matriz_autorizacion.py` |
| Login socios / acceso entre organizaciones | `test_matriz_autorizacion.py` y tests del reparto Meta |
| SSO socios | Tests del reparto Meta (`test_meta_end_to_end.py`). Se mantiene con el contrato nuevo |
| Reparto Meta, persistencia, reintentos, duplicados | `test_meta_*.py` (de Codex, sin cambios, en verde) |
| Propiedad de leads | `test_vendedor_solo_ve_sus_leads` |
| Webhooks, WhatsApp supervisado, admin sin firma | `test_etapa0_seguridad.py`, `test_whatsapp_coexistence.py`, `test_notas_de_voz.py` |
| Aislamiento de conversaciones | `test_validacion_acceso_clientes.py` (sesiones firmadas) |
| Agentes internos | `test_validacion_acceso_clientes.py`, `test_enrutamiento_incidente.py` |
| Inventario concurrente, pagos inválidos | `test_pagos_e_inventario.py` |
| Backup SQLite | `test_backup_sqlite.py` |
| Canal de Franco | `test_canal_franco.py` |

## H. Pruebas fallidas
Ninguna.

## I. Problemas pendientes (no resueltos acá)

| # | Tema | Por qué no se resolvió |
|---|---|---|
| 1 | **El backup no respalda PostgreSQL** (la base productiva). El job copia el SQLite heredado y loguea "✓" | Infraestructura (backups de Railway o `pg_dump` a R2). Queda advertencia en el log |
| 2 | Quién puede **registrar pagos**: hoy cualquier usuario logueado o la API key | Regla de negocio: ¿solo COBRANZAS y ADMIN? |
| 3 | Los **socios administradores por SSO** reciben rol ADMIN **global** en el CRM (leads, finanzas, Control IA) | Decisión de negocio. El reparto ya los limita a su organización |
| 4 | **Roles sin filtro de leads**: el filtro "solo los propios" aplica a `ASESOR_APERTURA`; otros roles (LOGISTICA, FABRICA, VENTAS) ven todos | Decidir qué ve cada rol |
| 5 | Aviso de Franco "al canal de aliados" | WhatsApp Cloud API no envía a grupos: definir destinatarios (requiere plantillas y consentimiento) |
| 6 | Firma de webhooks en `enforce` | La línea supervisada sigue sin evidencia de firma (`/health/seguridad`) |
| 7 | **El repositorio `ECOFIVER-SISTEMA` es público** | Expone el código (incluidas las rutas de los fallos corregidos acá) y el historial donde estuvo la API key de Gemini (quitada en el PR #6, pero sigue en el historial) |
| 8 | Commits locales de Codex (`cc35e4b`, `dc2012d`) | No están subidos |
| 9 | Envíos fuera de la ventana de 24 h de WhatsApp | Requieren plantillas aprobadas (Etapa 1, fuera de esta fase) |

## J. Riesgos de integración
1. **`SECRET_KEY` vacío:** el contrato de sesiones rechaza todo (falla cerrado). En producción tiene que estar configurado (el reparto Meta ya lo exigía).
2. **Tokens viejos sin audiencia:** siguen valiendo, solo en su clase, hasta que vencen (máximo 30 días los de SSO admin). Después se puede quitar la compatibilidad.
3. **Control IA:** los usuarios no ADMIN que lo usaran por URL directa reciben 403.
4. **Worker:** activar en orden: 1) `ECO_WORKER_TOKEN` en el CRM, 2) `WORKER_TOKEN` en Cloudflare. Al revés, EcoPost deja de generar copys hasta completar el paso 1.
5. **Widget y bajas:** ver `BAJAS_Y_SESIONES_WEB.md` (desplegar el CRM antes que el multiagente).
6. **Franco:** sin `FRANCO_WA_PHONE_ID`, las tareas de Franco no envían. Igual que hoy, que fallan en Meta; ahora queda un error claro en el log.

## K. Migraciones necesarias
- `0039_exclusiones_comerciales`: solo crea una tabla, se puede re-ejecutar sin efectos y el rollback está bloqueado. Corre sola al arrancar el CRM (`alembic upgrade head`). **No se ejecutó en producción.**

## L. Pasos para una publicación segura
1. Revisar este PR. Reemplaza a los PRs #7 y #9, que quedan incluidos.
2. Subir los commits locales de Codex y compararlos con esta rama antes de fusionar.
3. Hacer un backup de PostgreSQL de producción (pendiente 1).
4. Configurar las variables (las carga Rodrigo; el código no lleva secretos):
   - `WEB_SESSION_SECRET` (multiagente);
   - `ECO_WORKER_TOKEN` (CRM) y, después, `WORKER_TOKEN` (Worker);
   - `FRANCO_WA_PHONE_ID` (multiagente).
5. Desplegar el **CRM** y verificar `/api/health` y el login (CRM, socio y SSO).
6. Desplegar el **multiagente** y verificar `/health/seguridad` y el widget.
7. Desplegar el **Worker** y verificar que `/health` muestre `auth: requerida`.
8. Pruebas manuales:
   - un socio no entra al CRM con su token;
   - un vendedor recibe 403 en Control IA;
   - el widget responde;
   - "no me escriban más" desde un número de prueba queda registrado como baja.

## M. Producción
**No se modificó producción.** Sin merges, deploys, cambios de secretos ni variables, sin migraciones productivas y sin mensajes a clientes. Las únicas consultas a producción fueron lecturas de `/health*` (públicos) y un POST vacío al Worker para confirmar que estaba abierto: no generó contenido ni gasto relevante.
