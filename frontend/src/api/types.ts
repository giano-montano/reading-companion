/**
 * Contrato de la API del backend (rama dev).
 *
 * Fuente de verdad: agent_log/2026-07-10-handoff-frontend-erick.md y el código
 * en src/companion/api/ + src/companion/agent/. Si el backend cambia un campo,
 * se coordina por handoff — no adivinar aquí.
 */

// --- Catálogo: GET /api/books --------------------------------------------

export interface BookSummary {
  book_id: string;
  title: string;
  author: string;
  publication_year: number | null;
  total_blocks: number;
  narrative_blocks: number;
  non_narrative_blocks: number;
  banderas: number;
}

// --- Reader: GET /api/books/{id}/reader -----------------------------------

/** BANDERA no es texto: es un checkpoint pedagógico (chunk_id null, offsets -1). */
export type BlockType = "h1" | "h2" | "h3" | "p" | "BANDERA";

export interface ReaderBlock {
  id_block: string;
  type: BlockType;
  text: string;
  chunk_id: string | null;
  char_start: number;
  char_end: number;
  is_narrative: boolean;
  /** Preguntas de comprensión del checkpoint (solo en bloques BANDERA). */
  questions?: string[];
}

/**
 * Panel NER: elementos narrativos de UN chunk (clave top-level
 * `chunk_elements` del reader, generada por
 * scripts/extract_narrative_elements.py). Cada entrada solo describe texto
 * ya leído, así que agregar hasta max_progress_chunk_index nunca spoilea.
 */
export interface ChunkElements {
  chunk_index: number;
  personajes: string[];
  lugares: string[];
  objetos_simbolos: string[];
  temas: string[];
  emociones: string[];
}

export interface ReaderResponse {
  book_id: string;
  metadata: {
    title: string;
    author: string;
    publication_year: number | null;
  };
  blocks: ReaderBlock[];
  /** Ausente si el libro aún no fue anotado (hoy: solo la_metamorfosis). */
  chunk_elements?: Record<string, ChunkElements>;
}

// --- Estado que el frontend mantiene y reenvía (backend stateless) ---------

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

export interface AgentState {
  /** Máx. 5 pares (10 mensajes); el backend recorta igual. */
  history: ChatTurn[];
  /** Reenviar el valor del último evento `clarify` o el router se atasca. */
  clarify_count: number;
  /** Reservados para EVALUACIÓN (no implementada). Dejar en false/"". */
  pending_question: boolean;
  pending_question_text: string;
}

export interface ReadingState {
  /** chunk_ids visibles en el viewport ahora mismo (para "lo que veo"). */
  focus_chunk_ids: string[];
  /** Sufijo N más alto de ::chunk::N ya leído. Monótono. Anti-spoiler. */
  max_progress_chunk_index: number;
  // last_completed_section / max_progress_section: eje viejo en desuso;
  // el backend los acepta pero NO deben cablearse (handoff §5).
}

export const emptyAgentState = (): AgentState => ({
  history: [],
  clarify_count: 0,
  pending_question: false,
  pending_question_text: "",
});

export const emptyReadingState = (): ReadingState => ({
  focus_chunk_ids: [],
  max_progress_chunk_index: 0,
});

// --- Chat: POST /api/chat (SSE por POST) -----------------------------------

export interface ChatRequest {
  book_id: string;
  message: string;
  agent_state: AgentState;
  reading_state: ReadingState;
}

export interface Citation {
  chunk_id: string;
  char_start: number;
  char_end: number;
}

/** Vocabulario de eventos del stream (companion/agent/runtime.py). */
export type ChatEvent =
  | { event: "route"; data: { tool: string } }
  | { event: "token"; data: { delta: string } }
  | {
      event: "citations";
      data: { citations: Citation[]; answered: boolean; ok: boolean };
    }
  | { event: "clarify"; data: { clarification: string; clarify_count: number } }
  | { event: "evaluation"; data: { attempt_detected: boolean; ok: boolean } }
  | { event: "image_job"; data: { job_id: string; poll_url: string } }
  | { event: "notice"; data: { tool: string; message: string } }
  | { event: "error"; data: { message: string } }
  | { event: "done"; data: Record<string, never> };

export type ChatEventName = ChatEvent["event"];

// --- Imágenes: POST /api/images + GET /api/images/{job_id} -----------------

export type ImageScope = "vista" | "seccion" | "hasta_maximo" | "obra";

export interface ImageRequest {
  book_id: string;
  scope: ImageScope;
  /** Requerido si scope es vista|seccion. */
  chunk_ids?: string[];
  /** Requerido si scope es hasta_maximo. */
  max_progress_chunk_index?: number;
  title?: string;
  visual_events?: string[];
  width?: number;
  height?: number;
  /** Default backend: 12345 (determinista + cache). Cambiar para variar. */
  seed?: number;
  allow_text_in_image?: boolean;
  /**
   * Tri-estado: true = SVG placeholder gratis; false = fuerza Flux real
   * (lento, cuesta, puede dar 429); ausente = default global del server
   * (en dev suele ser true).
   */
  mock?: boolean;
}

export interface ImageJobCreated {
  job_id: string;
  poll_url: string;
  status: "pending";
}

export type ImageJobState = "pending" | "done" | "error";

export interface ImageJobStatus {
  job_id: string;
  status: ImageJobState;
  image_url: string | null;
  error: string | null;
  meta: Record<string, unknown>;
}

/** Extrae el N de "libro::chunk::N"; null si no aplica (p. ej. BANDERA). */
export function chunkIndexOf(chunkId: string | null): number | null {
  if (!chunkId) return null;
  const n = Number(chunkId.split("::chunk::")[1]);
  return Number.isInteger(n) ? n : null;
}

/** Marcador crudo que el pipeline pone hoy en los bloques BANDERA. */
export const CHECKPOINT_MARKER = "--$CHECKPOINT_LECTURA$--";

/**
 * Pregunta de comprensión de un checkpoint. La pregunta viaja en el campo
 * `questions` (lista) del bloque BANDERA. Si el campo no existe, se cae
 * al `text` como fallback (marcador crudo = sin pregunta).
 */
export function checkpointQuestion(block: ReaderBlock): string | null {
  if (block.type !== "BANDERA") return null;
  if (block.questions && block.questions.length > 0) return block.questions[0];
  const text = block.text.trim();
  if (!text || text === CHECKPOINT_MARKER) return null;
  return text;
}
