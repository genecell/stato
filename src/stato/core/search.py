"""Search — shared lexical scoring for registry search and local `stato find`.

Deliberately embedding-free: tokenized multi-term matching with fuzzy
fallback (difflib) covers real query patterns ("qc filtering", "batch
effect", typos) with zero extra dependencies.
"""
from __future__ import annotations

import difflib
import re

_TOKEN_RE = re.compile(r"[a-z0-9]+")

FUZZY_THRESHOLD = 0.8


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def score_text(query: str, text: str) -> float:
    """Score how well text matches a (possibly multi-term) query.

    Per query token: 1.0 for an exact token match, substring credit 0.75,
    fuzzy credit up to 0.5. Total is the mean over query tokens, so a
    two-term query needs both terms to score well.
    """
    query_tokens = tokenize(query)
    if not query_tokens:
        return 0.0
    text_tokens = tokenize(text)
    if not text_tokens:
        return 0.0
    text_token_set = set(text_tokens)

    total = 0.0
    for qt in query_tokens:
        if qt in text_token_set:
            total += 1.0
            continue
        if any(qt in tt or tt in qt for tt in text_token_set if len(qt) >= 3):
            total += 0.75
            continue
        best = max(
            (difflib.SequenceMatcher(None, qt, tt).ratio() for tt in text_token_set),
            default=0.0,
        )
        if best >= FUZZY_THRESHOLD:
            total += 0.5 * best
    return total / len(query_tokens)


def search_items(query: str, items: list[dict], weights: dict[str, float]) -> list[tuple[float, dict]]:
    """Score dicts against a query. weights maps item key -> weight.

    List-valued fields are scored per element (summed). Returns
    (score, item) pairs sorted descending, zero-score items dropped.
    """
    results = []
    for item in items:
        score = 0.0
        for key, weight in weights.items():
            value = item.get(key, "")
            if isinstance(value, (list, tuple)):
                score += weight * sum(score_text(query, str(v)) for v in value)
            else:
                score += weight * score_text(query, str(value))
        if score > 0:
            results.append((score, item))
    results.sort(key=lambda pair: pair[0], reverse=True)
    return results
