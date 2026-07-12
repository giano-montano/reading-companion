import { memo, useCallback, useEffect, useState } from "react";
import { getReader } from "../api/client";
import type { Citation, ReaderBlock, ReaderResponse } from "../api/types";
import { chunkIndexOf } from "../api/types";
import { useReadingTracker } from "../hooks/useReadingTracker";
import { ChatPanel } from "./ChatPanel";
import { IllustrateBar } from "./IllustrateBar";

type ReaderState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; reader: ReaderResponse };

interface Props {
  bookId: string;
  onBack: () => void;
}

/**
 * ¿Este bloque está citado? Mismo chunk y solapamiento de offsets absolutos
 * (contrato: char_start/char_end sobre el texto canónico). Si la cita viene
 * sin rango útil, cae a resaltar el chunk completo.
 */
function isCited(block: ReaderBlock, citations: Citation[]): boolean {
  if (!block.chunk_id) return false;
  return citations.some((c) => {
    if (c.chunk_id !== block.chunk_id) return false;
    if (c.char_end > c.char_start) {
      return block.char_start < c.char_end && block.char_end > c.char_start;
    }
    return true;
  });
}

export function ReaderView({ bookId, onBack }: Props) {
  const [state, setState] = useState<ReaderState>({ status: "loading" });
  const [citations, setCitations] = useState<Citation[]>([]);
  const { readingState, observeBlock } = useReadingTracker();

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    setCitations([]);
    getReader(bookId)
      .then((reader) => {
        if (!cancelled) setState({ status: "ready", reader });
      })
      .catch((err: Error) => {
        if (!cancelled) setState({ status: "error", message: err.message });
      });
    return () => {
      cancelled = true;
    };
  }, [bookId]);

  const blocks = state.status === "ready" ? state.reader.blocks : [];

  const handleCitations = useCallback(
    (cits: Citation[], scrollToSource: boolean) => {
      setCitations(cits);
      if (!scrollToSource) return;
      const target = blocks.find((b) => isCited(b, cits));
      if (target) {
        document
          .getElementById(target.id_block)
          ?.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    },
    [blocks],
  );

  if (state.status === "loading") {
    return <p className="catalog-status">Abriendo el libro…</p>;
  }
  if (state.status === "error") {
    return (
      <p className="catalog-status catalog-error">
        No pude abrir el libro. <small>{state.message}</small>
        <br />
        <button onClick={onBack}>← Volver a la biblioteca</button>
      </p>
    );
  }

  const { metadata } = state.reader;
  return (
    <div className="reader">
      <header className="reader-header">
        <button onClick={onBack}>← Biblioteca</button>
        <div>
          <strong>{metadata.title}</strong> · {metadata.author}
        </div>
        <IllustrateBar bookId={bookId} blocks={blocks} readingState={readingState} />
      </header>

      <div className="reader-layout">
        <BlockList blocks={blocks} observeBlock={observeBlock} citations={citations} />
        <ChatPanel bookId={bookId} readingState={readingState} onCitations={handleCitations} />
      </div>

      {/* Barra de desarrollo: visualiza el estado que viajará al backend. */}
      <footer className="reading-debug">
        <span>
          viendo:{" "}
          {readingState.focus_chunk_ids.length > 0
            ? readingState.focus_chunk_ids.map((id) => chunkIndexOf(id)).join(", ")
            : "—"}
        </span>
        <span>leído hasta el chunk: {readingState.max_progress_chunk_index}</span>
      </footer>
    </div>
  );
}

/** Memoizado: el texto solo se re-renderiza si cambian bloques o citas. */
const BlockList = memo(function BlockList({
  blocks,
  observeBlock,
  citations,
}: {
  blocks: ReaderBlock[];
  observeBlock: (block: ReaderBlock) => (el: HTMLElement | null) => void;
  citations: Citation[];
}) {
  return (
    <article className="reader-text">
      {blocks.map((block) => (
        <Block
          key={block.id_block}
          block={block}
          observeBlock={observeBlock}
          cited={isCited(block, citations)}
        />
      ))}
    </article>
  );
});

function Block({
  block,
  observeBlock,
  cited,
}: {
  block: ReaderBlock;
  observeBlock: (block: ReaderBlock) => (el: HTMLElement | null) => void;
  cited: boolean;
}) {
  if (block.type === "BANDERA") {
    // Checkpoint pedagógico: no es texto (handoff §3). La interacción real
    // llegará cuando el backend implemente la tool de EVALUACIÓN.
    return (
      <aside className="checkpoint">
        ✋ Pausa de lectura — aquí aparecerá una pregunta de comprensión cuando
        la evaluación esté disponible (próximamente).
      </aside>
    );
  }

  const ref = observeBlock(block);
  const cls = `block${block.is_narrative ? "" : " paratext"}${cited ? " cited" : ""}`;
  const chunk = block.chunk_id ?? undefined;

  switch (block.type) {
    case "h1":
      return <h1 id={block.id_block} data-chunk={chunk} ref={ref} className={cls}>{block.text}</h1>;
    case "h2":
      return <h2 id={block.id_block} data-chunk={chunk} ref={ref} className={cls}>{block.text}</h2>;
    case "h3":
      return <h3 id={block.id_block} data-chunk={chunk} ref={ref} className={cls}>{block.text}</h3>;
    default:
      return <p id={block.id_block} data-chunk={chunk} ref={ref} className={cls}>{block.text}</p>;
  }
}
