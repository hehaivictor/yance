from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests
from bs4 import BeautifulSoup

from ..config import settings
from .parsing import domain_from_url, extract_page_date


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)


def school_domain_hints(school_name: str) -> list[str]:
    if "武汉大学" in school_name:
        return ["whu.edu.cn"]
    return []


def request_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def search_duckduckgo(query: str, max_results: int = 6) -> list[dict[str, Any]]:
    session = request_session()
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    response = session.get(url, timeout=settings.search_timeout_seconds)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    results: list[dict[str, Any]] = []
    for link in soup.select(".result__a"):
        href = link.get("href", "")
        resolved = _resolve_duckduckgo_url(href)
        title = html.unescape(link.get_text(" ", strip=True))
        snippet_node = link.find_parent(class_="result")
        snippet = ""
        if snippet_node:
            snippet_text = snippet_node.get_text(" ", strip=True)
            snippet = re.sub(r"\s+", " ", snippet_text)
        results.append({"title": title, "url": resolved, "snippet": snippet})
        if len(results) >= max_results:
            break
    return results


def _resolve_duckduckgo_url(href: str) -> str:
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc and parsed.path == "/l/":
        encoded = parse_qs(parsed.query).get("uddg", [""])[0]
        return unquote(encoded)
    return href


def fetch_page(url: str) -> dict[str, Any]:
    session = request_session()
    result: dict[str, Any] = {
        "url": url,
        "title": "",
        "published_date": "",
        "status": "pending",
        "text": "",
    }
    try:
        response = session.get(url, timeout=settings.search_timeout_seconds)
        result["http_status"] = response.status_code
        if not response.ok:
            result["status"] = "pending_confirmation"
            return result
        result["status"] = "verified"
        html_text = response.text[:120000]
        title_match = re.search(r"<title>(.*?)</title>", html_text, re.IGNORECASE | re.DOTALL)
        result["title"] = html.unescape(title_match.group(1).strip()) if title_match else url
        text = BeautifulSoup(html_text, "html.parser").get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text)
        result["text"] = text[:5000]
        result["published_date"] = extract_page_date(html_text) or extract_page_date(text)
        if not result["published_date"]:
            result["status"] = "pending_confirmation"
    except Exception as exc:  # pragma: no cover - depends on network
        result["status"] = exc.__class__.__name__
    return result


def rank_search_results(
    results: list[dict[str, Any]],
    official_domains: list[str],
    trusted_keywords: list[str],
) -> list[dict[str, Any]]:
    ranked: list[tuple[tuple[int, int], dict[str, Any]]] = []
    for item in results:
        domain = domain_from_url(item["url"])
        official = any(domain.endswith(expected) for expected in official_domains if expected)
        keyword_hits = sum(1 for keyword in trusted_keywords if keyword and keyword in (item["title"] + item["snippet"]))
        ranked.append((((1 if official else 0), keyword_hits), item))
    ranked.sort(key=lambda entry: entry[0], reverse=True)
    return [item for _, item in ranked]
