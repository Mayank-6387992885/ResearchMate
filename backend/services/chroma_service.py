from __future__ import annotations

from typing import Any

import chromadb


class ChromaVectorStore:
    """Wrapper around ChromaDB for storing and querying paper chunk embeddings."""

    def __init__(self, persist_directory: str | None = None, collection_name: str = "researchmate_chunks"):
        if persist_directory:
            self.client = chromadb.PersistentClient(path=persist_directory)
        else:
            self.client = chromadb.Client()
        self.collection = self.client.get_or_create_collection(name=collection_name)

    def upsert_paper_chunks(
        self,
        paper_id: int,
        chunks: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> int:
        """Upsert text chunks and their embeddings for a given paper."""
        if not chunks:
            return 0
        ids = [f"paper_{paper_id}_chunk_{idx}" for idx in range(len(chunks))]
        meta = metadatas or [{"paper_id": paper_id, "chunk_index": idx} for idx in range(len(chunks))]
        self.collection.upsert(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=meta,
        )
        return len(chunks)

    def query_paper_chunks(
        self,
        query_embedding: list[float],
        paper_id: int | None = None,
        n_results: int = 5,
    ) -> dict[str, Any]:
        """Query similar chunks, optionally filtered to a single paper_id."""
        where = {"paper_id": paper_id} if paper_id is not None else None
        return self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where,
        )
