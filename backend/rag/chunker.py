CHUNK_SIZE = 300   # words per chunk
OVERLAP    = 30    # words shared between consecutive chunks


def split_into_chunks(text: str, filename: str = "") -> list[dict]:
    words = text.split()
    chunks = []
    start = 0
    index = 0

    while start < len(words):
        end = min(start + CHUNK_SIZE, len(words))
        chunk_text = " ".join(words[start:end])

        # Detect which page this chunk likely belongs to
        page = _detect_page(words, start)

        chunks.append({
            "id":       f"{filename}__chunk_{index}",
            "text":     chunk_text,
            "source":   filename,
            "page":     page,
            "chunk_index": index,
        })
        index += 1
        start += CHUNK_SIZE - OVERLAP

    return chunks


def _detect_page(words: list, start: int) -> int:
    """Walk backwards from start to find the most recent [Page N] marker."""
    page = 1
    window = words[max(0, start - CHUNK_SIZE): start + 1]
    for i, w in enumerate(reversed(window)):
        if w.startswith("[Page") and i + 1 < len(window):
            try:
                page = int(window[len(window) - i].rstrip("]"))
                break
            except (ValueError, IndexError):
                pass
    return page
