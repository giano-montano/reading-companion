/**
 * Tracking de lectura por scroll → los dos valores que el backend necesita
 * en cada request (handoff 2026-07-10 §3 y §5):
 *
 *  - focus_chunk_ids: chunk_ids distintos de los bloques visibles en el
 *    viewport ahora mismo ("lo que veo").
 *  - max_progress_chunk_index: mayor N de ::chunk::N entre los bloques que el
 *    alumno ya dejó atrás (salieron del viewport por arriba). Monótono: nunca
 *    baja. Es el gate anti-spoiler del QA-RAG.
 *
 * Los bloques sin chunk_id (BANDERA, paratexto sin chunk) se ignoran.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import type { ReaderBlock, ReadingState } from "../api/types";
import { chunkIndexOf, emptyReadingState } from "../api/types";

export function useReadingTracker(): {
  readingState: ReadingState;
  /** Ref callback para cada bloque renderizado: observeBlock(block)(el). */
  observeBlock: (block: ReaderBlock) => (el: HTMLElement | null) => void;
} {
  const observerRef = useRef<IntersectionObserver | null>(null);
  const blockByEl = useRef(new Map<Element, ReaderBlock>());
  const visibleEls = useRef(new Set<Element>());
  const [readingState, setReadingState] = useState<ReadingState>(emptyReadingState());

  const handleEntries = useCallback((entries: IntersectionObserverEntry[]) => {
    let maxPassed = 0;
    for (const entry of entries) {
      const block = blockByEl.current.get(entry.target);
      if (!block) continue;
      if (entry.isIntersecting) {
        visibleEls.current.add(entry.target);
      } else {
        visibleEls.current.delete(entry.target);
        // Salió por arriba del viewport → el alumno lo dejó atrás (leído).
        if (entry.boundingClientRect.bottom <= 0) {
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

    setReadingState((prev) => {
      const max = Math.max(prev.max_progress_chunk_index, maxPassed);
      if (
        max === prev.max_progress_chunk_index &&
        focus.length === prev.focus_chunk_ids.length &&
        focus.every((id, i) => id === prev.focus_chunk_ids[i])
      ) {
        return prev; // sin cambios → sin re-render
      }
      return { focus_chunk_ids: focus, max_progress_chunk_index: max };
    });
  }, []);

  // Lazy: los ref callbacks corren antes que los efectos del padre.
  const getObserver = useCallback(() => {
    observerRef.current ??= new IntersectionObserver(handleEntries, { threshold: 0 });
    return observerRef.current;
  }, [handleEntries]);

  const observeBlock = useCallback(
    (block: ReaderBlock) => (el: HTMLElement | null) => {
      if (el) {
        blockByEl.current.set(el, block);
        getObserver().observe(el);
      }
    },
    [getObserver],
  );

  useEffect(
    () => () => {
      observerRef.current?.disconnect();
      blockByEl.current.clear();
      visibleEls.current.clear();
    },
    [],
  );

  return { readingState, observeBlock };
}
