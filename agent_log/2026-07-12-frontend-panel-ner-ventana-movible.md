# Handoff — Panel NER compacto + ventana de ilustración movible + chat más ancho

**Fecha:** 2026-07-12
**Autor:** agente de Erick (frontend)
**Para:** equipo (informativo; §4 tiene una consulta pendiente para Giano)
**Referencia:** [`2026-07-12-frontend-chat-ancho-textarea-imagenes.md`](2026-07-12-frontend-chat-ancho-textarea-imagenes.md),
[`2026-07-11-backend-evaluacion-ner-panel.md`](2026-07-11-backend-evaluacion-ner-panel.md)

## Diagnóstico previo (por qué no se veía el panel)

Ningún reader en `data/outputs/readers/` traía `chunk_elements` (ni
la_metamorfosis) → el panel se ocultaba por diseño. El reader anotado que
Giano compartió (`source_reader_companion/`) sí los trae (96 chunks); se
copió al directorio de datos local (con backup). El endpoint lee el archivo
por request: sin reiniciar el backend, recargar la página basta.

Dato del reader anotado: con el extractor spaCy solo `personajes` (91 chunks)
y `lugares` (2) traen datos; `objetos_simbolos`/`temas`/`emociones` vienen
vacías en toda la obra — justifica el cambio 1.

## Cambios (pedidos de Giano/Erick)

1. **Panel NER: solo personajes y lugares.** Se quitaron
   objetos_simbolos/temas/emociones (venían vacías con el NER actual).
2. **Panel compacto.** Se eliminaron los encabezados de sección; ahora es una
   **nube única de chips** ordenados por primera aparición, cada uno con
   **ícono** (👤 personaje / 📍 lugar) + **tooltip** con la categoría. Ocupa
   ~la mitad del alto.
3. **Ventana de ilustración movible.** Antes `position: fixed` sobre el chat,
   solo abrir/cerrar → tapaba el chat. Ahora se **arrastra por su cabecera**
   (pointer events + pointer capture, sin listeners globales), clamp a la
   ventana. Así el alumno la aparta para seguir leyendo/chateando.
4. **Chat más ancho.** Contenedor `1400→1600px` y columna del chat
   `minmax(400,460)→minmax(440,620)` para aprovechar el espacio horizontal a
   la derecha que Erick notó sin usar.
5. **Burbujas del chat aprovechan el ancho.** `.msg` de `max-width:90%` a
   `100%`; la respuesta del asistente ocupa toda la columna (como el panel),
   el mensaje del alumno queda a `85%` para conservar la asimetría.
   `overflow-wrap: anywhere` evita scroll horizontal con palabras largas.
6. **Tooltip del panel instantáneo.** El `title` nativo tardaba ~1s en salir
   (arruinaba el "pasa el ratón y sabes el tipo"). Se reemplazó por un tooltip
   propio `position: fixed` que aparece al instante y no lo recorta el
   overflow del panel.

## Verificación

`npm run build` + e2e (25 checks) en verde: nuevo check de arrastre de la
ventana; el del panel sigue pasando con la nube compacta. (La guardia
anti-ambigüedad NER y sus 2 checks e2e adicionales van en un handoff aparte:
`2026-07-12-frontend-guardia-ambiguedad-ner.md`.)

## ⚠️ Pendiente de decisión (Giano, por WhatsApp)

**Mover la fusión de alias al backend** (propuesto en `research/ner-plan-
mejora.md`). Hoy `ElementsPanel` fusiona variantes en el cliente ("Gregorio"
⊂ "Gregorio Samsa"). Si el backend pasa a canonicalizar, quito esa lógica —
pero **secuenciado**: backend canonicaliza primero, luego el frontend la
elimina; al revés el panel mostraría duplicados. En pausa hasta que Giano
confirme.

## Qué NO toqué

Solo `frontend/` + `agent_log/`. El reader copiado a `data/` es dato local
gitignored provisto por Giano (no versionado, no es edición de código ajeno).
