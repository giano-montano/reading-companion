/**
 * Tracking de lectura por scroll → los dos valores que el backend necesita
 * en cada request (handoff 2026-07-10 §3 y §5):
 *
 *  - focus_chunk_ids: chunk_ids distintos de los bloques visibles en el
 *    viewport ahora mismo ("lo que veo").
 *  - max_progress_chunk_index: hasta dónde ha llegado el lector = el mayor N
 *    de ::chunk::N entre lo visible ahora y lo ya dejado atrás (semántica
 *    aclarada por el equipo 2026-07-11: "hasta donde leyó", incluye lo que
 *    está en pantalla — el anti-spoiler no debe bloquear texto visible).
 *    Monótono: nunca baja.
 *
 * Calibración: un bloque tapado por el header sticky (TOP_OFFSET) o por la
 * barra de estado inferior (BOTTOM_OFFSET) NO cuenta como visible. "Dejado
 * atrás" = su borde inferior quedó por encima del header.
 *
 * Ciclo de vida: el useEffect es dueño del observer (lo crea, observa todo lo
 * registrado y lo destruye). Los ref callbacks solo registran elementos. Así
 * el tracking sobrevive al desmontaje/remontaje simulado de StrictMode, que
 * antes lo dejaba congelado (bug detectado por Erick el 2026-07-11).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import type { ReaderBlock, ReadingState } from "../api/types";
import { chunkIndexOf, emptyReadingState } from "../api/types";

/** Zona visible real: viewport menos header sticky y barra de estado. */
export const TOP_OFFSET = 64;
export const BOTTOM_OFFSET = 40;

export function useReadingTracker(): {
  readingState: ReadingState;
  /** Ref callback para cada bloque renderizado: observeBlock(block)(el). */
  observeBlock: (block: ReaderBlock) => (el: HTMLElement | null) => void;
} {
  const observerRef = useRef<IntersectionObserver | null>(null);
  const blockByEl = useRef(new Map<Element, ReaderBlock>());
  const visibleEls = useRef(new Set<Element>());
  const [readingState, setReadingState] = useState<ReadingState>(emptyReadingState());

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        let maxPassed = 0;
        for (const entry of entries) {
          const block = blockByEl.current.get(entry.target);
          if (!block) continue;
          if (entry.isIntersecting) {
            visibleEls.current.add(entry.target);
          } else {
            visibleEls.current.delete(entry.target);
            // Salió por arriba (queda sobre el header) → dejado atrás.
            if (entry.boundingClientRect.bottom <= TOP_OFFSET) {
              const idx = chunkIndexOf(block.chunk_id);
              if (idx !== null) maxPassed = Math.max(maxPassed, idx);
            }
          }
        }

        const focus = [
          ...new Set(
            [...visibleEls.current]
              .map((el) => blockByEl.current.get(el)?.chunk_id)
              .filter((id): id is string => id != null),
          ),
        ].sort((a, b) => (chunkIndexOf(a) ?? 0) - (chunkIndexOf(b) ?? 0));

        // "Hasta donde leyó" incluye lo visible: el chunk más alto en pantalla
        // también cuenta como alcanzado.
        const maxVisible = focus.reduce((m, id) => Math.max(m, chunkIndexOf(id) ?? 0), 0);

        setReadingState((prev) => {
          const max = Math.max(prev.max_progress_chunk_index, maxPassed, maxVisible);
          if (
            max === prev.max_progress_chunk_index &&
            focus.length === prev.focus_chunk_ids.length &&
            focus.every((id, i) => id === prev.focus_chunk_ids[i])
          ) {
            return prev; // sin cambios → sin re-render
          }
          return { focus_chunk_ids: focus, max_progress_chunk_index: max };
        });
      },
      // Recorta la zona de intersección: header arriba, barra de estado abajo.
      { threshold: 0, rootMargin: `-${TOP_OFFSET}px 0px -${BOTTOM_OFFSET}px 0px` },
    );

    observerRef.current = observer;
    // Re-observa todo lo ya registrado (StrictMode remonta el efecto,
    // los refs no vuelven a correr).
    for (const el of blockByEl.current.keys()) observer.observe(el);

    return () => {
      observer.disconnect();
      observerRef.current = null;
      visibleEls.current.clear();
    };
  }, []);

  const observeBlock = useCallback(
    (block: ReaderBlock) => (el: HTMLElement | null) => {
      if (el) {
        blockByEl.current.set(el, block);
        observerRef.current?.observe(el);
      }
      // el === null (desmontaje): el effect posee el ciclo de vida; un
      // elemento fuera del DOM no genera intersecciones y no estorba.
    },
    [],
  );

  return { readingState, observeBlock };
}
