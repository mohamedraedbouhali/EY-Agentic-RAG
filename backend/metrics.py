"""
RAG Evaluation Script — computes retrieval and generation metrics.

Metrics computed
----------------
Retrieval (no ground truth needed):
  - coverage_rate       : % of queries that return at least one chunk above threshold
  - no_answer_rate      : % of queries where the LLM answered "not found"
  - avg_top1_score      : mean cosine similarity of the best-ranked chunk
  - avg_mean_score      : mean cosine similarity across all retrieved chunks
  - score_distribution  : histogram of top-1 scores in four bands
  - tdr_ratio_in_results: % of retrieved sources classified as TDR

Retrieval (with ground-truth sources in the test set):
  - hit_rate            : % of queries where a relevant source appears in top K
  - mrr                 : Mean Reciprocal Rank of the first relevant source
  - precision_at_k      : fraction of top-K results that are relevant

Generation — LLM-as-judge via Groq (1–5 scale):
  - avg_faithfulness    : answer is grounded in context (no hallucination)
  - avg_relevancy       : answer addresses the question

System:
  - avg_retrieval_ms    : embedding + vector search time
  - avg_generation_ms   : LLM generation time
  - avg_total_ms        : end-to-end latency

Usage
-----
    cd backend
    python metrics.py                           # built-in test set
    python metrics.py --test my_test.json       # custom test set
    python metrics.py --output results.json     # custom output file
    python metrics.py --no-llm-judge            # skip Groq judge (faster)
    python metrics.py --top-k 5 --min-score 0.45

Custom test set JSON format
---------------------------
[
  {"query": "Quels sont les livrables attendus?"},
  {"query": "Who is the donor?", "relevant_sources": ["TDR_Mali_2023.pdf"]}
]
relevant_sources is optional — only needed for hit_rate / MRR / precision metrics.
"""

import sys
import os
import json
import time
import argparse
import re
from datetime import datetime

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from rag.step4_embedder     import embed_query, MODEL_NAME
from rag.step5_vector_store import search, collection_count
from rag.step6_generator    import generate_answer, get_client, MODEL

# ── Default test set ──────────────────────────────────────────────────────────

DEFAULT_TEST_SET = [
    {"query": "Quels sont les profils et qualifications recherchés pour cette mission de consultation?"},
    {"query": "Quelle est la durée de la mission et quels sont les livrables attendus?"},
    {"query": "Quel est le contexte et la justification de cette mission?"},
    {"query": "Quels sont les critères de sélection et d'évaluation des consultants?"},
    {"query": "Quel organisme finance ce projet et dans quel pays se déroule-t-il?"},
    {"query": "Quelles sont les tâches principales du consultant?"},
    {"query": "Quels sont les résultats attendus et les indicateurs de performance?"},
    {"query": "What are the expected outputs and deliverables of the assignment?"},
    {"query": "What qualifications and experience are required for the consultant?"},
    {"query": "What is the scope of work for this consultancy mission?"},
]

NO_INFO_PHRASE = "cette information ne figure pas"


# ── LLM judge ────────────────────────────────────────────────────────────────

def _ask_judge(prompt: str) -> int | None:
    """Send a prompt to the LLM and parse a single 1–5 digit from the response."""
    try:
        client = get_client()
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=5,
        )
        text = response.choices[0].message.content.strip()
        m = re.search(r"[1-5]", text)
        return int(m.group()) if m else None
    except Exception:
        return None


def _score_faithfulness(query: str, context: str, answer: str) -> int | None:
    """
    Faithfulness (1–5): does the answer use ONLY information from the retrieved context?
    5 = fully grounded, no hallucination
    1 = contradicts or ignores the context
    """
    prompt = (
        "Score the faithfulness of this answer on a scale from 1 to 5.\n"
        "Faithfulness = the answer uses ONLY information from the context below, with no hallucination.\n"
        "1 = answer ignores or contradicts the context\n"
        "2 = answer adds significant outside information not in context\n"
        "3 = answer mostly uses context with minor additions\n"
        "4 = answer uses context well with very minimal assumptions\n"
        "5 = answer is entirely and accurately grounded in the context\n\n"
        f"Question: {query}\n\n"
        f"Context (excerpt):\n{context[:1000]}\n\n"
        f"Answer:\n{answer[:600]}\n\n"
        "Reply with a SINGLE digit (1, 2, 3, 4, or 5) and nothing else."
    )
    return _ask_judge(prompt)


def _score_relevancy(query: str, answer: str) -> int | None:
    """
    Relevancy (1–5): does the answer directly and completely address the question?
    5 = perfectly addresses the question
    1 = does not address the question at all
    """
    prompt = (
        "Score how relevant this answer is to the question, on a scale from 1 to 5.\n"
        "1 = answer does not address the question at all\n"
        "2 = answer partially addresses the question\n"
        "3 = answer addresses the question but includes unnecessary content\n"
        "4 = answer directly and well addresses the question\n"
        "5 = answer perfectly and concisely addresses the question\n\n"
        f"Question: {query}\n\n"
        f"Answer:\n{answer[:600]}\n\n"
        "Reply with a SINGLE digit (1, 2, 3, 4, or 5) and nothing else."
    )
    return _ask_judge(prompt)


# ── Per-query evaluation ──────────────────────────────────────────────────────

def _clean_chunk(text: str) -> str:
    text = re.sub(r"\[Page \d+\]", "", text)
    text = re.sub(r"\[Tableau[^\]]*\]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def evaluate_query(
    query: str,
    relevant_sources: list[str],
    top_k: int,
    min_score: float,
    use_llm_judge: bool,
) -> dict:
    result: dict = {
        "query":            query,
        "relevant_sources": relevant_sources,
    }

    # ── Retrieval ──────────────────────────────────────────────────────────
    t0        = time.perf_counter()
    query_vec = embed_query(query)
    hits      = search(query_vec, top_k=top_k)
    t_retrieval_ms = (time.perf_counter() - t0) * 1000

    hits_above = [h for h in hits if h["score"] >= min_score]

    result["retrieval_ms"]              = round(t_retrieval_ms, 1)
    result["num_chunks_retrieved"]      = len(hits)
    result["num_chunks_above_threshold"]= len(hits_above)
    result["top1_score"]                = round(hits[0]["score"], 4) if hits else 0.0
    result["mean_score_all"]            = round(sum(h["score"] for h in hits) / len(hits), 4) if hits else 0.0
    result["mean_score_above"]          = round(sum(h["score"] for h in hits_above) / len(hits_above), 4) if hits_above else 0.0
    result["sources_retrieved"]         = list({h["source"] for h in hits_above})
    result["tdr_sources_retrieved"]     = [h["source"] for h in hits_above if h.get("is_tdr")]

    # Score distribution for this query
    s = result["top1_score"]
    result["score_band"] = (
        "0.0-0.3" if s < 0.3 else
        "0.3-0.5" if s < 0.5 else
        "0.5-0.7" if s < 0.7 else
        "0.7-1.0"
    )

    # Hit Rate, MRR, Precision@K  (only when relevant_sources provided)
    if relevant_sources:
        retrieved = [h["source"] for h in hits]
        hit_positions = [
            rank for rank, src in enumerate(retrieved, start=1)
            if src in relevant_sources
        ]
        result["hit"]              = bool(hit_positions)
        result["reciprocal_rank"]  = round(1.0 / hit_positions[0], 4) if hit_positions else 0.0
        result["precision_at_k"]   = round(len(hit_positions) / top_k, 4)
    else:
        result["hit"]             = None
        result["reciprocal_rank"] = None
        result["precision_at_k"]  = None

    # ── Generation ─────────────────────────────────────────────────────────
    if not hits_above:
        result["answer"]         = "Cette information ne figure pas dans les documents fournis."
        result["no_answer"]      = True
        result["generation_ms"]  = 0
        result["total_ms"]       = round(t_retrieval_ms, 1)
        result["faithfulness"]   = None
        result["relevancy"]      = None
        return result

    t1 = time.perf_counter()
    try:
        answer = generate_answer(query, hits_above)
    except Exception as exc:
        answer = f"[GENERATION ERROR: {exc}]"
    t_generation_ms = (time.perf_counter() - t1) * 1000

    result["answer"]        = answer[:500]
    result["no_answer"]     = NO_INFO_PHRASE in answer.lower()
    result["generation_ms"] = round(t_generation_ms, 1)
    result["total_ms"]      = round(t_retrieval_ms + t_generation_ms, 1)

    # ── LLM judge ──────────────────────────────────────────────────────────
    if use_llm_judge and not result["no_answer"]:
        context = "\n---\n".join(_clean_chunk(h["text"]) for h in hits_above[:4])
        result["faithfulness"] = _score_faithfulness(query, context, answer)
        result["relevancy"]    = _score_relevancy(query, answer)
    else:
        result["faithfulness"] = None
        result["relevancy"]    = None

    return result


# ── Aggregation ───────────────────────────────────────────────────────────────

def aggregate(results: list[dict], top_k: int) -> dict:
    n = len(results)

    # Retrieval
    coverage    = sum(1 for r in results if not r["no_answer"]) / n
    no_ans_rate = sum(1 for r in results if r["no_answer"]) / n
    avg_top1    = sum(r["top1_score"] for r in results) / n
    avg_mean    = sum(r["mean_score_all"] for r in results) / n
    avg_above   = sum(r["mean_score_above"] for r in results) / n

    tdr_ratios = []
    for r in results:
        total = len(r["sources_retrieved"])
        if total > 0:
            tdr_ratios.append(len(r["tdr_sources_retrieved"]) / total)
    tdr_ratio = round(sum(tdr_ratios) / len(tdr_ratios), 4) if tdr_ratios else None

    score_dist = {"0.0-0.3": 0, "0.3-0.5": 0, "0.5-0.7": 0, "0.7-1.0": 0}
    for r in results:
        score_dist[r["score_band"]] += 1

    # Hit Rate / MRR / Precision (only for queries that had relevant_sources)
    labelled = [r for r in results if r["hit"] is not None]
    hit_rate     = round(sum(r["hit"]             for r in labelled) / len(labelled), 4) if labelled else None
    mrr          = round(sum(r["reciprocal_rank"] for r in labelled) / len(labelled), 4) if labelled else None
    precision_k  = round(sum(r["precision_at_k"]  for r in labelled) / len(labelled), 4) if labelled else None

    # Generation
    faith_scores = [r["faithfulness"] for r in results if r["faithfulness"] is not None]
    rel_scores   = [r["relevancy"]    for r in results if r["relevancy"]    is not None]
    avg_faith    = round(sum(faith_scores) / len(faith_scores), 2) if faith_scores else None
    avg_rel      = round(sum(rel_scores)   / len(rel_scores),   2) if rel_scores   else None

    # Latency
    ret_ms  = [r["retrieval_ms"]  for r in results]
    gen_ms  = [r["generation_ms"] for r in results]
    tot_ms  = [r["total_ms"]      for r in results]

    retrieval_block = {
        "coverage_rate":         round(coverage, 4),
        "no_answer_rate":        round(no_ans_rate, 4),
        "avg_top1_score":        round(avg_top1, 4),
        "avg_mean_score_all":    round(avg_mean, 4),
        "avg_mean_score_above":  round(avg_above, 4),
        "tdr_ratio_in_results":  tdr_ratio,
        "score_distribution":    score_dist,
    }
    if hit_rate is not None:
        retrieval_block[f"hit_rate_at_{top_k}"] = hit_rate
        retrieval_block["mrr"]                   = mrr
        retrieval_block[f"precision_at_{top_k}"] = precision_k

    return {
        "total_queries":  n,
        "labelled_queries": len(labelled),
        "retrieval":  retrieval_block,
        "generation": {
            "avg_faithfulness":   avg_faith,
            "avg_relevancy":      avg_rel,
            "faithfulness_scores": faith_scores,
            "relevancy_scores":    rel_scores,
        },
        "latency": {
            "avg_retrieval_ms":  round(sum(ret_ms) / n, 1),
            "avg_generation_ms": round(sum(gen_ms) / n, 1),
            "avg_total_ms":      round(sum(tot_ms) / n, 1),
            "min_total_ms":      round(min(tot_ms), 1),
            "max_total_ms":      round(max(tot_ms), 1),
        },
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Evaluate the RAG pipeline.")
    parser.add_argument("--test",         default=None,                   help="Path to JSON test set")
    parser.add_argument("--output",       default="metrics_results.json", help="Output JSON file path")
    parser.add_argument("--top-k",        type=int,   default=8,          help="Chunks to retrieve per query (default 8)")
    parser.add_argument("--min-score",    type=float, default=0.40,       help="Relevance threshold (default 0.40)")
    parser.add_argument("--no-llm-judge", action="store_true",            help="Skip LLM faithfulness/relevancy scoring")
    args = parser.parse_args()

    print("=" * 62)
    print("EY Agentic RAG — Evaluation")
    print("=" * 62)

    count = collection_count()
    if count == 0:
        print("ERROR: no chunks indexed. Run index_documents.py first.")
        sys.exit(1)
    print(f"  Indexed chunks : {count}")
    print(f"  Top-K          : {args.top_k}")
    print(f"  Min score      : {args.min_score}")

    if args.test:
        with open(args.test, encoding="utf-8") as f:
            raw = json.load(f)
        test_set = raw
        print(f"  Test set       : {len(test_set)} queries  (from {args.test})")
    else:
        test_set = DEFAULT_TEST_SET
        print(f"  Test set       : {len(test_set)} queries  (built-in default)")

    use_judge = not args.no_llm_judge
    print(f"  LLM judge      : {'enabled (2 extra Groq calls/query)' if use_judge else 'disabled'}")
    print()

    per_query = []
    for i, item in enumerate(test_set, start=1):
        query       = item["query"] if isinstance(item, dict) else item
        rel_sources = item.get("relevant_sources", []) if isinstance(item, dict) else []

        print(f"  [{i:02d}/{len(test_set)}] {query[:65]}...")
        r = evaluate_query(query, rel_sources, args.top_k, args.min_score, use_judge)
        per_query.append(r)

        parts = [
            f"top1={r['top1_score']:.3f}",
            f"chunks={r['num_chunks_above_threshold']}/{args.top_k}",
        ]
        if r["faithfulness"] is not None:
            parts.append(f"faith={r['faithfulness']}/5")
        if r["relevancy"] is not None:
            parts.append(f"rel={r['relevancy']}/5")
        if r["no_answer"]:
            parts.append("NO ANSWER")
        print(f"         {' | '.join(parts)}")

    summary = aggregate(per_query, args.top_k)

    output = {
        "evaluation_date":    datetime.now().isoformat(timespec="seconds"),
        "config": {
            "index_chunks":        count,
            "llm_model":           MODEL,
            "embedding_model":     MODEL_NAME,
            "chunk_size":          "1500 chars (recursive character splitter)",
            "overlap":             "200 chars",
            "top_k":               args.top_k,
            "min_score_threshold": args.min_score,
            "llm_judge_enabled":   use_judge,
        },
        **summary,
        "per_query_results": per_query,
    }

    out_path = os.path.join(os.path.dirname(__file__), args.output)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # ── Summary print ──────────────────────────────────────────────────────
    print()
    print("=" * 62)
    print("RESULTS SUMMARY")
    print("=" * 62)
    ret = summary["retrieval"]
    gen = summary["generation"]
    lat = summary["latency"]

    print(f"  Coverage rate          : {ret['coverage_rate']*100:.0f}%  (queries with results)")
    print(f"  No-answer rate         : {ret['no_answer_rate']*100:.0f}%")
    print(f"  Avg top-1 score        : {ret['avg_top1_score']:.4f}  (cosine similarity)")
    print(f"  Avg mean score (all)   : {ret['avg_mean_score_all']:.4f}")
    print(f"  Avg mean score (above) : {ret['avg_mean_score_above']:.4f}")
    if ret.get("tdr_ratio_in_results") is not None:
        print(f"  TDR ratio in results   : {ret['tdr_ratio_in_results']*100:.0f}%")
    print(f"  Score distribution     : {ret['score_distribution']}")

    hr_key = f"hit_rate_at_{args.top_k}"
    pk_key = f"precision_at_{args.top_k}"
    if ret.get(hr_key) is not None:
        print(f"  Hit Rate@{args.top_k}            : {ret[hr_key]*100:.0f}%")
        print(f"  MRR                    : {ret['mrr']:.4f}")
        print(f"  Precision@{args.top_k}           : {ret[pk_key]:.4f}")

    print()
    if gen["avg_faithfulness"] is not None:
        print(f"  Faithfulness (1-5)     : {gen['avg_faithfulness']:.2f}  "
              f"(scores: {gen['faithfulness_scores']})")
        print(f"  Relevancy    (1-5)     : {gen['avg_relevancy']:.2f}  "
              f"(scores: {gen['relevancy_scores']})")
    else:
        print("  LLM judge              : skipped")

    print()
    print(f"  Avg retrieval latency  : {lat['avg_retrieval_ms']:.0f} ms")
    print(f"  Avg generation latency : {lat['avg_generation_ms']:.0f} ms")
    print(f"  Avg total latency      : {lat['avg_total_ms']:.0f} ms")
    print(f"  [min {lat['min_total_ms']:.0f} ms — max {lat['max_total_ms']:.0f} ms]")
    print()
    print(f"  Full results saved to  : {out_path}")
    print("=" * 62)


if __name__ == "__main__":
    main()
