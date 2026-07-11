import { memo, useEffect, useState } from "react";
import { getReader } from "../api/client";
import type { ReaderBlock, ReaderResponse } from "../api/types";
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

export function ReaderView({ bookId, onBack }: Props) {
  const [state, setState] = useState<ReaderState>({ status: "loading" });
  const { readingState, observeBlock } = useReadingTracker();

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
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

  const { metadata, blocks } = state.reader;
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
        <BlockList blocks={blocks} observeBlock={observeBlock} />
        <ChatPanel bookId={bookId} readingState={readingState} />
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

/** Memoizado: el texto no se re-renderiza con cada actualización del tracking. */
const BlockList = memo(function BlockList({
  blocks,
  observeBlock,
}: {
  blocks: ReaderBlock[];
  observeBlock: (block: ReaderBlock) => (el: HTMLElement | null) => void;
}) {
  return (
    <article className="reader-text">
      {blocks.map((block) => (
        <Block key={block.id_block} block={block} observeBlock={observeBlock} />
      ))}
    </article>
  );
});

function Block({
  block,
  observeBlock,
}: {
  block: ReaderBlock;
  observeBlock: (block: ReaderBlock) => (el: HTMLElement | null) => void;
}) {
  if (block.type === "BANDERA") {
    // Checkpoint pedagógico: no es texto (handoff §3). La interacción real
    // llegará con la tool de EVALUACIÓN; por ahora, una pausa visual.
    return (
      <aside className="checkpoint">
        ✋ Pausa de lectura — aquí irá una pregunta de comprensión.
      </aside>
    );
  }

  const ref = observeBlock(block);
  const muted = block.is_narrative ? "" : " paratext";

  switch (block.type) {
    case "h1":
      return <h1 ref={ref} className={`block${muted}`}>{block.text}</h1>;
    case "h2":
      return <h2 ref={ref} className={`block${muted}`}>{block.text}</h2>;
    case "h3":
      return <h3 ref={ref} className={`block${muted}`}>{block.text}</h3>;
    default:
      return <p ref={ref} className={`block${muted}`}>{block.text}</p>;
  }
}
