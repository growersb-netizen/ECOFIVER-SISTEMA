# Plan para Claude Cowork — Plantillas de WhatsApp de EcoFiver

> **Para Claude Cowork:** operás en la PC de Rodrigo, el propietario de EcoFiver.
> Tu tarea es **crear 5 plantillas de mensaje en WhatsApp Manager (Meta)** y, cuando Meta las apruebe, **activarlas en el CRM**.
> El código que las usa ya está desplegado y queda apagado hasta el último paso.

## Por qué hace falta
WhatsApp no deja que una empresa escriba texto libre a alguien que no le escribió en las últimas 24 h. Hoy, por eso:
- los leads de los formularios de Meta Ads **no reciben ningún mensaje** (nunca escribieron por WhatsApp);
- los seguimientos, las reactivaciones y los recordatorios de videollamada y de cuota a clientes que no escribieron hace más de 24 h **no se entregan**.

Con plantillas aprobadas, el sistema las usa solo en esos casos. Respeta las bajas, no repite contacto a la misma persona en 20 h y tiene un tope diario.

## Reglas obligatorias
1. **No toques** la configuración de los números, la coexistencia, los webhooks, los perfiles ni las líneas.
   - Solo creás plantillas y activás dos opciones del CRM.
   - **Nunca** uses la línea supervisada de Rodrigo ni la de Melanie para nada.
2. **No envíes mensajes a clientes.** No uses "Enviar mensaje de prueba" a números que no sean de Rodrigo.
3. No muestres tokens ni claves. Los IDs de número de teléfono no son secretos.
4. Copiá los textos **exactamente** como están acá: mismas palabras, signos, tildes y variables `{{1}}` `{{2}}`. El sistema envía esos nombres y esas variables; si no coinciden, Meta rechaza el envío.
5. Si una pantalla no coincide con el plan o Meta pide algo distinto, ⛔ **pará y preguntale a Rodrigo**.

---

## Paso 1 — Identificar la cuenta de WhatsApp correcta (5 min)
1. Railway → proyecto EcoFiver → servicio **eco-multiagente** → **Variables** → mirá el valor de **`WA_PHONE_ID`**. Es un ID numérico, no un secreto. Anotalo.
2. Abrí **business.facebook.com** → **WhatsApp Manager** (o `https://business.facebook.com/wa/manage/`).
3. En **Números de teléfono**, buscá el número cuyo **identificador del número de teléfono** (Phone number ID) coincide con `WA_PHONE_ID`. Las plantillas se crean en **la cuenta de WhatsApp Business (WABA) de ese número**.
4. ⛔ Confirmale a Rodrigo qué número es (los últimos 4 dígitos) antes de seguir. **No debe ser** la línea supervisada de Rodrigo, cuyo ID termina en `…7416`.

## Paso 2 — Crear las 5 plantillas (20 min)
En WhatsApp Manager de esa cuenta → **Administrar plantillas** (Message templates) → **Crear plantilla**. Para **cada** plantilla:
- **Categoría:** la indicada (Marketing o Utilidad).
- **Nombre:** exactamente el indicado (minúsculas, con guiones bajos).
- **Idioma:** **Español (ARG)** (`es_AR`). Si no aparece, ⛔ preguntá; **no** uses "Español" genérico, porque el sistema envía `es_AR`.
- **Encabezado:** ninguno. **Botones:** ninguno.
- **Cuerpo:** copiá el texto. Si te pregunta el tipo de variable, elegí **Número** ({{1}}, {{2}}).
- **Pie de página:** solo donde se indica.
- **Muestras de las variables:** las indicadas.
- Enviá para revisión.

### 1) `ecofiver_primer_contacto` — Categoría: **Marketing**
Cuerpo:
```
Hola {{1}}, soy Valentina de EcoFiver. Recibimos tu consulta por {{2}}. ¿Querés que te pase precios y opciones? Respondé este mensaje y te asesoro.
```
Pie: `Respondé BAJA si no querés recibir más mensajes.`
Muestras: {{1}} = `Ana` · {{2}} = `piscinas de fibra`

### 2) `ecofiver_seguimiento` — Categoría: **Marketing**
Cuerpo:
```
Hola {{1}}, ¿pudiste ver la información sobre {{2}}? Si tenés dudas sobre modelos, precios o financiación, respondé este mensaje y lo vemos juntos.
```
Pie: `Respondé BAJA si no querés recibir más mensajes.`
Muestras: {{1}} = `Ana` · {{2}} = `piscinas de fibra`

### 3) `ecofiver_reactivacion` — Categoría: **Marketing**
Cuerpo:
```
Hola {{1}}, hace un tiempo nos consultaste por {{2}}. Tenemos novedades de temporada. ¿Querés que te cuente? Respondé este mensaje y te paso la información actualizada.
```
Pie: `Respondé BAJA si no querés recibir más mensajes.`
Muestras: {{1}} = `Ana` · {{2}} = `módulos habitables`

### 4) `ecofiver_recordatorio_videollamada` — Categoría: **Utilidad**
Cuerpo:
```
Hola {{1}}, te recordamos tu videollamada con EcoFiver hoy a las {{2}}. ¿Confirmás que vas a poder estar? Respondé este mensaje para confirmar o reprogramar.
```
Sin pie. Muestras: {{1}} = `Ana` · {{2}} = `18:00`

### 5) `ecofiver_recordatorio_cuota` — Categoría: **Utilidad**
Cuerpo:
```
Hola {{1}}, te recordamos que la cuota de {{2}} de tu plan EcoFiver está pendiente de pago. Si ya la abonaste, ignorá este mensaje. Ante cualquier consulta, respondé este mensaje.
```
Sin pie. Muestras: {{1}} = `Ana` · {{2}} = `noviembre`

## Paso 3 — Esperar la aprobación (de minutos a 24 h)
- En **Administrar plantillas**, el estado tiene que pasar a **Aprobada / Activa**.
- Si Meta **rechaza** una, anotá el motivo exacto y ⛔ avisale a Rodrigo. No cambies el texto por tu cuenta: el código usa este texto.
- Si Meta **cambia la categoría** (por ejemplo, de Utilidad a Marketing), está bien: anotalo para Rodrigo, porque cambia el costo.
- Si la plantilla está en "Calidad pendiente" o similar pero **aprobada**, se puede usar.

## Paso 4 — Activar en el CRM (⛔ con OK de Rodrigo: tiene costo por mensaje)
Meta cobra cada plantilla enviada (Marketing cuesta más que Utilidad). El precio vigente se ve en WhatsApp Manager → **Panel / Precios**. El tope diario limita el gasto.

1. ⛔ Confirmá con Rodrigo que las 5 están aprobadas y que quiere activarlas, y el **tope diario** (sugerido: 40 plantillas comerciales por día).
2. CRM → **🔑 Configuración** → sección **Meta**:
   - **"WhatsApp: máximo de plantillas comerciales por día"**: el número que decida Rodrigo (por defecto 40). Guardá.
   - **"WhatsApp: usar plantillas aprobadas fuera de la ventana de 24 h (si/no)"**: escribí `si`. Guardá.

   Para apagarlas en cualquier momento, volvé a poner `no`. El efecto es inmediato.

## Paso 5 — Verificación (al día siguiente, o en cuanto entre un lead de Meta)
1. Abrí `https://eco-multiagente-production.up.railway.app/health/whatsapp`. En `salientes_autorizacion` tiene que aparecer el contador `plantillas` con un valor mayor que 0.
2. CRM → **Bandeja**: los mensajes enviados con plantilla aparecen como `[Plantilla ecofiver_…] Hola …`.
3. WhatsApp Manager → **Panel**: se ven los mensajes de plantilla enviados y entregados.
4. Si un cliente responde, la conversación sigue normal con Valentina. Ya está dentro de la ventana de 24 h, así que va texto libre.

**Opcional, prueba controlada:** ⛔ solo con OK de Rodrigo.
- Crear en el CRM un lead de prueba con un celular **personal** de Rodrigo (no la línea supervisada), de origen Meta y estado NUEVO.
- En los 15 minutos siguientes tiene que llegarle la plantilla `ecofiver_primer_contacto`.
- Después, marcar ese lead como prueba o descartado.

---

## Informe final para Rodrigo
| Plantilla | Categoría final | Estado en Meta | Nota |
|---|---|---|---|
| ecofiver_primer_contacto | | | |
| ecofiver_seguimiento | | | |
| ecofiver_reactivacion | | | |
| ecofiver_recordatorio_videollamada | | | |
| ecofiver_recordatorio_cuota | | | |
| Activación en el CRM (`si`, tope = …) | | | |

Cuando esté listo, Rodrigo le avisa a Claude Code, que verifica desde producción.
