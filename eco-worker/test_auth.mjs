// Prueba de autenticación del Worker (sin red: OpenRouter simulado). Ejecutar: node eco-worker/test_auth.mjs
import w from "./worker.js";
globalThis.fetch = async () => new Response(JSON.stringify({choices:[{message:{content:"copy simulado"}}]}), {status:200});
const req = (tok) => new Request("https://x/generar-copy", {method:"POST",
  headers: Object.assign({"Content-Type":"application/json"}, tok ? {Authorization:`Bearer ${tok}`} : {}),
  body: JSON.stringify({producto:"piscina"})});
const base = {OPENROUTER_API_KEY:"k"};
const r = async (env, tok) => (await w.fetch(req(tok), env)).status;
const out = {
  sin_token_configurado_anonimo: await r(base),
  con_token_anonimo: await r({...base, WORKER_TOKEN:"t0ken-largo"}),
  con_token_incorrecto: await r({...base, WORKER_TOKEN:"t0ken-largo"}, "t0ken-larga"),
  con_token_correcto: await r({...base, WORKER_TOKEN:"t0ken-largo"}, "t0ken-largo"),
  health_publico: (await w.fetch(new Request("https://x/health"), {...base, WORKER_TOKEN:"t"})).status,
};
console.log(JSON.stringify(out));
const esperado = {sin_token_configurado_anonimo:200, con_token_anonimo:401, con_token_incorrecto:401,
                  con_token_correcto:200, health_publico:200};
for (const [k, v] of Object.entries(esperado)) if (out[k] !== v) { console.error("FALLA", k, out[k]); process.exit(1); }
console.log("OK");
