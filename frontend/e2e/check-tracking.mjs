// Verificación e2e: calibración del tracking + flujo de checkpoint con gate.
//
// Compara la barra de estado contra la verdad medida en el DOM (mismos
// offsets del hook), y ejercita el flujo completo de evaluación: el texto se
// corta en el gate, la pregunta dispara cuando la bandera está casi arriba,
// responder en el chat libera el gate, y las fuentes son chips numerados.
//
// Requiere el mock y la app corriendo (ver npm run mock / npm run dev).
// Uso:  APP_URL=http://localhost:5173 npm run e2e:tracking
import { chromium } from "playwright";

const APP_URL = process.env.APP_URL ?? "http://localhost:5173";
const TOP_OFFSET = 64; // mantener en sincronía con useReadingTracker.ts
const BOTTOM_OFFSET = 40;

let failures = 0;
const check = (cond, label, detail = "") => {
  console.log(`${cond ? "ok " : "FALLO"} — ${label}${cond || !detail ? "" : `  (${detail})`}`);
  if (!cond) failures += 1;
};

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
await page.goto(APP_URL);
await page.click(".book-card");
await page.waitForSelector(".reader-text p");
await page.waitForTimeout(400);

/** Lo que reporta la barra de estado. */
async function reportedState() {
  const text = await page.textContent(".reading-debug");
  const viendo = /viendo:\s*([^·]*?)leído/s.exec(text.replace(/\n/g, " "))?.[1] ?? "";
  const nums = [...viendo.matchAll(/\d+/g)].map((m) => Number(m[0]));
  const max = Number(/leído hasta el chunk:\s*(\d+)/.exec(text)?.[1] ?? -1);
  return { viendo: nums.sort((a, b) => a - b), max };
}

/** La verdad medida en el DOM con los mismos offsets del hook. */
async function measuredState() {
  return page.evaluate(
    ([top, bottom]) => {
      const visible = new Set();
      let passedMax = 0;
      for (const el of document.querySelectorAll("[data-chunk]")) {
        const r = el.getBoundingClientRect();
        const n = Number(el.dataset.chunk.split("::chunk::")[1]);
        if (r.bottom > top && r.top < innerHeight - bottom) visible.add(n);
        if (r.bottom <= top) passedMax = Math.max(passedMax, n);
      }
      // semántica "hasta donde leyó": lo visible también cuenta como alcanzado
      passedMax = Math.max(passedMax, ...visible, 0);
      return { viendo: [...visible].sort((a, b) => a - b), passedMax };
    },
    [TOP_OFFSET, BOTTOM_OFFSET],
  );
}

let expectedMax = 0;
async function compareAt(label) {
  await page.waitForTimeout(300); // deja actuar al IntersectionObserver
  const reported = await reportedState();
  const measured = await measuredState();
  check(
    JSON.stringify(reported.viendo) === JSON.stringify(measured.viendo),
    `${label}: "viendo" coincide con los chunks visibles`,
    `barra=[${reported.viendo}] medido=[${measured.viendo}]`,
  );
  expectedMax = Math.max(expectedMax, measured.passedMax);
  check(
    reported.max === expectedMax,
    `${label}: "leído hasta" correcto y monótono`,
    `barra=${reported.max} esperado=${expectedMax}`,
  );
  return { reported, measured };
}

// 1. Arriba del todo.
await compareAt("inicio");

// 2. El gate corta el texto: solo se ve la primera sección (un checkpoint) y
//    la pregunta aún NO está en el chat (la bandera no llegó arriba).
const checkpointsAtStart = await page.$$eval(".checkpoint", (els) => els.length);
check(checkpointsAtStart === 1, "el texto se corta en el primer gate", `checkpoints=${checkpointsAtStart}`);
let chatText = await page.textContent(".chat-messages");
check(!chatText.includes("Pregunta de comprensión"), "la pregunta no se adelanta al inicio");

// 3. Bajar por pasos hasta que el gate llegue casi arriba y dispare.
let fired = false;
for (let i = 0; i < 20 && !fired; i++) {
  await page.evaluate(() => window.scrollBy(0, 600));
  await compareAt(`bajando(${i})`);
  fired = await page.evaluate(() => document.querySelector(".gate-actions") !== null);
  const atBottom = await page.evaluate(
    () => scrollY + innerHeight >= document.body.scrollHeight - 2,
  );
  if (atBottom && !fired) break;
}
check(fired, "la pregunta dispara cuando el gate está casi arriba");
chatText = await page.textContent(".chat-messages");
check(chatText.includes("Pregunta de comprensión"), "la pregunta aparece en el chat");

// 4. Responder en el chat libera el gate y revela la siguiente sección.
await page.fill(".chat-input textarea", "Porque están preocupados por Gregorio");
await page.press(".chat-input textarea", "Enter");
await page.waitForSelector('.chat-messages :text("(evaluación mock)")', { timeout: 30_000 });
check(true, "la respuesta gatilla la rama evaluación y llega feedback");
await page.waitForFunction(() => document.querySelectorAll(".checkpoint").length === 2, {
  timeout: 5_000,
});
check(true, "el gate se libera al responder y se revela la siguiente sección");

// 5. Seguir hasta el final (la 2ª bandera no tiene pregunta: no bloquea).
for (let i = 0; i < 20; i++) {
  await page.evaluate(() => window.scrollBy(0, 700));
  await compareAt(`final(${i})`);
  const atBottom = await page.evaluate(
    () => scrollY + innerHeight >= document.body.scrollHeight - 2,
  );
  if (atBottom) break;
}
const questionCount = await page.$$eval(".chat-messages .msg", (msgs) =>
  msgs.filter((m) => m.textContent.includes("Pregunta de comprensión")).length,
);
check(questionCount === 1, "solo la bandera con pregunta generó mensaje en el chat");

// 6. De vuelta arriba: el progreso no retrocede.
await page.evaluate(() => window.scrollTo(0, 0));
await compareAt("de vuelta arriba");

// 7. Tooltips en los botones de ilustrar.
const untitled = await page.$$eval(".illustrate-bar button", (btns) =>
  btns.filter((b) => !b.title).length,
);
check(untitled === 0, "los 4 botones de ilustrar tienen tooltip");

// 8. Panel NER: renderiza los chunk_elements del reader (anti-spoiler aparte).
const panelText = await page.textContent(".elements-panel").catch(() => null);
check(
  panelText !== null && panelText.includes("Gregorio"),
  "el panel de elementos renderiza los chunk_elements del reader",
);

// 9. Fuentes como chips numerados (sin la palabra "chunk") que navegan al pasaje.
await page.fill(".chat-input textarea", "¿En qué se convirtió Gregorio?");
await page.press(".chat-input textarea", "Enter");
await page.waitForSelector(".msg-citations button", { timeout: 30_000 });
const citText = await page.textContent(".msg-citations");
check(!/chunk/i.test(citText), "las fuentes no muestran la palabra 'chunk'", citText.trim());
const chipLabel = await page.textContent(".msg-citations button");
check(chipLabel.trim() === "1", "el chip de fuente es un número referencial", chipLabel);
await page.click(".msg-citations button");
await page.waitForTimeout(700);
const citedVisible = await page.evaluate(() => {
  const el = document.querySelector(".reader-text .cited");
  if (!el) return false;
  const r = el.getBoundingClientRect();
  return r.bottom > 0 && r.top < innerHeight;
});
check(citedVisible, "el chip navega al pasaje citado y queda resaltado");

await browser.close();
console.log(failures === 0 ? "\nTodo en verde." : `\n${failures} verificaciones fallaron.`);
process.exit(failures === 0 ? 0 : 1);
