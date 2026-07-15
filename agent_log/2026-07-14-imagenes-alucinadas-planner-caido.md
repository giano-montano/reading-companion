# Las imágenes "alucinadas" — causa raíz y cierre

**Fecha:** 2026-07-14
**Estado:** resuelto (el bug de fondo). Queda abierto el bloqueo NSFW de Cloudflare (§5).

## 1. El síntoma

Durante días las ilustraciones salían con **texto en español deformado dentro de la imagen**
y con supuestas **deformidades anatómicas**. Se culpó al modelo de difusión de alucinar.

Se probaron y descartaron dos hipótesis:

1. *"Falta retrieval / contexto"* → se añadió (`visual_support/background.py`). Arregló un
   problema real y distinto (a media obra el texto nunca repite que Gregorio es un insecto,
   así que el planificador describía "a un hombre"), pero no el texto ni las deformidades.
2. *"El prompt es demasiado largo y el muro anti-texto invoca al texto"* → se reescribió el
   prompt de 1.638 a 267 chars, sin una sola mención a "text/caption/label/sign". Siguió igual.

## 2. La causa raíz

**No había alucinación. A Flux se le estaba mandando el texto en español de la novela como
prompt, y él lo dibujaba de pie de foto — que es exactamente lo que se le pedía.**

La cadena completa:

1. `.env` tenía `VISUAL_PLANNER_MODEL=gpt-5.4-mini`, pero el provider efectivo era **NVIDIA**
   (había un `LLM_PROVIDER=nvidia` exportado en el shell que **pisa al `.env`**: en
   pydantic-settings la variable de entorno del SO gana siempre al fichero).
2. Cada llamada del `scene_planner` pedía un modelo de OpenAI a `integrate.api.nvidia.com`
   → **404 en el 100% de las llamadas**, en cada trozo del map-reduce.
3. `service.prepare()` capturaba la excepción con un `logger.warning` y **seguía adelante**.
4. `visual_events` quedaba vacío.
5. `prompt_builder` caía a su fallback: `" ".join(request.text.split())[:200]` — **la prosa
   de Kafka, en español, como prompt de un modelo de difusión.**

El router y el content nunca se rompieron porque sus nombres de modelo **sí** eran de NVIDIA
(también exportados en el shell). Por eso el chat funcionaba y nadie sospechó de la config:
lo único que se coló del `.env` fue `VISUAL_PLANNER_MODEL`, y es lo único que se rompió.

### Cómo se demostró

El nombre de cada PNG generado **es el `sha256` del prompt que lo produjo**
(`service._build_cache_key`). Así que se reconstruyeron prompts candidatos (builder nuevo y
el commiteado, sobre todos los chunks de todos los libros) y se hashearon contra los nombres
de fichero. La imagen más reciente, `visual_d62c887959e9728a6617a52f.png`, casó exacto con el
**camino de fallback**, sobre *La metamorfosis*, chunks 3+:

```
Si no tuviera que dominarme por mis padres, ya me habría despedido hace tiempo, me habría
presentado ante el jefe y le habría dicho mi opinión con toda mi alma. ¡Se habría caído de
la mesa! Sé que es  children's storybook illustration, warm soft lighting, ...
```

Y el texto dibujado dentro de esa imagen era **«¡Se habrse cáño die la mesa!»**. Es el prompt.

La supuesta "deformidad anatómica" de `visual_16760779...` (una señora con una pezuña moteada)
era el **«pesado manguito de piel»** del cuadro de la pared del cuarto de Gregorio: el prompt
describía ese cuadro, y Flux lo dibujó correctamente. Obedecía bien; se le pedía mal.

### La lección

Las dos hipótesis anteriores no es que fueran falsas: **nunca se probaron**. El
`prompt_builder` reescrito no llegó a ejecutarse ni una sola vez, porque `visual_events`
jamás fue distinto de vacío. Se estuvo razonando sobre un prompt que no era el que salía.

> **Mirar el artefacto antes que el código.** El `prompt_used` de la respuesta del job y la
> propia imagen tenían la respuesta desde el primer día.

## 3. El arreglo

**a) Sin plan no hay imagen.** `build_visual_prompt` levanta `ValueError` si no hay
`visual_events`, y `service.prepare()` **revienta** en vez de tragarse el fallo del planner.
`images/runner.py` ya lo convierte en un job fallido con su mensaje. Se eliminó el fallback
que volcaba `request.text[:200]`: el prompt no puede contener el texto de la obra, nunca.
Un planner caído producía imágenes plausibles, equivocadas y de pago; ahora se ve.

**b) Provider por rol** (`config.py`, `providers/factory.py`). El modelo ya era por rol; el
provider no, y esa asimetría es lo que permitió dejar un modelo de OpenAI apuntando a NVIDIA
sin que nada chillara. Ahora: `ROUTER_PROVIDER`, `CONTENT_PROVIDER`, `VISUAL_PLANNER_PROVIDER`,
cada uno cayendo a `LLM_PROVIDER` si no se define. El `provider_tag` de la caché ya incluía
provider + rol, así que el contrato #3 se respeta solo.

Config resultante — se paga solo el content:

| rol | provider | modelo |
|---|---|---|
| router | NVIDIA | `meta/llama-3.1-8b-instruct` (gratis) |
| visual planner | NVIDIA | `meta/llama-3.1-8b-instruct` (gratis) |
| content | OpenAI | `gpt-5.4-mini` |

**c) Limpieza:** `build_background(scene=...)` no usaba `scene`; `infer_frame_count(scope, text)`
no usaba `text`; `import math` huérfano en `cloudflare_flux.py`; y el
`allow_text_in_image=False, #payload.allow_text_in_image` hardcodeado en `api/images.py`.

## 4. Trampa que sigue viva

**Hay exports de `LLM_PROVIDER`, `ROUTER_MODEL` y `CONTENT_MODEL` en el shell** desde el que se
arranca el backend, y **pisan al `.env`**. Hoy apuntan a lo mismo, así que no hacen daño — pero
son la razón de que se creyera estar corriendo OpenAI mientras se corría NVIDIA. Mientras
existan, el `.env` miente. Arrancar uvicorn desde una PowerShell limpia.

## 5. ABIERTO: el bloqueo NSFW de Cloudflare (error 3030)

Investigado, **no arreglado**. Dos hallazgos, y los dos dicen que el reintento actual es inútil:

1. **El clasificador es de ENTRADA, no de salida.** El error 3030 de Workers AI es
   `"Input prompt contains NSFW content"`: se juzga el **prompt**, no la imagen generada. El
   comentario de `service.py:19` ("Flux runs a safety classifier on the OUTPUT") es falso, y es
   la premisa sobre la que se construyó `_generate_with_flag_retry`. Como el prompt no cambia
   entre intentos y el clasificador es determinista, **los 3 reintentos dan el mismo veredicto
   por construcción**. No es que "a veces bloquee los 3": es que cuando bloquea, bloquea
   siempre los 3.
2. **La semilla ni siquiera se envía.** `cloudflare_flux._post_multipart()` — la ruta que usa
   `flux-2-klein-9b` — manda `prompt`, `width`, `height` y `steps`, **y nada más**. El `seed`
   que `_generate_with_flag_retry` va variando no llega a Cloudflare. Los 3 intentos son tres
   peticiones HTTP idénticas.

Por qué se dispara con nuestros prompts (hipótesis, sin verificar): el filtro tiene falsos
positivos notorios con prompts inocuos, y los nuestros combinan `"children's storybook
illustration"` (fijo, en `_STYLE`) con escenas que el 8B describe con "lies in bed", "his body",
"young girl"… Un menor + una cama es precisamente lo que un clasificador NSFW ingenuo castiga.

Vías a evaluar, de más barata a más cara:

- **Quitar `children's` de `_STYLE`.** Una palabra. Si es el disparador, sale gratis.
- **Matar el reintento por semilla.** No puede funcionar. O se elimina, o se sustituye por lo
  único que tiene sentido contra un filtro de entrada: **reintentar con el prompt reescrito**
  (pedirle al 8B que redescriba la escena evitando términos sensibles). Es la única forma de
  cambiar lo que el clasificador juzga.
- **Saneado determinista** del prompt (mapa de reemplazos para los disparadores típicos).
  Barato, sin llamada extra, pero frágil.
- **Fallback a NVIDIA.** Ya existe `images/nvidia_image.py` y `NVIDIA_IMAGE_MODEL=flux.1-schnell`
  en `.env`. Es la salida real cuando Cloudflare se cierra en banda.
- **NO sirve** cambiar a `@cf/black-forest-labs/flux-1-schnell` para esquivar el filtro: el
  filtro es de la plataforma Workers AI, no del modelo, y schnell tiene los mismos falsos
  positivos. Tampoco hay parámetro para desactivarlo (issue abierto en `workers-sdk#13970`).

Antes de tocar nada, el experimento que decide: mandar **dos veces el mismo prompt que ya
falló** y ver si falla idéntico. Si sí, el filtro es de entrada y queda cerrado el asunto.

## Referencias

- `workers-sdk#13970` — petición de opt-out del filtro NSFW, abierta desde 2024-10.
- Docs de errores de Workers AI (el 3030 ni siquiera está documentado en la tabla oficial).
