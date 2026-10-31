# Plan de activación para Claude Cowork — EcoFiver (PC de Rodrigo)

> **Para Claude Cowork:** sos el operador de este plan en la PC de Rodrigo, el propietario de EcoFiver.
>
> - Todo el código ya está desplegado en producción. Este plan es solo **configuración en paneles web**: el CRM, Railway, Google Cloud, Cloudflare y GitHub.
> - Seguí las etapas **en orden**. No te saltees las verificaciones.
> - Rodrigo autorizó este plan. Igual, **pedile confirmación en los puntos marcados con ⛔ ANTES DE SEGUIR**.

## Reglas obligatorias (leelas antes de empezar)

1. **Secretos:** nunca escribas el valor de una clave en el chat, en un archivo, en una captura que compartas ni en un resumen.
   - Las claves se generan y se copian solo por portapapeles al campo donde van.
   - En los informes, decí "configurada" o "no configurada", nunca el valor.
2. **No borres** servicios, bases, variables existentes ni datos. Si un paso dice "cambiar", anotá antes en qué servicio está la variable, **pero no copies su valor a ningún lado**.
3. **WhatsApp:** no toques nada de WhatsApp, Meta ni números de teléfono. No mandes mensajes a clientes.
4. **Si una pantalla no coincide** con lo que dice el plan, si algo falla o si un paso pide pagar algo distinto de lo indicado: **PARÁ y preguntale a Rodrigo**. No improvises.
5. Después de cada etapa, informale a Rodrigo en una línea: ✅ hecho y verificado, o ❌ qué falló.

**Direcciones de producción:**
- CRM: `https://eco-crm-production.up.railway.app`
- Multiagente: `https://eco-multiagente-production.up.railway.app`
- Worker: `https://eco-agentes.growersb.workers.dev`
- Repositorio: `https://github.com/growersb-netizen/ECOFIVER-SISTEMA`

**Cómo generar una clave aleatoria sin que se vea** (PowerShell; queda solo en el portapapeles):
```powershell
$b = New-Object byte[] 32; [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b); ([Convert]::ToBase64String($b) -replace '[+/=]','') | Set-Clipboard
```
Pegala en el destino con Ctrl+V. Si la misma clave va en dos lugares, pegala en los dos **antes** de generar otra.

---

## Etapa 0 — Preparación (5 min)

1. Abrí en el navegador estas pestañas con la sesión de Rodrigo:
   - CRM `/login`;
   - railway.app;
   - console.cloud.google.com;
   - dash.cloudflare.com;
   - github.com;
   - drive.google.com.
2. Si alguna pide iniciar sesión, pedile a Rodrigo que la inicie él. No escribas contraseñas.
3. Verificá la salud del sistema abriendo estas direcciones:
   - `…eco-crm-production…/api/health` debe responder `"status":"ok"`.
   - `…eco-multiagente-production…/health/motor` debe responder `"activo":true` y `"fallidas":0`.

## Etapa 1 — Backup inicial (antes de tocar nada) · 10 min

1. CRM → menú **💼 Mis comisiones** → sección **Backups de la base** → **💾 Hacer backup ahora**.
2. Cuando aparezca en la lista, hacé clic en **descargar**. El archivo se llama `eco_crm_pg_AAAAMMDD_HHMMSS.jsonl.gz` y contiene todos los datos del CRM.
3. Google Drive → creá una carpeta **privada** "EcoFiver Backups" (sin compartir) y subí el archivo.
4. Railway → proyecto de EcoFiver → servicio **Postgres** → pestaña **Backups**:
   - activá los backups programados (diarios) si la opción existe en el plan contratado;
   - si pide cambiar de plan o pagar, ⛔ preguntale a Rodrigo.

**Verificación:** el archivo está en Drive y pesa más de 100 KB.

## Etapa 2 — Dirección de la fábrica · 2 min

1. CRM → **🔑 Configuración** → sección **Precios** → campo **"Dirección de la fábrica (origen del traslado)"**.
2. Escribí exactamente esto y guardá:
   ```
   Av. Antártida Argentina & Calle 6, Zárate, Provincia de Buenos Aires, Argentina
   ```

## Etapa 3 — Clave de Google Maps (cotización automática) · 15 min

1. console.cloud.google.com → selector de proyecto → **Proyecto nuevo** → nombre `EcoFiver` → Crear → seleccionarlo.
2. **Facturación:** vincular una cuenta de facturación.
   - ⛔ Si no existe una, Rodrigo tiene que cargar la tarjeta. Pedíselo y esperá.
   - Después: Facturación → **Presupuestos y alertas** → crear un presupuesto de **US$ 10/mes** con alertas al 50 %, al 90 % y al 100 %, enviadas a su mail.
3. **APIs y servicios → Biblioteca:** habilitá **Geocoding API** y **Routes API**, las dos.
4. **APIs y servicios → Credenciales → Crear credenciales → Clave de API.**
   - Después: **Editar clave** → nombre `EcoFiver CRM cotizador`.
   - En **Restricciones de API**, elegí **Restringir clave** y marcá solo Geocoding API y Routes API.
   - En restricciones de aplicación dejá **Ninguna**: el CRM llama desde un servidor y su IP cambia.
   - Guardá.
5. Copiá la clave al portapapeles con el botón de copiar. **No la muestres.**
6. CRM → **🔑 Configuración** → sección **API Keys** → campo **"Google Maps Platform API Key (Geocoding + Routes)"** → pegá y guardá.
7. **Verificación** (en el CRM, logueado como Rodrigo):
   - Abrí la consola del navegador (F12 → Console) y ejecutá:
     ```js
     fetch('/api/comercial/cotizar',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({modelo:'Minideck',localidad:'Campana',provincia:'Buenos Aires'})}).then(r=>r.json()).then(d=>console.log(d.ok, d.precio_final, d.interno&&d.interno.km_ida, d.interno&&d.interno.tarifa_km, d.motivo||''))
     ```
   - **Esperado:** `true`, un precio, unos **10 a 30 km** y tarifa `3000`.
   - Repetí con `modelo:'Arco Romano Grande'`: la tarifa tiene que dar `5000`.
   - Si responde `distancia_no_disponible`, esperá 5 minutos (las APIs recién habilitadas tardan) y reintentá una vez. Si sigue fallando, ⛔ informá a Rodrigo el `motivo` (no la clave).

## Etapa 4 — Rotar la clave de Gemini expuesta · 20 min

La clave vieja quedó en commits de un repositorio público. Hay que crear una nueva, ponerla en **todos** los lugares donde se usa y recién después borrar la vieja.

1. **Inventario de consumidores.** Anotá **solo los nombres de servicio**:
   - Railway: en cada servicio del proyecto (al menos **eco-crm** y **eco-multiagente**; revisá también si hay otros), pestaña **Variables**. Anotá cuáles tienen `GEMINI_API_KEY`.
   - CRM → Configuración → API Keys: fijate si existe el campo **Gemini** y si dice configurado.
   - Si hay más proyectos en Railway o en Fly.io con `GEMINI_API_KEY`, anotalos también.
   - ⛔ Mostrale la lista a Rodrigo y confirmá antes de seguir.
2. Google AI Studio (aistudio.google.com → **Get API key**) o Cloud Console → Credenciales. Ubicá la clave de Gemini actual (es la que figura en uso) y **creá una nueva** en el mismo proyecto.
3. Copiá la nueva y pegala en **cada** consumidor del inventario: variable `GEMINI_API_KEY` de cada servicio de Railway y el campo Gemini del CRM, si estaba configurado. Railway redeploya solo al guardar una variable.
4. Esperá 3 minutos y verificá:
   - `…/api/health` del CRM sigue `ok`;
   - `…/health` del multiagente sigue `ok`;
   - `…/health/motor` del multiagente sigue con `fallidas: 0`.
5. ⛔ Con el OK de Rodrigo, **borrá o deshabilitá la clave vieja** en Google.

**Si algo deja de funcionar después del paso 5:** falta algún consumidor. Revisá el inventario y cargá la clave nueva ahí. La vieja ya no sirve, y eso es lo que buscamos.

## Etapa 5 — Repositorio privado · 3 min

1. GitHub → `growersb-netizen/ECOFIVER-SISTEMA` → **Settings** → **General** → al final, **Danger Zone** → **Change visibility** → **Make private** → confirmar.
2. **Verificación:** Railway sigue desplegando, porque usa la app de GitHub con acceso propio.
   - En Railway → eco-crm → **Deployments**, el último deploy tiene que verse "Active".
   - Si en el próximo deploy Railway dice que no puede acceder al repo: Railway → Settings del servicio → reconectar GitHub y dar acceso al repositorio. ⛔ Avisale a Rodrigo.
3. Repetí el paso 1 para `growersb-netizen/eco-modulos-web` **solo si Rodrigo lo confirma**. Esa web usa Vercel, que también accede con su app de GitHub.

## Etapa 6 — Clave propia de la IA (`AGENTES_IA_API_KEY`) · 10 min

El CRM ya está preparado para aceptar las dos claves a la vez, así que este cambio no corta nada.

1. Generá una clave con el comando de PowerShell de arriba.
2. Railway → servicio **eco-crm** → Variables → **New Variable**:
   - nombre `AGENTES_IA_API_KEY`;
   - valor: pegar.
   - Guardá y esperá a que el deploy quede "Active" (2-4 min).
3. Railway → servicio **eco-multiagente** → Variables → editá **`CRM_API_KEY`** → reemplazá el valor por **la misma clave** (pegar de nuevo) → guardá y esperá el deploy.
4. **Verificación (5 min después):**
   - `…/health/motor` del multiagente: `"activo":true` y `"fallidas":0`.
   - CRM → **Operaciones IA** → dale a **Aurora** la instrucción "Resumí el embudo comercial de la semana". En 1-2 minutos tiene que quedar **COMPLETADO**, con resultado.
5. **Si falla:** en eco-multiagente volvé `CRM_API_KEY` a su valor anterior. Ese valor sigue siendo igual a la variable `API_KEY` de eco-crm: copiala desde ahí con el portapapeles. ⛔ Avisale a Rodrigo.

## Etapa 7 — Token del Worker de Cloudflare · 15 min

Hacelo **en este orden** para no cortar la generación de imágenes.

1. Generá una clave nueva (PowerShell).
2. Railway → **eco-crm** → Variables → nueva `ECO_WORKER_TOKEN` = pegar.
3. Railway → **eco-multiagente** → Variables → nueva `ECO_WORKER_TOKEN` = pegar (la misma).
4. Cloudflare → **Workers & Pages** → **eco-agentes** → **Settings → Variables and Secrets** → **Add** → tipo **Secret**:
   - nombre `WORKER_TOKEN`;
   - valor: pegar la misma.
   - Guardá.
   - No toques `OPENROUTER_API_KEY`, que ya existe.
5. Publicar el código nuevo del Worker:
   - Abrí `https://github.com/growersb-netizen/ECOFIVER-SISTEMA/blob/main/eco-worker/worker.js` → botón **Raw** → copiá todo el contenido.
   - Cloudflare → eco-agentes → **Edit code** → reemplazá todo el contenido por el copiado → **Deploy**.
6. **Verificación:**
   - `https://eco-agentes.growersb.workers.dev/health` tiene que mostrar `"auth":"requerida"`.
   - Desde una ventana de incógnito, un POST sin token a `/generate` tiene que dar 401. Si no sabés hacerlo, alcanza con el `/health`.
7. **Si algo de imágenes deja de funcionar:** Cloudflare → eco-agentes → **Deployments** → **Rollback** a la versión anterior. ⛔ Avisale a Rodrigo.

## Etapa 8 — Copia de backups fuera de Railway (opcional, recomendado) · 15 min

1. Cloudflare → **R2** → **Create bucket** → nombre `ecofiver-backups` (privado).
   - Si R2 pide activar facturación, ⛔ preguntale a Rodrigo. Tiene cupo gratuito.
2. R2 → **Manage API tokens** → **Create API token** → permiso **Object Read & Write**, solo para el bucket `ecofiver-backups`.
3. Railway → **eco-crm** → Variables → cargá las cuatro, pegando cada valor desde la pantalla de Cloudflare:
   - `R2_ACCOUNT_ID` (el Account ID de Cloudflare);
   - `R2_BUCKET_NAME` = `ecofiver-backups`;
   - `R2_ACCESS_KEY_ID`;
   - `R2_SECRET_ACCESS_KEY`.
4. **Verificación:** CRM → Mis comisiones → **Hacer backup ahora** → Cloudflare R2 → bucket → carpeta `backups/crm/`: tiene que aparecer el archivo nuevo.

---

## Informe final para Rodrigo (completar sin valores secretos)

| Etapa | Estado | Nota |
|---|---|---|
| 1 Backup inicial en Drive + backups de Railway | | |
| 2 Dirección de la fábrica | | |
| 3 Google Maps (cotización Minideck/Campana: km y tarifa) | | |
| 4 Gemini rotada (consumidores actualizados: …) | | |
| 5 Repositorio privado | | |
| 6 Clave propia de la IA (Aurora COMPLETADO) | | |
| 7 Token del Worker (`auth: requerida`) | | |
| 8 R2 (archivo en `backups/crm/`) | | |

Cuando esté listo, Rodrigo le avisa a Claude Code (la sesión de desarrollo), que verifica todo desde producción.
