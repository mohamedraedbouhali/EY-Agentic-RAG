import re

CHUNK_SIZE  = 800    # characters — roughly 130 words
OVERLAP     = 150    # characters carried into the next chunk

# Separators tried in order from coarsest to finest.
# The splitter tries \n\n first (paragraphs), falls back to \n (lines),
# then to sentence-ending punctuation, then words, then raw characters.
SEPARATORS = ["\n\n", "\n", ". ", "? ", "! ", "; ", " ", ""]


# ── Core recursive splitter ───────────────────────────────────────────────────

def _split_text_recursive(text: str, separators: list[str]) -> list[str]:
    """
    Recursively split `text` until every piece is <= CHUNK_SIZE chars.

    Algorithm:
      1. Try the first separator. Split the text on it.
      2. Pieces that still exceed CHUNK_SIZE are recursed with remaining separators.
      3. All fine-grained pieces are then greedily merged back up to CHUNK_SIZE,
         carrying the last OVERLAP chars of each chunk into the start of the next.
    """
    if len(text) <= CHUNK_SIZE:
        return [text] if text.strip() else []

    sep  = separators[0] if separators else ""
    rest = separators[1:] if separators else []

    # Character-level fallback (empty separator)
    if not sep:
        chunks = []
        for i in range(0, len(text), CHUNK_SIZE - OVERLAP):
            piece = text[i: i + CHUNK_SIZE]
            if piece.strip():
                chunks.append(piece)
        return chunks

    raw_splits = text.split(sep)

    # Recurse on any split that is still oversized
    fine_splits: list[str] = []
    for s in raw_splits:
        if not s.strip():
            continue
        if len(s) <= CHUNK_SIZE:
            fine_splits.append(s)
        elif rest:
            fine_splits.extend(_split_text_recursive(s, rest))
        else:
            # No more separators — hard-slice
            for i in range(0, len(s), CHUNK_SIZE - OVERLAP):
                piece = s[i: i + CHUNK_SIZE]
                if piece.strip():
                    fine_splits.append(piece)

    # Greedy merge: accumulate pieces until we'd exceed CHUNK_SIZE, then flush
    chunks: list[str] = []
    buf = ""
    for piece in fine_splits:
        joined = (buf + sep + piece) if buf else piece
        if len(joined) <= CHUNK_SIZE:
            buf = joined
        else:
            if buf:
                chunks.append(buf)
                # Carry OVERLAP chars from end of previous chunk into the new one
                tail = buf[-OVERLAP:] if len(buf) > OVERLAP else buf
                buf  = (tail + sep + piece) if tail else piece
            else:
                # Single piece already > CHUNK_SIZE — emit as-is (handled above)
                chunks.append(piece)
                buf = ""

    if buf.strip():
        chunks.append(buf)

    return chunks


# ── Page detection ────────────────────────────────────────────────────────────

def _detect_page(chunk_text: str) -> int | None:
    """Return the first [Page N] marker found in the chunk, or None."""
    matches = re.findall(r'\[Page (\d+)\]', chunk_text)
    return int(matches[0]) if matches else None


# ── Public API ────────────────────────────────────────────────────────────────

def split_into_chunks(text: str, filename: str = "") -> list[dict]:
    raw_chunks = _split_text_recursive(text, SEPARATORS)
    chunks     = []
    last_page  = 1

    for index, chunk_text in enumerate(raw_chunks):
        found = _detect_page(chunk_text)
        if found is not None:
            last_page = found
        page = last_page

        chunks.append({
            "id":          f"{filename}__chunk_{index}",
            "text":        chunk_text,
            "source":      filename,
            "page":        page,
            "chunk_index": index,
        })

    return chunks
