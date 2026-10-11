/**
 * Updates piscina image fields via the eco-modulos-web admin API.
 * Uses static paths from /public/piscinas/ (served by Vercel CDN).
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

const BASE_URL = 'https://eco-modulos-web.vercel.app'
const API_KEY  = env.WEB_API_KEY

async function getPiscina(id) {
  const res = await fetch(`${BASE_URL}/api/admin/piscinas/${id}`, {
    headers: { 'x-api-key': API_KEY },
  })
  if (!res.ok) throw new Error(`GET ${id} failed (${res.status})`)
  return res.json()
}

async function updateImagen(id, imagen) {
  const piscina = await getPiscina(id)
  const res = await fetch(`${BASE_URL}/api/admin/piscinas/${id}`, {
    method: 'PUT',
    headers: { 'x-api-key': API_KEY, 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...piscina, imagen }),
  })
  if (!res.ok) throw new Error(`PUT ${id} failed (${res.status}): ${await res.text()}`)
  const updated = await res.json()
  console.log(`✓ ${updated.nombre} → ${updated.imagen}`)
}

// piscina-2 = Miniportante → best photo: miniportante-1.jpg (real installation)
// piscina-3 = Autoportante → best photo: autoportante-6.jpg (garden, vintage car)
await updateImagen('piscina-2', '/piscinas/miniportante-1.jpg')
await updateImagen('piscina-3', '/piscinas/autoportante-6.jpg')

console.log('\nDone.')
