/**
 * Cliente HTTP de la API. Una función por endpoint + el consumidor SSE.
 *
 * Mañas del backend cubiertas aquí (handoff 2026-07-10 §7):
 *  - #1 el chat es SSE por POST → fetch + getReader(), no EventSource.
 *  - #8 poll_url llega relativo desde /api/chat y absoluto desde /api/images
 *       → resolvePollUrl() normaliza siempre.
 */
import { API_BASE_URL } from "./config";
import type {
  BookSummary,
  ChatEvent,
  ChatEventName,
  ChatRequest,
  ImageJobCreated,
  ImageJobStatus,
  ImageRequest,
  ReaderResponse,
} from "./types";

// ngrok muestra un warning HTML en el navegador si no ve este header.
// Para este MVP lo centralizamos acá para no repetirlo en cada pantalla.
const NGROK_BROWSER_WARNING_HEADER = {
  "ngrok-skip-browser-warning": "true",
};

class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(`HTTP ${status}: ${detail}`);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...NGROK_BROWSER_WARNING_HEADER,
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  if (!res.ok) {
    const detail = await res
      .json()
      .then((body: { detail?: string }) => body.detail ?? res.statusText)
      .catch(() => res.statusText);
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

// --- Catálogo y reader ------------------------------------------------------

export const getBooks = (): Promise<BookSummary[]> => request("/api/books");

export const getReader = (bookId: string): Promise<ReaderResponse> =>
  request(`/api/books/${encodeURIComponent(bookId)}/reader`);

// --- Imágenes (async: encolar + poll) ---------------------------------------

export const createImageJob = (body: ImageRequest): Promise<ImageJobCreated> =>
  request("/api/images", { method: "POST", body: JSON.stringify(body) });

/**
 * Reconstruye cualquier URL que nos dé el backend contra API_BASE_URL, quedándonos
 * solo con su path.
 *
 * Maña #8: /api/chat devuelve el poll_url relativo y /api/images lo devuelve absoluto.
 * Maña #10 (2026-07-13): además, el absoluto puede venir MAL. El backend lo firma con
 * `request.base_url`, y ngrok reescribe el Host a localhost:8000 → el backend anuncia
 * `https://localhost:8000/...`; el navegador intenta TLS contra el uvicorn en claro y
 * revienta con ERR_SSL_PROTOCOL_ERROR ("Failed to fetch"; en el server, "Invalid HTTP
 * request received").
 *
 * El host que diga el backend es irrelevante: el frontend ya sabe dónde vive la API.
 */
export const resolvePollUrl = (url: string): string => {
  const path = url.startsWith("/") ? url : new URL(url).pathname;
  return `${API_BASE_URL}${path}`;
};

export async function getImageJob(pollUrl: string): Promise<ImageJobStatus> {
  const res = await fetch(resolvePollUrl(pollUrl), {
    headers: NGROK_BROWSER_WARNING_HEADER,
  });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  return res.json() as Promise<ImageJobStatus>;
}

/**
 * Descarga la imagen y la devuelve como object URL para pintarla en un <img>.
 *
 * Maña #9 (2026-07-13): un <img src="https://…"> NO puede mandar headers, así
 * que ngrok le sirve su página HTML de advertencia (200 text/html) en vez del
 * PNG y la imagen nunca carga. `fetch` sí puede mandar el header, así que
 * bajamos los bytes por aquí y pintamos desde un blob local.
 *
 * El caller es dueño del object URL: debe llamar a `URL.revokeObjectURL(url)`
 * cuando deje de mostrarlo, o se filtra memoria.
 */
export async function fetchImageObjectUrl(imageUrl: string): Promise<string> {
  const res = await fetch(resolvePollUrl(imageUrl), {
    headers: NGROK_BROWSER_WARNING_HEADER,
  });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  return URL.createObjectURL(await res.blob());
}

/** Hace poll cada `intervalMs` hasta status done|error. Abortable. */
export async function pollImageJob(
  pollUrl: string,
  { intervalMs = 1500, signal }: { intervalMs?: number; signal?: AbortSignal } = {},
): Promise<ImageJobStatus> {
  for (;;) {
    const job = await getImageJob(pollUrl);
    if (job.status !== "pending") return job;
    await new Promise<void>((resolve, reject) => {
      const t = setTimeout(resolve, intervalMs);
      signal?.addEventListener(
        "abort",
        () => {
          clearTimeout(t);
          reject(new DOMException("Polling abortado", "AbortError"));
        },
        { once: true },
      );
    });
  }
}

// --- Chat SSE ----------------------------------------------------------------

/**
 * Consume POST /api/chat y entrega cada evento SSE a `onEvent`, en orden.
 * Resuelve cuando llega `done` o se cierra el stream. Sin timeout propio:
 * el QA-RAG puede tardar ~90s (maña #2); usa `signal` para cancelar.
 */
export async function streamChat(
  body: ChatRequest,
  onEvent: (ev: ChatEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...NGROK_BROWSER_WARNING_HEADER,
    },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    throw new ApiError(res.status, res.statusText);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";

  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });

    // Frames separados por línea en blanco: "event: X\ndata: {json}\n\n"
    let sep: number;
    while ((sep = buf.indexOf("\n\n")) !== -1) {
      const frame = buf.slice(0, sep);
      buf = buf.slice(sep + 2);
      const event = frame.match(/^event: (.+)$/m)?.[1] as ChatEventName | undefined;
      const rawData = frame.match(/^data: (.+)$/m)?.[1];
      if (!event) continue;
      const data = rawData ? JSON.parse(rawData) : {};
      onEvent({ event, data } as ChatEvent);
      if (event === "done") return;
    }
  }
}
