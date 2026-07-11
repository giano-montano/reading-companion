import { useEffect, useState } from "react";
import { getBooks } from "../api/client";
import type { BookSummary } from "../api/types";

type CatalogState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; books: BookSummary[] };

interface Props {
  onSelect: (book: BookSummary) => void;
}

export function BookCatalog({ onSelect }: Props) {
  const [state, setState] = useState<CatalogState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    getBooks()
      .then((books) => {
        if (!cancelled) setState({ status: "ready", books });
      })
      .catch((err: Error) => {
        if (!cancelled) setState({ status: "error", message: err.message });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (state.status === "loading") {
    return <p className="catalog-status">Cargando biblioteca…</p>;
  }

  if (state.status === "error") {
    return (
      <p className="catalog-status catalog-error">
        No pude cargar la biblioteca. ¿Está corriendo el backend?
        <br />
        <small>{state.message}</small>
      </p>
    );
  }

  if (state.books.length === 0) {
    return <p className="catalog-status">No hay libros disponibles todavía.</p>;
  }

  return (
    <ul className="catalog">
      {state.books.map((book) => (
        <li key={book.book_id}>
          <button className="book-card" onClick={() => onSelect(book)}>
            <span className="book-title">{book.title}</span>
            <span className="book-author">
              {book.author}
              {book.publication_year ? ` · ${book.publication_year}` : ""}
            </span>
            <span className="book-meta">
              {book.narrative_blocks} bloques · {book.banderas} checkpoints
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
