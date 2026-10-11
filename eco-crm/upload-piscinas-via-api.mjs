/**
 * Uploads piscina images via the eco-modulos-web admin API.
 * Uses WEB_BASE_URL and WEB_API_KEY from eco-crm .env.
 */
import { readFileSync } from 'fs'

// Parse .env
const envLines = readFileSync('./eco-crm/.env', 'utf-8').split(/\r?\n/)
const env = {}
for (const line of envLines) {
  if (!line || line.startsWith('#')) continue
  const idx = line.indexOf('=')
  if (idx < 0) continue
  env[line.substring(0, idx).trim()] = line.substring(idx + 1).trim().replace(/^["']|["']$/g, '')
}

const BASE_URL = 'https://eco-modulos-web.vercel.app'
const API_KEY  = env.WEB_API_KEY

if (!BASE_URL || !API_KEY) {
  console.error('Missing WEB_BASE_URL or WEB_API_KEY in eco-crm/.env')
  process.exit(1)
}

console.log('API endpoint:', BASE_URL)

async function uploadImage(localPath, filename) {
  const buf = readFileSync(localPath)
  const form = new FormData()
  form.append('file', new Blob([buf], { type: 'image/jpeg' }), filename)

  const res = await fetch(`${BASE_URL}/api/admin/upload`, {
    method: 'POST',
    headers: { 'x-api-key': API_KEY },
    body: form,
  })

  if (!res.ok) {
    const text = await res.text()
    const ct = res.headers.get('content-type') || ''
    throw new Error(`Upload failed (${res.status} ${res.statusText}) ct=${ct}: ${text.substring(0, 500)}`)
  }
  const { url } = await res.json()
  return url
}

async function updatePiscina(id, imagen) {
  // First get current data
  const getRes = await fetch(`${BASE_URL}/api/admin/piscinas/${id}`, {
    headers: { 'x-api-key': API_KEY },
  })
  if (!getRes.ok) throw new Error(`GET piscina failed (${getRes.status})`)
  const piscina = await getRes.json()

  // Update with imagen
  const putRes = await fetch(`${BASE_URL}/api/admin/piscinas/${id}`, {
    method: 'PUT',
    headers: { 'x-api-key': API_KEY, 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...piscina, imagen }),
  })
  if (!putRes.ok) {
    const text = await putRes.text()
    throw new Error(`PUT piscina failed (${putRes.status}): ${text}`)
  }
  return await putRes.json()
}

// List piscinas to find IDs
const listRes = await fetch(`${BASE_URL}/api/admin/piscinas`, {
  headers: { 'x-api-key': API_KEY },
})
if (!listRes.ok) {
  console.error('Cannot list piscinas:', await listRes.text())
  process.exit(1)
}
const piscinas = await listRes.json()
console.log('Piscinas en DB:')
piscinas.forEach(p => console.log(`  ${p.id} — ${p.nombre}`))

const BASE_UPLOADS = 'C:/Users/PC/.claude/uploads/0734bb3c-c877-44fc-b7cd-cbe902df7916'

// Upload best photo per model
const UPLOADS = [
  {
    label: 'Miniportante',
    // First image: dark indoor installation (more authentic)
    file: `${BASE_UPLOADS}/0787a721-image.jpg`,
    filename: 'piscina-miniportante.jpg',
    matchName: 'miniportante',
  },
  {
    label: 'Autoportante (best: garden with vintage car)',
    file: `${BASE_UPLOADS}/8f502f43-image.jpg`,
    filename: 'piscina-autoportante.jpg',
    matchName: 'autoportante',
  },
]

for (const u of UPLOADS) {
  try {
    console.log(`\nUploading ${u.label}...`)
    const url = await uploadImage(u.file, u.filename)
    console.log(`  Uploaded: ${url}`)

    const piscina = piscinas.find(p => p.nombre.toLowerCase().includes(u.matchName))
    if (!piscina) {
      console.log(`  WARN: No piscina found matching "${u.matchName}"`)
      continue
    }
    await updatePiscina(piscina.id, url)
    console.log(`  ✓ DB updated: ${piscina.nombre} (${piscina.id})`)
  } catch (e) {
    console.error(`  ✗ Error: ${e.message}`)
  }
}

console.log('\nDone.')
