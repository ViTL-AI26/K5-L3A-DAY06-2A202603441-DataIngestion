"""Run the Day 06 ingestion and retrieval experiment.

Run from the starter directory:
    python -m src.run
"""
from __future__ import annotations

import csv
import json
import os
import statistics
import time
from collections import Counter
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .chunking import by_paragraph, fixed_size
from .embeddings import MyEmbedder
from .evaluation import evaluate_query, summarize
from .ingestion import load_corpus
from .store import PgVectorStore


STARTER_DIR = Path.cwd()
DATA_DIR = STARTER_DIR / "data"
OUTPUT_DIR = STARTER_DIR.parent / "artifacts" / "day06"
MANIFEST_PATH = DATA_DIR / "manifest.json"
BENCHMARK_PATH = DATA_DIR / "benchmark.json"


def read_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def validate_inputs(pages: list[Any], questions: list[dict[str, Any]]) -> None:
    if len(pages) < 30:
        raise ValueError(
            f"Corpus has only {len(pages)} pages; at least 30 are required."
        )
    if len(questions) < 20:
        raise ValueError("Benchmark must contain at least 20 questions.")

    split_counts = Counter(q.get("split") for q in questions)
    if split_counts["dev"] < 15 or split_counts["test"] < 5:
        raise ValueError(
            f"Expected at least 15 dev and 5 test questions; got {dict(split_counts)}"
        )

    required = {
        "id", "split", "question", "expected_answer",
        "gold_source_id", "gold_page", "evidence_quote",
    }
    for question in questions:
        missing = required - set(question)
        if missing:
            raise ValueError(f"{question.get('id', 'Unknown')} missing fields: {sorted(missing)}")
        if question.get("filter"):
            if not isinstance(question["filter"], dict):
                raise ValueError(f"{question['id']}: filter must be an object.")
            if set(question["filter"]) - PgVectorStore.ALLOWED_FILTERS:
                raise ValueError(f"{question['id']}: unsupported filter fields.")


def chunk_stats(chunks: list[Any]) -> dict[str, Any]:
    lengths = [len(chunk.text) for chunk in chunks]
    return {
        "chunk_count": len(chunks),
        "total_characters": sum(lengths),
        "min_length": min(lengths) if lengths else 0,
        "max_length": max(lengths) if lengths else 0,
        "mean_length": round(statistics.mean(lengths), 2) if lengths else 0,
        "median_length": round(statistics.median(lengths), 2) if lengths else 0,
    }


def main() -> None:
    load_dotenv(DATA_DIR.parent / ".env")
    load_dotenv()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise EnvironmentError(
            "DATABASE_URL is missing. Check starter/.env; do not share its credentials."
        )

    model_name = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
    fixed_size_chars = int(os.getenv("CHUNK_SIZE", "500"))
    overlap_chars = int(os.getenv("CHUNK_OVERLAP", "50"))
    paragraph_max_size = int(os.getenv("PARAGRAPH_MAX_SIZE", "500"))

    print("Loading corpus and benchmark...")
    pages = load_corpus(MANIFEST_PATH)
    benchmark_data = read_json(BENCHMARK_PATH)
    questions = benchmark_data["questions"] if isinstance(benchmark_data, dict) else benchmark_data
    validate_inputs(pages, questions)

    print(f"Corpus pages: {len(pages)}")
    print(f"Benchmark: {len(questions)} ({dict(Counter(q['split'] for q in questions))})")
    print(f"Embedding model: {model_name}")

    embedder = MyEmbedder(model_name=model_name)
    store = PgVectorStore(database_url=database_url, dimensions=embedder.dimensions)
    store.create_schema()

    # A: fixed-size chunks. B: paragraph-aware chunks. C reuses B's chunks,
    # embeddings and metadata; only eligible questions receive metadata filters.
    strategy_chunks: dict[str, list[Any]] = {"A": [], "B": [], "C": []}
    chunking_seconds: dict[str, float] = {}

    started = time.perf_counter()
    for page in pages:
        strategy_chunks["A"].extend(
            fixed_size(page, size=fixed_size_chars, overlap=overlap_chars)
        )
    chunking_seconds["A"] = time.perf_counter() - started

    started = time.perf_counter()
    for page in pages:
        strategy_chunks["B"].extend(
            by_paragraph(page, max_size=paragraph_max_size)
        )
    chunking_seconds["B"] = time.perf_counter() - started
    strategy_chunks["C"] = strategy_chunks["B"]

    resource_rows = []
    vector_cache: dict[str, list[list[float]]] = {}

    for strategy in ("A", "B"):
        chunks = strategy_chunks[strategy]
        print(f"\nStrategy {strategy}: {len(chunks)} chunks")
        started = time.perf_counter()
        vectors = embedder.embed_documents([chunk.text for chunk in chunks])
        embedding_seconds = time.perf_counter() - started
        vector_cache[strategy] = vectors

        started = time.perf_counter()
        store.upsert(strategy=strategy, chunks=chunks, vectors=vectors)
        storage_seconds = time.perf_counter() - started

        stats = chunk_stats(chunks)
        stats.update({
            "chunking_seconds": round(chunking_seconds[strategy], 3),
            "embedding_seconds": round(embedding_seconds, 3),
            "storage_seconds": round(storage_seconds, 3),
            "embedding_model": model_name,
            "embedding_dimensions": embedder.dimensions,
        })
        resource_rows.append({"strategy": strategy, **stats})

    # C has exactly the same paragraph chunks as B. Reuse the same vectors,
    # but store them under a separate strategy key for a fair comparison.
    started = time.perf_counter()
    store.upsert(
        strategy="C",
        chunks=strategy_chunks["C"],
        vectors=vector_cache["B"],
    )
    c_storage_seconds = time.perf_counter() - started
    c_stats = chunk_stats(strategy_chunks["C"])
    c_stats.update({
        "chunking_seconds": 0.0,
        "embedding_seconds": 0.0,
        "storage_seconds": round(c_storage_seconds, 3),
        "embedding_model": model_name,
        "embedding_dimensions": embedder.dimensions,
        "note": "Reuses Strategy B chunks and vectors; only retrieval filtering differs.",
    })
    resource_rows.append({"strategy": "C", **c_stats})

    print("\nEmbedding benchmark queries...")
    query_vectors: dict[str, list[float]] = {}
    for question in questions:
        query_vectors[question["id"]] = embedder.embed_query(question["question"])

    all_traces: list[dict[str, Any]] = []
    for strategy in ("A", "B", "C"):
        print(f"\nRetrieving Strategy {strategy}...")
        for question in questions:
            filters = question.get("filter", {}) if strategy == "C" else {}
            hits = store.search(
                strategy=strategy,
                query_vector=query_vectors[question["id"]],
                top_k=3,
                filters=filters,
            )
            evaluated = evaluate_query(question, hits)
            evaluated["strategy"] = strategy
            evaluated["applied_filters"] = filters
            all_traces.append(evaluated)

    metrics = summarize(all_traces)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_json(OUTPUT_DIR / "retrieval_traces.json", all_traces)
    write_json(OUTPUT_DIR / "retrieval_summary.json", metrics)
    write_json(OUTPUT_DIR / "resource_summary.json", resource_rows)

    csv_path = OUTPUT_DIR / "resource_summary.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as file:
        fieldnames = sorted({key for row in resource_rows for key in row})
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(resource_rows)

    print("\n=== RETRIEVAL METRICS ===")
    for strategy in ("A", "B", "C"):
        for split in ("dev", "test"):
            group = metrics.get(strategy, {}).get(split)
            if not group:
                continue
            print(
                f"{strategy} | {split} | n={group['total']} | "
                f"Hit@1={group['hit_at_1_rate']:.3f} | "
                f"Evidence Hit@3={group['evidence_hit_at_3_rate']:.3f}"
            )

    print("\n=== RESOURCE SUMMARY ===")
    for row in resource_rows:
        print(
            f"{row['strategy']}: chunks={row['chunk_count']}, "
            f"mean_chars={row['mean_length']}, "
            f"max_chars={row['max_length']}, "
            f"embed_seconds={row['embedding_seconds']}"
        )

    print(f"\nOutputs saved to: {OUTPUT_DIR}")
    print("Manual assessment is still required for coherence, metadata usefulness, and grounding quality.")


if __name__ == "__main__":
    main()
