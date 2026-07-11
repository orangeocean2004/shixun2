"""Unified evaluation entry point — dual-mode.

LongBench mode : JSONL with context/input/answers → use built-in QA pairs
Regular mode   : any other file → LLM generates QA pairs → evaluate

All three strategies (Smart / Heading / Fixed) are compared head-to-head
using deterministic answer matching for relevance judgment.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

from backend.app.services.segmenting import SegmentConfig, segment_text
from backend.app.services.evaluation import fixed_length_segment, heading_based_segment
from backend.app.services.retrieval import EmbeddingStore


# ── Detection ────────────────────────────────────────────────


def is_longbench_jsonl(raw_bytes: bytes) -> bool:
    """Check whether uploaded bytes look like a LongBench JSONL file."""
    try:
        text = raw_bytes.decode("utf-8")
        first_line = text.split("\n")[0].strip()
        if not first_line:
            return False
        obj = json.loads(first_line)
        return (
            isinstance(obj, dict)
            and "context" in obj
            and "input" in obj
            and "answers" in obj
        )
    except Exception:
        return False


def parse_longbench_samples(raw_bytes: bytes, max_samples: int = 50) -> list[dict]:
    """Parse LongBench JSONL bytes into sample dicts."""
    text = raw_bytes.decode("utf-8")
    samples: list[dict] = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if obj.get("context") and obj.get("input") and obj.get("answers"):
                samples.append(obj)
        except json.JSONDecodeError:
            continue
        if max_samples and len(samples) >= max_samples:
            break
    return samples


# ── Answer matching ──────────────────────────────────────────


def _norm(text: str) -> str:
    result = []
    for ch in text:
        if ch.isalnum() or ('一' <= ch <= '鿿'):
            result.append(ch)
    return ''.join(result).lower()


def _answer_in_chunks(chunks: list[dict], answers: list[str]) -> bool:
    combined_raw = '\n'.join(c.get('content', '') for c in chunks)
    combined = _norm(combined_raw)
    for ans in answers:
        answer = ans.strip()
        a = _norm(answer)
        if len(a) >= 2 and a in combined:
            return True
        if _keyword_overlap_relevant(combined_raw, answer):
            return True
        if _semantic_answer_relevant(combined_raw, answer):
            return True
    return False


def _keyword_overlap_relevant(content: str, answer: str) -> bool:
    terms = _answer_terms(answer)
    if not terms:
        return False
    normalized_content = _norm(content)
    hits = sum(1 for term in terms if _norm(term) in normalized_content)
    if len(terms) == 1:
        return hits == 1
    return hits >= 2 and hits / len(terms) >= 0.34


def _semantic_answer_relevant(content: str, answer: str) -> bool:
    if len(_norm(answer)) < 8 or len(_norm(content)) < 8:
        return False
    try:
        from backend.app.services.retrieval.embedding import embedding_similarity

        score = embedding_similarity(answer[:500], content[:1500])
    except Exception:
        return False
    return score is not None and score >= 0.42


def _answer_terms(answer: str) -> list[str]:
    stopwords = {
        '本文', '文档', '内容', '部分', '核心', '主要', '进行', '通过',
        '以及', '可以', '需要', '实现', '支持', '相关', '一个', '一种',
        '如何', '什么', '其中', '使用', '用于', '要求', '包括', '提升',
    }
    terms: list[str] = []
    import re

    for term in re.findall(r'[A-Za-z][A-Za-z0-9_@.+-]{1,}', answer or ''):
        if term not in terms:
            terms.append(term)

    try:
        import jieba
        candidates = jieba.lcut(answer or '')
    except Exception:
        candidates = re.findall(r'[\u4e00-\u9fff]{2,6}', answer or '')

    for raw in candidates:
        term = raw.strip(' ，。！？；：、()（）[]【】《》"\'')
        if not term or term in stopwords:
            continue
        if re.fullmatch(r'[\u4e00-\u9fff]', term):
            continue
        if len(term) >= 2 and term not in terms:
            terms.append(term)
        if len(terms) >= 12:
            break
    return terms


def _strategy_summary(strategy: str, chunks: list[dict], metrics: dict[str, float]) -> dict[str, Any]:
    total_chars = sum(int(c.get('char_count') or len(c.get('content', ''))) for c in chunks)
    avg_chunk_size = round(total_chars / len(chunks), 1) if chunks else 0.0
    return {
        'strategy': strategy,
        'label': strategy,
        'chunk_count': len(chunks),
        'avg_chunk_size': avg_chunk_size,
        **metrics,
    }


def _compute_metrics(ranked: list[dict], answers: list[str]) -> dict[str, float]:
    ks = (1, 3, 5)
    hits = [_answer_in_chunks(ranked[:k], answers) for k in ks]
    total = 1 if hits[-1] else 0
    result: dict[str, float] = {}
    for i, k in enumerate(ks):
        rel = 1 if hits[i] else 0
        result['recall_at_%d' % k] = rel / total if total > 0 else 0.0
        result['precision_at_%d' % k] = rel / k
        dcg = 1.0 / math.log2(k + 1) if rel else 0.0
        idcg = 1.0 / math.log2(2) if total > 0 else 0.0
        result['ndcg_at_%d' % k] = dcg / idcg if idcg > 0 else 0.0
    for rank, c in enumerate(ranked, 1):
        if _answer_in_chunks([c], answers):
            result['mrr'] = 1.0 / rank
            break
    else:
        result['mrr'] = 0.0
    return result


# ── Core: three-strategy comparison ──────────────────────────


def _segment_three_ways(raw_text: str) -> dict[str, list[dict]]:
    """Segment one document with all three strategies."""
    config = SegmentConfig()

    smart = segment_text(raw_text, doc_id='eval_smart', config=config)['chunks']

    h_objs = heading_based_segment(
        raw_text, doc_id='eval_heading',
        min_chars=config.min_chars, target_chars=config.target_chars,
        max_chars=config.max_chars,
    )
    heading = [
        {'chunk_id': c.chunk_id, 'content': c.content, 'title_path': c.title_path,
         'chunk_type': c.chunk_type, 'char_count': c.char_count,
         'source_refs': c.source_refs, 'quality_flags': c.quality_flags}
        for c in h_objs
    ]

    f_objs = fixed_length_segment(raw_text, doc_id='eval_fixed')
    fixed = [
        {'chunk_id': c.chunk_id, 'content': c.content, 'title_path': c.title_path,
         'chunk_type': c.chunk_type, 'char_count': c.char_count,
         'source_refs': c.source_refs, 'quality_flags': c.quality_flags}
        for c in f_objs
    ]

    return {'smart': smart, 'heading': heading, 'fixed': fixed}


def _run_one_qa(chunks_by_strategy: dict, question: str, answers: list[str]) -> dict:
    """Evaluate one QA pair against all three strategies."""
    store = EmbeddingStore()
    result = {'question': question, 'answers': answers, 'hits': {}}
    for st in ['smart', 'heading', 'fixed']:
        chunks = chunks_by_strategy[st]
        if not chunks:
            result['hits'][st] = False
            continue
        store.add_chunks(st, chunks)
        hits = store.search(st, question, top_k=5)
        result['hits'][st] = _answer_in_chunks(hits, answers)
    return result


def _aggregate(per_qa: list[dict]) -> dict:
    """Aggregate per-question results into strategy-level metrics."""
    accum = {s: {'recall_at_1': [], 'recall_at_3': [], 'recall_at_5': [],
                  'precision_at_5': [], 'ndcg_at_5': [], 'mrr': []}
             for s in ['smart', 'heading', 'fixed']}

    for qr in per_qa:
        question = qr['question']
        answers = qr['answers']
        # Re-run each QA through _compute_metrics for detailed accum
        # (we already have hit/miss, but need full metrics)
        # Use a simpler approach: from hit/miss, compute per-QA metrics
        store = EmbeddingStore()
        all_chunks = qr.get('_chunks', {})
        for st in ['smart', 'heading', 'fixed']:
            chunks = all_chunks.get(st, [])
            if not chunks:
                continue
            store.add_chunks(st, chunks)
            ranked = store.search(st, question, top_k=5)
            m = _compute_metrics(ranked, answers)
            for k in accum[st]:
                accum[st][k].append(m.get(k, 0.0))

    def avg(v): return sum(v) / len(v) if v else 0.0
    return {st: {k: avg(accum[st][k]) for k in accum[st]} for st in accum}


# ── Public API ───────────────────────────────────────────────


def evaluate_longbench(raw_bytes: bytes, max_samples: int = 30) -> dict[str, Any]:
    """Run three-strategy evaluation on uploaded LongBench JSONL data.

    Returns a dict with keys: mode, samples, question_results, strategies, gains
    """
    samples = parse_longbench_samples(raw_bytes, max_samples=max_samples)
    if not samples:
        return {'mode': 'longbench', 'error': 'No valid LongBench samples found'}

    per_qa: list[dict] = []
    for i, s in enumerate(samples):
        ctx, q, ans = s['context'], s['input'], s['answers']
        if not ctx.strip() or not q.strip() or not ans:
            continue
        try:
            chunks_by_st = _segment_three_ways(ctx)
        except Exception:
            continue
        qr = _run_one_qa(chunks_by_st, q, ans)
        qr['_chunks'] = chunks_by_st  # keep for aggregation
        per_qa.append(qr)

    strategies = _aggregate(per_qa)

    # Gains
    s = {st: strategies[st] for st in ['smart', 'heading', 'fixed']}
    total_gain = round((s['smart']['recall_at_5'] - s['fixed']['recall_at_5']) * 100, 1)
    structure_gain = round((s['heading']['recall_at_5'] - s['fixed']['recall_at_5']) * 100, 1)
    semantic_gain = round((s['smart']['recall_at_5'] - s['heading']['recall_at_5']) * 100, 1)

    # Per-question details (without _chunks)
    details = [
        {'question': qr['question'], 'answers': qr['answers'], 'hits': qr['hits']}
        for qr in per_qa
    ]

    return {
        'mode': 'longbench',
        'samples': len(samples),
        'processed': len(per_qa),
        'strategies': [
            _strategy_summary(st, _segment_three_ways(samples[0]['context'])[st] if samples else [], strategies[st])
            for st in ['smart', 'heading', 'fixed']
        ],
        'question_results': details,
        'structure_gain': structure_gain,
        'semantic_gain': semantic_gain,
        'total_gain': total_gain,
    }


def evaluate_with_qa_pairs(raw_text: str, qa_pairs: list[dict]) -> dict[str, Any]:
    """Run three-strategy evaluation using provided QA pairs (from LLM generation)."""

    try:
        chunks_by_st = _segment_three_ways(raw_text)
    except Exception as e:
        return {'mode': 'llm_qa', 'error': f'Segmentation failed: {e}'}

    per_qa: list[dict] = []
    for pair in qa_pairs:
        q = pair.get('question', '').strip()
        ans = [pair.get('answer', '').strip()]
        if not q or not ans[0]:
            continue
        qr = _run_one_qa(chunks_by_st, q, ans)
        qr['_chunks'] = chunks_by_st
        per_qa.append(qr)

    strategies = _aggregate(per_qa)
    s = {st: strategies[st] for st in ['smart', 'heading', 'fixed']}

    details = [
        {'question': qr['question'], 'answers': qr['answers'], 'hits': qr['hits']}
        for qr in per_qa
    ]

    return {
        'mode': 'llm_qa',
        'processed': len(per_qa),
        'strategies': [
            _strategy_summary(st, chunks_by_st[st], strategies[st])
            for st in ['smart', 'heading', 'fixed']
        ],
        'question_results': details,
        'total_gain': round((s['smart']['recall_at_5'] - s['fixed']['recall_at_5']) * 100, 1),
        'structure_gain': round((s['heading']['recall_at_5'] - s['fixed']['recall_at_5']) * 100, 1),
        'semantic_gain': round((s['smart']['recall_at_5'] - s['heading']['recall_at_5']) * 100, 1),
    }

