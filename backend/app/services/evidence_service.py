from __future__ import annotations

from pathlib import Path
from typing import Any

import requests

from ..config import settings
from ..core.parsing import (
    build_citation_reference,
    citation_completeness_score,
    parse_citation_file,
)
from .workspace_service import add_evidence_item


def _crossref_lookup(metadata: dict[str, Any]) -> dict[str, Any]:
    doi = str(metadata.get("doi", "")).strip()
    title = str(metadata.get("title", "")).strip()
    if not doi and not title:
        return metadata
    url = "https://api.crossref.org/works"
    params = {"rows": 1}
    if doi:
        response = requests.get(f"{url}/{doi}", timeout=settings.search_timeout_seconds)
        if response.ok:
            payload = response.json().get("message", {})
            return _merge_crossref(metadata, payload)
        return metadata
    params["query.title"] = title
    response = requests.get(url, params=params, timeout=settings.search_timeout_seconds)
    if not response.ok:
        return metadata
    items = response.json().get("message", {}).get("items", [])
    if not items:
        return metadata
    return _merge_crossref(metadata, items[0])


def _merge_crossref(metadata: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    authors = []
    for author in payload.get("author", []):
        given = author.get("given", "")
        family = author.get("family", "")
        name = " ".join(part for part in [given, family] if part).strip()
        if name:
            authors.append(name)
    year = ""
    for key in ["published-print", "published-online", "issued"]:
        date_parts = payload.get(key, {}).get("date-parts", [])
        if date_parts and date_parts[0]:
            year = str(date_parts[0][0])
            break
    merged = dict(metadata)
    merged["author"] = merged.get("author") or "; ".join(authors)
    merged["title"] = merged.get("title") or (payload.get("title") or [""])[0]
    merged["year"] = merged.get("year") or year
    merged["source"] = merged.get("source") or (payload.get("container-title") or [""])[0]
    merged["doi"] = merged.get("doi") or payload.get("DOI", "")
    merged["url"] = merged.get("url") or payload.get("URL", "")
    return merged


def import_citation_file(workspace_id: str, file_path: Path) -> list[dict[str, Any]]:
    records = parse_citation_file(file_path)
    created: list[dict[str, Any]] = []
    for index, record in enumerate(records, start=1):
        try:
            record = _crossref_lookup(record)
        except Exception:  # pragma: no cover - network instability
            pass
        is_complete, missing = citation_completeness_score(record)
        status = "verified" if is_complete else "pending_confirmation"
        created.append(
            add_evidence_item(
                workspace_id=workspace_id,
                evidence_type="citation",
                title=record.get("title") or f"文献 {index}",
                summary=build_citation_reference(record, index),
                grade="B",
                status=status,
                source_label=file_path.name,
                source_uri=str(file_path),
                source_date=record.get("year", ""),
                metadata={
                    **record,
                    "missing_fields": missing,
                },
                content={"reference": build_citation_reference(record, index)},
            )
        )
    return created
