import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getReader } from "../api/client";
import type { Citation, ReaderBlock, ReaderResponse } from "../api/types";
import { checkpointQuestion, chunkIndexOf } from "../api/types";
import { TOP_OFFSET, useReadingTracker } from "../hooks/useReadingTracker";
import { ChatPanel } from "./ChatPanel";
import { ElementsPanel } from "./ElementsPanel";
import { IllustrateBar } from "./IllustrateBar";

export interface CheckpointPrompt {
  id: string;
  question: string;
}

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
  const [checkpoint, setCheckpoint] = useState<CheckpointPrompt | null>(null);
  // Checkpoints resueltos (respondidos en el chat o saltados por el alumno).
  const [cleared, setCleared] = useState<ReadonlySet<string>>(new Set());
  const [skippedId, setSkippedId] = useState<string | null>(null);
  const { readingState, observeBlock } = useReadingTracker();

  // La pregunta se gatilla cuando la BANDERA está CASI ARRIBA del viewport
  // (sección realmente terminada), no apenas asoma por abajo: la zona de
  // intersección es solo la franja superior (35%) bajo el header.
  const checkpointObserver = useRef<IntersectionObserver | null>(null);
  const checkpointEls = useRef(new Map<Element, CheckpointPrompt>());
  const firedCheckpoints = useRef(new Set<string>());

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const prompt = checkpointEls.current.get(entry.target);
          if (!prompt || firedCheckpoints.current.has(prompt.id)) continue;
          firedCheckpoints.current.add(prompt.id);
          setCheckpoint(prompt);
        }
      },
      { threshold: 0, rootMargin: `-${TOP_OFFSET}px 0px -65% 0px` },
    );
    checkpointObserver.current = observer;
    for (const el of checkpointEls.current.keys()) observer.observe(el);
    return () => {
      observer.disconnect();
      checkpointObserver.current = null;
    };
  }, []);

  const observeCheckpoint = useCallback(
    (block: ReaderBlock) => (el: HTMLElement | null) => {
      const question = checkpointQuestion(block);
      if (el && question) {
        checkpointEls.current.set(el, { id: block.id_block, question });
        checkpointObserver.current?.observe(el);
      }
    },
    [],
  );

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    setCitations([]);
    setCheckpoint(null);
    setCleared(new Set());
    setSkippedId(null);
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

  // Gate anti scroll-dump: el texto se corta en el primer checkpoint con
  // pregunta sin resolver. El alumno responde en el chat o lo salta; recién
  // ahí se revela la siguiente sección (y sus preguntas).
  const { visibleBlocks, activeGateId } = useMemo(() => {
    const idx = blocks.findIndex(
      (b) => checkpointQuestion(b) !== null && !cleared.has(b.id_block),
    );
    if (idx === -1) return { visibleBlocks: blocks, activeGateId: null };
    return { visibleBlocks: blocks.slice(0, idx + 1), activeGateId: blocks[idx].id_block };
  }, [blocks, cleared]);

  // El gate muestra el prompt de saltar solo cuando su pregunta ya se disparó.
  const gateFired = activeGateId !== null && checkpoint?.id === activeGateId;

  const clearGate = useCallback((id: string) => {
    setCleared((prev) => new Set(prev).add(id));
  }, []);

  const handleSkip = useCallback(
    (id: string) => {
      clearGate(id);
      setSkippedId(id); // ChatPanel baja pending_question y avisa al alumno
    },
    [clearGate],
  );

  const handleAnswered = useCallback(
    (checkpointId: string) => {
      clearGate(checkpointId);
    },
    [clearGate],
  );

  const handleCitations = useCallback(
    (cits: Citation[], scrollToSource: boolean, target?: Citation) => {
      setCitations(cits);
      if (!scrollToSource) return;
      const wanted = target ? [target] : cits;
      const block = blocks.find((b) => isCited(b, wanted));
      if (block) {
        document
          .getElementById(block.id_block)
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
        <BlockList
          blocks={visibleBlocks}
          observeBlock={observeBlock}
          observeCheckpoint={observeCheckpoint}
          citations={citations}
          activeGateId={activeGateId}
          gateFired={gateFired}
          onSkip={handleSkip}
        />
        <div className="reader-side">
          <ElementsPanel
            elements={state.reader.chunk_elements}
            readingState={readingState}
          />
          <ChatPanel
            bookId={bookId}
            readingState={readingState}
            onCitations={handleCitations}
            checkpoint={checkpoint}
            skippedCheckpointId={skippedId}
            onQuestionAnswered={handleAnswered}
          />
        </div>
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

/** Memoizado: el texto solo se re-renderiza si cambian bloques, citas o gate. */
const BlockList = memo(function BlockList({
  blocks,
  observeBlock,
  observeCheckpoint,
  citations,
  activeGateId,
  gateFired,
  onSkip,
}: {
  blocks: ReaderBlock[];
  observeBlock: (block: ReaderBlock) => (el: HTMLElement | null) => void;
  observeCheckpoint: (block: ReaderBlock) => (el: HTMLElement | null) => void;
  citations: Citation[];
  activeGateId: string | null;
  gateFired: boolean;
  onSkip: (id: string) => void;
}) {
  return (
    <article className="reader-text">
      {blocks.map((block) => (
        <Block
          key={block.id_block}
          block={block}
          observeBlock={observeBlock}
          observeCheckpoint={observeCheckpoint}
          cited={isCited(block, citations)}
          isActiveGate={block.id_block === activeGateId}
          gateFired={gateFired}
          onSkip={onSkip}
        />
      ))}
      {/* Espaciador bajo el gate: permite que la bandera llegue casi arriba
          (donde se dispara la pregunta) aunque sea el último elemento. */}
      {activeGateId !== null && <div className="gate-spacer" aria-hidden="true" />}
    </article>
  );
});

function Block({
  block,
  observeBlock,
  observeCheckpoint,
  cited,
  isActiveGate,
  gateFired,
  onSkip,
}: {
  block: ReaderBlock;
  observeBlock: (block: ReaderBlock) => (el: HTMLElement | null) => void;
  observeCheckpoint: (block: ReaderBlock) => (el: HTMLElement | null) => void;
  cited: boolean;
  isActiveGate: boolean;
  gateFired: boolean;
  onSkip: (id: string) => void;
}) {
  if (block.type === "BANDERA") {
    const hasQuestion = checkpointQuestion(block) !== null;
    if (!hasQuestion) {
      return <aside className="checkpoint">✋ Pausa de lectura.</aside>;
    }
    return (
      <aside ref={observeCheckpoint(block)} className="checkpoint checkpoint-gate">
        {isActiveGate && gateFired ? (
          <>
            <p>
              ✋ Hay una pregunta de comprensión esperándote en el chat. ¿Deseas
              saltarla y seguir leyendo?
            </p>
            <div className="gate-actions">
              <button onClick={() => onSkip(block.id_block)}>Sí, seguir leyendo</button>
              <button
                className="gate-primary"
                onClick={() =>
                  document
                    .querySelector<HTMLTextAreaElement>(".chat-input textarea")
                    ?.focus()
                }
              >
                No, la responderé en el chat 👉
              </button>
            </div>
          </>
        ) : (
          "✋ Fin de la sección — al terminar de leerla aparecerá una pregunta en el chat."
        )}
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
