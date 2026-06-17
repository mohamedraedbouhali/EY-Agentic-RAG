import os

MODEL = "llama-3.1-8b-instant"

_client = None


def get_client():
    global _client
    if _client is None:
        # Import only when first needed — keeps backend startup fast
        from groq import Groq
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set in .env")
        _client = Groq(api_key=api_key)
    return _client


def generate_answer(query: str, context_chunks: list[dict]) -> str:
    context_blocks = []
    for i, chunk in enumerate(context_chunks, start=1):
        context_blocks.append(
            f"[Source {i}: {chunk['source']} — Page {chunk['page']}]\n{chunk['text']}"
        )
    context = "\n\n---\n\n".join(context_blocks)

    prompt = f"""You are an expert assistant specialized in analyzing Tender Reference Documents (TdR) for development projects in Africa and the Middle East.

Answer the following question using ONLY the document excerpts provided below.
- Respond in the same language as the question (French or English).
- Be precise and cite which source document(s) your answer comes from.
- If the answer is not found in the provided excerpts, say clearly: "Cette information ne figure pas dans les documents fournis."
- Do not invent information.

=== DOCUMENT EXCERPTS ===
{context}

=== QUESTION ===
{query}

=== ANSWER ==="""

    client = get_client()
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=512,
    )
    return response.choices[0].message.content.strip()
