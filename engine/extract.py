"""Extract — deterministic compile-time extraction for source records."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple


ASSERTION_CUES = (
    "is", "are", "was", "were", "means", "requires", "causes", "prevents",
    "enables", "produces", "shows", "proves", "demonstrates", "outperforms",
    "beats", "must", "should", "cannot", "can't", "never", "always",
    "supports", "lacks", "does not", "doesn't", "isn't", "aren't",
    "do not", "don't", "did not", "didn't", "has", "have", "had",
)

NEGATION_CUES = ("not ", "n't", " no ", "never", "fails", "lacks", "cannot", "without")

HEDGES = ("may", "might", "could", "possibly", "perhaps", "suggests", "seems", "appears")

STOPWORDS = set(
    """a an the and or but if then than that this these those of to in on for with as by from at is are was were be been
    being it its it's we you they he she i our your his her my me us them so such not no nor only own same too very
    can will just should now here there what which who whom when where why how all any both each few more most other some
    do does did doing have has had having would could may might must about into over under again further once""".split()
)

_PROPER = re.compile(r"\b([A-Z][A-Za-z0-9]+(?:[ -][A-Z][A-Za-z0-9]+){0,3})\b")
_ACRONYM = re.compile(r"\b([A-Z]{2,8})\b")
_CODE_TOKEN = re.compile(r"`([^`\n]{2,48})`")
_URLISH = re.compile(r"https?://[^\s)]+")


def entity_id(label: str) -> str:
    return "ent-" + hashlib.sha256(normalise_entity(label).encode()).hexdigest()[:32]


def claim_id(text: str, source_id: str) -> str:
    """Claim identity is the normalized assertion text alone.

    The same sentence observed in different sources must resolve to the
    SAME claim so that corroboration and independence terms can function.
    source_id is accepted for signature compatibility but deliberately
    excluded from the hash.
    """
    return "clm-" + hashlib.sha256(normalise_entity(text).encode()).hexdigest()[:32]


def normalise_entity(label: str) -> str:
    s = label.strip().strip(".,;:()[]\"'").lower()
    s = re.sub(r"[_\-]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    toks = s.split()
    if toks and len(toks[-1]) > 4 and toks[-1].endswith("s") and not toks[-1].endswith("ss"):
        toks[-1] = toks[-1][:-1]
    return " ".join(toks)


@dataclass
class Extraction:
    source_id: str = ""
    source_checksum: str = ""
    entities: List[Dict] = field(default_factory=list)
    claims: List[Dict] = field(default_factory=list)
    evidence: List[Dict] = field(default_factory=list)
    relationships: List[Dict] = field(default_factory=list)


def _sentences(text: str) -> List[Tuple[int, str]]:
    out = []
    pos = 0
    for part in re.split(r"(?<=[.!?])\s+|\n{2,}", text):
        idx = text.find(part, pos)
        if idx < 0:
            idx = pos
        pos = idx + len(part)
        s = part.strip()
        if s:
            out.append((idx, s))
    return out


def is_claim(sentence: str) -> bool:
    low = sentence.lower()
    if len(sentence) < 25 or len(sentence) > 400:
        return False
    if sentence.lstrip().startswith(("#", "```", "|", ">", "!", "- [")):
        return False
    words = low.split()
    if len(words) < 5:
        return False
    return any(f" {c} " in f" {low} " or low.startswith(c + " ") for c in ASSERTION_CUES)


def stance_of(sentence: str) -> str:
    low = sentence.lower()
    return "contradict" if any(c in low for c in NEGATION_CUES) else "support"


def hedged(sentence: str) -> bool:
    low = sentence.lower()
    return any(f" {h} " in f" {low} " for h in HEDGES)


def extract_entities(text: str, vocabulary: Optional[Sequence[str]] = None) -> Dict[str, int]:
    counts: Dict[str, int] = {}

    def bump(lbl: str) -> None:
        n = normalise_entity(lbl)
        if not n or n in STOPWORDS or len(n) < 3:
            return
        if n.isdigit():
            return
        counts[n] = counts.get(n, 0) + 1

    body = _URLISH.sub(" ", text)
    for m in _CODE_TOKEN.finditer(body):
        bump(m.group(1))
    for m in _ACRONYM.finditer(body):
        bump(m.group(1))
    for _, sent in _sentences(body):
        for m in _PROPER.finditer(sent):
            span = m.group(1)
            if m.start() == 0 and " " not in span:
                continue
            bump(span)
    if vocabulary:
        low = body.lower()
        for term in vocabulary:
            n = normalise_entity(term)
            if n and n in low:
                counts[n] = counts.get(n, 0) + low.count(n)
    return counts


def extract_source(
    source: Dict,
    *,
    structural_units: List[Dict] = None,
    vocabulary: Optional[Sequence[str]] = None,
    max_claims: int = 60,
    parser_version: str = "1.0.0",
) -> Extraction:
    """Deterministic compile-time extraction for ONE source record."""
    sid = source["id"]
    text = source.get("text", "")
    domain = source.get("domain") or ""
    author = source.get("author") or ""
    ts = source.get("fetched_at")

    ex = Extraction(
        source_id=sid,
        source_checksum=source.get("checksum", ""),
    )

    ent_counts = extract_entities(text, vocabulary)
    threshold = 2 if len(text) > 6000 else 1
    kept = {k: v for k, v in ent_counts.items() if v >= threshold}
    if len(kept) > 120:
        kept = dict(sorted(kept.items(), key=lambda kv: -kv[1])[:120])
    for label, n in kept.items():
        ex.entities.append({
            "id": entity_id(label),
            "label": label,
            "mentions": n,
            "sources": [sid],
        })

    ent_labels = set(kept)
    sents = _sentences(text)
    claims_made = 0
    for offset, sent in sents:
        if claims_made >= max_claims:
            break
        if not is_claim(sent):
            continue
        cid = claim_id(sent, sid)
        mentioned = sorted(
            {entity_id(l) for l in ent_labels if l in normalise_entity(sent)}
        )
        ex.claims.append({
            "id": cid,
            "text": sent,
            "source_ids": [sid],
            "entity_ids": mentioned,
            "hedged": hedged(sent),
            "stance": stance_of(sent),
        })
        ex.evidence.append({
            "id": "ev-" + hashlib.sha256((cid + sid + str(offset)).encode()).hexdigest()[:32],
            "claim_id": cid,
            "source_id": sid,
            "domain": domain,
            "author": author,
            "stance": stance_of(sent),
            "quote": sent[:400],
            "offset": offset,
            "timestamp": ts,
            "reliability": source.get("reliability"),
            "source_checksum": source.get("checksum"),
        })
        claims_made += 1
        for i, a in enumerate(mentioned):
            for b in mentioned[i + 1:]:
                ex.relationships.append({
                    "id": f"rel-{a}-{b}",
                    "source_entity": a,
                    "target_entity": b,
                    "type": "co_mentioned",
                    "co_count": 1,
                    "source_ids": [sid],
                    "claim_ids": [cid],
                })
    return ex
