"""OpenAI embedding provider adapter."""

import os

from dotenv import load_dotenv
from openai import OpenAI


class MyEmbedder:
    """Generate real text embeddings using the OpenAI Embeddings API."""

    def __init__(self, model_name: str = "text-embedding-3-small") -> None:
        load_dotenv()

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "OPENAI_API_KEY is missing. Check your .env file."
            )

        self.model_name = model_name
        # Keep the same vector size as the existing pgvector schema.
        self.dimensions = 768
        self.client = OpenAI(api_key=api_key)

    def _embed(
        self,
        texts: list[str],
        task_type: str | None = None,
    ) -> list[list[float]]:
        """Generate embeddings and validate the returned vectors.

        task_type is retained for compatibility with the previous Gemini
        adapter. OpenAI uses the same embedding endpoint for documents/queries.
        """

        if not texts:
            return []

        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("All input texts must be non-empty strings.")

        vectors: list[list[float]] = []

        # Keep requests moderate in size; each batch is one API request.
        batch_size = 100

        for start in range(0, len(texts), batch_size):
            batch = texts[start:start + batch_size]

            response = self.client.embeddings.create(
                model=self.model_name,
                input=batch,
                dimensions=self.dimensions,
                encoding_format="float",
            )

            if not response.data:
                raise RuntimeError("OpenAI returned no embeddings.")

            # Sort by input index to preserve the original text/vector order.
            ordered_data = sorted(response.data, key=lambda item: item.index)

            for item in ordered_data:
                vector = item.embedding

                if vector is None or len(vector) != self.dimensions:
                    raise ValueError(
                        "Unexpected embedding dimension returned by OpenAI."
                    )

                vectors.append([float(value) for value in vector])

        if len(vectors) != len(texts):
            raise RuntimeError(
                f"Expected {len(texts)} vectors, received {len(vectors)}."
            )

        return vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed document chunks for retrieval."""
        return self._embed(texts)

    def embed_query(self, question: str) -> list[float]:
        """Embed a search query compatible with document vectors."""

        if not isinstance(question, str) or not question.strip():
            raise ValueError("Query must be a non-empty string.")

        vectors = self._embed([question])
        return vectors[0]
