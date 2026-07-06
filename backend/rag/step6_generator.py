import os
import re

MODEL          = "llama-3.3-70b-versatile"
FALLBACK_MODEL = "llama-3.1-8b-instant"   # separate Groq daily quota — used when MODEL hits 429

_client = None


def get_client():
    global _client
    if _client is None:
        from groq import Groq
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set in .env")
        _client = Groq(api_key=api_key)
    return _client


def _clean_chunk(text: str) -> str:
    """Remove indexing markers before sending chunk text to the LLM."""
    text = re.sub(r'\[Page \d+\]', '', text)
    text = re.sub(r'\[Tableau[^\]]*\]', '', text)
    text = re.sub(r'<!--.*?-->', ' ', text, flags=re.DOTALL)  # pymupdf4llm picture comments
    text = re.sub(r'<br\s*/?>', ' ', text)   # pymupdf4llm line breaks inside table cells
    # pymupdf4llm decoration tags (<u>, <sup>, <mark>…): keep the inner text,
    # drop the tags — react-markdown renders them as literal "<u>" otherwise.
    text = re.sub(r'</?(?:u|sup|sub|mark|i|b|span)\s*>', '', text)
    text = re.sub(r'[ \t]+', ' ', text)        # collapse horizontal whitespace only
    text = re.sub(r'\n{3,}', '\n\n', text)     # at most one blank line
    return text.strip()


MAX_CONTEXT_CHARS          = 20_000  # ~5000 tokens — fits a whole small TdR when the query targets one document
# 8b-instant caps REQUESTS (prompt + history + max_tokens) at 6000 tokens/min.
# French text runs ~3.3 chars/token (not 3.7): 11500 chars ≈ 3500 tokens
# + ~900 prompt/query + truncated history + 700 completion ≈ 5400, under 6000.
# A 15000-char budget was measured at 6252 tokens → Groq 413.
FALLBACK_MAX_CONTEXT_CHARS = 11_500
FALLBACK_MAX_TOKENS        = 700
# History messages are only needed to resolve follow-up references ("et pour
# ce document ?") — a previous answer's full table is dead weight that can
# push the fallback request over the per-minute cap.
HISTORY_MSG_MAX_CHARS      = 800


def _select_chunks(context_chunks: list[dict], budget_chars: int) -> list[dict]:
    # Fill the context budget with the highest-scored chunks first, then
    # re-sort the selection by document/page/position so the LLM reads the
    # excerpts in natural document order (matters for multi-page sections).
    selected = []
    total_chars = 0
    for chunk in context_chunks:
        block_len = len(_clean_chunk(chunk['text'])) + 60  # + header overhead
        if total_chars + block_len > budget_chars:
            continue
        selected.append(chunk)
        total_chars += block_len
    selected.sort(key=lambda c: (c['source'], c['page'], c.get('chunk_index', 0)))
    return selected


def _join_overlap(a: str, b: str, max_probe: int = 600) -> str:
    """Concatenate consecutive chunk texts, removing the repeated overlap
    (the chunker carries ~50 tokens of trailing context into each next chunk)."""
    tail = a[-max_probe:]
    for length in range(min(len(tail), len(b)), 20, -1):
        if b.startswith(tail[-length:]):
            return a + b[length:]
    return a + "\n" + b


def _merge_adjacent(chunks: list[dict]) -> list[dict]:
    """Merge chunks of the same document with consecutive indexes into one
    continuous block. A section split across two chunks then reads as one
    passage — the LLM reliably reproduces it in full, instead of stopping at
    an arbitrary excerpt boundary."""
    if not chunks:
        return []
    merged: list[dict] = []
    cur = None
    for c in chunks:
        if (cur is not None
                and c["source"] == cur["source"]
                and c.get("chunk_index", 0) == cur["_last_idx"] + 1):
            cur["text"] = _join_overlap(cur["text"], c["text"])
            cur["_last_idx"]  = c["chunk_index"]
            cur["_last_page"] = c.get("page", cur["_last_page"])
        else:
            if cur is not None:
                merged.append(cur)
            cur = dict(c)
            cur["_last_idx"]  = c.get("chunk_index", 0)
            cur["_last_page"] = c.get("page", 1)
    merged.append(cur)
    return merged


def _build_system_content(query: str, context_chunks: list[dict], budget_chars: int) -> str:
    selected = _merge_adjacent(_select_chunks(context_chunks, budget_chars))
    context_blocks = []
    for i, chunk in enumerate(selected, start=1):
        clean_text = _clean_chunk(chunk['text'])
        first, last = chunk['page'], chunk.get('_last_page', chunk['page'])
        page_label = f"Page {first}" if last == first else f"Pages {first}-{last}"
        context_blocks.append(
            f"[Extrait {i} — Document: {chunk['source']} — {page_label}]\n{clean_text}"
        )
    context = "\n\n---\n\n".join(context_blocks)

    return f"""You are a document extraction assistant. Your ONLY job is to reproduce, faithfully and completely, the information from the document excerpts below that answers the user's question.

STRICT RULES — follow them without exception:
1. Answer using ONLY text present in the excerpts below. Never use outside knowledge, never infer, never estimate.
2. Respond in the same language as the question (French or English).
3. REPRODUCE, do not rewrite: keep the source's own wording. Do NOT paraphrase, summarize, shorten, or reorganize. Include EVERY bullet point, list item, value, and detail of the relevant passage — complete and in order.
4. When the question names a section title, article, or numbered activity (e.g. "1.1", "ACTIVITÉS DES EXPERTS", "profils recherchés"), your answer is the ENTIRE content under that heading: every bullet point, sub-bullet and paragraph from the heading down to the next heading — never a one-line summary of it. The section may continue across several excerpts: include the continuation. But NEVER merge in content from OTHER sections (e.g. 1.2, 1.3 when asked about 1.1).
5. Do NOT invent headings, labels, or categories that are not in the source. Never add rubrics like "Objectif :", "Méthodologie :", "Résultats attendus :" unless those exact words appear in the excerpt you are quoting.
6. If the information is NOT explicitly stated in the excerpts, respond with EXACTLY and ONLY: "Cette information ne figure pas dans les documents fournis." — then STOP. No extra sentence, no disclaimer, no suggestion.
7. NEVER guess, approximate, or extrapolate a value (date, number, name) that is not word-for-word in the excerpts.
8. NEVER hedge ("je ne peux pas confirmer", "il est possible que"...), NEVER ask for clarification, NEVER offer help beyond the excerpts.
9. Use the conversation history only to resolve follow-up references ("et pour ce document ?", "la même chose pour...").
10. If the user input is a single word or short phrase, treat it as "What do the documents say about [topic]?" and reproduce ALL relevant information found in the excerpts.

FORMAT:
- Respond in Markdown. MIRROR the structure of the source passage: keep its own headings, numbering, bullets and tables as they appear. Bold (**...**) may be used for terms the source itself emphasizes.
- Tables: write each table row on EXACTLY ONE line (|cell|cell|). NEVER insert a line break inside a table cell — when a cell contains several "- item" entries, keep them all inside the cell on that same line, separated by spaces. A row split across several lines breaks the table rendering.
- End your answer with the line: **Source :** <document name> — Page <n> (list each document/page you actually used).

EXAMPLE — how to answer a question about a titled section:
Question: « quelles sont les PIÈCES CONSTITUTIVES du dossier ? »
Excerpt contains: "### 4. PIÈCES CONSTITUTIVES - Une lettre de candidature - Un CV détaillé et signé - Les références de missions similaires ### 5. CALENDRIER Le dossier doit être déposé..."
CORRECT answer (locate the heading, copy everything under it, stop at the next heading):
### 4. PIÈCES CONSTITUTIVES
- Une lettre de candidature
- Un CV détaillé et signé
- Les références de missions similaires

**Source :** document.pdf — Page 3
WRONG answers: a one-sentence summary of the section; content taken from section 5 or from the document's table of contents; a reformulation in your own words.

=== DOCUMENT EXCERPTS ===
{context}"""


def _repair_table_rows(answer: str) -> str:
    """Rejoin Markdown table rows that the LLM split across several lines.

    remark-gfm (frontend renderer) only parses |...|...| rows that sit on a
    single line; despite explicit prompt instructions the model still breaks
    '- item' lists inside a cell onto new lines, which renders as a broken
    table. Deterministic fix: a line that starts with '|' but does not end
    with '|' absorbs the following lines until the row closes. A blank line
    aborts the absorption so an unclosed row can never swallow the rest of
    the answer."""
    out: list[str] = []
    buf: str | None = None
    for line in answer.split("\n"):
        s = line.rstrip()
        if buf is None:
            if s.lstrip().startswith("|") and not s.endswith("|"):
                buf = s
            else:
                out.append(line)
        else:
            if not s.strip():
                out.append(buf)
                out.append(line)
                buf = None
                continue
            buf += " " + s.strip()
            if s.endswith("|"):
                out.append(buf)
                buf = None
    if buf is not None:
        out.append(buf)
    return "\n".join(out)


def generate_answer(query: str, context_chunks: list[dict], history: list[dict] = None) -> str:
    def _messages(budget_chars: int, history_limit: int | None = None) -> list[dict]:
        msgs = [{"role": "system",
                 "content": _build_system_content(query, context_chunks, budget_chars)}]
        hist = history or []
        if history_limit is not None:
            hist = hist[-history_limit:]
        for msg in hist:
            if msg.get("role") in ("user", "assistant") and msg.get("content"):
                content = msg["content"]
                if len(content) > HISTORY_MSG_MAX_CHARS:
                    content = content[:HISTORY_MSG_MAX_CHARS] + " […]"
                msgs.append({"role": msg["role"], "content": content})
        msgs.append({"role": "user", "content": query})
        return msgs

    client = get_client()
    last_exc = None
    # Groq rate limits are tracked PER MODEL: when the main model's daily
    # token quota is exhausted (429), the fallback model still has its own
    # separate quota. Extraction-style answering works fine on the smaller
    # model, and a slightly weaker answer beats an error page. The fallback
    # also has a small per-minute cap, so it gets a reduced context budget.
    attempts = (
        (MODEL,          MAX_CONTEXT_CHARS,          2048,                None),
        (FALLBACK_MODEL, FALLBACK_MAX_CONTEXT_CHARS, FALLBACK_MAX_TOKENS, 2),
        # Last resort: minimal context, no history — must fit under any cap.
        (FALLBACK_MODEL, 6_000,                      600,                 0),
    )
    for model, budget_chars, max_tokens, history_limit in attempts:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=_messages(budget_chars, history_limit),
                temperature=0.0,
                max_tokens=max_tokens,
            )
            answer = _repair_table_rows(response.choices[0].message.content.strip())

            # Guard: if the model hedged ("je ne peux pas confirmer", "cependant",
            # "n'est pas fourni", etc.) it means it hallucinated then self-corrected.
            # Replace the whole answer with the standard not-found sentence.
            hedge_markers = [
                "je ne peux pas confirmer",
                "n'est pas fourni dans les extraits",
                "n'est pas dans les extraits",
                "comme le document spécifique",
                "i cannot confirm",
                "not provided in the excerpts",
                "not found in the excerpts",
            ]
            if any(m in answer.lower() for m in hedge_markers):
                return "Cette information ne figure pas dans les documents fournis."

            return answer
        except Exception as exc:
            last_exc = exc
            err = str(exc)
            if ("rate_limit" in err or "429" in err
                    or "413" in err or "too large" in err.lower()):
                continue   # next attempt: other model and/or smaller request
            raise RuntimeError(f"Groq API error: {exc}") from exc

    raise RuntimeError(f"Groq API error: {last_exc}") from last_exc
