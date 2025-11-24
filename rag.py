# rag.py
"""
RecallAI - Simple RAG System

This module provides a lightweight in-memory RAGSystem that:
- Stores text from uploaded lecture PDFs in overlapping chunks
- Retrieves the most relevant chunks for a user query
- Tracks which source files (slides) the retrieved chunks came from

It is intentionally dependency-free so it works out of the box with app.py.
"""

from __future__ import annotations
from typing import List, Dict, Tuple
import math
import re


class RAGSystem:
    def __init__(self, chunk_size: int = 800, overlap: int = 100) -> None:
        """
        Initialize the RAG system.

        :param chunk_size: Number of characters per chunk.
        :param overlap: Overlap between consecutive chunks (in characters).
        """
        self.chunk_size = chunk_size
        self.overlap = overlap

        # Each chunk is a dict: {"text": str, "source": str, "index": int}
        self._chunks: List[Dict[str, object]] = []

        # Stored after the last retrieval so get_sources() can report them
        self._last_retrieved_chunks: List[Dict[str, object]] = []

    # ---------------------------------------------------------------------
    # Document ingestion
    # ---------------------------------------------------------------------
    def add_document(self, text: str, source_name: str) -> None:
        """
        Add a new document's text to the RAG index.

        :param text: Full text extracted from the PDF.
        :param source_name: Filename or human-readable source label.
        """
        if not text or not text.strip():
            return

        # Normalize whitespace/newlines a bit
        cleaned = self._normalize_text(text)

        # Chunk and store
        self._chunk_and_store(cleaned, source_name)

    def _normalize_text(self, text: str) -> str:
        """
        Basic text normalization: normalize newlines and collapse extra spaces.
        """
        # Normalize line endings
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # Optionally, you can keep newlines for structure; here we keep them
        # but collapse crazy spacing.
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()

    def _chunk_and_store(self, text: str, source_name: str) -> None:
        """
        Split text into overlapping character-based chunks and append to store.
        """
        start = 0
        index = len(self._chunks)

        while start < len(text):
            end = start + self.chunk_size
            chunk_text = text[start:end].strip()
            if chunk_text:
                self._chunks.append({
                    "text": chunk_text,
                    "source": source_name,
                    "index": index,
                })
                index += 1

            # Move forward with overlap
            if end >= len(text):
                break
            start = end - self.overlap

    # ---------------------------------------------------------------------
    # Status helpers (used by /status endpoint)
    # ---------------------------------------------------------------------
    def has_documents(self) -> bool:
        """
        Return True if any chunks have been added.
        """
        return len(self._chunks) > 0

    def count_chunks(self) -> int:
        """
        Return total number of stored chunks.
        """
        return len(self._chunks)

    # ---------------------------------------------------------------------
    # Retrieval
    # ---------------------------------------------------------------------
    def retrieve(self, query: str, n_results: int = 3) -> List[str]:
        """
        Retrieve the top-n chunks most relevant to the query.

        This uses a very simple lexical overlap scoring function.
        It’s intentionally lightweight and dependency-free.

        :param query: User question / prompt.
        :param n_results: Max number of chunks to return.
        :return: List of chunk texts.
        """
        query = query or ""
        q_tokens = self._tokenize(query)
        if not q_tokens or not self._chunks:
            self._last_retrieved_chunks = []
            return []

        scored: List[Tuple[float, Dict[str, object]]] = []

        for chunk in self._chunks:
            c_tokens = self._tokenize(chunk["text"])  # type: ignore[arg-type]
            score = self._score_overlap(q_tokens, c_tokens)
            if score > 0:
                scored.append((score, chunk))

        # If nothing scored > 0, return empty so app.py can handle it
        if not scored:
            self._last_retrieved_chunks = []
            return []

        # Sort by score (desc) and take top-n
        scored.sort(key=lambda x: x[0], reverse=True)
        top = [c for _, c in scored[:n_results]]

        # Remember these for get_sources()
        self._last_retrieved_chunks = top

        # Return just the text for context
        return [c["text"] for c in top]

    def _tokenize(self, text: str) -> List[str]:
        """
        Very simple tokenizer: lowercase, split on non-letters, drop short words.
        """
        text = text.lower()
        # Split on anything that isn't a letter or number
        tokens = re.split(r"[^a-z0-9]+", text)
        # Filter out super short tokens
        return [t for t in tokens if len(t) > 2]

    def _score_overlap(self, q_tokens: List[str], c_tokens: List[str]) -> float:
        """
        Compute a simple similarity score between two token lists.

        Score = |intersection| / sqrt(|query| * |chunk|)
        """
        q_set = set(q_tokens)
        c_set = set(c_tokens)

        if not q_set or not c_set:
            return 0.0

        overlap = q_set.intersection(c_set)
        if not overlap:
            return 0.0

        return len(overlap) / math.sqrt(len(q_set) * len(c_set))

    # ---------------------------------------------------------------------
    # Source reporting (used by /query endpoint)
    # ---------------------------------------------------------------------
    def get_sources(self, query: str) -> List[str]:
        """
        Return a list of unique source names for the last retrieval.

        app.py calls this as `rag.get_sources(user_query)` right after
        `rag.retrieve(user_query, ...)`. We don't actually need the query
        value again, so it's ignored here and only used for signature
        compatibility.

        :param query: User query (ignored; retrieval already ran).
        :return: List of unique source filenames/labels.
        """
        if not self._last_retrieved_chunks:
            return []

        sources = [c["source"] for c in self._last_retrieved_chunks]
        # Preserve order but remove duplicates
        seen = set()
        unique_sources: List[str] = []
        for s in sources:
            if s not in seen:
                seen.add(s)
                unique_sources.append(s)
        return unique_sources

    # ---------------------------------------------------------------------
    # (Optional) utility if you ever want to reset the index
    # ---------------------------------------------------------------------
    def clear(self) -> None:
        """
        Clear all stored chunks and retrieval history.
        """
        self._chunks = []
        self._last_retrieved_chunks = []
