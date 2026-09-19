"""Canonicalization — common envelope across source formats."""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml
except ImportError:  # pragma: no cover — yaml is a declared dependency
    yaml = None


def _parse_frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
    """Split YAML frontmatter from body. Returns ({}, text) if absent."""
    if not text.startswith("---"):
        return {}, text
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.DOTALL)
    if not match:
        return {}, text
    raw = match.group(1)
    meta: Dict[str, Any] = {}
    if yaml is not None:
        try:
            parsed = yaml.safe_load(raw)
            if isinstance(parsed, dict):
                meta = parsed
        except Exception:
            meta = {}
    if not meta:  # fallback: simple key: value lines
        for line in raw.splitlines():
            m = re.match(r"^([A-Za-z0-9_]+):\s*(.*)$", line)
            if m:
                val = m.group(2).strip().strip("'\"")
                meta[m.group(1)] = val
    return meta, text[match.end():]


def _parse_iso_timestamp(value: Any) -> Optional[float]:
    """Parse an ISO-8601-ish timestamp into epoch seconds (UTC)."""
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in ("null", "none", "false"):
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            continue
    return None


def read_source_file(file_path: Path) -> Optional[Dict]:
    """Read a source file and produce a canonical envelope."""
    suffix = file_path.suffix.lower()

    readers = {
        ".json": _read_json_export,
        ".txt": _read_text,
        ".md": _read_text,
    }

    reader = readers.get(suffix)
    if reader is None:
        raise ValueError(f"unsupported file format: {suffix}")

    return reader(file_path)


def _read_text(file_path: Path) -> Dict:
    """Read a plain text or markdown file (with optional YAML frontmatter)."""
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()
    # PostgreSQL TEXT cannot store NUL bytes; strip them at the boundary.
    raw = raw.replace("\x00", "")
    meta, body = _parse_frontmatter(raw)

    # Reddit export: author / created_utc / permalink / subreddit / type
    author = meta.get("author")
    url = meta.get("permalink") or meta.get("url")
    timestamp = _parse_iso_timestamp(meta.get("created_utc") or meta.get("created"))

    # ChatGPT conversation export: "- **Date**: 2023-03-16" in header
    if timestamp is None:
        m = re.search(r"\*\*Date\*\*:\s*(\d{4}-\d{2}-\d{2})", body[:2000])
        if m:
            timestamp = _parse_iso_timestamp(m.group(1))

    source_type = "document"
    if meta.get("type") == "comment" or meta.get("type") == "submission":
        source_type = "post"
    elif re.search(r"^## Messages\b", body, re.MULTILINE) or "### 👤 User" in body[:3000]:
        source_type = "conversation"

    return _make_envelope(
        text=body,
        source_type=source_type,
        origin=str(file_path),
        metadata={
            "filename": file_path.name,
            **({"author": author} if author else {}),
            **({"url": url} if url else {}),
            **({"subreddit": meta.get("subreddit")} if meta.get("subreddit") else {}),
            **({"reddit_id": meta.get("id")} if meta.get("id") else {}),
            **({"timestamp": timestamp} if timestamp else {}),
        },
        author=author,
        url=url,
        timestamp=timestamp,
    )


def _make_envelope(
    text: str,
    source_type: str,
    origin: str,
    metadata: Dict[str, Any],
    author: Optional[str] = None,
    url: Optional[str] = None,
    timestamp: Optional[float] = None,
) -> Dict:
    """Create the canonical envelope."""
    now = time.time()
    checksum = hashlib.sha256(text.encode()).hexdigest()
    source_id = f"src-{checksum[:32]}"

    return {
        "id": source_id,
        "type": source_type,
        "origin": origin,
        "text": text,
        "url": url,
        "domain": _domain_of(url),
        "author": author,
        "fetched_at": timestamp if timestamp is not None else now,
        "checksum": checksum,
        "parser_version": "1.1.0",
        "normalization_version": "1.1.0",
        "metadata": metadata,
    }


def _domain_of(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    m = re.match(r"https?://([^/]+)/", url + "/")
    return m.group(1).lower() if m else None


def _read_json_export(file_path: Path) -> Dict:
    """Read a JSON export (ChatGPT, Reddit, etc.)."""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Detect format from structure
    if isinstance(data, list) and data and isinstance(data[0], dict):
        if "mapping" in data[0]:
            return _parse_chatgpt_export(data, file_path)
        if "selftext" in data[0] or "title" in data[0]:
            return _parse_reddit_export(data, file_path)

    # Generic JSON — treat as a single document
    text = json.dumps(data, ensure_ascii=False, indent=2)
    return _make_envelope(
        text=text,
        source_type="json",
        origin=str(file_path),
        metadata={"format": "generic_json"},
    )


def _parse_chatgpt_export(data: List[Dict], file_path: Path) -> Dict:
    """Parse a ChatGPT export."""
    parts = []
    for conv in data:
        mapping = conv.get("mapping", {})
        for node_id, node in mapping.items():
            message = node.get("message", {})
            if message:
                author = message.get("author", {}).get("role", "unknown")
                content = message.get("content", {})
                if isinstance(content, dict):
                    text = content.get("parts", [])
                    text = " ".join(text) if isinstance(text, list) else str(text)
                else:
                    text = str(content)
                if text:
                    parts.append(f"{author}: {text}")

    text = "\n\n".join(parts)
    return _make_envelope(
        text=text,
        source_type="conversation",
        origin=str(file_path),
        metadata={"format": "chatgpt_export"},
    )


def _parse_reddit_export(data: List[Dict], file_path: Path) -> Dict:
    """Parse a Reddit export."""
    parts = []
    for post in data:
        title = post.get("title", "")
        selftext = post.get("selftext", "")
        if title:
            parts.append(f"title: {title}")
        if selftext:
            parts.append(f"body: {selftext}")
        # Comments would be nested; this is a simplified version

    text = "\n\n".join(parts)
    return _make_envelope(
        text=text,
        source_type="post",
        origin=str(file_path),
        metadata={"format": "reddit_export"},
    )


def structural_parse(source: Dict) -> List[Dict]:
    """Parse a canonical source into structural units."""
    parser_map = {
        "conversation": _parse_conversation,
        "post": _parse_post,
        "document": _parse_document,
    }

    parser = parser_map.get(source["type"], _parse_document)
    return parser(source)


def _parse_conversation(source: Dict) -> List[Dict]:
    """Parse a conversation into turns."""
    units = []
    text = source["text"]
    turns = text.split("\n\n")

    offset = 0
    for i, turn in enumerate(turns):
        if not turn.strip():
            continue
        unit_id = f"su-{hashlib.sha256((source['id'] + str(i) + str(offset)).encode()).hexdigest()[:32]}"
        units.append({
            "id": unit_id,
            "source_id": source["id"],
            "type": "turn",
            "text": turn,
            "offset": offset,
            "span_start": offset,
            "span_end": offset + len(turn),
            "parent_id": None,
            "metadata": {"turn_index": i},
        })
        offset += len(turn) + 2  # +2 for the \n\n separator

    return units


def _parse_post(source: Dict) -> List[Dict]:
    """Parse a post into structural units."""
    units = []
    text = source["text"]
    # Split on double newlines for paragraphs
    paragraphs = text.split("\n\n")

    offset = 0
    for i, para in enumerate(paragraphs):
        if not para.strip():
            continue
        unit_id = f"su-{hashlib.sha256((source['id'] + str(i) + str(offset)).encode()).hexdigest()[:32]}"
        units.append({
            "id": unit_id,
            "source_id": source["id"],
            "type": "paragraph",
            "text": para,
            "offset": offset,
            "span_start": offset,
            "span_end": offset + len(para),
            "parent_id": None,
            "metadata": {"paragraph_index": i},
        })
        offset += len(para) + 2

    return units


def _parse_document(source: Dict) -> List[Dict]:
    """Parse a document into structural units (paragraphs)."""
    units = []
    text = source["text"]
    paragraphs = text.split("\n\n")

    offset = 0
    for i, para in enumerate(paragraphs):
        if not para.strip():
            continue
        unit_id = f"su-{hashlib.sha256((source['id'] + str(i) + str(offset)).encode()).hexdigest()[:32]}"
        units.append({
            "id": unit_id,
            "source_id": source["id"],
            "type": "paragraph",
            "text": para,
            "offset": offset,
            "span_start": offset,
            "span_end": offset + len(para),
            "parent_id": None,
            "metadata": {"paragraph_index": i},
        })
        offset += len(para) + 2

    return units


def normalize_text(text: str) -> str:
    """Normalize text for deduplication."""
    # Lowercase, strip whitespace, collapse multiple spaces
    normalized = " ".join(text.lower().split())
    return normalized
