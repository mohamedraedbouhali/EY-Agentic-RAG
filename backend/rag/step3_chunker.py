import re
import tiktoken

CHUNK_SIZE = 512   # max tokens per chunk
OVERLAP    = 50    # tokens of trailing context carried into the next chunk

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
    """Split on sentence-ending punctuation and newlines — except inside
    Markdown tables. Consecutive lines starting with '|' are kept together as
    ONE atomic block with internal newlines preserved: a table only stays a
    table if each row keeps its own line. Flattening it (the old behaviour)
    left the LLM guessing where rows ended, which produced garbled answers."""
    parts:     list[str] = []
    table_buf: list[str] = []
    text_buf:  list[str] = []

    def flush_text():
        if text_buf:
            for p in re.split(r'(?<=[.!?])\s+|\n+', "\n".join(text_buf)):
                if p.strip():
                    parts.append(p.strip())
            text_buf.clear()

    def flush_table():
        if table_buf:
            parts.append("\n".join(table_buf))
            table_buf.clear()

    for line in text.split("\n"):
        if line.strip().startswith("|"):
            flush_text()
            table_buf.append(line.strip())
        else:
            flush_table()
            text_buf.append(line)
    flush_table()
    flush_text()
    return parts


def _split_oversized(sentence: str) -> list[str]:
    """Hard-split a single sentence that alone exceeds CHUNK_SIZE tokens."""
    enc = _tokenizer()
    tokens = enc.encode(sentence)
    pieces = []
    for i in range(0, len(tokens), CHUNK_SIZE - OVERLAP):
        piece = enc.decode(tokens[i: i + CHUNK_SIZE])
        if piece.strip():
            pieces.append(piece)
    return pieces


_TABLE_SEP_RE = re.compile(r'\|(?:\s*:?-+:?\s*\|)+')


def _split_table_block(block: str) -> list[str]:
    """Split an oversized Markdown table on ROW boundaries, repeating the
    header lines in every piece so each piece stays a valid, self-describing
    table (token-level hard splits cut rows in half)."""
    lines = block.split("\n")
    if len(lines) >= 2 and _TABLE_SEP_RE.fullmatch(lines[1].strip()):
        header, body = lines[:2], lines[2:]
    else:
        header, body = [], lines

    header_tokens = _token_len("\n".join(header)) if header else 0
    pieces: list[str] = []
    cur, cur_tokens = list(header), header_tokens

    for row in body:
        row_tokens = _token_len(row) + 1
        if row_tokens > CHUNK_SIZE:            # single monster row
            if len(cur) > len(header):
                pieces.append("\n".join(cur))
            pieces.extend(_split_oversized(row))
            cur, cur_tokens = list(header), header_tokens
            continue
        if cur_tokens + row_tokens > CHUNK_SIZE and len(cur) > len(header):
            pieces.append("\n".join(cur))
            cur, cur_tokens = list(header), header_tokens
        cur.append(row)
        cur_tokens += row_tokens

    if len(cur) > len(header):
        pieces.append("\n".join(cur))
    return pieces


# ── Chunk assembly ────────────────────────────────────────────────────────────

def _is_table(sentence: str) -> bool:
    return sentence.lstrip().startswith("|")


# Lines that carry Markdown structure and must therefore START a new line:
# table rows, headings, bullet items, numbered items. Gluing them onto the
# previous line with a space destroys the structure — the LLM then has to
# guess where each bullet ends, and drops items (WISEMED conditions bug).
_STRUCTURAL_RE = re.compile(r'^(#{1,6}\s|\||[-*•]\s|\d{1,3}[.)]\s)')


def _starts_structure(sentence: str) -> bool:
    return bool(_STRUCTURAL_RE.match(sentence.lstrip()))


def _join_sentences(parts: list[str]) -> str:
    """Join sentences with spaces, but keep structural lines (table rows,
    headings, bullets, numbered items) at the start of their own line."""
    out = ""
    for p in parts:
        if not out:
            out = p
        elif _starts_structure(p) or out.rstrip().endswith("|"):
            out += "\n" + p
        else:
            out += " " + p
    return out


# ── Page tracking ─────────────────────────────────────────────────────────────

_PAGE_RE       = re.compile(r'\[Page (\d+)\]')
_TABLE_PAGE_RE = re.compile(r'\[Tableau p\.(\d+)')


def _sentence_pages(sentences: list[str]) -> list[int]:
    """Assign each sentence the page it belongs to, by walking the [Page N]
    markers in order. The chunk's page is then the page of its FIRST sentence
    — deterministic, instead of 'first marker that happens to appear inside
    the chunk text' (which pointed one page too far for chunks straddling a
    page break)."""
    pages: list[int] = []
    current = 1
    for s in sentences:
        table_m = _TABLE_PAGE_RE.findall(s)
        page_m  = _PAGE_RE.findall(s)
        if table_m:
            current = int(table_m[0])
            pages.append(current)
        elif page_m:
            # A '[Page N]' marker precedes that page's text: the sentence is
            # on page N only when it starts with the marker.
            pages.append(int(page_m[0]) if s.lstrip().startswith("[Page") else current)
            current = int(page_m[-1])
        else:
            pages.append(current)
    return pages


# ── Public API ────────────────────────────────────────────────────────────────

def split_into_chunks(text: str, filename: str = "") -> list[dict]:
    """Fixed-size chunking: pack sentences greedily up to CHUNK_SIZE tokens,
    carrying roughly OVERLAP tokens of trailing context into the next chunk.
    Markdown tables are atomic blocks (split by rows only when a table alone
    exceeds CHUNK_SIZE) and keep one row per line.
    """
    sentences: list[str] = []
    for s in _split_sentences(text):
        if _token_len(s) > CHUNK_SIZE:
            if _is_table(s):
                sentences.extend(_split_table_block(s))
            else:
                sentences.extend(_split_oversized(s))
        else:
            sentences.append(s)

    if not sentences:
        return []

    enc = _tokenizer()
    tokenized = [enc.encode(s) for s in sentences]
    pages     = _sentence_pages(sentences)

    # ── Pack sentences into fixed-size, overlapping chunks ───────────────────
    raw_chunks: list[tuple[str, int]] = []   # (text, page)
    n = len(sentences)
    start = 0
    while start < n:
        count = 0
        end = start
        while end < n and (end == start or count + len(tokenized[end]) <= CHUNK_SIZE):
            count += len(tokenized[end])
            end += 1
        raw_chunks.append((_join_sentences(sentences[start:end]), pages[start]))

        if end >= n:
            break

        # Back up from `end` by roughly OVERLAP tokens so the next chunk
        # repeats a bit of trailing context. Big blocks (tables) are never
        # used as overlap — repeating a 400-token table in the next chunk
        # would duplicate it almost entirely.
        back = end - 1
        overlap_count = 0
        while (back > start and overlap_count < OVERLAP
               and len(tokenized[back]) <= 2 * OVERLAP):
            overlap_count += len(tokenized[back])
            back -= 1
        start = max(back + 1, start + 1)  # guarantee forward progress

    # ── Build output dicts ────────────────────────────────────────────────────
    chunks: list[dict] = []
    for index, (chunk_text, page) in enumerate(raw_chunks):
        chunks.append({
            "id":          f"{filename}__chunk_{index}",
            "text":        chunk_text,
            "source":      filename,
            "page":        page,
            "chunk_index": index,
        })

    return chunks
