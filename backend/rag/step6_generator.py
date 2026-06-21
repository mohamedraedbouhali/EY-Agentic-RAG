import os
import re

MODEL = "llama-3.1-8b-instant"

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
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def generate_answer(query: str, context_chunks: list[dict], history: list[dict] = None) -> str:
    context_blocks = []
    for i, chunk in enumerate(context_chunks, start=1):
        clean_text = _clean_chunk(chunk['text'])
        context_blocks.append(
            f"[Source {i}: {chunk['source']} — Page {chunk['page']}]\n{clean_text}"
        )
    context = "\n\n---\n\n".join(context_blocks)

    system_content = f"""You are a document analysis assistant. Your ONLY job is to extract and present information from the document excerpts below.

STRICT RULES — follow them without exception:
1. Answer using ONLY the information present in the excerpts. Never use outside knowledge.
2. Respond in the same language as the question (French or English).
3. Cite the source document(s) your answer comes from.
4. If the information is NOT in the excerpts, respond with EXACTLY and ONLY this sentence: "Cette information ne figure pas dans les documents fournis." — then STOP. Do not add any other sentence. Do not suggest anything. Do not explain. Do not offer help. Just that one sentence and nothing else.
5. NEVER ask the user for clarification.
6. NEVER offer to help with topics not covered by the excerpts.
7. NEVER say what you "could" help with or what topics you "can" discuss.
7b. NEVER add any sentence after the "not found" response. One sentence. Full stop.
8. You have access to the conversation history — use it to understand follow-up questions.
9. If the user input is a single word or short phrase (a topic or keyword), treat it as "What do the documents say about [topic]?" and summarize ALL relevant information found in the excerpts about that topic. Always produce an answer if the excerpts contain ANY related content.

=== DOCUMENT EXCERPTS ===
{context}"""

    messages = [{"role": "system", "content": system_content}]

    if history:
        for msg in history:
            if msg.get("role") in ("user", "assistant") and msg.get("content"):
                messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({"role": "user", "content": query})

    client = get_client()
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.1,
            max_tokens=1024,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        raise RuntimeError(f"Groq API error: {exc}") from exc
