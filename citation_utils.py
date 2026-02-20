"""
Utilities to extract and format citations from tool metadata.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterator, List, Optional, Tuple
from urllib.parse import quote


CITATION_BASE_URL = "http://127.0.0.1:8008/"

_DOC_KEYS = ("document_name", "source")
_PAGE_KEYS = ("page_label", "page_number", "page")


def build_citation_url(document_name: str, page_number: int) -> str:
    """
    Build URL in the form:
    http://127.0.0.1:8008/<ENCODED_DOC_NAME_NO_PDF>/pageNNNN.png
    """
    if not document_name:
        return ""
    doc_no_pdf = re.sub(r"\.pdf$", "", document_name, flags=re.IGNORECASE)
    encoded = quote(doc_no_pdf, safe="")
    return f"{CITATION_BASE_URL}{encoded}/page{page_number:04d}.png"


def _pick_first(d: Dict[str, Any], keys: Tuple[str, ...]) -> Optional[Any]:
    for key in keys:
        if key in d and d[key] not in (None, ""):
            return d[key]
    return None


def _parse_page_number(raw: Any) -> Optional[int]:
    if isinstance(raw, int):
        return raw if raw >= 0 else None
    if isinstance(raw, float):
        val = int(raw)
        return val if val >= 0 else None
    if isinstance(raw, str):
        m = re.search(r"\d+", raw)
        if not m:
            return None
        return int(m.group(0))
    return None


def _extract_from_node(node: Any) -> Iterator[Tuple[str, int]]:
    if isinstance(node, dict):
        meta = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}

        doc = _pick_first(meta, _DOC_KEYS) or _pick_first(node, _DOC_KEYS)
        page_raw = _pick_first(meta, _PAGE_KEYS) or _pick_first(node, _PAGE_KEYS)
        page = _parse_page_number(page_raw)

        if isinstance(doc, str) and doc.strip() and page is not None:
            yield doc.strip(), page

        for value in node.values():
            yield from _extract_from_node(value)

    elif isinstance(node, list):
        for item in node:
            yield from _extract_from_node(item)


def extract_citations_from_metadata(metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract unique (document_name, page) citations from metadata.tool_results.
    """
    tool_results = metadata.get("tool_results", []) if isinstance(metadata, dict) else []

    seen: set[Tuple[str, int]] = set()
    citations: List[Dict[str, Any]] = []

    for tr in tool_results:
        if not isinstance(tr, dict):
            continue
        payload = tr.get("result")
        if payload is None:
            continue

        for doc_name, page in _extract_from_node(payload):
            key = (doc_name, page)
            if key in seen:
                continue
            seen.add(key)
            citations.append(
                {
                    "document_name": doc_name,
                    "page_number": page,
                    "url": build_citation_url(doc_name, page),
                }
            )

    return citations


def render_citations_markdown(citations: List[Dict[str, Any]]) -> str:
    """
    Build a markdown section with clickable links.
    """
    if not citations:
        return ""

    lines = ["## Citations"]
    for c in citations:
        doc = c["document_name"]
        page = c["page_number"]
        url = c["url"]
        lines.append(f"- [{doc} - page {page}]({url})")
    return "\n".join(lines)
