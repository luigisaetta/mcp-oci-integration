"""
brave_search_client.py

Minimal Brave Search API client for Python.

Usage:
    export BRAVE_API_KEY=sk_...
    from brave_search_client import BraveSearchClient

    client = BraveSearchClient()
    results, meta = client.search("Oracle AI Agents", count=5)
"""

from __future__ import annotations
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Literal
import requests

Vertical = Literal["web", "news", "images"]

BRAVE_ENDPOINTS: Dict[Vertical, str] = {
    "web": "https://api.search.brave.com/res/v1/web/search",
    "news": "https://api.search.brave.com/res/v1/news/search",
    "images": "https://api.search.brave.com/res/v1/images/search",
}


@dataclass
class BraveSearchResult:
    """
    Represents a single Brave Search result.
    """

    title: str
    url: str
    snippet: Optional[str] = None
    site: Optional[str] = None
    language: Optional[str] = None
    published: Optional[str] = None
    rank: Optional[int] = None


class BraveSearchError(RuntimeError):
    """
    Represents an error during Brave Search API interaction.
    """


class BraveSearchClient:
    """
    Simple Brave Search client with retries and normalization.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout_s: float = 10.0,
        max_retries: int = 3,
        backoff_base_s: float = 0.7,
    ) -> None:
        self.api_key = api_key or os.getenv("BRAVE_API_KEY")
        if not self.api_key:
            raise BraveSearchError("Missing Brave API key (set BRAVE_API_KEY).")
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.backoff_base_s = backoff_base_s
        self._headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self.api_key,
            "User-Agent": "brave-search-client/1.0",
        }

    def search(
        self,
        q: str,
        *,
        vertical: Vertical = "web",
        count: int = 10,
        offset: int = 0,
        safesearch: Literal["off", "moderate", "strict"] = "moderate",
        country: Optional[str] = None,
        ui_lang: Optional[str] = None,
        freshness: Optional[str] = None,
    ) -> Tuple[List[BraveSearchResult], Dict[str, Any]]:
        """
        Perform a Brave Search query.
        """
        if vertical not in BRAVE_ENDPOINTS:
            raise ValueError(f"Invalid vertical: {vertical}")

        count = max(1, min(20, count))
        params: Dict[str, Any] = {
            "q": q,
            "count": count,
            "offset": offset,
            "safesearch": safesearch,
        }
        if country:
            params["country"] = country
        if ui_lang:
            params["ui_lang"] = ui_lang
        if freshness:
            params["freshness"] = freshness

        data = self._request_json("GET", BRAVE_ENDPOINTS[vertical], params)
        results = self._normalize_results(data, vertical, offset)
        meta = self._extract_meta(data, vertical, offset, count)
        return results, meta

    # --- internal helpers -------------------------------------------------

    def _request_json(
        self, method: str, url: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        for attempt in range(self.max_retries + 1):
            try:
                r = requests.request(
                    method,
                    url,
                    headers=self._headers,
                    params=params,
                    timeout=self.timeout_s,
                )
                if r.status_code == 429 or 500 <= r.status_code < 600:
                    raise BraveSearchError(f"HTTP {r.status_code}: {r.text[:200]}")
                r.raise_for_status()
                return r.json()
            except Exception as e:
                if attempt == self.max_retries:
                    raise BraveSearchError(
                        f"Request failed after {self.max_retries} retries: {e}"
                    )
                time.sleep(self.backoff_base_s * (2**attempt))
        return {}

    @staticmethod
    def _normalize_results(
        payload: Dict[str, Any], vertical: Vertical, offset: int
    ) -> List[BraveSearchResult]:
        key = {"web": "web", "news": "news", "images": "images"}[vertical]
        arr = (payload.get(key) or {}).get("results") or []
        results: List[BraveSearchResult] = []
        for i, item in enumerate(arr):
            results.append(
                BraveSearchResult(
                    title=item.get("title") or item.get("name", ""),
                    url=item.get("url") or item.get("link", ""),
                    snippet=item.get("description") or item.get("snippet"),
                    site=item.get("site") or item.get("source"),
                    language=item.get("language"),
                    published=item.get("published"),
                    rank=offset + i + 1,
                )
            )
        return [r for r in results if r.title and r.url]

    @staticmethod
    def _extract_meta(
        payload: Dict[str, Any], vertical: Vertical, offset: int, count: int
    ) -> Dict[str, Any]:
        bucket = payload.get(vertical) or {}
        total = bucket.get("total") or bucket.get("estimatedResults")
        return {
            "vertical": vertical,
            "offset": offset,
            "count": count,
            "total_estimated": total,
        }
