import { useState } from "react";
import { BookCatalog } from "./components/BookCatalog";
import type { BookSummary } from "./api/types";

export default function App() {
  const [selected, setSelected] = useState<BookSummary | null>(null);

  return (
    <main>
      <h1>Reading Companion</h1>
      {selected ? (
        <>
          <p>
            Elegiste <strong>{selected.title}</strong> de {selected.author}. La
            vista de lectura llega en la siguiente iteración.
          </p>
          <button onClick={() => setSelected(null)}>← Volver a la biblioteca</button>
        </>
      ) : (
        <>
          <p>Elige un libro para empezar a leer.</p>
          <BookCatalog onSelect={setSelected} />
        </>
      )}
    </main>
  );
}
