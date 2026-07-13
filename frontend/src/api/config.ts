// Optional chaining: fuera de Vite (scripts node/tsx) import.meta.env no existe.
export const API_BASE_URL =
  import.meta.env?.VITE_API_BASE_URL ?? "http://localhost:8000";
