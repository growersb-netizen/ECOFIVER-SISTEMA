# Recuperar las ramas locales de Codex (Windows / PowerShell)

Objetivo: publicar en GitHub, **sin modificarlas**, estas ramas:

| Repo | Rama | Commit esperado |
|---|---|---|
| ECOFIVER-SISTEMA | `fix/chat-session-isolation` | `cc35e4b` |
| ECOFIVER-SISTEMA | `fix/crm-socio-token-isolation` (si existe) | — |
| eco-modulos-web | `fix/chat-session-proxy` | `dc2012d` |

Reglas:
- Ningún comando de esta guía borra, resetea ni reescribe nada.
- No usar `git reset --hard`, `git clean`, `git push --force` ni `git stash`.
- No fusionar ni desplegar.

> ⚠️ **ECOFIVER-SISTEMA y eco-modulos-web son repositorios PÚBLICOS.** Todo lo que se sube queda visible en el acto, y un secreto subido hay que considerarlo filtrado aunque después se borre. Por eso el paso 3 (revisión de secretos) es obligatorio. Lo recomendable es pasar los repos a **privados antes** del paso 4: GitHub → Settings → General → Danger Zone → Change visibility.

---

## Paso 1: localizar los repositorios

Abrí PowerShell (no hace falta que sea como administrador) y ejecutá:

```powershell
# Unidades disponibles
Get-PSDrive -PSProvider FileSystem | Select-Object Name, Root

# Buscar repos Git con esos nombres en tu carpeta de usuario (hasta 6 niveles)
Get-ChildItem -Path $env:USERPROFILE -Directory -Recurse -Depth 6 -Force -ErrorAction SilentlyContinue -Filter ".git" |
  ForEach-Object { $_.Parent.FullName } |
  Where-Object { $_ -match 'ECOFIVER|eco-modulos' }
```

Si no aparecen, repetí la búsqueda cambiando `$env:USERPROFILE` por otra unidad, por ejemplo `D:\`.

Anotá las dos rutas:

```powershell
$SISTEMA  = "C:\ruta\a\ECOFIVER-SISTEMA"      # reemplazar
$FRONTEND = "C:\ruta\a\eco-modulos-web"       # reemplazar
```

## Paso 2: verificar ramas, commits y cambios sin guardar (solo lectura)

```powershell
cd $SISTEMA
git remote -v
git status
git worktree list
git branch -a
git fetch origin
git log --oneline -1 cc35e4b
git branch --contains cc35e4b
git log --oneline origin/main..fix/chat-session-isolation
git diff --stat origin/main...fix/chat-session-isolation
git log --oneline origin/main..fix/crm-socio-token-isolation 2>$null
```

```powershell
cd $FRONTEND
git remote -v
git status
git worktree list
git branch -a
git fetch origin
git log --oneline -1 dc2012d
git branch --contains dc2012d
git log --oneline origin/master..fix/chat-session-proxy
git diff --stat origin/master...fix/chat-session-proxy
```

Qué revisar:
- **`git status` muestra cambios sin commitear:** no los descartes. Antes del paso 4, mandame la salida de `git status` y `git diff --stat` y decidimos juntos.
- **`git worktree list` muestra otras carpetas:** el trabajo puede estar en un worktree. Repetí el paso 2 dentro de esa carpeta.
- **Los commits no son `cc35e4b` / `dc2012d`:** está bien si la rama avanzó. Anotá el commit actual.

### Respaldo completo antes de publicar (no modifica nada)

```powershell
New-Item -ItemType Directory -Force C:\backup-ecofiver | Out-Null
cd $SISTEMA;  git bundle create C:\backup-ecofiver\ecofiver-sistema.bundle --all
cd $SISTEMA;  git diff > C:\backup-ecofiver\ecofiver-sistema-sin-commitear.patch
cd $FRONTEND; git bundle create C:\backup-ecofiver\eco-modulos-web.bundle --all
cd $FRONTEND; git diff > C:\backup-ecofiver\eco-modulos-web-sin-commitear.patch
```

## Paso 3: revisar que no se publiquen secretos ni archivos sensibles

Se revisa **cada commit** que se va a subir, no solo el resultado final: un secreto agregado y después borrado en otro commit igual queda publicado.

```powershell
cd $SISTEMA
$RANGO = "origin/main..fix/chat-session-isolation"

# 1) Archivos sensibles por nombre en cualquier commit del rango
git log --name-only --pretty=format: $RANGO | Sort-Object -Unique |
  Select-String -Pattern '(^|/)\.env($|\.)|\.pem$|\.key$|\.p12$|\.pfx$|\.db$|\.sqlite|\.bundle$|credential|secret|id_rsa|backup' 

# 2) Valores con forma de credencial en el contenido de cada commit
git log -p $RANGO |
  Select-String -Pattern 'sk-or-v1-[0-9a-f]{20}|sk-[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_\-]{30}|EAA[A-Za-z0-9]{30,}|ghp_[A-Za-z0-9]{30}|github_pat_|xox[bp]-|-----BEGIN [A-Z ]*PRIVATE KEY|(?i)(password|passwd|secret|api_key|token)\s*[:=]\s*["''][^"''\s]{8,}'

# 3) Archivos grandes (bases, exports, backups)
git log --pretty=format: --name-only $RANGO | Sort-Object -Unique | Where-Object { $_ } |
  ForEach-Object { if (Test-Path $_) { Get-Item $_ | Where-Object Length -gt 1MB | Select-Object FullName, Length } }
```

Repetí lo mismo en `$FRONTEND` con `$RANGO = "origin/master..fix/chat-session-proxy"`. Ahí revisá también archivos `.env.local` y `.env.production`.

**Resultado esperado:** las tres búsquedas sin coincidencias. Los nombres de variables (`OPENROUTER_API_KEY=`) sin valor son normales.
- **Si aparece un valor real:** no subas nada y avisame. Hay que sacarlo del commit en una rama nueva sin reescribir la original, y además **rotar** esa credencial.
- **Informes de auditoría** (`INFORME_ECOFIVER_AI_COMPANY_FASE_0.md`, `AUDITORIA_INTEGRAL_ECOFIVER.md`): describen vulnerabilidades. **No los subas a un repo público.** Subilos solo si el repo es privado, o pasámelos por otro medio.

## Paso 4: publicar las ramas (sin fusionar)

Recién cuando el paso 3 dio limpio:

```powershell
cd $SISTEMA
git push origin fix/chat-session-isolation:fix/chat-session-isolation
git push origin fix/crm-socio-token-isolation:fix/crm-socio-token-isolation   # solo si existe
git ls-remote origin fix/chat-session-isolation

cd $FRONTEND
git push origin fix/chat-session-proxy:fix/chat-session-proxy
git ls-remote origin fix/chat-session-proxy
```

`git ls-remote` tiene que mostrar el mismo commit que `git log -1` local.
- **Si el push pide credenciales:** usá el inicio de sesión del navegador de Git Credential Manager. No pegues tokens en scripts.
- **Si el push es rechazado** (la rama ya existe con otro contenido): **no** uses `--force`. Avisame.

No abras PRs ni fusiones. Avisame cuando estén subidas.

## Paso 5 (lo hago yo, en la sesión remota)
1. `git fetch` de las ramas nuevas.
2. Comparar contra el PR #10 (`ccr-b6d2e636-iqq5ux-integracion-fase-0-5`), archivo por archivo.
3. Clasificar cada cambio de Codex: ya cubierto / complementario / en conflicto.
4. Integrar lo que falte, con pruebas, en la rama de integración, sin descartar el trabajo de Codex.
5. Documentar el resultado en el MASTER PLAN.
