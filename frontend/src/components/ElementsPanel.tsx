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

const CATEGORIES = [
  { key: "personajes", icon: "👤", label: "Personajes" },
  { key: "lugares", icon: "📍", label: "Lugares" },
  { key: "objetos_simbolos", icon: "🗝️", label: "Objetos y símbolos" },
  { key: "temas", icon: "💭", label: "Temas" },
  { key: "emociones", icon: "🎭", label: "Emociones" },
] as const;

type CategoryKey = (typeof CATEGORIES)[number]["key"];

interface ElementItem {
  label: string;
  /** Chunk donde apareció por primera vez (orden cronológico del panel). */
  firstIndex: number;
  /** ¿Aparece en algún chunk visible en el viewport ahora mismo? */
  inFocus: boolean;
}

/**
 * Fusiona variantes del mismo elemento entre chunks: mismo texto (case-
 * insensitive) o una variante contenida en otra ("Gregorio" ⊂ "Gregorio
 * Samsa") se quedan con la forma MÁS LARGA y el primer índice de aparición.
 * El mínimo de 4 letras evita fusiones accidentales de palabras cortas.
 */
function addItem(items: ElementItem[], label: string, index: number, inFocus: boolean) {
  const low = label.toLowerCase();
  for (const item of items) {
    const itemLow = item.label.toLowerCase();
    const contained =
      itemLow === low ||
      (low.length >= 4 && itemLow.includes(low)) ||
      (itemLow.length >= 4 && low.includes(itemLow));
    if (contained) {
      if (label.length > item.label.length) item.label = label;
      item.firstIndex = Math.min(item.firstIndex, index);
      item.inFocus = item.inFocus || inFocus;
      return;
    }
  }
  items.push({ label, firstIndex: index, inFocus });
}

function aggregate(
  elements: Record<string, ChunkElements>,
  maxIndex: number,
  focusIndexes: Set<number>,
): Record<CategoryKey, ElementItem[]> {
  const result = Object.fromEntries(
    CATEGORIES.map((c) => [c.key, [] as ElementItem[]]),
  ) as Record<CategoryKey, ElementItem[]>;

  const visible = Object.values(elements)
    .filter((e) => e.chunk_index <= maxIndex)
    .sort((a, b) => a.chunk_index - b.chunk_index);

  for (const entry of visible) {
    const inFocus = focusIndexes.has(entry.chunk_index);
    for (const { key } of CATEGORIES) {
      for (const label of entry[key] ?? []) {
        addItem(result[key], label, entry.chunk_index, inFocus);
      }
    }
  }
  return result;
}

interface Props {
  elements: Record<string, ChunkElements> | undefined;
  readingState: ReadingState;
}

export function ElementsPanel({ elements, readingState }: Props) {
  const [open, setOpen] = useState(true);

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

  const total = CATEGORIES.reduce((n, c) => n + byCategory[c.key].length, 0);

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
          {total > 0 ? total : "—"} {open ? "▾" : "▸"}
        </span>
      </button>

      {open && (
        <div className="elements-body">
          {total === 0 ? (
            <p className="elements-empty">
              Los personajes, lugares y temas irán apareciendo aquí a medida
              que avances en la lectura.
            </p>
          ) : (
            CATEGORIES.map(({ key, icon, label }) => {
              const items = byCategory[key];
              if (items.length === 0) return null;
              return (
                <div key={key} className="elements-category">
                  <h3>
                    <span aria-hidden="true">{icon}</span> {label}
                    <small>{items.length}</small>
                  </h3>
                  <ul>
                    {items.map((item) => (
                      <li
                        key={item.label}
                        className={`element-chip${item.inFocus ? " in-focus" : ""}`}
                        title={
                          item.inFocus
                            ? "Aparece en lo que estás leyendo ahora"
                            : `Apareció por primera vez cerca del chunk ${item.firstIndex}`
                        }
                      >
                        {item.label}
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })
          )}
        </div>
      )}
    </section>
  );
}
