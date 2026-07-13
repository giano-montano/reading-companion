# Despliegue MVP — frontend en Vercel + backend auto-hospedado vía Cloudflare Tunnel

**Fecha:** 2026-07-12 · Objetivo: demo/MVP gratis, sin tarjeta, seguro.

## Por qué esta arquitectura

El backend carga **torch + sentence-transformers (E5)** + chromadb en runtime
(~1–2GB). Eso **no cabe** en funciones serverless (Vercel Functions: 250MB) ni en
Cloudflare Workers (no corren Python/torch), y las capas gratuitas de contenedores
con RAM suficiente exigen tarjeta (Cloud Run, Oracle) o ya son de pago (HF Spaces
Docker). Solución para el MVP: **el backend corre en la máquina del equipo** y se
expone por un **túnel saliente** de Cloudflare; el frontend, que sí es estático,
va a Vercel.

```
[navegador] → https://tu-app.vercel.app   (frontend estático, Vercel)
                      │
                      ▼  VITE_API_BASE_URL
            https://xxx.trycloudflare.com  (Cloudflare Tunnel, HTTPS)
                      │  conexión SALIENTE — no hay puertos abiertos
                      ▼
            http://127.0.0.1:8000          (uvicorn en tu máquina)
                      │
                      ▼
            NVIDIA NIM / Cloudflare Workers AI   (LLM e imágenes, remotos)
```

## Pasos

### 1. Backend + túnel (obtienes la URL pública)

```powershell
winget install --id Cloudflare.cloudflared      # una sola vez

# terminal 1 — backend (solo loopback: nadie en la red local lo alcanza)
$env:PYTHONPATH="src"; uvicorn companion.api.server:app --host 127.0.0.1 --port 8000

# terminal 2 — túnel (déjalo vivo TODA la demo)
cloudflared tunnel --url http://localhost:8000
```
Copia la URL HTTPS que imprime (`https://xxxx.trycloudflare.com`) y compruébala en
`/health` → `{"status":"ok"}`.

> ⚠️ El Quick Tunnel da una URL **aleatoria que cambia en cada reinicio**. Si el
> proceso se cae, hay que actualizar la env en Vercel y redeployar. Para una URL
> estable hace falta un *named tunnel* con dominio propio en Cloudflare.

### 2. Frontend en Vercel

1. vercel.com → **Add New → Project** → importa el repo de GitHub.
2. **Root Directory:** `frontend` · **Framework:** Vite (autodetectado).
3. **Environment Variable:** `VITE_API_BASE_URL` = la URL del túnel (sin barra final).
4. Deploy → te da `https://tu-app.vercel.app`.

### 3. Cerrar CORS al dominio de Vercel

Ya con el dominio, en el `.env` local del backend:
```
CORS_ALLOW_ORIGINS=https://tu-app.vercel.app
```
y **reinicia** uvicorn. (Por defecto es `*`, útil en dev; en la demo conviene cerrarlo.)
Lo lee `settings.cors_allow_origins` y lo aplica `api/server.py`.

## Seguridad

| Riesgo | Mitigación |
|---|---|
| Exponer la máquina | **Nunca port-forwarding.** El túnel es una conexión *saliente*: cero puertos abiertos en router/PC. |
| Alcance en la red del evento | uvicorn atado a `127.0.0.1`, no a `0.0.0.0`. |
| Origen arbitrario desde navegador | `CORS_ALLOW_ORIGINS` = dominio de Vercel. |
| **Gasto de créditos NVIDIA** | El endpoint no tiene auth: quien descubra la URL del túnel puede llamarlo con `curl` (CORS solo frena navegadores). Riesgo bajo con URL aleatoria y ventana corta. Blindaje real pendiente: header `X-API-Key` (requiere cambio en el cliente del frontend). |
| Fuga de secretos | `.env` nunca se commitea; vive solo en la máquina. |

**Baja el túnel al terminar la demo.**

## Durante la presentación

- No reinicies `cloudflared` (cambiaría la URL). Mantén ambas terminales vivas.
- Máquina enchufada y con la suspensión desactivada.
- **Precalienta ~15 min antes**: una pregunta de prueba carga el embedder E5 (~24s)
  y deja todo caliente.
- Ten una **grabación de pantalla** de un flujo completo como red de seguridad.