// Verificación e2e de la calibración del tracking de lectura.
//
// Compara, en varios puntos de scroll, lo que la barra de estado reporta
// ("viendo" / "leído hasta el chunk") contra la verdad medida con
// getBoundingClientRect sobre los bloques [data-chunk], usando los mismos
// offsets del hook (TOP_OFFSET=64 del header sticky, BOTTOM_OFFSET=40 de la
// barra). También verifica que el progreso sea monótono al volver arriba.
//
// Requiere el mock y la app corriendo:  npm run mock  +  npm run dev
// Uso:  npm run e2e:tracking
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
      return { viendo: [...visible].sort((a, b) => a - b), passedMax };
    },
    [TOP_OFFSET, BOTTOM_OFFSET],
  );
}

async function compareAt(label) {
  await page.waitForTimeout(300); // deja actuar al IntersectionObserver
  const reported = await reportedState();
  const measured = await measuredState();
  check(
    JSON.stringify(reported.viendo) === JSON.stringify(measured.viendo),
    `${label}: "viendo" coincide con los chunks visibles`,
    `barra=[${reported.viendo}] medido=[${measured.viendo}]`,
  );
  return { reported, measured };
}

// 1. Arriba del todo: sin nada leído.
let { reported } = await compareAt("inicio");
check(reported.max === 0, "inicio: nada leído aún", `barra=${reported.max}`);

// 2. Scroll descendente por pasos, verificando en cada parada.
const pageHeight = await page.evaluate(() => document.body.scrollHeight);
let expectedMax = 0;
for (let y = 500; y < pageHeight; y += 700) {
  await page.evaluate((py) => window.scrollTo(0, py), y);
  const { reported: rep, measured: mea } = await compareAt(`scroll@${y}px`);
  expectedMax = Math.max(expectedMax, mea.passedMax);
  check(
    rep.max === expectedMax,
    `scroll@${y}px: "leído hasta" correcto y monótono`,
    `barra=${rep.max} esperado=${expectedMax}`,
  );
}

// 3. De vuelta arriba: "viendo" se recalcula, "leído hasta" NO baja.
await page.evaluate(() => window.scrollTo(0, 0));
({ reported } = await compareAt("de vuelta arriba"));
check(
  reported.max === expectedMax,
  "de vuelta arriba: el progreso no retrocede (monótono)",
  `barra=${reported.max} esperado=${expectedMax}`,
);

// 4. Los botones de ilustrar tienen tooltip.
const untitled = await page.$$eval(".illustrate-bar button", (btns) =>
  btns.filter((b) => !b.title).length,
);
check(untitled === 0, "los 4 botones de ilustrar tienen tooltip");

await browser.close();
console.log(failures === 0 ? "\nTracking calibrado: todo en verde." : `\n${failures} verificaciones fallaron.`);
process.exit(failures === 0 ? 0 : 1);
