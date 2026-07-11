/**
 * Chat del compañero de lectura.
 *
 * Es dueño del agent_state (backend stateless): acumula history (máx 5 pares),
 * reenvía clarify_count cuando el router pide aclarar (maña #3) y lo reinicia
 * tras una interacción exitosa. El reading_state llega por props desde el
 * tracker de scroll. Sin timeout: el QA-RAG real tarda ~90s (maña #2).
 */
import { useEffect, useRef, useState } from "react";
import { pollImageJob, streamChat } from "../api/client";
import type { AgentState, Citation, ReadingState } from "../api/types";
import { chunkIndexOf, emptyAgentState } from "../api/types";

const MAX_HISTORY = 10; // 5 pares user/assistant, igual que el backend

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
}

let nextId = 1;

export function ChatPanel({ bookId, readingState }: Props) {
  const [items, setItems] = useState<ChatItem[]>([]);
  const [input, setInput] = useState("");
  const [phase, setPhase] = useState<"idle" | "thinking" | "streaming">("idle");
  const agentStateRef = useRef<AgentState>(emptyAgentState());
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [items, phase]);

  const push = (item: Omit<ChatItem, "id">): number => {
    const id = nextId++;
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

    let assistantId: number | null = null;
    let assistantText = "";
    let gotClarify = false;

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
              }
              break;
            case "clarify":
              // Maña #3: reenviar este conteo o el router pide aclarar por siempre.
              gotClarify = true;
              agentStateRef.current = {
                ...agentStateRef.current,
                clarify_count: ev.data.clarify_count,
              };
              push({ kind: "assistant", text: ev.data.clarification });
              break;
            case "image_job": {
              const imgId = push({ kind: "image", text: "Generando la ilustración…" });
              void pollImageJob(ev.data.poll_url)
                .then((job) =>
                  patch(
                    imgId,
                    job.status === "done"
                      ? { text: "", imageUrl: job.image_url }
                      : { text: "", imageError: job.error ?? "La imagen no se pudo generar." },
                  ),
                )
                .catch((err: Error) => patch(imgId, { text: "", imageError: err.message }));
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
    } catch (err) {
      push({
        kind: "system",
        text: `No pude contactar al backend: ${err instanceof Error ? err.message : String(err)}`,
      });
    } finally {
      setPhase("idle");
    }
    void gotClarify; // el clarify no toca history: el próximo turno lo resuelve
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
          <ChatBubble key={item.id} item={item} />
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
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Escribe tu pregunta…"
          disabled={phase !== "idle"}
        />
        <button type="submit" disabled={phase !== "idle" || !input.trim()}>
          Enviar
        </button>
      </form>
    </aside>
  );
}

function ChatBubble({ item }: { item: ChatItem }) {
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
          Fuentes: chunk {item.citations.map((c) => chunkIndexOf(c.chunk_id) ?? "?").join(", ")}
        </div>
      )}
    </div>
  );
}
