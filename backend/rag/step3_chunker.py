import re
import tiktoken

CHUNK_SIZE           = 512   # max tokens per chunk (hard ceiling)
OVERLAP              = 100   # tokens carried over when a semantic chunk is too large
WINDOW_SIZE          = 3     # sentences merged into each embedding window for context
SIMILARITY_THRESHOLD = 0.75  # split where cosine similarity drops below this value (0–1)

_enc = None


def _tokenizer() -> tiktoken.Encoding:
    global _enc
    if _enc is None:
        _enc = tiktoken.get_encoding("cl100k_base")
    return _enc


def _token_len(text: str) -> int:
    return len(_tokenizer().encode(text))


# ── Sentence splitter ─────────────────────────────────────────────────────────

def _split_sentences(text: str) -> list[str]:
    """Split on sentence-ending punctuation and newlines."""
    parts = re.split(r'(?<=[.!?])\s+|\n+', text)
    return [p.strip() for p in parts if p.strip()]


# ── Similarity ────────────────────────────────────────────────────────────────

def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na  = sum(x * x for x in a) ** 0.5
    nb  = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ── Token-limit enforcement (fallback for oversized semantic chunks) ──────────

def _enforce_token_limit(chunks: list[str]) -> list[str]:
    result = []
    enc = _tokenizer()
    for chunk in chunks:
        if _token_len(chunk) <= CHUNK_SIZE:
            result.append(chunk)
        else:
            tokens = enc.encode(chunk)
            for i in range(0, len(tokens), CHUNK_SIZE - OVERLAP):
                piece = enc.decode(tokens[i: i + CHUNK_SIZE])
                if piece.strip():
                    result.append(piece)
    return result


# ── Page detection ────────────────────────────────────────────────────────────

def _detect_page(chunk_text: str) -> int | None:
    matches = re.findall(r'\[Page (\d+)\]', chunk_text)
    return int(matches[0]) if matches else None


# ── Public API ────────────────────────────────────────────────────────────────

def split_into_chunks(text: str, filename: str = "") -> list[dict]:
    # Lazy import — avoids loading the model at import time
    from rag.step4_embedder import embed_documents

    sentences = _split_sentences(text)
    if not sentences:
        return []

    # ── Build context windows ────────────────────────────────────────────────
    # Each window = the sentence plus its WINDOW_SIZE neighbours, joined.
    # Embedding a window captures local context rather than an isolated sentence.
    half = WINDOW_SIZE // 2
    windows = [
        " ".join(sentences[max(0, i - half): min(len(sentences), i + half + 1)])
        for i in range(len(sentences))
    ]

    # ── Embed all windows in one batch ───────────────────────────────────────
    embeddings = embed_documents(windows)

    # ── Find breakpoints ─────────────────────────────────────────────────────
    # Compute cosine similarity between every pair of consecutive windows.
    # A sudden drop in similarity signals a topic change → chunk boundary.
    similarities = [_cosine(embeddings[i], embeddings[i + 1])
                    for i in range(len(embeddings) - 1)]

    breakpoints = {i + 1 for i, sim in enumerate(similarities) if sim < SIMILARITY_THRESHOLD}

    # ── Group sentences into semantic chunks ─────────────────────────────────
    raw_chunks: list[str] = []
    current:    list[str] = []
    for i, sentence in enumerate(sentences):
        if i in breakpoints and current:
            raw_chunks.append(" ".join(current))
            current = []
        current.append(sentence)
    if current:
        raw_chunks.append(" ".join(current))

    # ── Enforce token ceiling ─────────────────────────────────────────────────
    bounded = _enforce_token_limit(raw_chunks)

    # ── Build output dicts ────────────────────────────────────────────────────
    chunks:    list[dict] = []
    last_page: int        = 1
    for index, chunk_text in enumerate(bounded):
        found = _detect_page(chunk_text)
        if found is not None:
            last_page = found
        chunks.append({
            "id":          f"{filename}__chunk_{index}",
            "text":        chunk_text,
            "source":      filename,
            "page":        last_page,
            "chunk_index": index,
        })

    return chunks
