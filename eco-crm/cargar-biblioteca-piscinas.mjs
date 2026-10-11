/**
 * Carga fotos y videos de piscinas a la biblioteca del panel de aliados.
 * Imágenes → url_externa (Vercel public folder).
 * Videos → archivo físico subido al CRM Railway.
 */
import { readFileSync } from 'fs'

const envLines = readFileSync('./eco-crm/.env', 'utf-8').split(/\r?\n/)
const env = {}
for (const line of envLines) {
  if (!line || line.startsWith('#')) continue
  const idx = line.indexOf('=')
  if (idx < 0) continue
  env[line.substring(0, idx).trim()] = line.substring(idx + 1).trim().replace(/^["']|["']$/g, '')
}

const CRM_BASE = 'https://eco-crm-production.up.railway.app'
const API_KEY  = env.API_KEY
const WEB_BASE = 'https://eco-modulos-web.vercel.app'

const UPLOADS_DIR = 'C:/Users/PC/.claude/uploads/0734bb3c-c877-44fc-b7cd-cbe902df7916'

async function crearMaterial(data) {
  const form = new FormData()
  for (const [k, v] of Object.entries(data)) {
    if (v !== null && v !== undefined) form.append(k, v)
  }
  const res = await fetch(`${CRM_BASE}/api/materiales-socio`, {
    method: 'POST',
    headers: { 'x-api-key': API_KEY },
    body: form,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status}: ${text.substring(0, 200)}`)
  }
  return res.json()
}

async function crearMaterialConArchivo(localPath, filename, tipo, categoria, titulo, descripcion) {
  const buf = readFileSync(localPath)
  const isVideo = filename.endsWith('.mp4')
  const mimeType = isVideo ? 'video/mp4' : 'image/jpeg'

  const form = new FormData()
  form.append('tipo', tipo)
  form.append('categoria', categoria)
  form.append('titulo', titulo)
  form.append('descripcion', descripcion)
  form.append('archivo', new Blob([buf], { type: mimeType }), filename)

  const res = await fetch(`${CRM_BASE}/api/materiales-socio`, {
    method: 'POST',
    headers: { 'x-api-key': API_KEY },
    body: form,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status}: ${text.substring(0, 200)}`)
  }
  return res.json()
}

// ── IMÁGENES (url_externa → Vercel public) ──────────────────────────────────
const imagenes = [
  // Miniportante
  { tipo: 'imagen', categoria: 'piscinas', titulo: 'Miniportante — Instalación cliente (modelo arena)', descripcion: 'Foto de instalación real en obra. Miniportante color arena. Apta para redes sociales y publicaciones.', url_externa: `${WEB_BASE}/piscinas/miniportante-1.jpg` },
  { tipo: 'imagen', categoria: 'piscinas', titulo: 'Miniportante — Showroom modelos disponibles', descripcion: 'Foto del showroom con distintos modelos de miniportante. Blanca y turquesa. Útil para mostrar opciones de color.', url_externa: `${WEB_BASE}/piscinas/miniportante-2.jpg` },
  // Autoportante
  { tipo: 'imagen', categoria: 'piscinas', titulo: 'Autoportante — Instalación al aire libre (campo)', descripcion: 'Autoportante instalada al aire libre bajo quincho. Perfecta para mostrar facilidad de instalación.', url_externa: `${WEB_BASE}/piscinas/autoportante-1.jpg` },
  { tipo: 'imagen', categoria: 'piscinas', titulo: 'Autoportante — Patio urbano (color blanca)', descripcion: 'Autoportante blanca en patio de casa urbana. Excelente foto para mostrar resultado final en espacios pequeños.', url_externa: `${WEB_BASE}/piscinas/autoportante-2.jpg` },
  { tipo: 'imagen', categoria: 'piscinas', titulo: 'Autoportante — Vista cenital (showroom)', descripcion: 'Vista desde arriba del molde/interior de la piscina autoportante. Muestra la calidad del fibra de vidrio.', url_externa: `${WEB_BASE}/piscinas/autoportante-3.jpg` },
  { tipo: 'imagen', categoria: 'piscinas', titulo: 'Autoportante — Versión turquesa con iluminación LED', descripcion: 'Autoportante turquesa encendida con luces LED violetas. Foto impactante para redes sociales.', url_externa: `${WEB_BASE}/piscinas/autoportante-4.jpg` },
  { tipo: 'imagen', categoria: 'piscinas', titulo: 'Autoportante — Jardín verde (blanca)', descripcion: 'Autoportante blanca en jardín, con vegetación de fondo. Transmite frescura y calidad.', url_externa: `${WEB_BASE}/piscinas/autoportante-5.jpg` },
  { tipo: 'imagen', categoria: 'piscinas', titulo: 'Autoportante — Jardín con auto clásico (foto destacada)', descripcion: 'Foto premium: autoportante blanca en jardín con auto clásico. La mejor foto del catálogo para publicidades.', url_externa: `${WEB_BASE}/piscinas/autoportante-6.jpg` },
]

console.log('Cargando imágenes a la biblioteca...')
for (const img of imagenes) {
  try {
    const r = await crearMaterial(img)
    console.log(`  ✓ [${r.id}] ${r.titulo}`)
  } catch (e) {
    console.error(`  ✗ ${img.titulo}: ${e.message}`)
  }
}

// ── VIDEOS (archivo físico → Railway) ────────────────────────────────────────
const videos = [
  { path: `${UPLOADS_DIR}/75aef245-VID-20260926-WA02801.mp4`, filename: 'miniportante-video-1.mp4', categoria: 'piscinas', titulo: 'Miniportante — Video 1 (WhatsApp)', descripcion: 'Video de la piscina Miniportante. Ideal para compartir por WhatsApp con clientes.' },
  { path: `${UPLOADS_DIR}/1ae9b427-VID-20260926-WA0283.mp4`, filename: 'miniportante-video-2.mp4', categoria: 'piscinas', titulo: 'Miniportante — Video 2 (WhatsApp)', descripcion: 'Segundo video de la Miniportante. Muestra otro ángulo o instalación diferente.' },
  { path: `${UPLOADS_DIR}/55941928-VID-20260926-WA0278.mp4`, filename: 'autoportante-video-1.mp4', categoria: 'piscinas', titulo: 'Autoportante — Video 1 (WhatsApp)', descripcion: 'Video de la piscina Autoportante. Ideal para compartir por WhatsApp con clientes.' },
  { path: `${UPLOADS_DIR}/d6eed790-VID-20260926-WA0276.mp4`, filename: 'autoportante-video-2.mp4', categoria: 'piscinas', titulo: 'Autoportante — Video 2 (WhatsApp)', descripcion: 'Segundo video de la Autoportante. Muestra otro ángulo o instalación diferente.' },
]

console.log('\nSubiendo videos al CRM...')
for (const vid of videos) {
  try {
    const r = await crearMaterialConArchivo(vid.path, vid.filename, 'video', vid.categoria, vid.titulo, vid.descripcion)
    console.log(`  ✓ [${r.id}] ${r.titulo} → ${r.archivo_path || r.url_externa}`)
  } catch (e) {
    console.error(`  ✗ ${vid.titulo}: ${e.message}`)
  }
}

console.log('\n✓ Listo.')
