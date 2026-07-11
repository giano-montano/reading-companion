import { useState } from "react";
import { BookCatalog } from "./components/BookCatalog";
import { ReaderView } from "./components/ReaderView";
import type { BookSummary } from "./api/types";

export default function App() {
  const [selected, setSelected] = useState<BookSummary | null>(null);

  if (selected) {
    return (
      <main className="main-reader">
        <ReaderView bookId={selected.book_id} onBack={() => setSelected(null)} />
      </main>
    );
  }

  return (
    <main>
      <h1>Reading Companion</h1>
      <p>Elige un libro para empezar a leer.</p>
      <BookCatalog onSelect={setSelected} />
    </main>
  );
}
