/**
 * Chat del compañero de lectura.
 *
 * Es dueño del agent_state (backend stateless): acumula history (máx 5 pares),
 * reenvía clarify_count cuando el router pide aclarar (maña #3) y lo reinicia
 * tras una interacción exitosa. El reading_state llega por props desde el
 * tracker de scroll. Sin timeout: el QA-RAG real tarda ~90s (maña #2).
 */
import { useEffect, useRef, useState } from "react";
import { fetchImageObjectUrl, pollImageJob, streamChat } from "../api/client";
import type { AgentState, Citation, ReadingState } from "../api/types";
import { emptyAgentState } from "../api/types";

const MAX_HISTORY = 10; // 5 pares user/assistant, igual que el backend

/**
 * Interino (2026-07-13): cuando el QA-RAG no responde porque el anti-spoiler
 * filtró TODOS los chunks (el alumno pregunta por algo que aún no ha leído),
 * el backend manda este texto técnico (orchestrator.py, rama `if not filtered`).
 * Lo detectamos por una parte distintiva del mensaje —"suficiente contexto"—
 * que NO aparece en el otro "sin resultados" ("no encontré fragmentos
 * relevantes"), y lo reemplazamos por algo amable y con intención pedagógica.
 *
 * Acoplamiento FRÁGIL a propósito: si el backend cambia el texto, degradamos
 * a mostrar el mensaje original (no rompe). El fix robusto es que el backend
 * mande una señal explícita (p. ej. `reason: "anti_spoiler"` en `citations`);
 * pedido en el handoff. El mensaje amable tiene valor permanente (siempre
 * habrá preguntas legítimamente bloqueadas por anti-spoiler).
 */
const ANTI_SPOILER_HINT = "suficiente contexto";
const SPOILER_FRIENDLY = "Sigue leyendo y lo descubrirás… ¡no quiero hacerte spoiler! 📖";

interface ChatItem {
  id: number;
  kind: "user" | "assistant" | "system" | "image";
  text: string;
  citations?: Citation[];
  imageUrl?: string | null;
  imageError?: string | null;
}

interface Props {
  bookId: string;
  readingState: ReadingState;
  /** Al llegar citas se resaltan; con scroll=true navega (a target si viene). */
  onCitations: (citations: Citation[], scrollToSource: boolean, target?: Citation) => void;
  /** Checkpoint alcanzado: la pregunta del profe se despliega en el chat. */
  checkpoint: { id: string; question: string } | null;
  /** El alumno saltó este checkpoint desde el gate: bajar pending_question. */
  skippedCheckpointId: string | null;
  /** La pregunta pendiente fue respondida (stream exitoso): libera el gate. */
  onQuestionAnswered: (checkpointId: string) => void;
}

export function ChatPanel({
  bookId,
  readingState,
  onCitations,
  checkpoint,
  skippedCheckpointId,
  onQuestionAnswered,
}: Props) {
  const [items, setItems] = useState<ChatItem[]>([]);
  const [input, setInput] = useState("");
  const [phase, setPhase] = useState<"idle" | "thinking" | "streaming">("idle");
  const agentStateRef = useRef<AgentState>(emptyAgentState());
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const lastCheckpointId = useRef<string | null>(null);
  const nextIdRef = useRef(1); // ref y no módulo: sobrevive HMR sin colisionar ids
  // Object URLs de las imágenes ya pintadas (maña #9): se liberan al desmontar.
  const objectUrls = useRef<string[]>([]);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [items, phase]);

  useEffect(
    () => () => {
      for (const url of objectUrls.current) URL.revokeObjectURL(url);
      objectUrls.current = [];
    },
    [],
  );

  // Auto-grow del textarea: crece con el texto hasta el max-height del CSS,
  // y vuelve a una línea cuando se limpia (tras enviar).
  useEffect(() => {
    const ta = inputRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${ta.scrollHeight}px`;
  }, [input]);

  // Checkpoint alcanzado → la pregunta entra al chat y la próxima respuesta
  // del alumno viaja con pending_question=true (flujo de EVALUACIÓN).
  useEffect(() => {
    if (!checkpoint || checkpoint.id === lastCheckpointId.current) return;
    lastCheckpointId.current = checkpoint.id;
    agentStateRef.current = {
      ...agentStateRef.current,
      pending_question: true,
      pending_question_text: checkpoint.question,
    };
    push({ kind: "assistant", text: `📋 Pregunta de comprensión:\n${checkpoint.question}` });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [checkpoint]);

  // El alumno saltó la pregunta desde el gate: bajar el flag para que su
  // próximo mensaje NO se enrute a evaluación, y confirmárselo en el chat.
  useEffect(() => {
    if (!skippedCheckpointId || skippedCheckpointId !== lastCheckpointId.current) return;
    if (!agentStateRef.current.pending_question) return;
    agentStateRef.current = {
      ...agentStateRef.current,
      pending_question: false,
      pending_question_text: "",
    };
    push({ kind: "system", text: "Saltaste la pregunta de esta sección. ¡Sigue leyendo! 📖" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [skippedCheckpointId]);

  const push = (item: Omit<ChatItem, "id">): number => {
    const id = nextIdRef.current++;
    setItems((prev) => [...prev, { ...item, id }]);
    return id;
  };
  const patch = (id: number, p: Partial<ChatItem>) =>
    setItems((prev) => prev.map((it) => (it.id === id ? { ...it, ...p } : it)));

  async function send() {
    const message = input.trim();
    if (!message || phase !== "idle") return;
    setInput("");
    setPhase("thinking");
    push({ kind: "user", text: message });

    // Captura ANTES del stream: si un checkpoint dispara pending_question
    // mientras este stream corre, el reset de abajo no debe tragárselo.
    const wasPending = agentStateRef.current.pending_question;
    const pendingTextAtSend = agentStateRef.current.pending_question_text;

    let assistantId: number | null = null;
    let assistantText = "";

    try {
      await streamChat(
        {
          book_id: bookId,
          message,
          agent_state: agentStateRef.current,
          reading_state: readingState,
        },
        (ev) => {
          switch (ev.event) {
            case "token":
              setPhase("streaming");
              assistantText += ev.data.delta;
              if (assistantId === null) {
                assistantId = push({ kind: "assistant", text: assistantText });
              } else {
                patch(assistantId, { text: assistantText });
              }
              break;
            case "citations":
              if (assistantId !== null && ev.data.citations.length > 0) {
                patch(assistantId, { citations: ev.data.citations });
                onCitations(ev.data.citations, false); // resalta sin mover el scroll
              } else if (
                assistantId !== null &&
                !ev.data.answered &&
                assistantText.includes(ANTI_SPOILER_HINT)
              ) {
                // El anti-spoiler filtró todo → mensaje amable en vez del técnico.
                patch(assistantId, { text: SPOILER_FRIENDLY });
              }
              break;
            case "clarify":
              // Maña #3: reenviar este conteo o el router pide aclarar por
              // siempre. El clarify no toca history: el próximo turno resuelve.
              agentStateRef.current = {
                ...agentStateRef.current,
                clarify_count: ev.data.clarify_count,
              };
              push({ kind: "assistant", text: ev.data.clarification });
              break;
            case "image_job": {
              const imgId = push({ kind: "image", text: "Generando la ilustración…" });
              void (async () => {
                const job = await pollImageJob(ev.data.poll_url);
                if (job.status !== "done" || !job.image_url) {
                  patch(imgId, {
                    text: "",
                    imageError: job.error ?? "La imagen no se pudo generar.",
                  });
                  return;
                }
                // Maña #9: el <img> no puede mandar el header de ngrok, así que
                // bajamos los bytes por fetch y pintamos desde un blob local.
                const objectUrl = await fetchImageObjectUrl(job.image_url);
                objectUrls.current.push(objectUrl);
                patch(imgId, { text: "", imageUrl: objectUrl });
              })().catch((err: Error) =>
                patch(imgId, { text: "", imageError: err.message }),
              );
              break;
            }
            case "notice":
              push({ kind: "system", text: ev.data.message });
              break;
            case "error":
              push({ kind: "system", text: `Algo salió mal: ${ev.data.message}` });
              break;
          }
        },
      );

      if (assistantText) {
        // Interacción exitosa: history al día y clarify_count a 0.
        const history = [
          ...agentStateRef.current.history,
          { role: "user" as const, content: message },
          { role: "assistant" as const, content: assistantText },
        ].slice(-MAX_HISTORY);
        agentStateRef.current = { ...agentStateRef.current, history, clarify_count: 0 };
      }
      // La pregunta de evaluación se responde una sola vez: si ESTE mensaje
      // viajó con pending_question y ningún checkpoint nuevo la reemplazó
      // durante el stream, el flag baja y el gate de lectura se libera. Si el
      // fetch falló (catch), se conserva para reintentar.
      if (wasPending && agentStateRef.current.pending_question_text === pendingTextAtSend) {
        agentStateRef.current = {
          ...agentStateRef.current,
          pending_question: false,
          pending_question_text: "",
        };
        if (lastCheckpointId.current) onQuestionAnswered(lastCheckpointId.current);
      }
    } catch (err) {
      push({
        kind: "system",
        text: `No pude contactar al backend: ${err instanceof Error ? err.message : String(err)}`,
      });
    } finally {
      setPhase("idle");
    }
  }

  return (
    <aside className="chat">
      <div className="chat-messages" ref={listRef}>
        {items.length === 0 && (
          <p className="chat-hint">
            Pregunta sobre lo que estás leyendo, o pide "dibújame esto".
          </p>
        )}
        {items.map((item) => (
          <ChatBubble key={item.id} item={item} onCitations={onCitations} />
        ))}
        {phase === "thinking" && (
          <div className="msg assistant thinking">Pensando…</div>
        )}
      </div>
      <form
        className="chat-input"
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
      >
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            // Enter envía; Shift+Enter inserta salto de línea para revisar
            // preguntas largas antes de mandarlas.
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
          placeholder="Escribe tu pregunta…  (Enter envía · Shift+Enter salta de línea)"
          rows={1}
          disabled={phase !== "idle"}
        />
        <button type="submit" disabled={phase !== "idle" || !input.trim()}>
          Enviar
        </button>
      </form>
    </aside>
  );
}

function ChatBubble({
  item,
  onCitations,
}: {
  item: ChatItem;
  onCitations: (citations: Citation[], scrollToSource: boolean, target?: Citation) => void;
}) {
  if (item.kind === "image") {
    if (item.imageError) return <div className="msg system">🖼️ {item.imageError}</div>;
    if (item.imageUrl) {
      return (
        <div className="msg assistant msg-image">
          <img src={item.imageUrl} alt="Ilustración generada del fragmento" />
        </div>
      );
    }
    return <div className="msg assistant thinking">🖌️ {item.text}</div>;
  }

  return (
    <div className={`msg ${item.kind}`}>
      {item.text}
      {item.citations && (
        <div className="msg-citations">
          <span>📖 Fuentes:</span>
          {item.citations.map((c, i) => (
            <button
              key={`${c.chunk_id}-${c.char_start}-${i}`}
              type="button"
              title="Ir al pasaje en el texto"
              onClick={() => onCitations(item.citations!, true, c)}
            >
              {i + 1}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
