// Mock del backend para desarrollar el frontend sin los datos reales
// (data/*.json está gitignorado; ver agent_log/2026-07-11-frontend-api-client-catalogo.md).
// Replica el contrato del handoff 2026-07-10: books, reader, chat SSE, imágenes async.
//
// Uso:  npm run mock   (escucha en :8000, mismo default que el backend real)
import { createServer } from "node:http";

const PORT = Number(process.env.MOCK_PORT ?? 8000);
const BOOK_ID = "la_metamorfosis_franz_kafka";

const BOOK = {
  book_id: BOOK_ID,
  title: "La metamorfosis (mock)",
  author: "Franz Kafka",
  publication_year: 2022,
  total_blocks: 0, // se recalcula abajo
  narrative_blocks: 0,
  non_narrative_blocks: 0,
  banderas: 0,
};

// --- Reader sintético: 3 capítulos, 9 chunks, 1 BANDERA, paratexto inicial ---

const FRASES = [
  "Gregorio recorrió la habitación mientras la luz de la mañana se estiraba sobre el suelo de madera.",
  "Desde el pasillo llegaban voces apagadas que hablaban de él como si no pudiera oírlas.",
  "El reloj de la estación marcó la hora con una campanada que hizo temblar los cristales.",
  "Pensó en su trabajo, en los trenes perdidos y en la deuda que sus padres aún arrastraban.",
  "La puerta seguía cerrada con llave, tal como la había dejado la noche anterior.",
];

function buildBlocks() {
  const blocks = [];
  let cursor = 0;
  let n = 0;
  const push = (type, text, chunkId, isNarrative = true) => {
    const isBandera = type === "BANDERA";
    blocks.push({
      id_block: `${BOOK_ID}::block::${n++}`,
      type,
      text,
      chunk_id: isBandera ? null : chunkId,
      char_start: isBandera || !chunkId ? -1 : cursor,
      char_end: isBandera || !chunkId ? -1 : cursor + text.length,
      is_narrative: isNarrative,
    });
    if (chunkId && !isBandera) cursor += text.length + 2;
  };

  push("h1", "La metamorfosis", null, false);
  push("p", "Edición sintética generada por el mock del frontend. No es el texto real.", null, false);

  let chunk = 0;
  for (let cap = 1; cap <= 3; cap++) {
    chunk += 1;
    push("h2", `Capítulo ${cap}`, `${BOOK_ID}::chunk::${chunk}`);
    for (let c = 0; c < 3; c++) {
      if (c > 0) chunk += 1;
      const chunkId = `${BOOK_ID}::chunk::${chunk}`;
      for (let p = 0; p < 3; p++) {
        const frase = FRASES[(chunk + p) % FRASES.length];
        push("p", `(${chunkId.split("::chunk::")[1]}.${p + 1}) ${frase} ${FRASES[(chunk + p + 2) % FRASES.length]}`, chunkId);
      }
    }
    if (cap === 2) push("BANDERA", "--$CHECKPOINT_LECTURA$--", null);
  }
  return blocks;
}

const BLOCKS = buildBlocks();
BOOK.total_blocks = BLOCKS.length;
BOOK.narrative_blocks = BLOCKS.filter((b) => b.is_narrative).length;
BOOK.non_narrative_blocks = BOOK.total_blocks - BOOK.narrative_blocks;
BOOK.banderas = BLOCKS.filter((b) => b.type === "BANDERA").length;

const READER = {
  book_id: BOOK_ID,
  metadata: { title: BOOK.title, author: BOOK.author, publication_year: BOOK.publication_year },
  blocks: BLOCKS,
};

// --- Imagen SVG placeholder (equivale al mock:true del backend real) --------

const svgPlaceholder = (label) =>
  `<svg xmlns="http://www.w3.org/2000/svg" width="768" height="512">
    <rect width="100%" height="100%" fill="#e8e2d6"/>
    <text x="50%" y="48%" text-anchor="middle" font-family="sans-serif" font-size="22" fill="#6b6355">Ilustración mock</text>
    <text x="50%" y="58%" text-anchor="middle" font-family="sans-serif" font-size="14" fill="#8a8272">${label}</text>
  </svg>`;

const jobs = new Map(); // job_id -> { pollsLeft, label }

const sse = (event, data) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
const json = (res, status, body, type = "application/json") => {
  res.writeHead(status, { "Content-Type": type });
  res.end(type === "application/json" ? JSON.stringify(body) : body);
};

createServer(async (req, res) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  if (req.method === "OPTIONS") return json(res, 204, "");

  const url = new URL(req.url, `http://localhost:${PORT}`);

  if (url.pathname === "/api/books" && req.method === "GET") return json(res, 200, [BOOK]);

  const readerMatch = url.pathname.match(/^\/api\/books\/(.+)\/reader$/);
  if (readerMatch && req.method === "GET") {
    if (decodeURIComponent(readerMatch[1]) !== BOOK_ID)
      return json(res, 404, { detail: `Reader not found for book '${readerMatch[1]}'` });
    return json(res, 200, READER);
  }

  if (url.pathname === "/api/chat" && req.method === "POST") {
    let body = "";
    for await (const c of req) body += c;
    const { message = "", reading_state = {} } = JSON.parse(body || "{}");

    res.writeHead(200, { "Content-Type": "text/event-stream" });

    // rama imagen: como el backend, ilustra los focus_chunk_ids
    // Heurística solo del mock (el router real es un LLM); tolera tildes.
    if (/dib[uú]j|ilustr|imagen/i.test(message)) {
      const focus = reading_state.focus_chunk_ids ?? [];
      res.write(sse("route", { tool: "imagen" }));
      if (focus.length === 0) {
        res.write(sse("notice", { tool: "imagen", message: "No sé qué parte estás viendo ahora mismo para ilustrarla." }));
      } else {
        const jobId = crypto.randomUUID();
        jobs.set(jobId, { pollsLeft: 2, label: focus.join(", ") });
        res.write(sse("image_job", { job_id: jobId, poll_url: `/api/images/${jobId}` }));
      }
      res.write(sse("done", {}));
      return res.end();
    }

    res.write(sse("route", { tool: "qa_rag" }));
    await new Promise((r) => setTimeout(r, 1200)); // simula "pensando"
    const answer =
      "Gregorio Samsa despertó una mañana convertido en un insecto monstruoso, " +
      "y su primera preocupación fue haber perdido el tren al trabajo. (respuesta mock)";
    for (const m of answer.match(/\S+\s*/g)) {
      res.write(sse("token", { delta: m }));
      await new Promise((r) => setTimeout(r, 40));
    }
    res.write(
      sse("citations", {
        citations: [{ chunk_id: `${BOOK_ID}::chunk::1`, char_start: 0, char_end: 120 }],
        answered: true,
        ok: true,
      }),
    );
    res.write(sse("done", {}));
    return res.end();
  }

  if (url.pathname === "/api/images" && req.method === "POST") {
    let body = "";
    for await (const c of req) body += c;
    const payload = JSON.parse(body || "{}");
    if ((payload.scope === "vista" || payload.scope === "seccion") && !(payload.chunk_ids ?? []).length)
      return json(res, 422, { detail: `scope '${payload.scope}' requires chunk_ids` });
    const jobId = crypto.randomUUID();
    jobs.set(jobId, { pollsLeft: 2, label: payload.scope });
    // absoluto a propósito (así lo hace el backend en esta ruta)
    return json(res, 202, {
      job_id: jobId,
      poll_url: `http://localhost:${PORT}/api/images/${jobId}`,
      status: "pending",
    });
  }

  const jobMatch = url.pathname.match(/^\/api\/images\/([^/]+)$/);
  if (jobMatch && req.method === "GET") {
    const job = jobs.get(jobMatch[1]);
    if (!job) return json(res, 404, { detail: `Unknown job '${jobMatch[1]}'` });
    if (job.pollsLeft > 0) {
      job.pollsLeft -= 1;
      return json(res, 200, { job_id: jobMatch[1], status: "pending", image_url: null, error: null, meta: {} });
    }
    return json(res, 200, {
      job_id: jobMatch[1],
      status: "done",
      image_url: `http://localhost:${PORT}/generated-visuals/${jobMatch[1]}.svg`,
      error: null,
      meta: { provider: "mock", frame_count: 1, label: job.label },
    });
  }

  const svgMatch = url.pathname.match(/^\/generated-visuals\/([^/]+)\.svg$/);
  if (svgMatch && req.method === "GET") {
    const job = jobs.get(svgMatch[1]);
    return json(res, 200, svgPlaceholder(job?.label ?? svgMatch[1]), "image/svg+xml");
  }

  json(res, 404, { detail: "Not found" });
}).listen(PORT, () => console.log(`Mock del backend en http://localhost:${PORT}`));
