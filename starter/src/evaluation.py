"""Evaluate retrieval evidence and preserve per-query traces."""

import re
import unicodedata
from typing import Any


def _normalize_text(text: str) -> str:
    """Normalize text for evidence comparison."""

    text = unicodedata.normalize("NFC", text or "")
    text = text.replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip().casefold()


def _get_gold_evidence(question: dict[str, Any]) -> list[dict[str, Any]]:
    """Support one gold evidence or multiple documented alternatives."""

    alternatives = question.get("gold_evidence")

    if alternatives:
        if not isinstance(alternatives, list):
            raise ValueError("gold_evidence must be a list.")

        return alternatives

    sources = question.get("gold_source_id")
    pages = question.get("gold_page")
    quotes = question.get("evidence_quote")

    sources = sources if isinstance(sources, list) else [sources]
    pages = pages if isinstance(pages, list) else [pages]
    quotes = quotes if isinstance(quotes, list) else [quotes]

    if not sources or not pages or not quotes:
        raise ValueError(
            "Each question needs gold_source_id, gold_page "
            "and evidence_quote."
        )

    if not (len(sources) == len(pages) == len(quotes)):
        raise ValueError(
            "Alternative gold sources, pages and quotes "
            "must have matching lengths."
        )

    return [
        {
            "source_id": source,
            "page": page,
            "evidence_quote": quote,
        }
        for source, page, quote in zip(sources, pages, quotes)
    ]


def _is_evidence_hit(
    hit: dict[str, Any],
    gold_evidence: list[dict[str, Any]],
) -> bool:
    """Check source, page and complete evidence quote."""

    hit_source = hit.get("document_id")
    hit_page = hit.get("page")
    hit_text = _normalize_text(hit.get("text", ""))

    for gold in gold_evidence:
        gold_source = gold.get("source_id")
        gold_page = gold.get("page")
        gold_quote = _normalize_text(gold.get("evidence_quote", ""))

        if not gold_source or gold_page is None or not gold_quote:
            continue

        source_matches = hit_source == gold_source
        page_matches = str(hit_page) == str(gold_page)
        evidence_matches = gold_quote in hit_text

        if source_matches and page_matches and evidence_matches:
            return True

    return False


def evaluate_query(
    question: dict[str, Any],
    hits: list[dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate Hit@1 and Evidence Hit@3, retaining the retrieval trace."""

    required_fields = [
        "id",
        "split",
        "question",
        "expected_answer",
    ]

    missing = [field for field in required_fields if field not in question]

    if missing:
        raise ValueError(f"Question is missing fields: {missing}")

    if question["split"] not in {"dev", "test"}:
        raise ValueError("Question split must be 'dev' or 'test'.")

    if not hits:
        top_hits = []
    else:
        top_hits = hits[:3]

    gold_evidence = _get_gold_evidence(question)

    evidence_flags = [
        _is_evidence_hit(hit, gold_evidence)
        for hit in top_hits
    ]

    hit_at_1 = bool(evidence_flags and evidence_flags[0])
    evidence_hit_at_3 = any(evidence_flags)

    trace = []

    for rank, hit in enumerate(top_hits, start=1):
        trace.append({
            "rank": rank,
            "chunk_id": hit.get("chunk_id"),
            "document_id": hit.get("document_id"),
            "source": hit.get("source"),
            "page": hit.get("page"),
            "text": hit.get("text"),
            "score": hit.get("score"),
            "metadata": hit.get("metadata", {}),
            "evidence_hit": evidence_flags[rank - 1],
        })

    return {
        "question_id": question["id"],
        "split": question["split"],
        "question": question["question"],
        "expected_answer": question["expected_answer"],
        "gold_evidence": gold_evidence,
        "hit_at_1": hit_at_1,
        "evidence_hit_at_3": evidence_hit_at_3,
        "trace": trace,
    }


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate Hit@1 and Evidence Hit@3 by strategy and split."""

    summary: dict[str, Any] = {}

    for trace in traces:
        strategy = trace.get("strategy")
        split = trace.get("split")

        if strategy not in {"A", "B", "C"}:
            raise ValueError(f"Unsupported strategy: {strategy}")

        if split not in {"dev", "test"}:
            raise ValueError(f"Unsupported split: {split}")

        summary.setdefault(strategy, {})
        summary[strategy].setdefault(split, {
            "total": 0,
            "hit_at_1": 0,
            "evidence_hit_at_3": 0,
            "hit_at_1_rate": 0.0,
            "evidence_hit_at_3_rate": 0.0,
        })

        group = summary[strategy][split]

        group["total"] += 1
        group["hit_at_1"] += int(trace["hit_at_1"])
        group["evidence_hit_at_3"] += int(
            trace["evidence_hit_at_3"]
        )

    for strategy_groups in summary.values():
        for group in strategy_groups.values():
            total = group["total"]

            if total:
                group["hit_at_1_rate"] = (
                    group["hit_at_1"] / total
                )
                group["evidence_hit_at_3_rate"] = (
                    group["evidence_hit_at_3"] / total
                )

    return summary
