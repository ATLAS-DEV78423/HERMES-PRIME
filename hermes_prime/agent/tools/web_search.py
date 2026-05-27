from __future__ import annotations

from typing import Any

import httpx


def web_search(query: str, num_results: int = 5) -> str:
    """Search the web using DuckDuckGo."""
    try:
        from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=num_results))
        if not results:
            return "No results found."
        formatted = []
        for i, r in enumerate(results[:num_results], 1):
            title = r.get("title", "")
            link = r.get("href", "")
            snippet = r.get("body", "")
            formatted.append(f"{i}. [{title}]({link})\n   {snippet[:200]}")
        return "\n\n".join(formatted)
    except ImportError:
        return "DuckDuckGo search not available. Install: pip install duckduckgo_search"
    except Exception as e:
        return f"Search error: {e}"


def web_fetch(url: str) -> str:
    """Fetch and extract content from a URL."""
    try:
        resp = httpx.get(url, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        content = resp.text
        import re

        text = re.sub(r"<[^>]+>", " ", content)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:5000]
    except Exception as e:
        return f"Fetch error: {e}"


def get_search_schema() -> dict[str, Any]:
    return {
        "name": "web_search",
        "description": "Search the web for information",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"},
                "num_results": {"type": "integer", "description": "Number of results (default 5)", "default": 5},
            },
            "required": ["query"],
        },
    }


def get_fetch_schema() -> dict[str, Any]:
    return {
        "name": "web_fetch",
        "description": "Fetch and extract text content from a URL",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to fetch"},
            },
            "required": ["url"],
        },
    }


__all__ = ["web_search", "web_fetch", "get_search_schema", "get_fetch_schema"]
