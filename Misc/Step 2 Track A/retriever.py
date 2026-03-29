"""
rag/retriever.py – Simple but effective RAG using TF-IDF cosine similarity.

No vector database required. Uses only stdlib + optional scikit-learn.

If scikit-learn is available:  TF-IDF + cosine similarity (recommended).
Fallback (no sklearn):         BM25-style keyword overlap scoring.

Usage
-----
    retriever = RAGRetriever(chunk_size=500, chunk_overlap=50)
    retriever.index("knowledge.txt")
    context = retriever.retrieve("What are the key risks?", top_k=3)
"""

from __future__ import annotations

import logging
import math
import re
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger(__name__)

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    import numpy as np
    _HAS_SKLEARN = True
except ImportError:
    _HAS_SKLEARN = False
    logger.warning(
        "scikit-learn not found – falling back to keyword overlap RAG. "
        "For better results: pip install scikit-learn"
    )


class RAGRetriever:
    """
    Chunk-based RAG retriever.

    Parameters
    ----------
    chunk_size    : Target character size per chunk.
    chunk_overlap : Character overlap between consecutive chunks.
    """

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        self.chunk_size    = chunk_size
        self.chunk_overlap = chunk_overlap
        self._chunks:       List[str]            = []
        self._vectorizer                         = None
        self._matrix                             = None

    # ─────────────────────────────────────────────────────────
    # Indexing
    # ─────────────────────────────────────────────────────────

    def index(self, path: str) -> None:
        """Read the text file and build the search index."""
        text = Path(path).read_text(encoding="utf-8")
        self._chunks = self._chunk_text(text)
        logger.info("RAG: indexed %d chunks from %s", len(self._chunks), path)

        if _HAS_SKLEARN:
            self._vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
            self._matrix     = self._vectorizer.fit_transform(self._chunks)
        # No else needed – keyword overlap uses self._chunks directly

    def index_text(self, text: str) -> None:
        """Index raw text directly (alternative to index())."""
        self._chunks = self._chunk_text(text)
        if _HAS_SKLEARN:
            self._vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
            self._matrix     = self._vectorizer.fit_transform(self._chunks)

    # ─────────────────────────────────────────────────────────
    # Retrieval
    # ─────────────────────────────────────────────────────────

    def retrieve(self, query: str, top_k: int = 3) -> str:
        """
        Retrieve the most relevant chunks for a query.

        Returns
        -------
        str : Concatenated relevant passages, ready to inject into a prompt.
        """
        if not self._chunks:
            raise RuntimeError("Call index() before retrieve().")

        scored = self._score_sklearn(query) if _HAS_SKLEARN else self._score_keyword(query)

        # Pick top_k highest-scoring chunks (deduped)
        seen   = set()
        top    = []
        for idx, score in scored:
            if idx not in seen:
                seen.add(idx)
                top.append((idx, score))
            if len(top) >= top_k:
                break

        passages = [f"[Passage {i+1}]\n{self._chunks[idx]}" for i, (idx, _) in enumerate(top)]
        return "\n\n".join(passages)

    # ─────────────────────────────────────────────────────────
    # Scoring helpers
    # ─────────────────────────────────────────────────────────

    def _score_sklearn(self, query: str) -> List[Tuple[int, float]]:
        qvec  = self._vectorizer.transform([query])
        sims  = cosine_similarity(qvec, self._matrix).flatten()
        order = np.argsort(sims)[::-1]
        return [(int(i), float(sims[i])) for i in order]

    def _score_keyword(self, query: str) -> List[Tuple[int, float]]:
        """Simple keyword overlap fallback."""
        query_tokens = set(re.findall(r"\w+", query.lower()))
        scores       = []
        for idx, chunk in enumerate(self._chunks):
            chunk_tokens = set(re.findall(r"\w+", chunk.lower()))
            overlap      = len(query_tokens & chunk_tokens)
            # TF-style normalisation
            score = overlap / (1 + math.log1p(len(chunk_tokens)))
            scores.append((idx, score))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores

    # ─────────────────────────────────────────────────────────
    # Chunking
    # ─────────────────────────────────────────────────────────

    def _chunk_text(self, text: str) -> List[str]:
        """Split text into overlapping character chunks, respecting sentence boundaries."""
        # Normalise whitespace
        text = re.sub(r"\r\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)

        chunks  = []
        start   = 0
        end     = self.chunk_size

        while start < len(text):
            slice_ = text[start:end]

            # Try to break at a sentence boundary
            if end < len(text):
                last_period = max(
                    slice_.rfind(". "),
                    slice_.rfind(".\n"),
                    slice_.rfind("! "),
                    slice_.rfind("? "),
                )
                if last_period > self.chunk_size // 2:
                    slice_ = text[start : start + last_period + 1]

            chunk = slice_.strip()
            if chunk:
                chunks.append(chunk)

            # Advance with overlap
            advance = max(len(slice_) - self.chunk_overlap, 1)
            start  += advance
            end     = start + self.chunk_size

        return chunks
