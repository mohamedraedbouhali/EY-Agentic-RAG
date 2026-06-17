MODEL_NAME   = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

_model = None


def get_model():
    global _model
    if _model is None:
        # Import only when first needed — keeps backend startup fast
        from sentence_transformers import SentenceTransformer
        print(f"Loading embedding model: {MODEL_NAME} ...")
        _model = SentenceTransformer(MODEL_NAME)
        print("Model loaded.")
    return _model


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed document chunks — no prefix needed for BGE passages."""
    model = get_model()
    return model.encode(texts, show_progress_bar=True, normalize_embeddings=True).tolist()


def embed_query(query: str) -> list[float]:
    """Embed a search query — BGE requires the instruction prefix for queries."""
    model = get_model()
    prefixed = QUERY_PREFIX + query
    return model.encode(prefixed, normalize_embeddings=True).tolist()
