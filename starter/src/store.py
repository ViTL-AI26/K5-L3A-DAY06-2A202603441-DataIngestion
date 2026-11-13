"""PostgreSQL + pgvector storage and similarity search."""

from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .models import Chunk


class PgVectorStore:
    """Store and retrieve document chunks using PostgreSQL + pgvector."""

    # Only these metadata fields can be used as search filters.
    ALLOWED_FILTERS = {
        "source",
        "document_id",
        "page",
        "year",
        "document_type",
        "topic",
    }

    def __init__(self, database_url: str, dimensions: int) -> None:
        """Retain connection settings and validate embedding dimensions."""

        if not database_url:
            raise ValueError("DATABASE_URL must not be empty.")

        if not isinstance(dimensions, int) or dimensions <= 0:
            raise ValueError("Embedding dimensions must be a positive integer.")

        self.database_url = database_url
        self.dimensions = dimensions

    def _vector_literal(self, vector: list[float]) -> str:
        """Convert a vector to PostgreSQL pgvector literal format."""

        if len(vector) != self.dimensions:
            raise ValueError(
                f"Expected {self.dimensions} dimensions, "
                f"received {len(vector)}."
            )

        values = []

        for value in vector:
            number = float(value)

            if not (-float("inf") < number < float("inf")):
                raise ValueError("Vector contains a non-finite value.")

            values.append(str(number))

        return "[" + ",".join(values) + "]"

    def create_schema(self) -> None:
        """Create the chunk table and cosine similarity index."""

        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS document_chunks (
                        strategy TEXT NOT NULL,
                        chunk_id TEXT NOT NULL,
                        document_id TEXT NOT NULL,
                        source TEXT NOT NULL,
                        page INTEGER NOT NULL,
                        text TEXT NOT NULL,
                        metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                        embedding VECTOR({self.dimensions}) NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (strategy, chunk_id)
                    );
                    """
                )

                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                    idx_document_chunks_strategy
                    ON document_chunks (strategy);
                    """
                )

                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                    idx_document_chunks_metadata
                    ON document_chunks USING GIN (metadata);
                    """
                )

                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                    idx_document_chunks_embedding
                    ON document_chunks
                    USING hnsw (embedding vector_cosine_ops);
                    """
                )

    def upsert(
        self,
        strategy: str,
        chunks: list[Chunk],
        vectors: list[list[float]],
    ) -> None:
        """Replace existing chunks for ingested documents and save vectors."""

        if not strategy:
            raise ValueError("Strategy must not be empty.")

        if len(chunks) != len(vectors):
            raise ValueError(
                f"Chunks ({len(chunks)}) and vectors ({len(vectors)}) "
                "must have the same length."
            )

        if not chunks:
            return

        chunk_ids = [chunk.chunk_id for chunk in chunks]

        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("Duplicate chunk_id detected in input.")

        for chunk, vector in zip(chunks, vectors):
            if not chunk.chunk_id or not chunk.document_id:
                raise ValueError("Chunk ID and document ID must not be empty.")

            if not chunk.source:
                raise ValueError("Chunk source must not be empty.")

            if chunk.page < 1:
                raise ValueError("Page number must be at least 1.")

            if not chunk.text.strip():
                raise ValueError("Chunk text must not be empty.")

            self._vector_literal(vector)

        document_ids = list({chunk.document_id for chunk in chunks})

        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                # Remove old chunks for these documents in this strategy.
                # This also removes obsolete chunks after re-ingestion.
                cur.execute(
                    """
                    DELETE FROM document_chunks
                    WHERE strategy = %s
                      AND document_id = ANY(%s);
                    """,
                    (strategy, document_ids),
                )

                rows = [
                    (
                        strategy,
                        chunk.chunk_id,
                        chunk.document_id,
                        chunk.source,
                        chunk.page,
                        chunk.text,
                        Jsonb(chunk.metadata),
                        self._vector_literal(vector),
                    )
                    for chunk, vector in zip(chunks, vectors)
                ]

                cur.executemany(
                    """
                    INSERT INTO document_chunks (
                        strategy,
                        chunk_id,
                        document_id,
                        source,
                        page,
                        text,
                        metadata,
                        embedding
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s::vector
                    )
                    ON CONFLICT (strategy, chunk_id)
                    DO UPDATE SET
                        document_id = EXCLUDED.document_id,
                        source = EXCLUDED.source,
                        page = EXCLUDED.page,
                        text = EXCLUDED.text,
                        metadata = EXCLUDED.metadata,
                        embedding = EXCLUDED.embedding,
                        created_at = NOW();
                    """,
                    rows,
                )

    def search(
        self,
        strategy: str,
        query_vector: list[float],
        top_k: int = 3,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Search by cosine similarity with parameterized metadata filters."""

        if not strategy:
            raise ValueError("Strategy must not be empty.")

        if not isinstance(top_k, int) or top_k <= 0:
            raise ValueError("top_k must be a positive integer.")

        vector_literal = self._vector_literal(query_vector)

        filters = filters or {}

        unsupported = set(filters) - self.ALLOWED_FILTERS

        if unsupported:
            raise ValueError(
                f"Unsupported metadata filters: {sorted(unsupported)}"
            )

        conditions = ["strategy = %s"]
        params: list[Any] = [strategy]

        for key, value in filters.items():
            if value is None:
                raise ValueError(f"Filter '{key}' cannot be None.")

            if key == "source":
                conditions.append("source = %s")
                params.append(value)

            elif key == "document_id":
                conditions.append("document_id = %s")
                params.append(value)

            elif key == "page":
                conditions.append("page = %s")
                params.append(value)

            else:
                conditions.append("metadata ->> %s = %s")
                params.extend([key, str(value)])

        where_clause = " AND ".join(conditions)

        query = f"""
            SELECT
                chunk_id,
                document_id,
                source,
                page,
                text,
                metadata,
                1 - (embedding <=> %s::vector) AS score
            FROM document_chunks
            WHERE {where_clause}
            ORDER BY embedding <=> %s::vector
            LIMIT %s;
        """

        query_params = [
            vector_literal,
            *params,
            vector_literal,
            top_k,
        ]

        with psycopg.connect(
            self.database_url,
            row_factory=dict_row,
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(query, query_params)
                results = cur.fetchall()

        return [
            {
                "chunk_id": row["chunk_id"],
                "document_id": row["document_id"],
                "source": row["source"],
                "page": row["page"],
                "text": row["text"],
                "score": float(row["score"]),
                "metadata": row["metadata"],
            }
            for row in results
        ]
