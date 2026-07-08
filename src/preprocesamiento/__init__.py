"""Preprocessing pipeline: EPUB → master.json → chunks.

Modules:
    build_master          EPUB → master.json (extract + structure)
    generate_chunks       master.json → master.json + chunks (tokenizer-based)
    classify_narrative    set is_narrative on blocks (editorial vs literary)
    insert_banderas       insert BANDERA reading checkpoints
    build_books_index     generate static index_books.json catalog
"""

from __future__ import annotations
