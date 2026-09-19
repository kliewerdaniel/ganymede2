"""Contradictions — first-class nodes in the Evidence Graph."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Sequence

STOPWORDS = set(
    """a an the and or but if then than that this these those of to in on for with as by from at is are was were be been
    being it its it's we you they he she i our your his her my me us them so such not no nor only own same too very
    can will just should now here there what which who whom when where why how all any both each few more most other some
    do does did doing have has had having would could may might must about into over under again further once""".split()
)

NEGATION_CUES = ("not ", "n't", " no ", "never", "fails", "lacks", "cannot", "without")


def _content_words(text: str) -> set:
    toks = re.findall(r"[a-z0-9']+", text.lower())
    return {t for t in toks if t not in STOPWORDS and len(t) > 2}


def _polarity(text: str) -> int:
    low = text.lower()
    return -1 if any(c in low for c in NEGATION_CUES) else 1


def overlap(a: str, b: str) -> float:
    wa, wb = _content_words(a), _content_words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def contradiction_id(a: str, b: str) -> str:
    key = "|".join(sorted([a, b]))
    return "con-" + hashlib.sha256(key.encode()).hexdigest()[:32]


GENERIC = {
    "ai", "llm", "model", "data", "system", "code", "tool", "user", "thing",
    "work", "time", "way", "post", "project", "file", "test", "run", "graph",
    "claim", "answer", "question", "result", "number", "state", "part", "kind",
    "type", "use", "using", "used", "set", "make", "made", "get", "got",
    "day", "year", "world", "people", "person", "group", "case", "point",
}


def mine_contradictions(
    claims: Sequence[Dict],
    *,
    min_overlap: float = 0.30,
) -> List[Dict]:
    """Find opposed claim pairs."""
    by_word: Dict[str, List[Dict]] = defaultdict(list)
    for c in claims:
        for w in _content_words(c["text"]):
            by_word[w].append(c)

    seen: set = set()
    out: List[Dict] = []
    for word, group in by_word.items():
        if len(group) < 2:
            continue
        if word in GENERIC:
            continue
        # Scale guard: a word shared by thousands of claims (e.g. a person's
        # name across a large corpus) yields O(n²) pairs. Skip such groups —
        # a contradiction needs topical overlap, not a single common token.
        if len(group) > 200:
            continue
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if len(out) > 400:
                    break
                if a["id"] == b["id"]:
                    continue
                if _polarity(a["text"]) == _polarity(b["text"]):
                    continue
                ov = overlap(a["text"], b["text"])
                if ov < min_overlap:
                    continue
                if set(a.get("source_ids") or []) == set(b.get("source_ids") or []) and ov > 0.85:
                    continue
                if a["id"] > b["id"]:
                    a, b = b, a
                cid = contradiction_id(a["id"], b["id"])
                if cid in seen:
                    continue
                seen.add(cid)
                anchor = _content_words(a["text"]) & _content_words(b["text"])
                out.append({
                    "id": cid,
                    "anchor_words": sorted(anchor),
                    "entity_id": (a.get("entity_ids") or [None])[0],
                    "claim_a_id": a["id"],
                    "claim_b_id": b["id"],
                    "text_a": a["text"],
                    "text_b": b["text"],
                    "overlap": round(ov, 3),
                    "sources_a": a.get("source_ids") or [],
                    "sources_b": b.get("source_ids") or [],
                    "status": "open",
                    "resolution": None,
                    "resolved_by": None,
                })
    return out
