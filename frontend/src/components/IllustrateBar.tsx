/**
 * Botones de ilustración por scope (handoff §6): cada botón mapea a un scope
 * del backend y arma los campos que ese scope exige. El flag `mock` no se
 * envía: rige el default del server (en dev, SVG placeholder). Cuando el
 * equipo quiera imagen real se añade un toggle que mande mock:false explícito.
 */
import { useMemo, useRef, useState } from "react";
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
  // Posición arrastrada de la ventana; null = ancla por defecto (abajo-derecha,
  // vía CSS). Se puede mover para no tapar el chat mientras se lee/responde.
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  const dragRef = useRef<{ dx: number; dy: number } | null>(null);

  function onDragStart(e: React.PointerEvent<HTMLElement>) {
    if ((e.target as HTMLElement).closest("button")) return; // no arrastrar al cerrar
    const cardEl = e.currentTarget.parentElement as HTMLElement;
    const rect = cardEl.getBoundingClientRect();
    dragRef.current = { dx: e.clientX - rect.left, dy: e.clientY - rect.top };
    setPos({ x: rect.left, y: rect.top }); // fija en su sitio actual sin saltar
    e.currentTarget.setPointerCapture(e.pointerId);
  }
  function onDragMove(e: React.PointerEvent<HTMLElement>) {
    const d = dragRef.current;
    if (!d) return;
    setPos({
      x: Math.max(4, Math.min(e.clientX - d.dx, window.innerWidth - 80)),
      y: Math.max(4, Math.min(e.clientY - d.dy, window.innerHeight - 40)),
    });
  }
  function onDragEnd(e: React.PointerEvent<HTMLElement>) {
    dragRef.current = null;
    e.currentTarget.releasePointerCapture(e.pointerId);
  }

  // Sección de cada chunk: NO son capítulos. Son tramos anotados por el
  // profesor y cada BANDERA marca el fin de uno (aclarado por el equipo,
  // 2026-07-11). Una sección = chunks entre banderas.
  const sectionOfChunk = useMemo(() => {
    const map = new Map<string, number>();
    let section = 0;
    for (const b of blocks) {
      if (b.type === "BANDERA") {
        section += 1;
        continue;
      }
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
          title="Dibuja lo que tienes en pantalla en este momento"
          onClick={() => void illustrate("lo que veo", { book_id: bookId, scope: "vista", chunk_ids: focus })}
        >
          lo que veo
        </button>
        <button
          disabled={busy || currentSectionChunks.length === 0}
          title="Dibuja la sección que estás leyendo (los tramos marcados en la obra)"
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
          title="Dibuja un resumen de todo lo que has leído hasta ahora"
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
          title="Dibuja el libro completo (¡cuidado: puede adelantarte cosas que aún no lees!)"
          onClick={() => void illustrate("toda la obra", { book_id: bookId, scope: "obra" })}
        >
          toda la obra
        </button>
      </div>

      {card && (
        <div
          className="illustration-card"
          style={
            pos
              ? { left: pos.x, top: pos.y, right: "auto", bottom: "auto" }
              : undefined
          }
        >
          <header
            className="illustration-drag"
            onPointerDown={onDragStart}
            onPointerMove={onDragMove}
            onPointerUp={onDragEnd}
            title="Arrastra para mover la ventana"
          >
            <span>⠿ Ilustración: {card.label}</span>
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
