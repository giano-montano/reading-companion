/**
 * Botones de ilustración por scope (handoff §6): cada botón mapea a un scope
 * del backend y arma los campos que ese scope exige. El flag `mock` no se
 * envía: rige el default del server (en dev, SVG placeholder). Cuando el
 * equipo quiera imagen real se añade un toggle que mande mock:false explícito.
 */
import { useMemo, useState } from "react";
import { createImageJob, pollImageJob } from "../api/client";
import type { ImageRequest, ReaderBlock, ReadingState } from "../api/types";

interface Props {
  bookId: string;
  blocks: ReaderBlock[];
  readingState: ReadingState;
}

type Card =
  | null
  | { label: string; status: "pending" }
  | { label: string; status: "done"; url: string }
  | { label: string; status: "error"; error: string };

export function IllustrateBar({ bookId, blocks, readingState }: Props) {
  const [card, setCard] = useState<Card>(null);

  // Sección de cada chunk: se abre una nueva en cada h2 (capítulo).
  const sectionOfChunk = useMemo(() => {
    const map = new Map<string, number>();
    let section = 0;
    for (const b of blocks) {
      if (b.type === "h2") section += 1;
      if (b.chunk_id && !map.has(b.chunk_id)) map.set(b.chunk_id, section);
    }
    return map;
  }, [blocks]);

  const focus = readingState.focus_chunk_ids;
  const currentSection = focus.length > 0 ? (sectionOfChunk.get(focus[0]) ?? 0) : 0;
  const currentSectionChunks = useMemo(
    () =>
      [...sectionOfChunk]
        .filter(([, s]) => s === currentSection)
        .map(([id]) => id),
    [sectionOfChunk, currentSection],
  );

  async function illustrate(label: string, body: ImageRequest) {
    setCard({ label, status: "pending" });
    try {
      const created = await createImageJob(body);
      const job = await pollImageJob(created.poll_url);
      if (job.status === "done" && job.image_url) {
        setCard({ label, status: "done", url: job.image_url });
      } else {
        setCard({ label, status: "error", error: job.error ?? "La imagen no se pudo generar." });
      }
    } catch (err) {
      setCard({
        label,
        status: "error",
        error: err instanceof Error ? err.message : String(err),
      });
    }
  }

  const busy = card?.status === "pending";

  return (
    <>
      <div className="illustrate-bar">
        <span>🖌️ Ilustrar:</span>
        <button
          disabled={busy || focus.length === 0}
          onClick={() => void illustrate("lo que veo", { book_id: bookId, scope: "vista", chunk_ids: focus })}
        >
          lo que veo
        </button>
        <button
          disabled={busy || currentSectionChunks.length === 0}
          onClick={() =>
            void illustrate("esta sección", {
              book_id: bookId,
              scope: "seccion",
              chunk_ids: currentSectionChunks,
            })
          }
        >
          esta sección
        </button>
        <button
          disabled={busy || readingState.max_progress_chunk_index === 0}
          onClick={() =>
            void illustrate("hasta aquí", {
              book_id: bookId,
              scope: "hasta_maximo",
              max_progress_chunk_index: readingState.max_progress_chunk_index,
            })
          }
        >
          hasta aquí
        </button>
        <button
          disabled={busy}
          onClick={() => void illustrate("toda la obra", { book_id: bookId, scope: "obra" })}
        >
          toda la obra
        </button>
      </div>

      {card && (
        <div className="illustration-card">
          <header>
            <span>Ilustración: {card.label}</span>
            <button onClick={() => setCard(null)} aria-label="Cerrar">✕</button>
          </header>
          {card.status === "pending" && <p className="thinking">Generando…</p>}
          {card.status === "error" && <p className="catalog-error">{card.error}</p>}
          {card.status === "done" && (
            <img src={card.url} alt={`Ilustración de ${card.label}`} />
          )}
        </div>
      )}
    </>
  );
}
