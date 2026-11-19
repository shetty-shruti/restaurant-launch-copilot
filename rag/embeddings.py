"""Embedding model wrapper: bge-small-en-v1.5 via sentence-transformers, run locally."""

from functools import lru_cache
from typing import TYPE_CHECKING

from app.config import get_settings

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

# bge models were trained with this prefix on queries (not on documents) for retrieval.
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@lru_cache
def _model() -> "SentenceTransformer":
    # Imported lazily because loading torch takes a few seconds.
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(get_settings().embedding_model)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed documents or chunks. Vectors are normalized, so cosine similarity = dot product."""
    vectors = _model().encode(texts, normalize_embeddings=True)
    return [v.tolist() for v in vectors]


def embed_query(text: str) -> list[float]:
    """Embed a search query, with the bge query prefix."""
    return embed_texts([BGE_QUERY_PREFIX + text])[0]
