import { useMemo, useState } from "react";
import type { ChunkElements, ReadingState } from "../api/types";
import { chunkIndexOf } from "../api/types";

/**
 * Panel NER — "Elementos de la historia".
 *
 * Agrega los chunk_elements del reader HASTA max_progress_chunk_index (gate
 * por VALOR del índice, no por conteo: hay huecos). Crece a medida que el
 * alumno lee; los elementos presentes en los chunks visibles ahora mismo se
 * resaltan como "en lo que lees". Anti-spoiler por construcción: cada entrada
 * solo describe texto ya alcanzado.
 */

// Solo personajes y lugares: el extractor NER (spaCy) únicamente puebla esas
// dos categorías; objetos/temas/emociones venían siempre vacías (decisión del
// equipo, 2026-07-12). El `label` es singular porque va en el tooltip por chip.
const CATEGORIES = [
  { key: "personajes", icon: "👤", label: "Personaje" },
  { key: "lugares", icon: "📍", label: "Lugar" },
] as const;

type CategoryKey = (typeof CATEGORIES)[number]["key"];

interface ElementItem {
  label: string;
  /** Chunk donde apareció por primera vez (orden cronológico del panel). */
  firstIndex: number;
  /** ¿Aparece en algún chunk visible en el viewport ahora mismo? */
  inFocus: boolean;
}

const MIN_FRAGMENT_LEN = 4; // evita fusionar palabras muy cortas

/**
 * ¿La forma `a` es una variante contenida en la forma más larga `b`?
 * ("samsa" ⊂ "gregorio samsa"). Solo cuando `b` es estrictamente más larga.
 */
function isFragmentOf(a: string, b: string): boolean {
  return a.length >= MIN_FRAGMENT_LEN && b.length > a.length && b.includes(a);
}

/**
 * Canonicaliza las variantes de UNA categoría con GUARDIA DE AMBIGÜEDAD.
 *
 * Guardia interina (2026-07-12): el backend emite fragmentos ambiguos como
 * "Samsa" a secas, contenido en 3 personajes distintos ("Gregorio Samsa",
 * "señor Samsa", "señora Samsa"). La fusión ingenua lo pegaba al primero y lo
 * atribuía mal (bug reportado por Giano). Regla:
 *   - fragmento contenido en 0 formas más largas → entidad propia (canónica).
 *   - contenido en EXACTAMENTE 1 → se fusiona en ella (variante inequívoca).
 *   - contenido en 2+ → AMBIGUO: se descarta (no se muestra ni se atribuye).
 * El arreglo de raíz es del backend (canonicalización con contexto); mientras,
 * esta guardia evita la atribución errónea. Al canonicalizar el backend, esta
 * lógica se elimina por completo.
 */
function canonicalize(forms: Map<string, ElementItem>): ElementItem[] {
  const lows = [...forms.keys()];
  const containersOf = (f: string) => lows.filter((g) => isFragmentOf(f, g));

  // Las formas sin contenedor son canónicas (los nombres completos).
  const canonical = new Map<string, ElementItem>();
  for (const low of lows) {
    if (containersOf(low).length === 0) canonical.set(low, { ...forms.get(low)! });
  }

  // Los fragmentos se fusionan solo si son inequívocos (un único contenedor).
  for (const low of lows) {
    const containers = containersOf(low);
    if (containers.length !== 1) continue; // 0 = ya canónica · 2+ = ambigua, se descarta
    const target = canonical.get(containers[0]);
    const frag = forms.get(low)!;
    if (target) {
      target.firstIndex = Math.min(target.firstIndex, frag.firstIndex);
      target.inFocus = target.inFocus || frag.inFocus;
    }
  }

  return [...canonical.values()];
}

function aggregate(
  elements: Record<string, ChunkElements>,
  maxIndex: number,
  focusIndexes: Set<number>,
): Record<CategoryKey, ElementItem[]> {
  const visible = Object.values(elements)
    .filter((e) => e.chunk_index <= maxIndex)
    .sort((a, b) => a.chunk_index - b.chunk_index);

  const result = {} as Record<CategoryKey, ElementItem[]>;
  for (const { key } of CATEGORIES) {
    // Formas distintas de la categoría (case-insensitive), con sus stats.
    const forms = new Map<string, ElementItem>();
    for (const entry of visible) {
      const inFocus = focusIndexes.has(entry.chunk_index);
      for (const raw of entry[key] ?? []) {
        const low = raw.toLowerCase();
        const cur = forms.get(low);
        if (cur) {
          cur.firstIndex = Math.min(cur.firstIndex, entry.chunk_index);
          cur.inFocus = cur.inFocus || inFocus;
        } else {
          forms.set(low, { label: raw, firstIndex: entry.chunk_index, inFocus });
        }
      }
    }
    result[key] = canonicalize(forms);
  }
  return result;
}

interface Props {
  elements: Record<string, ChunkElements> | undefined;
  readingState: ReadingState;
}

export function ElementsPanel({ elements, readingState }: Props) {
  const [open, setOpen] = useState(true);
  // Tooltip propio (posición fija): el `title` nativo tarda ~1s en salir, lo
  // que arruina el "pasa el ratón y sabes el tipo". Este aparece al instante y
  // no lo recorta el overflow del panel.
  const [tip, setTip] = useState<{ text: string; x: number; y: number } | null>(null);

  const focusKey = readingState.focus_chunk_ids.join(",");
  const byCategory = useMemo(() => {
    if (!elements) return null;
    const focusIndexes = new Set<number>();
    for (const id of readingState.focus_chunk_ids) {
      const n = chunkIndexOf(id);
      if (n !== null) focusIndexes.add(n);
    }
    return aggregate(elements, readingState.max_progress_chunk_index, focusIndexes);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [elements, readingState.max_progress_chunk_index, focusKey]);

  // Libro sin anotar: el panel no existe (no un panel vacío permanente).
  if (!byCategory) return null;

  // Nube única: todos los chips juntos (ordenados por primera aparición). El
  // tipo (Personaje/Lugar) lo dan el ícono y el tooltip, no un encabezado de
  // sección — ocupa la mitad del alto (pedido de Giano, 2026-07-12).
  const items = CATEGORIES.flatMap(({ key, icon, label }) =>
    byCategory[key].map((it) => ({ ...it, icon, category: label })),
  ).sort((a, b) => a.firstIndex - b.firstIndex);

  return (
    <section className="elements-panel" aria-label="Elementos de la historia">
      <button
        type="button"
        className="elements-header"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        <span className="elements-title">📖 Elementos de la historia</span>
        <span className="elements-count">
          {items.length > 0 ? items.length : "—"} {open ? "▾" : "▸"}
        </span>
      </button>

      {open && (
        <div className="elements-body">
          {items.length === 0 ? (
            <p className="elements-empty">
              Los personajes y lugares irán apareciendo aquí a medida que
              avances en la lectura.
            </p>
          ) : (
            <ul className="elements-cloud">
              {items.map((item) => (
                <li
                  key={`${item.category}:${item.label}`}
                  className={`element-chip${item.inFocus ? " in-focus" : ""}`}
                  onMouseEnter={(e) => {
                    const r = e.currentTarget.getBoundingClientRect();
                    setTip({
                      text: `${item.category}${
                        item.inFocus ? " · aparece en lo que lees" : ""
                      }`,
                      x: r.left + r.width / 2,
                      y: r.top,
                    });
                  }}
                  onMouseLeave={() => setTip(null)}
                >
                  <span aria-hidden="true">{item.icon}</span> {item.label}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {tip && (
        <div className="chip-tip" style={{ left: tip.x, top: tip.y }} role="tooltip">
          {tip.text}
        </div>
      )}
    </section>
  );
}
